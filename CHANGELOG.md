# Changelog

All notable changes to xzSSH are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
from 1.0 onward. The CLI surface and the JSON schema are subject to change
during the 0.x series.

## [Unreleased]

## [0.9.0] — 2026-05-28

### Added

- **Eight new SSH fields on `Host`**, each wired through the full
  Parse → Validate → Generate pipeline plus the importer and the `add`
  CLI:
  - `forward_agent` (`ForwardAgent`), `compression` (`Compression`),
    `identities_only` (`IdentitiesOnly`) — tri-state bools (unset /
    yes / no), set via `--forward-agent` / `--no-forward-agent` etc.
  - `server_alive_interval` (`ServerAliveInterval`, `--server-alive-interval`).
  - `strict_host_key_checking` (`StrictHostKeyChecking`,
    `--strict-host-key-checking`, validated against
    yes/no/ask/accept-new/off).
  - `user_known_hosts_file` (`UserKnownHostsFile`,
    `--user-known-hosts-file`).
  - `remote_forwards` (`RemoteForward`, `--remote-forward
    remote_port:local_host:local_port`) and `dynamic_forwards`
    (`DynamicForward`, repeatable `--dynamic-forward PORT`).
- The OpenSSH importer now also reads `LocalForward`, `RemoteForward`,
  `DynamicForward`, and the new scalar options, mapping `yes`/`no` back
  to booleans.
- `build_ssh_command` emits the scalar options as `-o Key=value`, so
  `connect` / `which` / `test` reflect them. Forwards stay
  generator-only (they belong in the config, not an interactive
  command line).

### Fixed

- `xzssh which` now writes straight to stdout instead of through rich,
  so a long resolved command (many `-o` options) is never soft-wrapped
  into multiple lines — `$(xzssh which host)` stays intact.

## [0.8.0] — 2026-05-28

### Added

- **`xzssh edit <alias>`** — open a single host's JSON entry in
  `$EDITOR` (falls back to `$VISUAL`, then `nano`/`vim`/`vi`, or
  `notepad` on Windows). On save the edited JSON is re-parsed and the
  **whole** config is re-validated before an atomic write.
  - Editing the `alias` field renames the host — the entry is spliced
    back **by position**, not by name, so renames don't orphan it.
  - Bad JSON, a missing required field, or a validation failure (e.g.
    a rename that collides with another alias) aborts with the original
    config untouched.
  - The scratch file is created `0600` (it holds hostnames and key
    paths).

## [0.7.0] — 2026-05-28

### Added

- **`xzssh export`** — print a pretty-printed JSON snapshot of the
  config to stdout (or `--output FILE`). Stdout is written raw,
  bypassing rich, so `xzssh export > backup.json` is always valid JSON.
- **`xzssh import-json <file>`** — restore from a snapshot. Distinct
  from `xzssh import` (which reads an OpenSSH `ssh_config`).
  - `--merge` (default): adds new hosts/keys; on an alias collision the
    existing host is kept — the import never clobbers silently.
  - `--replace`: swaps in the whole snapshot, saving the previous
    `xzssh.json` to `xzssh.json.bak` first.
  - The snapshot is parsed **and semantically validated before any
    write**; a malformed or invalid file aborts with the live config
    untouched.

## [0.6.0] — 2026-05-28

### Added

- **`xzssh search <query>`** — case-insensitive substring search across
  alias, hostname, user, tags, and the ProxyJump bastion, printed as a
  host table. Exit codes mirror `grep`: `0` when something matches, `1`
  when nothing does, so `xzssh search prod && ...` is scriptable.

## [0.5.0] — 2026-05-28

First Tier 2 feature.

### Added

- **`xzssh which <alias>`** — print the fully resolved `ssh` command
  line for a host (port, identity file, ProxyJump, user) without
  running it. Output is a single shell-safe line via `shlex.join`, so
  `$(xzssh which db)` works and `xzssh which db` is redirect-clean.
- `which`, `search`, and `export` are now **banner-suppressed**: these
  machine-consumable commands no longer emit the decorative ASCII
  banner that would otherwise corrupt piped / redirected output.
- Backfilled `test` and `which` into `xzssh --help`.

## [0.4.2] — 2026-05-28

### Fixed

- **Release publication.** After fixing the Nuitka build in 0.4.1,
  two more issues showed up in the `Create Release` job:
  - Asset file paths were wrong. The Windows / macOS artifact folders
    held the binary under the *artifact_name* (`xzssh.exe`, `xzssh.bin`),
    but the release step's glob looked for the *asset_name*
    (`xzssh-windows.exe`, `xzssh-macos`). Unified the names so
    `artifacts/<asset>/<asset>` resolves to the actual binary.
  - The release job was missing `permissions: contents: write`, so the
    default `GITHUB_TOKEN` couldn't create the release (HTTP 403:
    *Resource not accessible by integration*). Added the permission.

No code changes.

## [0.4.1] — 2026-05-28

### Fixed

- **Release binaries build.** The Nuitka-Action upstream removed its
  `onefile: true` input; the deprecated `--onefile` flag now conflicts
  with the implicit `--mode=app` Nuitka passes by default, and every
  release-binary job on `v0.1.0`–`v0.4.0` failed at the `Build with
  Nuitka` step. Switched the workflow to `mode: onefile`, which is the
  supported way to ask for a single-binary build.

No code changes — same feature surface as 0.4.0.

## [0.4.0] — 2026-05-28

### Added

