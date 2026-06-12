"""``xzssh sync`` — detect and resolve drift with ``~/.ssh/config``.

The normal flow is one-way (JSON → generated file). When the user
hand-edits the file, this command closes the loop:

- ``xzssh sync`` — report only. Exit 0 when in sync, 1 when drift was
  found (scriptable, like ``git diff --exit-code``), 2 on usage errors.
- ``--prefer json`` — regenerate the file from the JSON (the
  ``generate --force`` path, so the existing file is backed up to
  ``.bak`` first).
- ``--prefer file`` — import the drift back into the JSON: hand-added
  hosts are imported, hosts missing from the file are removed, changed
  fields are copied over. JSON-only metadata (tags, ``last_used``) is
  preserved, the merged config is semantically validated **before**
  anything is written, and the previous JSON is saved to ``.bak``. The
  file itself is not touched.
- ``--interactive`` — choose json/file per drifted host; any json-wins
  choice triggers a final regeneration (after the file-wins choices
  were folded into the JSON, so mixed decisions compose correctly).

Constructs the model can't represent — ``Match`` blocks, ``Include``
directives, wildcard host patterns — don't count as drift, but a
json-wins regeneration would wipe them: that direction therefore
requires ``--force`` (or an explicit confirmation in interactive
mode). File-wins never touches the file, so it proceeds with a
warning.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Dict, List

import questionary

from xzssh.cli.commands import generate as generate_cmd
from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_info,
    print_step,
    print_success,
    print_warnings,
)
from xzssh.model import Config
from xzssh.parser import parse_openssh_config
from xzssh.sync import DriftReport, HostDrift, apply_file_version, compare_hosts
from xzssh.validator import validate_config


def run(args: argparse.Namespace, config_path: Path, output_path: Path) -> int:
    prefer = getattr(args, "prefer", None)
    interactive = getattr(args, "interactive", False)
    force = getattr(args, "force", False)

    if prefer and interactive:
        print_error("--prefer and --interactive are mutually exclusive.")
        return 2

    config = load_config_or_error(config_path)
    if config is None:
        return 1

    if output_path.exists():
        file_hosts, parse_warnings = parse_openssh_config(output_path)
    else:
        file_hosts, parse_warnings = [], []
        print_info(f"{output_path} does not exist yet.")

    report = compare_hosts(
        config.hosts,
        file_hosts,
        json_base_dir=config_path.parent,
        file_base_dir=output_path.parent,
        parse_warnings=parse_warnings,
    )

    _print_report(report, config_path, output_path)

    if report.in_sync:
        print_success(f"In sync: {len(config.hosts)} host(s) match.")
        return 0

    if prefer == "json":
        return _resolve_all_json(report, config_path, output_path, force)
    if prefer == "file":
        return _resolve(
            config,
            report,
            {d.alias: "file" for d in report.drifts},
            config_path,
            output_path,
        )
    if interactive:
        decisions = _ask_decisions(report)
        if decisions is None:
            print_info("Aborted; nothing was changed.")
            return 1
        if (
            "json" in decisions.values()
            and report.warnings
            and not _confirm_lossy_regeneration()
        ):
            print_info("Aborted; nothing was changed.")
            return 1
        return _resolve(config, report, decisions, config_path, output_path)

    print_info(
        "Resolve with `xzssh sync --prefer json` (regenerate the file), "
        "`--prefer file` (update the JSON), or `--interactive`."
    )
    return 1


def _print_report(
    report: DriftReport, config_path: Path, output_path: Path
) -> None:
    print_info(f"Comparing {config_path} (json) ↔ {output_path} (file)")
    if report.warnings:
        print_warnings(report.warnings)
    for drift in report.drifts:
        if drift.kind == "added":
            print_step(f"+ {drift.alias} — only in the file (hand-added?)")
        elif drift.kind == "removed":
            print_step(f"- {drift.alias} — only in the JSON (missing from the file)")
        else:
            details = "; ".join(
                f"{c.field}: {c.json_value!r} (json) vs {c.file_value!r} (file)"
                for c in drift.changes
            )
            print_step(f"~ {drift.alias} — {details}")


def _resolve_all_json(
    report: DriftReport, config_path: Path, output_path: Path, force: bool
) -> int:
    if report.warnings and not force:
        print_error(
            f"{output_path} contains constructs xzSSH does not model "
            "(see warnings above); regenerating would wipe them. "
            "Re-run with --force to overwrite anyway (a .bak is saved)."
        )
        return 2
    return generate_cmd.run(
        config_path, output_path, suggest_ports=False, force=True
    )


def _resolve(
    config: Config,
    report: DriftReport,
    decisions: Dict[str, str],
    config_path: Path,
    output_path: Path,
) -> int:
    json_changed = False
    file_regen_needed = False

    for drift in report.drifts:
        decision = decisions[drift.alias]
        if decision == "json":
            # The file side gets fixed by the final regeneration.
            file_regen_needed = True
            continue

        json_changed = True
        if drift.kind == "added":
            config.hosts.append(drift.file_host)
        elif drift.kind == "removed":
            config.hosts.remove(drift.json_host)
        else:
            apply_file_version(drift)

    if json_changed:
        # Same posture as import-json: semantic validation BEFORE any
        # write — a hand-edit that breaks invariants (e.g. a forward
        # port now conflicting across hosts) aborts with both files
        # untouched.
        result = validate_config(config, source_path=config_path)
        if result.errors:
            print_error(
                "Applying the file's version would leave an invalid "
                "config; nothing was changed:"
            )
            print_errors(result.errors)
            return 1
        if result.warnings:
            print_warnings(result.warnings)

        backup = config_path.with_name(config_path.name + ".bak")
        shutil.copy2(config_path, backup)
        print_info(f"Backed up JSON to {backup}")
        write_config(config_path, config)
        print_success(f"Updated {config_path} from the file.")

    if file_regen_needed:
        # Runs after the JSON write, so file-wins choices are reflected
        # in the regenerated file too — mixed decisions compose.
        return generate_cmd.run(
            config_path, output_path, suggest_ports=False, force=True
        )
    return 0


def _ask_decisions(report: DriftReport) -> "Dict[str, str] | None":
    decisions: Dict[str, str] = {}
    for drift in report.drifts:
        answer = questionary.select(
            f"{drift.alias} ({_drift_summary(drift)}):",
            choices=_choices_for(drift),
        ).ask()
        if answer is None:
            return None
        decisions[drift.alias] = answer
    return decisions


def _drift_summary(drift: HostDrift) -> str:
    if drift.kind == "added":
        return "only in the file"
    if drift.kind == "removed":
        return "only in the JSON"
    return "differs: " + ", ".join(c.field for c in drift.changes)


def _choices_for(drift: HostDrift) -> List[questionary.Choice]:
    if drift.kind == "added":
        return [
            questionary.Choice("Import it into the JSON", value="file"),
            questionary.Choice("Drop it when the file is regenerated", value="json"),
        ]
    if drift.kind == "removed":
        return [
            questionary.Choice("Restore it into the file", value="json"),
            questionary.Choice("Remove it from the JSON too", value="file"),
        ]
    return [
        questionary.Choice("Keep the JSON version (regenerate the file)", value="json"),
        questionary.Choice("Keep the file version (update the JSON)", value="file"),
    ]


def _confirm_lossy_regeneration() -> bool:
    return bool(
        questionary.confirm(
            "The file contains constructs xzSSH does not model "
            "(Match/Include/wildcards) — regenerating will wipe them. "
            "Continue?",
            default=False,
        ).ask()
    )
