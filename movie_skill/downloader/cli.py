"""CLI entry point for movie-dl.

Downloads magnet links through macOS Thunder client.

Usage:
    movie-dl download --show "权力的游戏" --season 3 --episode 5 --wait
    movie-dl download --show "Westworld" --wait
    movie-dl download --all --wait
    movie-dl status --show "权力的游戏"
    movie-dl status
"""

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from movie_skill.downloader.queue import DownloadQueue
from movie_skill.downloader.state import list_states, DEFAULT_DOWNLOAD_DIR, DownloadStatus
from movie_skill.output.terminal import print_error, print_info

app = typer.Typer(
    name="movie-dl",
    help="Download magnet links through macOS Thunder client",
    no_args_is_help=True,
)
console = Console()


@app.command()
def download(
    show: Optional[str] = typer.Option(
        None, "--show", "-s",
        help="Show name to filter magnets (required unless --all)",
    ),
    season: Optional[int] = typer.Option(
        None, "--season", "-S",
        help="Season number filter",
    ),
    episode: Optional[int] = typer.Option(
        None, "--episode", "-E",
        help="Episode number filter",
    ),
    all_magnets: bool = typer.Option(
        False, "--all", "-a",
        help="Download ALL unprocessed magnets (ignore --show filter)",
    ),
    wait: bool = typer.Option(
        False, "--wait", "-w",
        help="Wait for each download to complete before processing next",
    ),
    magnet_dir: Optional[str] = typer.Option(
        None, "--magnet-dir",
        help="Path to .magnet/ directory (default: .magnet/)",
    ),
    state_dir: Optional[str] = typer.Option(
        None, "--state-dir",
        help="Path to .download/ directory (default: .download/)",
    ),
    thunder_dir: Optional[str] = typer.Option(
        None, "--thunder-dir",
        help="Thunder download directory (auto-detected if not specified)",
    ),
    max_results: Optional[int] = typer.Option(
        None, "--max", "-m",
        help="Maximum number of magnets to process",
    ),
):
    """Download magnet links through macOS Thunder.

    Scans .magnet/ for unprocessed magnets, filters by show/season/episode,
    and processes them through Thunder sequentially.

    Use --wait to block until each download completes (supports completion
    detection via directory polling). Without --wait, processes the first
    magnet in --show mode or all in --all mode and exits immediately.

    Examples:
        movie-dl download --show "权力的游戏" --season 3 --episode 5 --wait
        movie-dl download --show "Westworld" --wait
        movie-dl download --all
    """
    if not show and not all_magnets:
        print_error("Provide --show or use --all to download all magnets")
        print_info("Usage: movie-dl download --show '权力的游戏' -S 3 -E 5 --wait")
        print_info("   or: movie-dl download --all")
        raise typer.Exit(code=1)

    # Build queue
    queue = DownloadQueue(
        magnet_dir=magnet_dir or ".magnet",
        state_dir=state_dir or DEFAULT_DOWNLOAD_DIR,
        thunder_dir=thunder_dir,
    )

    # Prepare filter params
    effective_show = None if all_magnets else (show or "")

    # Run the queue
    print_info(f"Scanning magnets...")
    results = queue.run(
        show=effective_show,
        season=season,
        episode=episode,
        wait=wait,
        max_results=max_results,
    )

    if not results:
        print_info("No magnets to download.")
        return

    # Display results
    total = len(results)
    done = sum(1 for r in results if r.status.value == "done")
    failed = sum(1 for r in results if r.status.value == "failed")

    console.print()
    console.print(f"[bold]Results:[/] {total} processed, "
                  f"[green]{done} completed[/], "
                  f"[red]{failed} failed[/]")
    console.print()

    for state in results:
        status_style = {
            "done": "[green]DONE[/]",
            "failed": "[red]FAILED[/]",
            "downloading": "[yellow]DOWNLOADING[/]",
        }.get(state.status.value, f"[dim]{state.status.value}[/]")

        console.print(f"  {status_style}  {state.title}")
        if state.download_path:
            console.print(f"        Path: {state.download_path}")
        if state.error:
            console.print(f"        Error: {state.error}")

    console.print()
    if failed > 0:
        print_info("Failed downloads can be retried by re-running the command.")
        print_info("The next-ranked magnet will be attempted on retry.")


@app.command()
def status(
    show: Optional[str] = typer.Option(
        None, "--show", "-s",
        help="Show name to filter status by",
    ),
    state_dir: Optional[str] = typer.Option(
        None, "--state-dir",
        help="Path to .download/ directory (default: .download/)",
    ),
):
    """Show download status for all or filtered magnets.

    Reads .download/ state files and displays current status
    for each processed magnet.

    Examples:
        movie-dl status
        movie-dl status --show "权力的游戏"
    """
    states = list_states(state_dir=state_dir or DEFAULT_DOWNLOAD_DIR)

    if not states:
        print_info("No download history found.")
        print_info("Run 'movie-dl download' to start downloading.")
        return

    # Filter by show if specified
    if show:
        show_lower = show.lower()
        states = [s for s in states if show_lower in s.show.lower()]

    if not states:
        print_info(f"No downloads found for '{show}'.")
        return

    # Display table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("BTIH", style="dim")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Progress")
    table.add_column("Error")

    for state in states:
        status_str = state.status.value
        status_style = {
            "done": "[green]done[/]",
            "failed": "[red]failed[/]",
            "downloading": "[yellow]downloading[/]",
        }.get(status_str, f"[dim]{status_str}[/]")

        progress = "100%" if state.status == DownloadStatus.DONE else (
            "failed" if state.status == DownloadStatus.FAILED else (
                "in progress" if state.status in ("downloading", "queueing") else "pending"
            )
        )

        error_str = state.error or ""

        table.add_row(
            state.btih[:12],
            state.title[:40],
            status_style,
            progress,
            error_str[:30],
        )

    console.print()
    console.print(f"[bold]Download Status:[/] {len(states)} total")
    console.print(table)
    console.print()


if __name__ == "__main__":
    app()
