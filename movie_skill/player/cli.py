"""CLI entry point for movie-play.

Finds and plays downloaded media files through locally installed media players
(IINA, VLC, mpv) with resume-from-last-position support.

Usage:
    movie-play play --show "权力的游戏" --season 3 --episode 5
    movie-play play --show "权力的游戏" --season 3 --episode 5 --player mpv
    movie-play play --show "权力的游戏" --season 3 --episode 5 --start-over
    movie-play status
    movie-play status --show "权力的游戏"
"""

import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from movie_skill.player.player import (
    PlayerName,
    play_best,
)
from movie_skill.player.scanner import (
    check_download_status,
    get_player_status_message,
    scan_media_file,
)
from movie_skill.player.state import (
    PlayState,
    list_states,
    read_state,
    write_state,
)
from movie_skill.output.terminal import (
    print_error,
    print_info,
    print_warning,
)

app = typer.Typer(
    name="movie-play",
    help="Find and play downloaded media files",
    no_args_is_help=True,
)
console = Console()


def _format_position(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@app.command()
def play(
    show: str = typer.Option(
        ..., "--show", "-s",
        help="Show name (e.g. '权力的游戏')",
    ),
    season: Optional[int] = typer.Option(
        None, "--season", "-S",
        help="Season number",
    ),
    episode: Optional[int] = typer.Option(
        None, "--episode", "-E",
        help="Episode number",
    ),
    player: Optional[str] = typer.Option(
        None, "--player", "-p",
        help="Player override (iina, vlc, mpv)",
    ),
    start_over: bool = typer.Option(
        False, "--start-over",
        help="Ignore saved position and start from beginning",
    ),
    state_dir: str = typer.Option(
        ".player", "--state-dir",
        help="Player state directory",
    ),
):
    """Find and play a media file matching the given show/season/episode.

    Scans the Thunder download directory for matching files, validates them
    with ffprobe, loads the last playback position from saved state, launches
    the best available player, and saves the updated state on exit.

    Use --start-over to ignore the saved position and play from the beginning.
    """
    # Step 1: Find file
    scan_result = scan_media_file(show, season=season, episode=episode)

    if not scan_result["found"]:
        # Step 2: Handle not found
        print_error("File not found")
        dl_state = check_download_status(show, season=season, episode=episode)
        status_msg = get_player_status_message(scan_result, dl_state)
        print_info(status_msg)
        raise typer.Exit(code=1)

    file_path = scan_result["file_path"]
    is_valid = scan_result["valid"]

    # Step 3: Handle corrupt file
    if not is_valid:
        print_warning("File may be corrupt. Playing anyway.")

    # Step 4: Load resume state
    position = 0.0
    if not start_over:
        saved_state = read_state(show, season=season, episode=episode, state_dir=state_dir)
        if saved_state is not None and saved_state.file_path == file_path:
            position = saved_state.position_seconds
            if position > 0:
                print_info(f"Resuming from {int(position)}s")

    # Step 5: Detect and launch player
    resolved_player: Optional[PlayerName] = None
    if player is not None:
        if player in ("iina", "vlc", "mpv"):
            resolved_player = player  # type: ignore
        else:
            available = ", ".join(["iina", "vlc", "mpv"])
            print_error(f"Unknown player '{player}'. Available: {available}")
            raise typer.Exit(code=1)

    try:
        player_name, process = play_best(
            player=resolved_player,
            file_path=file_path,
            start_position=position,
            fullscreen=True,
        )
    except RuntimeError as e:
        print_error(str(e))
        raise typer.Exit(code=1)

    print_info(f"Playing with {player_name}")

    # Step 6: Wait for player exit
    process.wait()
    print_info("Playback finished")

    # Step 7: Save state after exit
    info = scan_result.get("info") or {}
    duration = info.get("duration_seconds") if isinstance(info, dict) else None
    now = datetime.now(timezone.utc).isoformat()

    final_state = PlayState(
        show=show,
        season=season,
        episode=episode,
        file_path=file_path,
        position_seconds=0.0,
        duration_seconds=duration,
        played_at=now,
        updated_at=now,
    )
    write_state(final_state, state_dir=state_dir)


@app.command()
def status(
    show: Optional[str] = typer.Option(
        None, "--show", "-s",
        help="Filter by show name",
    ),
    state_dir: str = typer.Option(
        ".player", "--state-dir",
        help="Player state directory",
    ),
):
    """Show saved playback positions for all or filtered shows.

    Displays a table with Show, Season, Episode, Position, Duration,
    and Last Played columns for all saved .player/ state files.
    """
    states = list_states(state_dir=state_dir)

    if not states:
        print_info("No playback history found.")
        print_info("Run 'movie-play play' to start watching.")
        return

    # Filter by show if specified
    if show:
        show_lower = show.lower()
        states = [s for s in states if show_lower in s.show.lower()]

    if not states:
        print_info(f"No playback history for '{show}'.")
        return

    # Display table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Show", style="cyan", no_wrap=True)
    table.add_column("Season", justify="right")
    table.add_column("Episode", justify="right")
    table.add_column("Position", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Last Played")

    for state in states:
        season_str = str(state.season) if state.season is not None else "-"
        episode_str = str(state.episode) if state.episode is not None else "-"
        position_str = _format_position(state.position_seconds)

        if state.duration_seconds is not None:
            duration_str = _format_position(state.duration_seconds)
        else:
            duration_str = "?"

        # Show played_at as date only
        played_str = state.played_at[:10] if state.played_at else "-"

        table.add_row(
            state.show,
            season_str,
            episode_str,
            position_str,
            duration_str,
            played_str,
        )

    console.print()
    console.print(f"[bold]Playback History:[/] {len(states)} total")
    console.print(table)
    console.print()


if __name__ == "__main__":
    app()
