from __future__ import annotations

import sys
from typing import Any, List, Optional, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.status import Status
from rich.live import Live
from rich.text import Text
from rich.markup import escape
import questionary

from xzssh import __version__

# Themes. Each palette maps the semantic style names used throughout the
# CLI ("alias", "error", ...) to rich styles, plus a small "prompt" block
# of raw prompt_toolkit colors for the questionary widgets. All styling
# is centralized HERE — command handlers must only ever use the semantic
# names (plus [accent] for brand-colored text).
PALETTES = {
    # The original look: neutral tones, neon accents.
    "neon": {
        "styles": {
            "info": "#00FFFF",  # Neon Cyan
            "warning": "#FFFF33",  # Neon Yellow
            "error": "#FF3131",  # Neon Red
            "success": "#39FF14",  # Neon Green
            "highlight": "bold #FF00FF",  # Neon Pink/Magenta
            "muted": "dim white",
            "alias": "bold #39FF14",
            "host": "white",
            "user": "#39FF14",
            "port": "#00FFFF",
            "tag": "#FF00FF",
            "last_used": "dim white",
            "step": "italic dim white",
            "key": "#FFFF33",
            "radio_selected": "bold #39FF14",
            "radio_unselected": "dim white",
            "text": "white",
            "shortcut": "bold #39FF14",
            "section": "bold underline #39FF14",
            "accent": "bold #39FF14",
            "banner_border": "#39FF14",
        },
        "prompt": {
            "accent": "#39FF14",
            "separator": "#FF00FF",
            "text": "#ffffff",
            "muted": "#666666",
        },
    },
    # Sober ANSI-named colors that respect the terminal's own scheme.
    "classic": {
        "styles": {
            "info": "cyan",
            "warning": "yellow",
            "error": "red",
            "success": "green",
            "highlight": "bold magenta",
            "muted": "dim",
            "alias": "bold cyan",
            "host": "default",
            "user": "green",
            "port": "cyan",
            "tag": "magenta",
            "last_used": "dim",
            "step": "italic dim",
            "key": "yellow",
            "radio_selected": "bold green",
            "radio_unselected": "dim",
            "text": "default",
            "shortcut": "bold green",
            "section": "bold underline",
            "accent": "bold green",
            "banner_border": "green",
        },
        "prompt": {
            "accent": "ansigreen",
            "separator": "ansimagenta",
            "text": "",
            "muted": "ansibrightblack",
        },
    },
    # Maximum legibility: bright colors, bold accents, no dim text.
    "high-contrast": {
        "styles": {
            "info": "bright_cyan",
            "warning": "bold bright_yellow",
            "error": "bold bright_red",
            "success": "bold bright_green",
            "highlight": "bold bright_magenta",
            "muted": "white",
            "alias": "bold bright_white",
            "host": "bright_white",
            "user": "bright_green",
            "port": "bright_cyan",
            "tag": "bright_magenta",
            "last_used": "white",
            "step": "white",
            "key": "bright_yellow",
            "radio_selected": "bold bright_green",
            "radio_unselected": "white",
            "text": "bright_white",
            "shortcut": "bold bright_yellow",
            "section": "bold underline bright_white",
            "accent": "bold bright_white",
            "banner_border": "bright_white",
        },
        "prompt": {
            "accent": "ansibrightgreen",
            "separator": "ansibrightmagenta",
            "text": "ansibrightwhite",
            "muted": "ansiwhite",
        },
    },
    # No color at all — emphasis only. For pipes, screenshots, and
    # monochrome terminals.
    "mono": {
        "styles": {
            "info": "default",
            "warning": "bold",
            "error": "bold reverse",
            "success": "bold",
            "highlight": "bold",
            "muted": "dim",
            "alias": "bold",
            "host": "default",
            "user": "default",
            "port": "default",
            "tag": "italic",
            "last_used": "dim",
            "step": "italic dim",
            "key": "underline",
            "radio_selected": "bold",
            "radio_unselected": "dim",
            "text": "default",
            "shortcut": "bold",
            "section": "bold underline",
            "accent": "bold",
            "banner_border": "dim",
        },
        "prompt": {
            "accent": "bold",
            "separator": "",
            "text": "",
            "muted": "",
        },
    },
}

