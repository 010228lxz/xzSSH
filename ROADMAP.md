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

## Tier 3 — Shipped ✅

All Tier 3 items have shipped (v0.11.0 – v0.15.0):

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

- ✅ Encrypted JSON at rest — **v0.15.0**. `xzssh encrypt [--tool
  gpg|age]` / `xzssh decrypt`; envelope detected by magic bytes on
  load, re-applied on every write. The predicted UX cost is real and
  documented (passphrase prompt on every operation); completers skip
  encrypted configs so `<TAB>` never triggers pinentry, and no
  plaintext `.bak` is ever left behind.

- ✅ `xzssh tunnel` — **v0.13.0**. `tunnel start <alias>` (foreground
  `ssh -N`, Ctrl-C to stop) / `tunnel start --detach` / `tunnel list` /
  `tunnel stop <alias>|--all`, with a state file in the platform state
  dir. Two deviations from the sketch: the CLI is `tunnel start
  <alias>` rather than bare `tunnel <alias>` (so `list`/`stop` can't
  collide with alias names), and backgrounding uses `Popen` in its own
  session rather than `ssh -f` (ssh's fork hides the daemon pid, which
  would make `tunnel stop` impossible).

---

## Tier 4 — Resolved ✅

Every Tier 4 item is now either shipped or explicitly declined (the
declines moved to *Not planned* below). The backlog is empty — new
items start from a fresh proposal, not this list.

- ✅ `xzssh scp` / `xzssh sftp` / `xzssh rsync` wrappers — **v0.18.0**.
  Alias rewriting (`db:/x` → `user@host:/x`) plus per-host option
  injection (`-P/-i/-J/-o`, or `-e ssh …` for rsync), so they work even
  when `~/.ssh/config` was never generated — which is exactly the case
  where "just run scp" doesn't.

- ✅ `xzssh history` view + connection event log — **v0.16.0**.
  Shipped together, as predicted (history needs the exit codes only a
  log can provide). Opt-in via `xzssh history enable`; JSONL next to
  the config file (per-profile); `no-log` host tag respected; `0600`;
  best-effort writes that never fail a connect.

- ✅ macOS Keychain integration — **v0.19.0**. `xzssh key add-agent
  <name> --keychain` (ssh-add `--apple-use-keychain`). The portability
  concern is handled by failing fast: the flag is a clean error (exit
  2) off macOS rather than a silent no-op.

- ✅ Groups / folders — resolved **in the direction this item itself
  recommended**: no hierarchy. v0.19.0 adds `--match-all` to `list`
  and `connect`, so `--tag prod --tag db --match-all` expresses
  "prod databases" with AND semantics. Folder paths stay declined.

- ✅ Themes — **v0.17.0**. `classic` and `high-contrast` as sketched,
  plus `mono` (emphasis-only, for monochrome terminals). `--theme` /
  `$XZSSH_THEME` / `xzssh theme <name>` (saved in the profiles
  registry). All styling flows through semantic names in `ui.py`.

---

## Not planned

Explicit no's so they don't get re-proposed:

- **TUI dashboard (`textual`).** Declined after the Tier 4 review
  (2026-06): a big dependency and a rewrite of the menu loops, against
  the project's small-dep-tree principle (`rich` + `questionary`
  only), with no concrete user need the menus + themes don't already
  cover. Revisit only with a real reason, per the original note.
- **Web/desktop GUI.** Out of scope for a CLI tool. Don't.

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