- **Shell tab-completion** for bash, zsh, and fish via
  [argcomplete](https://kislyuk.github.io/argcomplete/). Hit `<TAB>`
  after `xzssh connect`, `xzssh test`, or `xzssh remove` to complete
  from your configured host aliases. `xzssh key add-agent <TAB>`
  completes from configured key names.
- Optional install via `pip install 'xzssh[completion]'`. Activate
  with `eval "$(register-python-argcomplete xzssh)"` in your shell
  rc file (or the fish equivalent — see README).

### Behavior notes

- argcomplete is an optional dependency. If it isn't installed the
  CLI works exactly as before; the completion hook is a silent
  no-op.
- The completer reads `--config` from the partial command line if
  the user has typed it; otherwise it falls back to the platform
  default (`~/.ssh/xzssh.json`). Missing / corrupt config files
  return an empty completion list rather than blowing up the shell.

## [0.3.0] — 2026-05-28

### Added

- **`ProxyJump` support.** Hosts now carry an optional `proxy_jump`
  field — a bastion-host alias — which is emitted as `ProxyJump
  <alias>` in the generated `~/.ssh/config` and passed through as
  `-J <alias>` when `xzssh connect` / `xzssh test` invoke `ssh(1)`.
- `xzssh add --proxy-jump <alias>` and a questionary prompt in the
  interactive `add` flow.
- OpenSSH importer (`xzssh import`) now picks up `ProxyJump` lines
  from an existing `~/.ssh/config` round-trip.
- `xzssh list` gains a "Via" column showing the bastion alias (or
  `-` when none).

### Validator

- A dangling `proxy_jump` reference (alias not present in the
  config) is now reported as an **error**, not silently emitted.
  Forward references are allowed — the bastion may be declared
  after the host that jumps through it.
- Self-referential `proxy_jump` (host → host) is rejected.

## [0.2.0] — 2026-05-28

### Added

- `xzssh test <alias>` — probe SSH connectivity without opening an
  interactive shell. Runs `ssh -o BatchMode=yes -o ConnectTimeout=5 ...
  true` and classifies the outcome as **reachable**, **auth-failed**,
  **timeout**, or **unreachable** based on the SSH return code and
  stderr.
- `xzssh test --all` — probes every configured host in parallel (small
  thread pool, capped at 8 workers) so a hung host can't stall the run.
- `--timeout SECONDS` flag tunes the per-host connect timeout
  (default 5 s).

### Behavior notes

- Exit codes: `0` when every probed host is reachable, `1` when at
  least one failed (auth, timeout, refused, etc.), `2` for usage or
  unknown-alias errors.
- Internal: extracted a shared `build_ssh_command(host)` helper in
  `xzssh/cli/helpers.py` so `connect`, `test`, and future commands
  (`which`, etc.) build the same ssh argv from a `Host`.

## [0.1.0] — 2026-05-28

First public release.

### Added

#### Core library
- Parse → Validate → Generate pipeline. The JSON file at
  `~/.ssh/xzssh.json` is the source of truth; the canonical
  `~/.ssh/config` is regenerated deterministically.
- Validator detects duplicate aliases, invalid port ranges, cross-host
  `LocalForward` conflicts (with optional `--suggest-ports`), and key
  file existence + `0600` permissions.
- OpenSSH config importer that handles multi-host lines (`Host a b c` →
  three entries), `=` separators, and quoted values; surfaces `Match` /
  `Include` / wildcard patterns as warnings rather than silently
  mis-importing them. Pure stdlib — no `paramiko` dependency.

#### CLI
- Subcommands: `list`, `connect`, `add`, `remove`, `import`, `check`,
  `generate`, `key {add,list,add-agent}`, `menu`.
- Interactive welcome (no-args) and full management (`xzssh menu`)
  loops with single-key shortcuts.
- Both argument-driven and questionary-prompted forms of `add` and
  `remove` share one handler — pass flags or be prompted.
- `--dry-run` on `generate` and `remove`/`remove --all` to preview the
  effect without touching the filesystem.
- `--tag` filter on `list` and `connect` (OR semantics across multiple
  `--tag` flags). `xzssh list --tag prod` narrows the table; `xzssh
  connect --tag prod` narrows the fuzzy-search candidates. Ignored
  when `connect` is given an explicit alias.

#### Tooling
- Cross-platform install scripts (`install.sh`, `install.bat`).
- GitHub Actions CI: `pytest` on Linux/macOS/Windows × Python
  3.9–3.14 on every push and PR.
- GitHub Actions release workflow: Nuitka one-file binaries for
  Linux/macOS/Windows on `v*` tags.

### Behavior notes

- **`xzssh connect` propagates SSH's exit code** instead of always
  returning 0. This makes shell pipelines like `xzssh connect host && deploy`
  behave correctly. If you were relying on the always-0 behavior of an
  earlier dev build, this is a breaking change.
- `host.last_used` is updated only when the SSH session actually
  connected — i.e. when `ssh` returned anything other than 255,
  OpenSSH's convention for "connection setup failed".

### Security

- `~/.ssh/xzssh.json` (the source-of-truth) and the generated
  `~/.ssh/config` are both written with mode `0600` on POSIX. Both
  files contain hostnames, usernames, and identity-file paths and
  are treated as secret.
- All config writes are **atomic**: written to a sibling `.tmp` file,
  permissions applied, then `os.replace`d into place. A crash
  mid-write cannot leave the live config truncated.
- `xzssh generate` **refuses to overwrite an existing file that was
  not generated by xzSSH** unless `--force` is passed. A `.bak` copy
  is saved whenever an existing file is overwritten.

[Unreleased]: https://github.com/010228lxz/xzSSH/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/010228lxz/xzSSH/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/010228lxz/xzSSH/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/010228lxz/xzSSH/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/010228lxz/xzSSH/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/010228lxz/xzSSH/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/010228lxz/xzSSH/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/010228lxz/xzSSH/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/010228lxz/xzSSH/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/010228lxz/xzSSH/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/010228lxz/xzSSH/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/010228lxz/xzSSH/releases/tag/v0.1.0
