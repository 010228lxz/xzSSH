# Changelog

All notable changes to xzSSH are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
from 1.0 onward. The CLI surface and the JSON schema are subject to change
during the 0.x series.

## [Unreleased]

## [0.20.1] — 2026-06-20

### Fixed

- **Validator now catches DynamicForward and RemoteForward port
  conflicts**, not just LocalForward. Client-side binds
  (`LocalForward.local_port` + `DynamicForward`) share one local-port
  namespace and are compared across all hosts; `RemoteForward.remote_port`
  binds on the server, so it's compared only among forwards landing on the
  same `host_name` (two different servers reusing a remote port is not a
  conflict). DynamicForward ports below 1024 also get the privilege
  warning LocalForward already had.
- **`xzssh tunnel start` now pre-checks that each local-bind port is
  free** before spawning `ssh`, failing with a named-port message
  (`Local port(s) already in use: 8080`) instead of a terse bind error
  buried in a detached tunnel's log. Only LocalForward/DynamicForward
  (client-side binds) are probed; RemoteForward is not.

## [0.20.0] — 2026-06-17

Opens a new line of work after the Tier 1–4 backlog: completing the
key lifecycle. `key` could reference and agent-load existing keys but
could neither create nor deploy one — so standing up a brand-new host
still meant dropping out to raw `ssh-keygen`/`ssh-copy-id`.

### Added

- **`xzssh key gen <name> [path]`** — generate a keypair with
  `ssh-keygen` (ed25519 by default; `--type rsa` defaults to 4096
  bits) and register it under `<name>` in one step. Defaults the file
  to `~/.ssh/<name>`; prompts for a passphrase unless
  `--no-passphrase`; refuses to clobber an existing file or registered
  name without `--replace`; `--no-register` writes the key only.
- **`xzssh key copy-id <alias>`** — install a public key on a host with
  `ssh-copy-id`, reusing the host's resolved user/port/ProxyJump and
  scalar SSH options. Picks the key by precedence `--key NAME` >
  the host's `identity_file` > your agent/default identities.
  `--dry-run` prints the resolved command without running it.

Both wrap their underlying tools through a single argv builder
(`build_ssh_copy_id_command` mirrors `build_ssh_command`); a missing
`ssh-keygen`/`ssh-copy-id` is a clean error, not a traceback.

## [0.19.0] — 2026-06-13

Closes out Tier 4 — the roadmap backlog is now empty (remaining
speculative items were explicitly declined and moved to *Not
planned*).

### Added

- **macOS Keychain integration** — `xzssh key add-agent <name>
  --keychain` passes `--apple-use-keychain` to `ssh-add`, storing the
  passphrase in the Keychain so subsequent loads don't prompt. Off
  macOS the flag is a clean usage error (exit 2), not a silent no-op.
- **`--match-all` on `list` and `connect`** — AND semantics across
  repeated `--tag` flags (`xzssh list --tag prod --tag db
  --match-all` = "prod databases"). This is the roadmap's own
  resolution of the groups/folders item: tags + multi-tag filtering,
  no hierarchy. Default OR behaviour is unchanged.

### Roadmap

- Declined and documented under *Not planned*: the `textual` TUI
  dashboard (big dep + menu rewrite against the small-dep-tree
  principle) and any web/desktop GUI.

## [0.18.0] — 2026-06-12

### Added

- **`xzssh scp` / `xzssh sftp` / `xzssh rsync`** — alias-aware
  wrappers around the real binaries:
  - Non-flag tokens of the form `<alias>:<path>` are rewritten to
    `user@hostname:<path>`; for sftp a bare `<alias>` works too (its
    positional *is* the host). Tokens that don't match a configured
    alias — local paths, `C:\…`, unknown prefixes — pass through
    untouched.
  - With exactly one alias referenced, the host's connection options
    are injected: `-P port -i identity -J jump -o Key=Value` for
    scp/sftp, `-e "ssh -p …"` for rsync (where `-P` would mean
    `--partial --progress`). With several aliases (remote→remote) the
    targets are still rewritten but per-host options are left to the
    generated `~/.ssh/config`, with a notice.
  - The wrapped tool's exit code propagates verbatim; a missing binary
    exits 127. `--dry-run` prints the resolved command (raw stdout,
    `$(...)`-safe).
  - Banner-suppressed like `which`/`export` — transfer output is often
    piped.
  - xzSSH's own flags go right after the subcommand; use the standard
    `--` separator when the tool's first argument starts with a dash
    (`xzssh rsync -- -az db:/data/ backup/`).

