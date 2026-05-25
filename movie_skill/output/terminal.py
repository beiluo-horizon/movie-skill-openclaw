"""Rich-styled terminal output for search results.

Provides human-readable output mode (default) with colored tables
and formatted result display.
"""

from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from movie_skill.output.schema import SearchResult, MagnetResult

# Shared console instance
_console = Console()


def print_search_result(
    result: SearchResult,
    show_all: bool = False,
) -> None:
    """Print search results in human-readable format.

    Args:
        result: SearchResult to display.
        show_all: If True, show all results. If False, only show best.
    """
    if result.total == 0:
        _print_no_results(result)
        return

    # Show best result prominently
    best = result.best()
    if best:
        _console.print()
        _console.print("[bold green]Best Result:[/]")
        _console.print(f"  Title:    [bold]{best.title}[/]")
        _console.print(f"  Source:   {best.source}")
        _console.print(f"  Size:     {_format_size(best.size_bytes)}")
        _console.print(f"  Quality:  {best.resolution}")
        _console.print(f"  Magnet:   {best.magnet_uri[:100]}...")
        if best.seeders is not None:
            _console.print(f"  Seeders:  {best.seeders}")

    # Show all results in a table
    _console.print()
    _console.print(f"[green]Found {result.total} unique result(s)[/]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim")
    table.add_column("Source", style="blue")
    table.add_column("Title")
    table.add_column("Size", justify="right")
    table.add_column("Quality")

    for i, mr in enumerate(result.results, 1):
        is_best = best and mr.btih == best.btih
        star = "[bold yellow]*[/]" if is_best else " "
        table.add_row(
            f"{star}{i}",
            mr.source,
            mr.title[:60] + ("..." if len(mr.title) > 60 else ""),
            _format_size(mr.size_bytes),
            mr.resolution,
        )

    _console.print(table)

    # Show errors if any
    if result.errors:
        _console.print()
        _console.print("[yellow]Warnings:[/]")
        for error in result.errors:
            _console.print(f"  [dim]- {error}[/]")
        _console.print()

    _console.print(f"[dim]Results saved to .magnet/ directory[/]")


def _print_no_results(result: SearchResult) -> None:
    """Print a formatted 'no results' message."""
    _console.print()
    _console.print("[yellow]No results found[/]")
    if result.errors:
        _console.print("Errors from source sites:")
        for error in result.errors:
            _console.print(f"  [red]- {error}[/]")
    else:
        _console.print("  No sites were configured or searched.")
    _console.print()


def print_error(message: str) -> None:
    """Print an error message in red."""
    _console.print(f"[bold red]Error:[/] {message}")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    _console.print(f"[yellow]Warning:[/] {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    _console.print(f"[blue]{message}[/]")


def _format_size(size_bytes: Optional[int]) -> str:
    """Format bytes to human-readable size string."""
    if size_bytes is None:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