DEFAULT_THEME = "neon"
_active_theme = DEFAULT_THEME

console = Console(theme=Theme(PALETTES[DEFAULT_THEME]["styles"]))
error_console = Console(theme=Theme(PALETTES[DEFAULT_THEME]["styles"]), stderr=True)

# Whether apply_theme has pushed a theme onto the consoles' stacks (so a
# re-apply pops the previous one instead of growing the stack forever).
_theme_pushed = False


def available_themes():
    return sorted(PALETTES)


def active_theme_name() -> str:
    return _active_theme


def apply_theme(name: str) -> None:
    """Switch both consoles (and the questionary palette) to *name*.

    Mutates the module-global consoles in place — every module that did
    ``from xzssh.cli.ui import console`` keeps working.
    """
    global _active_theme, _theme_pushed
    if name not in PALETTES:
        raise ValueError(
            f"Unknown theme '{name}' (available: {', '.join(available_themes())})"
        )
    theme = Theme(PALETTES[name]["styles"])
    for target in (console, error_console):
        if _theme_pushed:
            target.pop_theme()
        target.push_theme(theme)
    _theme_pushed = True
    _active_theme = name

def print_banner():
    """Prints a stylish banner for xzSSH."""
    logo = r"""
 [accent]   __  __ _____  _____  _____  __ __ [/accent]
 [accent]   \ \/ //__  / /  ___|/  ___|| | | |[/accent]
 [accent]    \  /   / /  \ `--. \ `--. | |_| |[/accent]
 [accent]    /  \  / /    `--. \ `--. \|  _  |[/accent]
 [accent]   / /\ \/ /__  /\__/ //\__/ /| | | |[/accent]
 [accent]  /_/  \_\_____|\____/ \____/ \_| |_/[/accent]
    """
    banner_text = f"{logo}\n[accent]xzSSH[/accent] [muted]v{__version__}[/muted]\n[dim]The SSH configuration CLI manager[/dim]"
    console.print(Panel(banner_text, border_style="banner_border", expand=False, padding=(0, 2), subtitle="[dim]Keyboard-first & Fast[/dim]", subtitle_align="right"))

def print_step(message: str):
    """Prints a styled step or action description."""
    console.print(f"[step]→[/step] [muted]{message}[/muted]")

def status(message: str):
    """Returns a rich Status context manager with modern styling."""
    return console.status(f"[muted]{message}...[/muted]", spinner="dots")

def print_error(message: str):
    """Prints an error message with an icon."""
    error_console.print(f"[error]✘[/error] {message}")

def print_errors(errors: List[str]):
    """Prints a list of error messages."""
    for error in errors:
        print_error(error)

def print_warning(message: str):
    """Prints a warning message with an icon."""
    error_console.print(f"[warning]⚠[/warning] {message}")

def print_warnings(warnings: List[str]):
    """Prints a list of warning messages."""
    for warning in warnings:
        print_warning(warning)

def print_success(message: str):
    """Prints a success message with an icon."""
    console.print(f"[success]✔[/success] {message}")

def print_info(message: str):
    """Prints an info message."""
    console.print(f"[info]ℹ[/info] {message}")

def print_notice(message: str):
    """Prints an info-styled message to STDERR.

    For notices emitted during config loading — they must not corrupt
    the stdout of piped commands like `xzssh export > backup.json`.
    """
    error_console.print(f"[info]ℹ[/info] {message}")

def print_host_status(alias: str, host_name: str, status: str):
    """Prints a styled status line for a host."""
    icon = "[success]●[/success]" if status == "online" else "[error]○[/error]"
    console.print(f" {icon} [alias]{alias.ljust(15)}[/alias] [muted]{host_name}[/muted]")