## [0.17.0] — 2026-06-12

### Added

- **Themes.** The neon palette is now one of four:
  - `neon` (default, unchanged), `classic` (sober ANSI colors that
    respect the terminal's own scheme), `high-contrast` (bright, bold,
    no dim text), and `mono` (no color at all — emphasis only; for
    pipes, screenshots, and monochrome terminals).
  - Resolution: `--theme NAME` (one invocation) > `$XZSSH_THEME` (one
    shell session) > the preference saved by `xzssh theme <name>` >
    default. `xzssh theme` lists themes; `--unset` clears the saved
    preference.
  - The preference is stored in the profiles registry
    (`~/.config/xzssh/profiles.json`) — it is CLI configuration, not
    SSH data, so it never touches `xzssh.json`.
  - All styling now flows through semantic style names + the active
    palette, including the banner and the questionary prompts; an
    unknown theme from env/registry degrades to the default with a
    stderr warning instead of failing the command.

### Fixed

- **Global flags before the subcommand were silently ignored on
  Python 3.13+** — `xzssh --config foo list` used the default config
  because argparse subparser defaults clobber already-parsed values in
  the shared namespace. The subparser copies of `--config`,
  `--profile`, `--theme`, and `--suggest-ports` now use
  `default=SUPPRESS`, so both positions work on every supported
  Python.

## [0.16.0] — 2026-06-12

First Tier 4 items: the connection event log and the history view that
the roadmap said should ship together (history needs the exit codes
only a log can provide).

### Added

- **Connection event log (opt-in)** — `xzssh history enable [--file
  PATH]` sets `Config.event_log`; from then on every `xzssh connect`
  appends one JSON line (timestamp, alias, target, **exit code**,
  duration) to the log. Default path is `xzssh.log` *next to the
  config file* (the value is stored relative, so each profile gets its
  own log). `history disable` stops logging (keeps the file);
  `history clear` deletes the file.
- **`xzssh history [--limit N]`** — the last connections (default 50),
  newest first: timestamp, alias, target, exit code (✔ for 0, red
  otherwise), duration. Failed connects are shown too — that's the
  point.

### Security / privacy

- Strictly **opt-in**; nothing is ever written unless `event_log` is
  set.
- Hosts tagged **`no-log`** are never recorded, as the roadmap
  required.
- The log file is created `0600` — it reveals when and where you
  connect.

### Behavior notes

- Logging is best-effort: an unwritable log degrades to a warning and
  never changes `connect`'s exit code (which still propagates ssh's).
- `--dry-run` connects are not logged; corrupt log lines are skipped
  on read (disposable-state posture, like the tunnel file).

## [0.15.0] — 2026-06-12

Closes out Tier 3.

### Added

- **Encrypted JSON at rest** — optional symmetric `gpg` or `age`
  envelope around `~/.ssh/xzssh.json`:
  - `xzssh encrypt [--tool gpg|age]` opts in (default: gpg, AES256,
    armored); `xzssh decrypt` opts out. Switching tools re-encrypts.
  - Transparent thereafter: `load_config` detects the envelope by
    magic bytes and decrypts; `write_config` re-encrypts whenever
    `Config.encryption` is set. The field travels inside the encrypted
    JSON, so the choice survives round-trips — and a config the user
    encrypted *manually* with gpg/age is detected from the file itself
    and stays encrypted across writes.
  - The passphrase is prompted by the tool itself (pinentry / age's
    tty prompt) on every config read **and** write; xzSSH never sees
    or stores it. A cancelled or failed prompt on write raises before
    anything touches disk — the encrypted file is never corrupted.
  - `xzssh export` remains the documented plaintext-backup escape
    hatch (it prints the **decrypted** snapshot — keep backups
    somewhere safe).

### Security

- `xzssh encrypt` deliberately leaves **no plaintext `.bak`** behind —
  that would silently defeat the encryption. It warns about the
  unrecoverable-passphrase risk instead and points at `export`.
- Shell completers refuse to touch an enveloped config (no pinentry
  popups mid-`<TAB>`); they return no completions instead.

### Behavior notes

- The generated `~/.ssh/config` stays plaintext — ssh itself has to
  read it. The envelope protects the source of truth only.
- `xzssh edit` still round-trips the host entry through a `0600`
  scratch file in `$TMPDIR` while the editor is open.
- Validator: `config.encryption` must be `gpg` or `age` when present.

## [0.14.0] — 2026-06-12

### Added

