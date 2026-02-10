"""Output formatting for icloud-cli.

Supports three output formats:
- table: Rich-formatted tables (default, human-friendly)
- json:  Machine-readable JSON
- plain: Simple text output for piping/scripting
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
error_console = Console(stderr=True)


def render(
    data: list[dict[str, Any]],
    format: str = "table",
    title: str | None = None,
    columns: list[str] | None = None,
) -> None:
    """Render a list of dicts in the chosen format.

    Args:
        data: List of dictionaries to display.
        format: Output format — 'table', 'json', or 'plain'.
        title: Optional title for table output.
        columns: Optional ordered list of column keys to show. If None, uses all keys.
    """
    if not data:
        info("No results found.")
        return

    if format == "json":
        _render_json(data)
    elif format == "plain":
        _render_plain(data, columns)
    else:
        _render_table(data, title, columns)


def render_detail(data: dict[str, Any], format: str = "table", title: str | None = None) -> None:
    """Render a single item's details.

    Args:
        data: Dictionary of key-value pairs to display.
        format: Output format.
        title: Optional title for panel output.
    """
    if format == "json":
        _render_json(data)
    elif format == "plain":
        for key, value in data.items():
            print(f"{key}: {value}")
    else:
        _render_detail_panel(data, title)


def success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/] {message}")


def error(message: str) -> None:
    """Print an error message to stderr."""
    error_console.print(f"[bold red]✗[/] {message}")


def warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/] {message}")


def info(message: str) -> None:
    """Print an info message."""
    console.print(f"[bold blue]ℹ[/] {message}")


def _render_json(data: Any) -> None:
    """Output data as formatted JSON."""
    print(json.dumps(data, indent=2, default=str))


def _render_plain(data: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    """Output data as tab-separated plain text."""
    if not data:
        return

    cols = columns or list(data[0].keys())

    # Header
    print("\t".join(cols))

    # Rows
    for row in data:
        values = [str(row.get(col, "")) for col in cols]
        print("\t".join(values))


def _render_table(
    data: list[dict[str, Any]], title: str | None = None, columns: list[str] | None = None
) -> None:
    """Output data as a Rich table."""
    if not data:
        return

    cols = columns or list(data[0].keys())

    table = Table(title=title, show_header=True, header_style="bold cyan", border_style="dim")

    for col in cols:
        table.add_column(col.replace("_", " ").title(), overflow="fold")

    for row in data:
        values = [str(row.get(col, "")) for col in cols]
        table.add_row(*values)

    console.print(table)


def _render_detail_panel(data: dict[str, Any], title: str | None = None) -> None:
    """Output a single item as a Rich panel."""
    lines = []
    for key, value in data.items():
        label = key.replace("_", " ").title()
        lines.append(f"[bold cyan]{label}:[/] {value}")

    content = "\n".join(lines)
    panel = Panel(content, title=title, border_style="blue", padding=(1, 2))
    console.print(panel)


def confirm(message: str) -> bool:
    """Ask for user confirmation."""
    try:
        response = console.input(f"[bold yellow]?[/] {message} [y/N]: ")
        return response.strip().lower() in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False