def print_host_table(hosts: List[Any], title: Optional[str] = None):
    """Prints a styled table of hosts."""
    if not hosts:
        console.print("[muted]No hosts configured.[/muted]")
        return

    if title:
        console.print(f"\n[section]{title}[/section]")

    table = Table(box=None, padding=(0, 2), show_header=True, header_style="bold underline")
    table.add_column("Alias", style="alias", no_wrap=True)
    table.add_column("Hostname", style="host")
    table.add_column("User", style="user")
    table.add_column("Port", style="port")
    table.add_column("Via", style="port")
    table.add_column("Tags", style="tag")
    table.add_column("Last Used", style="last_used")

    # Sort hosts: first by last_used (descending, None last), then by alias
    def sort_key(h):
        return (h.last_used or "", h.alias)

    sorted_hosts = sorted(hosts, key=sort_key, reverse=True)

    for host in sorted_hosts:
        tags_str = ", ".join(host.tags) if host.tags else "[muted]-[/muted]"
        
        # Format last used time
        last_used_str = "[muted]Never[/muted]"
        if host.last_used:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(host.last_used)
                now = datetime.now()
                diff = now - dt
                if diff.days > 0:
                    last_used_str = f"{diff.days}d ago"
                elif diff.seconds > 3600:
                    last_used_str = f"{diff.seconds // 3600}h ago"
                elif diff.seconds > 60:
                    last_used_str = f"{diff.seconds // 60}m ago"
                else:
                    last_used_str = "Just now"
            except Exception:
                last_used_str = "[muted]Unknown[/muted]"
        
        table.add_row(
            host.alias,
            host.host_name,
            host.user or "[muted]-[/muted]",
            str(host.port) if host.port else "[muted]22[/muted]",
            host.proxy_jump or "[muted]-[/muted]",
            tags_str,
            last_used_str
        )
    
    console.print(table)

def get_radio_style():
    """Returns a questionary style for the radio-like selection, from the active theme."""
    prompt = PALETTES[_active_theme]["prompt"]

    def fg(color: str, *extra: str) -> str:
        parts = [f"fg:{color}"] if color else []
        parts.extend(extra)
        return " ".join(parts)

    accent, separator = prompt["accent"], prompt["separator"]
    text, muted = prompt["text"], prompt["muted"]
    return questionary.Style([
        ('qmark', fg(accent, 'bold')),
        ('question', 'bold'),
        ('answer', fg(accent, 'bold')),
        ('pointer', fg(accent, 'bold')),
        ('highlighted', fg(accent, 'bold')),
        ('selected', fg(accent)),
        ('separator', fg(separator)),
        ('instruction', fg(muted, 'italic')),
        ('radio_off', fg(muted)),
        ('radio_on', fg(accent, 'bold')),
        ('shortcut', fg(accent, 'bold')),
        ('text', fg(text)),               # Questionary style tokens don't need class: prefix
        ('alias', fg(accent, 'bold')),
        ('host', fg(text)),
        ('muted', fg(muted)),
    ])

def prompt_select_action(message: str, choices: List[questionary.Choice], shortcuts: Optional[Dict[str, str]] = None) -> str:
    """Interactively select an action using a radio-like selection with optional shortcuts."""
    styled_choices = []
    for choice in choices:
        if isinstance(choice, questionary.Separator):
            styled_choices.append(choice)
            continue
            
        # We now keep the choices as provided in main.py which already includes shortcuts on the left
        styled_choices.append(choice)

    q = questionary.select(
        message,
        choices=styled_choices,
        style=get_radio_style(),
        pointer='→ ',
        instruction=" (Use arrow keys or shortcuts to navigate)"
    )

    # Add custom key bindings if shortcuts are provided
    if shortcuts:
        kb = q.application.key_bindings
        
        # Find InquirerControl
        ic = None
        for win in q.application.layout.find_all_windows():
            if hasattr(win.content, 'choices'):
                ic = win.content
                break
        
        if ic:
            def make_binding(char, val):
                @kb.add(char, eager=True)
                def _(event):
                    for i, choice in enumerate(ic.choices):
                        if choice.value == val:
                            ic.pointed_at = i
                            ic.is_answered = True
                            event.app.exit(result=choice.value)
                            break
            
            for char, val in shortcuts.items():
                make_binding(char, val)

    return q.ask()

