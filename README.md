# xzSSH 🚀

[![Python versions](https://img.shields.io/badge/python-3.9%E2%80%933.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**xzSSH** is a modern, interactive SSH configuration manager for OpenSSH. It provides a structured, developer-focused workflow for managing complex SSH environments.

## ✨ Key Features

- 🖥️ **Interactive Dashboard**: A keyboard-first, high-contrast neon TUI for managing and connecting to hosts.
- ⚡ **Fuzzy Search**: Quickly find and connect to servers by alias, hostname, or user with instant keyboard shortcuts.
- 🎨 **Neon Branding**: High-contrast modern aesthetics featuring Neon Green, Pink, and Cyan for better visual clarity.
- 🛠️ **Config Isolation**: Keeps your source configuration in a clean JSON file (`~/.ssh/xzssh.json`) and generates the final `~/.ssh/config` deterministically.
- 🔒 **Security First**: Automatically manages file permissions (e.g., `chmod 600`) and validates key paths.
- 📊 **Health Checks**: Detects duplicate aliases and LocalForward port conflicts across your entire fleet.
- 📥 **Easy Migration**: Import existing hosts directly from your standard OpenSSH config.

---

## 🚀 Quick Start

### 📦 Installation

#### Single-File Distribution (Recommended for Sharing)
For a standalone, source-protected experience without manually installing dependencies:

- **macOS / Linux / Windows (Native Binaries)**:
  Download the appropriate binary from the [GitHub Releases](https://github.com/010228lxz/xzSSH/releases) page.
  1. Transfer the binary to the target machine.
  2. (Linux/macOS) Grant execution permission: `chmod +x xzssh-linux` or `chmod +x xzssh-macos`.
  3. Run it directly: `./xzssh-linux` or `xzssh-windows.exe`.

- **Cross-Platform Zip-App (`xzssh.pyz`)**:
  If you have Python 3.9+ installed, you can use the cross-platform `xzssh.pyz` file:
  ```bash
  python3 xzssh.pyz
  ```

#### Standard Source Installation
Clone the repository and run the automated installation script:

#### macOS / Linux
```bash
git clone https://github.com/010228lxz/xzSSH.git
cd xzSSH
chmod +x install.sh
./install.sh
```
The script sets up a virtual environment and optionally creates a global `xzssh` symlink or adds an alias to your `~/.zshrc`.

#### Windows
```powershell
.\install.bat
venv\Scripts\activate
xzssh
```

### ⌨️ Tab Completion (optional)

xzSSH supports tab-completion for host aliases on bash, zsh, and fish via
[argcomplete](https://kislyuk.github.io/argcomplete/). Once installed, hit
`<TAB>` after `xzssh connect`, `xzssh test`, or `xzssh remove` to autocomplete
from your configured aliases — no need to remember them.

```bash
# install the optional dep
pip install 'xzssh[completion]'

# one-line shell hook (bash/zsh):
eval "$(register-python-argcomplete xzssh)"

# add it to your ~/.bashrc or ~/.zshrc so it sticks across sessions.
# fish users:
register-python-argcomplete --shell fish xzssh | source
```

The completion shim is a no-op when argcomplete isn't installed; the
rest of the CLI works exactly as before.

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
| `connect [alias]` | Quickly connect to a host via alias or fuzzy search (`--dry-run` to preview). |
| `which <alias>` | Print the resolved `ssh` command line without running it. |
| `search <query>` | Search hosts by alias, hostname, user, tag, or proxy-jump. |
| `test [alias]` | Probe connectivity (`--all` for every host) without opening a shell. |
| `tunnel start <alias>` | Open the host's port-forwards without a shell (`--detach` to background; `tunnel list` / `tunnel stop`). |
| `history` | Recent connections with exit codes (opt-in: `history enable`; hosts tagged `no-log` are never recorded). |
| `scp` / `sftp` / `rsync` | Transfer wrappers that rewrite `alias:path` and inject the host's port/identity/jump options. |
| `add` | Add a host — interactively, or via flags (`--proxy-jump`, `--tag`, forwards, …). |
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