- **`xzssh sync`** — closes the loop when `~/.ssh/config` was edited by
  hand (previously the next `generate` simply clobbered such edits):
  - **Report mode (default):** prints per-host drift — hosts only in
    the file (`+`), only in the JSON (`-`), or changed (`~`, with the
    exact fields) — and exits 1 when drift exists, 0 when in sync.
    Scriptable like `git diff --exit-code`.
  - **`--prefer json`** — regenerate the file from the JSON via the
    `generate --force` path (existing file backed up to `.bak`).
  - **`--prefer file`** — import the drift back into the JSON:
    hand-added hosts are imported, missing hosts removed, changed
    fields copied. JSON-only metadata (`tags`, `last_used`) is
    preserved; the merged config is **semantically validated before
    any write** (a hand-edit that e.g. introduces a forward-port
    conflict aborts with both files untouched); the previous JSON is
    saved to `.bak`. The file itself is never touched.
  - **`--interactive`** — choose json/file per drifted host. Mixed
    decisions compose: file-wins choices are folded into the JSON
    first, then a single regeneration reflects everything.
  - Drift comparison is normalization-aware: identity files are
    resolved on both sides, an unset `Port` equals an explicit `22`,
    and forward lists compare order-insensitively — formatting
    differences are not drift.
  - `Match` / `Include` / wildcard patterns (which the model can't
    represent) are **not** drift on their own, but a json-wins
    regeneration would wipe them — that direction requires `--force`
    (or an explicit confirmation interactively). File-wins only warns,
    since it never touches the file.
- New `xzssh/sync/` package: pure diff logic (`compare_hosts`,
  `DriftReport`) with no I/O — the CLI command only renders and
  applies.

## [0.13.0] — 2026-06-12

### Added

- **`xzssh tunnel`** — open a host's port-forwards without an
  interactive session (nested subcommands like `key`, so `list`/`stop`
  can never collide with a host alias):
  - `tunnel start <alias>` — foreground `ssh -N` with the host's
    LocalForward / RemoteForward / DynamicForward rules passed
    explicitly as `-L`/`-R`/`-D` flags (the tunnel works even when
    `~/.ssh/config` was never generated or is stale). Ctrl-C is the
    documented way to stop and exits 0; other ssh exit codes propagate.
  - `tunnel start <alias> --detach` — spawns ssh in its own session
    with a known pid, records it in a state file, and returns. A short
    startup grace period catches dead-on-arrival tunnels (unknown host,
    port already bound) and reports the per-alias log file instead of
    pretending success. Starting a second tunnel for the same alias
    while one is alive is refused.
  - `tunnel list` — table with per-pid liveness; dead records are
    pruned on the way out.
  - `tunnel stop <alias>` / `tunnel stop --all` — SIGTERM the recorded
    pid(s) and forget them.
- `ExitOnForwardFailure=yes` is always set on tunnel commands — a
  "tunnel" whose forwards failed to bind dies instead of lingering.
- Tunnel state lives in the platform *state* dir (it's runtime data,
  not config): `$XDG_STATE_HOME/xzssh/tunnels.json` on POSIX,
  `%LOCALAPPDATA%\xzssh\tunnels.json` on Windows, `$XZSSH_TUNNELS_FILE`
  to override. Corrupt state degrades to empty rather than blocking.
- New platform helpers `pid_alive` / `terminate_pid`
  (`xzssh/platform/process.py`). The Windows liveness path goes through
  `OpenProcess` — never `os.kill(pid, 0)`, which on Windows
  *terminates* the target instead of probing it.

### Behavior notes

- Deliberately **not** `ssh -f`: ssh's own daemonization forks a child
  whose pid can't be learned, which would make `tunnel stop`
  impossible. `Popen` + own session gives the same detachment with a
  known pid.
- Forwards stay out of `connect`/`which`/`test` command lines, as
  before — `tunnel` is the one command where forwards *are* the point.

## [0.12.0] — 2026-06-12

### Added

- **Multiple profiles** — named pointers to alternate config files, so
  work / personal / client setups don't need `--config` everywhere:
  - `xzssh profile add <name> <path>` (`--default` to also make it the
    default, `--replace` to overwrite), `profile list`, `profile use
    <name>` (set default), `profile remove <name>` (unregisters; never
    deletes the config file).
  - `xzssh --profile work connect db` — every command accepts
    `--profile`, before or after the subcommand.
  - Per-shell-session override via `$XZSSH_PROFILE`; resolution order
    is `--config` > `--profile` > `$XZSSH_PROFILE` > default profile >
    `~/.ssh/xzssh.json`. Passing `--config` *and* `--profile` together
    is an error rather than a silent precedence guess.
  - The registry lives outside `~/.ssh` (it's CLI configuration, not
    SSH data): `$XDG_CONFIG_HOME/xzssh/profiles.json` on POSIX,
    `%APPDATA%\xzssh\profiles.json` on Windows, `$XZSSH_PROFILES_FILE`
    to override. Written atomically with `0600`, like every other
    xzSSH file.
  - Tab completion: `--profile <TAB>`, `profile use <TAB>`, and
    `profile remove <TAB>` complete registered names; alias/key
    completion now honours `--profile` too.

