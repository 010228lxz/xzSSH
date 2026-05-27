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

# Define a theme that mimics a modern CLI (like junie or claudecode)
# Neutral tones for text, bright accents for highlights and status indicators.
CLI_THEME = Theme({
    "info": "#00FFFF",  # Neon Cyan
    "warning": "#FFFF33",  # Neon Yellow
    "error": "#FF3131",  # Neon Red
    "success": "#39FF14",  # Neon Green
    "highlight": "bold #FF00FF",  # Neon Pink/Magenta
    "muted": "dim white",
    "alias": "bold #39FF14",  # Neon Green
    "host": "white",
    "user": "#39FF14",  # Neon Green
    "port": "#00FFFF",  # Neon Cyan
    "tag": "#FF00FF",  # Neon Pink
    "last_used": "dim white",
    "step": "italic dim white",
    "key": "#FFFF33",  # Neon Yellow
    "radio_selected": "bold #39FF14",  # Neon Green
    "radio_unselected": "dim white",
    "text": "white",
    "shortcut": "bold #39FF14",  # Neon Green - User wants shortcuts noticeable, neon green is better than yellow
    "section": "bold underline #39FF14",  # Neon Green
})

console = Console(theme=CLI_THEME)
error_console = Console(theme=CLI_THEME, stderr=True)

def print_banner():
    """Prints a stylish banner for xzSSH."""
    logo = r"""
 [bold #39FF14]   __  __ _____  _____  _____  __ __ [/bold #39FF14]
 [bold #39FF14]   \ \/ //__  / /  ___|/  ___|| | | |[/bold #39FF14]
 [bold #39FF14]    \  /   / /  \ `--. \ `--. | |_| |[/bold #39FF14]
 [bold #39FF14]    /  \  / /    `--. \ `--. \|  _  |[/bold #39FF14]
 [bold #39FF14]   / /\ \/ /__  /\__/ //\__/ /| | | |[/bold #39FF14]
 [bold #39FF14]  /_/  \_\_____|\____/ \____/ \_| |_/[/bold #39FF14]
    """
    banner_text = f"{logo}\n[bold #39FF14]xzSSH[/bold #39FF14] [muted]v0.1.0 BETA[/muted]\n[dim]The SSH configuration CLI manager[/dim]"
    console.print(Panel(banner_text, border_style="#39FF14", expand=False, padding=(0, 2), subtitle="[dim]Keyboard-first & Fast[/dim]", subtitle_align="right"))

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
    """Returns a custom questionary style for the radio-like selection with neon colors."""
    return questionary.Style([
        ('qmark', 'fg:#39FF14 bold'),       # Neon Green
        ('question', 'bold'),
        ('answer', 'fg:#39FF14 bold'),       # Neon Green
        ('pointer', 'fg:#39FF14 bold'),      # Neon Green
        ('highlighted', 'fg:#39FF14 bold'),  # Neon Green
        ('selected', 'fg:#39FF14'),          # Neon Green
        ('separator', 'fg:#FF00FF'),         # Neon Pink
        ('instruction', 'fg:#666666 italic'),
        ('radio_off', 'fg:#666666'),
        ('radio_on', 'fg:#39FF14 bold'),     # Neon Green
        ('shortcut', 'fg:#39FF14 bold'),     # Neon Green
        ('text', 'fg:#ffffff'),              # Questionary style tokens don't need class: prefix
        ('alias', 'fg:#39FF14 bold'),        # Neon Green
        ('host', 'fg:#ffffff'),
        ('muted', 'fg:#666666'),
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
    console.print(f"[bold #39FF14]{title}[/bold #39FF14]")
    
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
    console.print("  Simply run [bold green]xzssh[/bold green] with no arguments to enter the interactive dashboard.")
    console.print("  From there, you can navigate with arrow keys to connect, add, or manage hosts.")
    
    console.print("\n[section]Standard CLI Usage[/section]")
    console.print("  [bold green]xzssh[/bold green] [muted][options][/muted] <command> [muted][args][/muted]")
    
    console.print("\n[bold]Commands:[/bold]")
    commands = [
        ("list", "List all configured hosts in a table"),
        ("connect [alias]", "Quickly connect to a host"),
        ("add", "Interactively add a new host"),
        ("remove [alias...]", "Remove one or more hosts by alias"),
        ("import [file]", "Import from SSH config"),
        ("check", "Analyze configuration for errors"),
        ("generate", "Generate ~/.ssh/config"),
        ("menu", "Open interactive management menu"),
        ("key", "Manage private keys and ssh-agent"),
    ]
    
    for cmd, desc in commands:
        cmd_escaped = escape(cmd)
        padding = " " * (30 - len(cmd))
        console.print(f"  [bold green]{cmd_escaped}[/bold green]{padding} {desc}")
        
    console.print("\n[bold]Global Options:[/bold]")
    options = [
        ("--config CONFIG", "Path to JSON config file"),
        ("--suggest-ports", "Suggest free ports on conflicts"),
        ("-h, --help", "Show this help message and exit"),
    ]
    
    for opt, desc in options:
        opt_escaped = escape(opt)
        padding = " " * (30 - len(opt))
        console.print(f"  [muted]{opt_escaped}[/muted]{padding} {desc}")
        
    console.print("\n[muted]Tip: Combine interactive and CLI modes as you prefer![/muted]\n")