def prompt_host_details(existing_host: Optional[Any] = None) -> Dict[str, Any]:
    """Interactively prompts for host details."""
    title = "Editing SSH host..." if existing_host else "Adding a new SSH host..."
    console.print(f"[accent]{title}[/accent]")
    
    alias = questionary.text(
        "Alias (e.g., web-prod):",
        default=existing_host.alias if existing_host else ""
    ).ask()
    if alias is None: return {}
    
    host_name = questionary.text(
        "Hostname (e.g., 1.2.3.4 or example.com):",
        default=existing_host.host_name if existing_host else ""
    ).ask()
    if host_name is None: return {}
        
    user = questionary.text(
        "User (optional):",
        default=existing_host.user if existing_host and existing_host.user else ""
    ).ask()
    
    port_str = questionary.text(
        "Port (optional, default 22):",
        default=str(existing_host.port) if existing_host and existing_host.port else ""
    ).ask()
    port = int(port_str) if port_str and port_str.isdigit() else None
    
    identity_file = questionary.text(
        "Identity File Path (optional):",
        default=existing_host.identity_file if existing_host and existing_host.identity_file else ""
    ).ask()

    proxy_jump = questionary.text(
        "ProxyJump bastion alias (optional, leave blank for direct connect):",
        default=existing_host.proxy_jump if existing_host and existing_host.proxy_jump else ""
    ).ask()

    tags_str = questionary.text(
        "Tags (comma separated, optional):",
        default=", ".join(existing_host.tags) if existing_host and existing_host.tags else ""
    ).ask()
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    return {
        "alias": alias,
        "host_name": host_name,
        "user": user if user else None,
        "port": port,
        "identity_file": identity_file if identity_file else None,
        "proxy_jump": proxy_jump if proxy_jump else None,
        "tags": tags,
        "local_forwards": existing_host.local_forwards if existing_host else []
    }

def prompt_select_host(hosts: List[Any], message: str = "Select a host to manage:", shortcuts: Optional[Dict[str, str]] = None) -> Optional[Any]:
    """Interactively select a host from a list."""
    if not hosts:
        return None
    
    choices = [
        questionary.Choice(
            title=f"{h.alias} ({h.host_name})",
            value=h
        )
        for h in hosts
    ]
    
    return prompt_select_action(message, choices, shortcuts)

def print_profile_table(rows: List[Any]):
    """Prints registered profiles. Rows are (name, path, is_default, exists)."""
    if not rows:
        console.print(
            "[muted]No profiles registered. "
            "Add one with `xzssh profile add <name> <path>`.[/muted]"
        )
        return

    table = Table(box=None, padding=(0, 2), show_header=True, header_style="bold underline")
    table.add_column("Profile", style="alias", no_wrap=True)
    table.add_column("Config Path", style="host")
    table.add_column("Default", style="tag")
    table.add_column("Exists", style="muted")

    for name, path, is_default, exists in rows:
        table.add_row(
            name,
            path,
            "[success]✔[/success]" if is_default else "[muted]-[/muted]",
            "yes" if exists else "[warning]not yet[/warning]",
        )

    console.print(table)

def print_tunnel_table(rows: List[Any]):
    """Prints recorded tunnels. Rows are (alias, pid, alive, started_at, forwards)."""
    if not rows:
        console.print(
            "[muted]No tunnels recorded. "
            "Start one with `xzssh tunnel start <alias> --detach`.[/muted]"
        )
        return

    table = Table(box=None, padding=(0, 2), show_header=True, header_style="bold underline")
    table.add_column("Alias", style="alias", no_wrap=True)
    table.add_column("PID", style="port")
    table.add_column("Status")
    table.add_column("Started", style="last_used")
    table.add_column("Forwards", style="tag")

    for alias, pid, alive, started_at, forwards in rows:
        status_str = (
            "[success]● up[/success]" if alive else "[error]○ dead[/error]"
        )
        table.add_row(
            alias,
            str(pid),
            status_str,
            started_at or "[muted]-[/muted]",
            ", ".join(forwards) if forwards else "[muted]-[/muted]",
        )

    console.print(table)

