# xzSSH Roadmap

This is the feature backlog for xzSSH — a brainstorm catalog, not a
commitment. Items are ordered by a rough sense of value vs. effort and
how cleanly they fit the existing Parse → Validate → Generate
architecture (see [CLAUDE.md](CLAUDE.md)).

Effort estimates assume someone familiar with the codebase. They are
deliberately rough; pad them when planning real work.

| Tag | Meaning                                       |
| --- | --------------------------------------------- |
| S   | A few hours. One CLI flag, one model field.   |
| M   | Half a day to a day. New command + tests.     |
| L   | Multiple days. Cross-cutting or risky design. |

---

## Tier 1 — Shipped ✅

All Tier 1 items have shipped — see [CHANGELOG.md](CHANGELOG.md) for
the exact version each one landed in:

- ✅ Tag filtering on `list` and `connect` — **v0.1.0**
- ✅ `xzssh test <alias>` connectivity probe — **v0.2.0**
- ✅ `ProxyJump` support (bastion hosts) end-to-end — **v0.3.0**
- ✅ Shell tab-completion via `argcomplete` — **v0.4.0**

`build_ssh_command()` was extracted along the way (in v0.2.0) and is
now the single source of truth for ssh argv construction — reused by
`connect`, `test`, and any future command like `which`.

---

## Tier 2 — Clear wins

Lower urgency, but each is a clean small-to-medium change that fits the
architecture.

### `xzssh edit <alias>` — `[M]`

Open the host's JSON entry in `$EDITOR`, re-validate on save. Currently
the only ways to change a host are `--replace` (full rewrite via flags)
or remove-then-add.

- Extract the host's `to_dict()`, write to a temp file, `subprocess.run([EDITOR, tmp])`.
- On editor exit, load + validate the edited JSON against the schema.
- If valid: splice back into the config and `write_config`.
- If invalid: print errors, keep the original.

### `xzssh which <alias>` — `[S]`

Print the resolved `ssh` command line without running it. Debug aid for
verifying ProxyJump / IdentityFile resolution.

- Reuses the `_build_ssh_args` logic from [connect.py](xzssh/cli/commands/connect.py).
- One-liner output: `ssh -i ~/.ssh/id_ed25519 -p 2222 alice@db.example.com`.

### More SSH fields on `Host` — `[M]`

Once `ProxyJump` is in, the rest of these become single-field additions
with one generator line each. Pick a subset based on demand.

- `RemoteForward`, `DynamicForward` (symmetric with the existing `LocalForward`).
- `ForwardAgent: bool`
- `Compression: bool`
- `ServerAliveInterval: int`
- `IdentitiesOnly: bool`
- `StrictHostKeyChecking: str` (yes / no / ask / accept-new)
- `UserKnownHostsFile: str`

The pattern is mechanical: model field, parser type-check, validator
constraint if any, generator emit, importer pickup, `--flag` on
[add.py](xzssh/cli/commands/add.py), questionary prompt.

### JSON export / import for backup — `[S]`

- `xzssh export > backup.json` — pretty-printed snapshot.
- `xzssh import-json backup.json --merge|--replace` — restore from snapshot.
- Already mostly there: `Config.to_dict()` and `load_config` exist. Just
  needs two thin CLI commands and `--merge` semantics for conflict
  resolution.

### `xzssh connect --dry-run` — `[S]`

Already have `--dry-run` on `generate` and `remove`. The
last-destructive-without-dry-run is technically `connect` (it stamps
`last_used`). Probably not worth the flag, but cheap to add for
consistency.

### `--tag` on `add` / `key add` for bulk classification — `[S]`

Already exists on `add` (`--tag` repeatable). Worth verifying the
prompt-driven path also captures tags cleanly.

### `xzssh search <query>` — `[S]`

Currently the only fuzzy search is in `connect`. A standalone
`xzssh search prod-db` that searches alias + hostname + user + tags
and prints matches is useful outside the connect flow.

---

## Tier 3 — Larger investments

Real design work; would benefit from a spec / RFC before coding.

### Schema versioning + migrations — `[M]`

`Config.version = 1` exists but there's no migration framework. Worth
setting up the pattern *before* the first schema break, not after.

- Define `MIGRATIONS: Dict[int, Callable[[dict], dict]]` keyed by
  source version.
- On load, if file version < current, run migrations in sequence,
  re-validate, write back with a `.bak`.
- Document the contract: never lower the version number; never re-use
  a version number; migrations must be idempotent.

