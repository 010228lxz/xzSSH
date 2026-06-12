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

## Tier 2 — Shipped ✅

All Tier 2 items have shipped — see [CHANGELOG.md](CHANGELOG.md) for
the version each one landed in:

- ✅ `xzssh which <alias>` (resolved ssh command) — **v0.5.0**
- ✅ `xzssh search <query>` (alias/host/user/tag/proxy) — **v0.6.0**
- ✅ JSON export / import-json (backup & restore) — **v0.7.0**
- ✅ `xzssh edit <alias>` (`$EDITOR` round-trip) — **v0.8.0**
- ✅ More SSH fields on `Host` (RemoteForward, DynamicForward,
  ForwardAgent, Compression, ServerAliveInterval, IdentitiesOnly,
  StrictHostKeyChecking, UserKnownHostsFile) — **v0.9.0**
- ✅ `xzssh connect --dry-run` + `add --tag` prompt-path verified —
  **v0.10.0**

Note on the `--tag on key add` sub-item: keys are a simple
`name → path` dict with no tag field, so "tag a key" was out of scope;
the item reduced to verifying `add --tag` works in both the flag and
prompt paths, which is now locked in by tests.

---

## Tier 3 — Larger investments

Real design work; would benefit from a spec / RFC before coding.

- ✅ Schema versioning + migrations — **v0.11.0**. The registry lives
  in `xzssh/parser/migrations.py` (with the contract in its
  docstring); `CURRENT_SCHEMA_VERSION` in `xzssh/model/types.py`.
  Old files are upgraded in memory on every load and written back once
  through the CLI load path with a `.bak`. Newer-than-supported files
  are refused. Still on schema v1 — the framework ships ahead of the
  first real break, as planned.

- ✅ Multiple profiles — **v0.12.0**. `xzssh profile
  add/list/use/remove`, `--profile NAME` on every command,
  `$XZSSH_PROFILE` session override, default profile in the registry.
  One deviation from the sketch: the registry is
  `~/.config/xzssh/profiles.json` (JSON, not TOML — Python 3.9 has no
  stdlib TOML reader and no version has a writer; the dep tree stays
  rich + questionary).

- ✅ `xzssh sync` — **v0.14.0**. Report mode by default (exit 1 on
  drift, scriptable), `--prefer json` (regenerate with `.bak`),
  `--prefer file` (import drift into the JSON, preserving
  tags/last_used, validated before write), `--interactive` (per-host
  choice; mixed decisions compose). The importer's `Match`/`Include`
  warnings did become the merge conflicts predicted here: they gate the
  json-wins direction behind `--force`/confirmation, while file-wins
  proceeds with a warning since it never touches the file.

### Encrypted JSON at rest — `[L]`

The JSON contains identity-file paths, usernames, and hostnames — all
already restricted to `0600`. Some users will want stronger guarantees.

- Optional `gpg --symmetric` or `age` envelope on the JSON.
- Decrypt on `load_config`; re-encrypt on `write_config`.
- Big UX cost (prompts for passphrase on every operation) — only worth
  it if there's clear demand. Likely behind a `--encrypt` flag and a
  config-level opt-in.

- ✅ `xzssh tunnel` — **v0.13.0**. `tunnel start <alias>` (foreground
  `ssh -N`, Ctrl-C to stop) / `tunnel start --detach` / `tunnel list` /
  `tunnel stop <alias>|--all`, with a state file in the platform state
  dir. Two deviations from the sketch: the CLI is `tunnel start
  <alias>` rather than bare `tunnel <alias>` (so `list`/`stop` can't
  collide with alias names), and backgrounding uses `Popen` in its own
  session rather than `ssh -f` (ssh's fork hides the daemon pid, which
  would make `tunnel stop` impossible).

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