### Behavior notes

- The registry is JSON, not the TOML the roadmap sketched: Python 3.9
  has no stdlib TOML reader (and no version has a writer), and the
  runtime dep tree deliberately stays `rich` + `questionary`.
- Relative profile paths anchor to the registry file's directory —
  same convention as `identity_file` anchoring to the config file.
- `xzssh profile ...` subcommands skip profile resolution on purpose:
  a dangling default profile fails other commands cleanly (exit 2) but
  can always be repaired via `profile use` / `profile remove`.

## [0.11.0] — 2026-06-12

First Tier 3 item: infrastructure for safe schema evolution, landed
*before* the first schema break rather than after.

### Added

- **Schema versioning + migration framework.** The JSON config's
  `version` field is now enforced end-to-end:
  - `CURRENT_SCHEMA_VERSION` lives in `xzssh/model/types.py` (the model
    owns the schema); `Config.version` defaults to it, and every
    fresh-config code path stamps it.
  - `xzssh/parser/migrations.py` holds the `MIGRATIONS` registry —
    `{source_version: fn}` where each fn upgrades a raw config dict one
    version step. The contract (never lower or re-use a version number;
    migrations are pure and idempotent; a gap in the chain is a hard
    error) is documented in the module docstring.
  - On load, an older file is upgraded **in memory** by running the
    chain, then written back **once** through the normal CLI load path
    (`load_config_if_exists`), with the original preserved as
    `xzssh.json.bak`. The write-back failing is non-fatal: the command
    keeps running on the migrated in-memory config and the upgrade
    retries next load.
  - A file with a *newer* schema version than the running xzSSH is
    refused with a clear "upgrade xzSSH" error instead of being
    half-parsed.
  - `load_config_versioned(path)` joins `load_config` in the parser's
    public API for callers that need the source version.

### Behavior notes

- Quiet paths stay quiet: the upgrade notice goes to stderr (piped
  `xzssh export` output stays valid JSON), and shell completers migrate
  in memory only — they never write from inside the completion shim.
- The schema is still v1 — no actual migration ships in this release;
  the framework is exercised by tests with synthetic migrations.

## [0.10.1] — 2026-05-30

Docs and release-pipeline polish — no feature changes.

### Added

- GitHub Release pages now carry **per-version notes**: the release
  workflow extracts the matching `CHANGELOG.md` section
  (`scripts/extract_changelog.py`) and sets it as the release body, so
  each version's page shows what it shipped — not just the binaries.

### Changed

- README Command Reference table now lists every command, including the
  Tier 2 additions (`which`, `search`, `test`, `edit`, `export`,
  `import-json`) and key flags.

### Security

- `xzssh export --output FILE` now writes the snapshot with `0600`
  permissions (via the platform helper), matching `xzssh.json` — the
  snapshot holds the same hostnames and key paths.

## [0.10.0] — 2026-05-28

Final Tier 2 feature — completes the Tier 2 backlog.

### Added

- **`xzssh connect --dry-run`** — resolve the host and print the exact
  `ssh` command that would run, without connecting and without stamping
  `last_used`. Rounds out `--dry-run` coverage (now on `generate`,
  `remove`, and `connect`).

### Notes

- Verified the `add --tag` prompt-driven path (not just the flag form)
  persists tags — locked in with a test, closing the last Tier 2 item.

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

[Unreleased]: https://github.com/010228lxz/xzSSH/compare/v0.20.1...HEAD
[0.20.1]: https://github.com/010228lxz/xzSSH/compare/v0.20.0...v0.20.1
[0.20.0]: https://github.com/010228lxz/xzSSH/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/010228lxz/xzSSH/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/010228lxz/xzSSH/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/010228lxz/xzSSH/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/010228lxz/xzSSH/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/010228lxz/xzSSH/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/010228lxz/xzSSH/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/010228lxz/xzSSH/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/010228lxz/xzSSH/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/010228lxz/xzSSH/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/010228lxz/xzSSH/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/010228lxz/xzSSH/compare/v0.9.0...v0.10.0
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