### Multiple profiles — `[M]`

Power users juggle work/personal/client configs. Currently the only
escape hatch is `--config path/to/other.json`.

- `xzssh profile add work ~/team-ssh.json`
- `xzssh profile list`
- `xzssh --profile work connect db`
- Profile registry at `~/.config/xzssh/profiles.toml` (separate from
  the SSH-related files).
- Default profile + per-shell-session override via env var.

### `xzssh sync` — bidirectional with `~/.ssh/config` — `[L]`

Right now the flow is one-way: JSON → generated config. If the user
edits `~/.ssh/config` by hand (common for one-off settings),
xzSSH overwrites their changes on the next `generate`. Hard problem
because:

- Need to detect that the user's file is no longer xzSSH-generated
  (the header check already catches this, but only as a refusal — not
  a merge path).
- Need to re-parse the generated config and detect drift vs. the JSON.
- Conflict resolution: file-wins / json-wins / interactive merge.

This is where the OpenSSH importer's `Match`/`Include` warnings become
real merge conflicts.

### Encrypted JSON at rest — `[L]`

The JSON contains identity-file paths, usernames, and hostnames — all
already restricted to `0600`. Some users will want stronger guarantees.

- Optional `gpg --symmetric` or `age` envelope on the JSON.
- Decrypt on `load_config`; re-encrypt on `write_config`.
- Big UX cost (prompts for passphrase on every operation) — only worth
  it if there's clear demand. Likely behind a `--encrypt` flag and a
  config-level opt-in.

### `xzssh tunnel <alias>` — `[M]`

Open the `LocalForward` rules defined for a host without starting an
interactive session. Daemon-style use case.

- `ssh -N -f` for background, or foreground with a clean stop signal.
- `xzssh tunnel list` to show active tunnels (requires a state file).
- `xzssh tunnel stop <alias>`.

---

## Tier 4 — Speculative

Worth considering, but each has real friction or out-of-scope risk.

### `xzssh scp` / `xzssh sftp` / `xzssh rsync` wrappers

Convenience wrappers that resolve an alias and pass through to the
real binary. Marginal value over just running `scp host:path .` once
the user's `~/.ssh/config` is set up.

### `xzssh history` view

`Host.last_used` exists; we already sort by it. A dedicated
`xzssh history` showing chronological recent connections (last 50,
with timestamps and exit codes) would be nice if we also log exit
codes — currently we don't.

### Connection event log

Opt-in `~/.ssh/xzssh.log` with timestamped connect events. Pairs with
the history view. Privacy-sensitive — must be opt-in and respect a
"no-log" host tag.

### macOS Keychain integration

`xzssh key add-agent` could store the passphrase in Keychain so
subsequent loads don't prompt. macOS-only feature; nice but limits
portability of the feature flag.

### Groups / folders

For users with 50+ hosts, hierarchical grouping (`prod/db/primary`,
`prod/db/replica`). Probably better served by tags + multi-tag
filtering than by a real hierarchy.

### Themes

`rich` makes per-theme styling easy. The current neon-green/cyan/pink
palette is opinionated; a `--theme classic` and `--theme high-contrast`
would help users who want something more sober.

### TUI dashboard (vs. menu loops)

A full-screen `textual` UI replacing the questionary-based menus. Big
dep, big rewrite of `xzssh/cli/commands/menu.py`. Probably overkill
unless we have a real reason.

### Web/desktop GUI

Out of scope for a CLI tool. Don't.

---

## Not planned

Explicit no's so they don't get re-proposed:

- **`paramiko` integration for an in-process SSH client.** xzSSH is a
  config manager, not an SSH client replacement. Always shell out to
  `ssh(1)`.
- **Cloud sync of the JSON file.** Out of scope. Users can put
  `~/.ssh/xzssh.json` in their own dotfiles repo.
- **A plugin system.** Premature. If/when there's a real third-party
  use case it can be designed for that use case.
- **Per-host scripts / hooks (pre-connect, post-connect).** Easy to
  abuse, hard to make portable. Defer until there's a strong concrete
  request.

---

## See also

- [CLAUDE.md](CLAUDE.md) — architecture and conventions; read this
  first before picking up a feature.
- [CHANGELOG.md](CHANGELOG.md) — what's already shipped.
- Architecture invariants worth preserving: the
  Parse → Validate → Generate split, the rule that semantic errors
  belong only in the validator, and that all writes go through
  [`write_config`](xzssh/cli/helpers.py).