def print_history_table(events: List[Dict[str, Any]]):
    """Prints connection history entries (dicts from the event log), newest first."""
    table = Table(box=None, padding=(0, 2), show_header=True, header_style="bold underline")
    table.add_column("When", style="last_used", no_wrap=True)
    table.add_column("Alias", style="alias", no_wrap=True)
    table.add_column("Target", style="host")
    table.add_column("Exit")
    table.add_column("Duration", style="port")

    for event in events:
        ts = str(event.get("ts", "?")).replace("T", " ")
        user = event.get("user")
        host_name = event.get("host_name", "?")
        target = f"{user}@{host_name}" if user else str(host_name)
        exit_code = event.get("exit_code")
        if exit_code == 0:
            exit_str = "[success]0 ✔[/success]"
        else:
            exit_str = f"[error]{exit_code}[/error]"
        duration = event.get("duration")
        duration_str = _format_duration(duration) if isinstance(duration, (int, float)) else "-"
        table.add_row(ts, str(event.get("alias", "?")), target, exit_str, duration_str)

    console.print(table)

def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    if seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"

def print_key_table(keys: dict[str, str]):
    """Prints a styled table of keys."""
    if not keys:
        console.print("[muted]No keys configured.[/muted]")
        return

    table = Table(box=None, padding=(0, 2), show_header=True, header_style="bold")
    table.add_column("Key Name", style="alias")
    table.add_column("Path", style="muted")

    for name, path in keys.items():
        table.add_row(name, path)
    
    console.print(table)


def print_help():
    """Prints a modern, guided help page."""
    console.print("\n[section]Interactive CLI (Recommended)[/section]")
    console.print("  Simply run [accent]xzssh[/accent] with no arguments to enter the interactive dashboard.")
    console.print("  From there, you can navigate with arrow keys to connect, add, or manage hosts.")
    
    console.print("\n[section]Standard CLI Usage[/section]")
    console.print("  [accent]xzssh[/accent] [muted][options][/muted] <command> [muted][args][/muted]")
    
    console.print("\n[bold]Commands:[/bold]")
    commands = [
        ("list", "List all configured hosts in a table"),
        ("connect [alias]", "Quickly connect to a host"),
        ("which <alias>", "Print the resolved ssh command without running it"),
        ("search <query>", "Search hosts by alias, hostname, user, or tag"),
        ("test [alias]", "Probe connectivity without opening a shell"),
        ("tunnel start <alias>", "Open the host's forwards without a shell"),
        ("history", "Recent connections (opt-in: history enable)"),
        ("scp / sftp / rsync", "Transfer wrappers that understand aliases"),
        ("add", "Interactively add a new host"),
        ("edit <alias>", "Edit a host's JSON entry in $EDITOR"),
        ("remove [alias...]", "Remove one or more hosts by alias"),
        ("import [file]", "Import from SSH config"),
        ("export", "Print a JSON snapshot of the config"),
        ("import-json <file>", "Restore config from a JSON snapshot"),
        ("check", "Analyze configuration for errors"),
        ("sync", "Detect/resolve drift with ~/.ssh/config"),
        ("encrypt / decrypt", "Toggle at-rest encryption of the JSON (gpg/age)"),
        ("generate", "Generate ~/.ssh/config"),
        ("menu", "Open interactive management menu"),
        ("key", "Manage private keys and ssh-agent"),
        ("profile", "Manage config profiles (work/personal/...)"),
        ("theme", "Show or set the UI color theme"),
    ]
    
    for cmd, desc in commands:
        cmd_escaped = escape(cmd)
        padding = " " * (30 - len(cmd))
        console.print(f"  [accent]{cmd_escaped}[/accent]{padding} {desc}")
        
    console.print("\n[bold]Global Options:[/bold]")
    options = [
        ("--config CONFIG", "Path to JSON config file"),
        ("--profile NAME", "Use a registered profile's config file"),
        ("--theme NAME", "UI color theme for this invocation"),
        ("--suggest-ports", "Suggest free ports on conflicts"),
        ("-h, --help", "Show this help message and exit"),
    ]
    
    for opt, desc in options:
        opt_escaped = escape(opt)
        padding = " " * (30 - len(opt))
        console.print(f"  [muted]{opt_escaped}[/muted]{padding} {desc}")
        
    console.print("\n[muted]Tip: Combine interactive and CLI modes as you prefer![/muted]\n")
