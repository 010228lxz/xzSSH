# xzSSH 🚀

[![Python versions](https://img.shields.io/badge/python-3.9%E2%80%933.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**xzSSH** is a modern, interactive SSH configuration manager for OpenSSH. It provides a structured, developer-focused workflow for managing complex SSH environments.

## ✨ Key Features

- 🖥️ **Interactive Dashboard**: A keyboard-first TUI for managing and connecting to hosts with single-key shortcuts.
- ⚡ **Fuzzy Search**: Quickly find and connect to servers by alias, hostname, user, tag, or proxy-jump.
- 🎨 **Themeable UI**: `neon` (default), `classic`, `high-contrast`, and `mono` themes via `--theme` / `$XZSSH_THEME`.
- 🛠️ **Config Isolation**: Keeps your source configuration in a clean JSON file (`~/.ssh/xzssh.json`) and generates the final `~/.ssh/config` deterministically.
- 🔒 **Security First**: Manages file permissions (`chmod 600`), validates key paths, and offers optional at-rest encryption of the JSON (`gpg` or `age`).
- 📊 **Health Checks & Sync**: Detects duplicate aliases and Local/Remote/Dynamic forward port conflicts, and reports or resolves drift against `~/.ssh/config`.
- 🔑 **Key Lifecycle**: Generate keys (`ssh-keygen`), install them on hosts (`ssh-copy-id`), and load them into `ssh-agent` (with macOS Keychain support).
- 🚇 **Tunnels & Transfers**: Background port-forwards (`tunnel`), `scp`/`sftp`/`rsync` wrappers with alias rewriting, and `mosh` support.
- 👤 **Profiles**: Register and switch between separate work / personal / client configs by name.
- 🗂️ **Connection History**: Opt-in log of recent connections with exit codes (`no-log` tag honored).
- 📥 **Easy Migration**: Import existing hosts directly from your standard OpenSSH config.

---

## 🚀 Quick Start

### 📦 Installation

#### Native Binaries (Recommended for Sharing)
For a standalone experience with no Python or dependencies to install, download the
binary for your platform from the [GitHub Releases](https://github.com/010228lxz/xzSSH/releases)
page (`xzssh-linux`, `xzssh-macos`, or `xzssh-windows.exe`):

1. Transfer the binary to the target machine.
2. (Linux/macOS) Grant execution permission: `chmod +x xzssh-linux` or `chmod +x xzssh-macos`.
3. Run it directly: `./xzssh-linux` or `xzssh-windows.exe`.

#### Standard Source Installation
Clone the repository and run the automated installation script:

#### macOS / Linux
```bash
git clone https://github.com/010228lxz/xzSSH.git
cd xzSSH
chmod +x install.sh
./install.sh
```
The script sets up a virtual environment, installs xzSSH in editable mode, and optionally creates a global `xzssh` symlink in `/usr/local/bin` (it also prints an alias snippet you can drop into your `~/.zshrc` / `~/.bashrc`).

#### Windows
```powershell
.\install.bat
venv\Scripts\activate
xzssh
```

### ⌨️ Tab Completion (optional)

**zsh (recommended)** — a native completion that groups commands,
sub-commands, and options into labelled sections (and completes live
host aliases / keys / profiles from your config) ships in
[`completions/_xzssh`](completions/_xzssh):

```zsh
# put it on your fpath, then register it (compinit must run first)
mkdir -p ~/.zsh/completions
ln -sf "$PWD/completions/_xzssh" ~/.zsh/completions/_xzssh
# in ~/.zshrc:
fpath=(~/.zsh/completions $fpath)
autoload -Uz _xzssh && compdef _xzssh xzssh
# optional polish: grouped headers, menu select, colors
zstyle ':completion:*' menu select
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '%F{cyan}%B%d%b%f'
```

**bash / fish (or a simpler zsh setup)** — dynamic completion via
[argcomplete](https://kislyuk.github.io/argcomplete/):

```bash
pip install 'xzssh[completion]'
eval "$(register-python-argcomplete xzssh)"        # bash/zsh; add to your rc file
register-python-argcomplete --shell fish xzssh | source   # fish
```

Both complete from your configured aliases so you never have to remember
them. The argcomplete shim is a no-op when argcomplete isn't installed;
the rest of the CLI works exactly as before.

### ⌨️ Interactive Usage

Simply run `xzssh` without any arguments to enter the interactive dashboard. Use arrow keys to navigate or press single-key shortcuts (e.g., `c` to connect, `a` to add).

```bash
xzssh
```

---

## 📖 Command Reference

While the interactive mode is recommended, `xzssh` provides a full standard CLI:

| Command | Description |
| :--- | :--- |
| `list [--tag T]` | Display all configured hosts in a styled table (filter by tag; `--match-all` for AND semantics). |
| `connect [alias]` | Quickly connect to a host via alias or fuzzy search (`--dry-run` to preview; `--forwards` to also open the host's port-forwards — the interactive picker offers this automatically). |
| `which <alias>` | Print the resolved `ssh` command line without running it. |
| `search <query>` | Search hosts by alias, hostname, user, tag, or proxy-jump. |
| `test [alias]` | Probe connectivity (`--all` for every host) without opening a shell. |
| `mosh <alias>` | Connect with [mosh](https://mosh.org/) using the host's port/identity/jump/options. |
| `known-hosts remove <alias>` | Drop a host's cached key (`ssh-keygen -R`) after a server rebuild. |
| `tunnel start <alias>` | Open the host's port-forwards without a shell (`--detach` to background; `tunnel list` / `tunnel stop`). |
| `history` | Recent connections with exit codes (opt-in: `history enable`; hosts tagged `no-log` are never recorded). |
| `scp` / `sftp` / `rsync` | Transfer wrappers that rewrite `alias:path` and inject the host's port/identity/jump options. |
| `add` | Add a host — interactively, or via flags (`--proxy-jump`, `--tag`, forwards, `--option KEY=VALUE` for any extra ssh_config directive, `--from <alias>` to clone an existing host, …). |
| `tag add/rm <alias> <tag>…` | Add or remove tags on a host without an `edit` round-trip. |
| `edit <alias>` | Edit a host's JSON entry in `$EDITOR`, re-validated on save. |
| `remove [alias...]` | Remove one or more hosts by alias (`--dry-run` to preview). |
| `import [file]` | Import host entries from an existing OpenSSH config. |
| `export` | Print a JSON snapshot of the config (for backup). |
| `import-json <file>` | Restore the config from a JSON snapshot (`--merge` / `--replace`). |
| `check` | Analyze configuration for errors or port conflicts. |
| `sync` | Detect drift with `~/.ssh/config`; resolve with `--prefer json/file` or `--interactive`. |
| `encrypt` / `decrypt` | Toggle at-rest encryption of the JSON config (`gpg` or `age` envelope). |
| `generate` | Regenerate the final `~/.ssh/config` file. |
| `key` | Manage private keys: `gen` (create with `ssh-keygen`), `copy-id` (install on a host), `add`, `list`, `add-agent` (`--keychain` on macOS). |
| `profile` | Manage config profiles: `add`, `list`, `use`, `remove`. |
| `theme` | UI color theme: `neon` (default), `classic`, `high-contrast`, `mono`. Also `--theme` / `$XZSSH_THEME`. |

### 👤 Profiles

Juggling work / personal / client configs? Register each JSON file once
and switch by name:

```bash
xzssh profile add work ~/team-ssh.json --default
xzssh profile add personal ~/.ssh/personal.json

xzssh --profile personal connect homelab   # one-off
export XZSSH_PROFILE=personal              # for this shell session
xzssh profile use personal                 # as the new default
```

Resolution order: `--config` > `--profile` > `$XZSSH_PROFILE` > default
profile > `~/.ssh/xzssh.json`.

---

## 🏗️ Architecture

xzSSH follows a strict **Parse ➔ Validate ➔ Generate** pipeline:

1. **Model**: Pure Python dataclasses define the configuration schema.
2. **Parser**: Maps JSON source files into the internal model with type coercion.
3. **Validator**: Performs semantic checks (ports, aliases, file paths).
4. **Generator**: Renders a deterministic, human-readable OpenSSH configuration.

The JSON schema is **versioned**: configs written by an older xzSSH are
migrated automatically on load (the original is kept as `xzssh.json.bak`),
and files from a *newer* xzSSH are refused with a clear error instead of
being half-parsed.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an issue on GitHub.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
