"""CLI entry point for movie-skill - unified pipeline command.

Accepts natural language queries, parses intent, and dispatches
to the appropriate pipeline (crawl -> download -> play).

Usage:
    movie-skill "我想看权力的游戏第三季第五集"
    movie-skill --auto "下载权力的游戏"
    movie-skill "播放权力的游戏第三季第五集"
    movie-skill --help
"""

from typing import Optional

import typer

from movie_skill.skill.parser import parse_intent, IntentType
from movie_skill.skill.pipeline import PipelineOrchestrator
from movie_skill.skill.interactor import ConsoleInteractor
from movie_skill.output.terminal import print_error, print_info

app = typer.Typer(
    name="movie-skill",
    help="Unified movie pipeline - search, download, and play movies/TV shows",
    pretty_exceptions_show_locals=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Handle direct invocation without subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    print_info("movie-skill - 统一影视资源管道")
    print_info("")
    print_info("使用方式:")
    print_info('  movie-skill "分步看权力的游戏"')
    print_info('  movie-skill "自动下载权力的游戏"')
    print_info('  movie-skill "播放列表"')
    print_info('  movie-skill list')
    print_info('  movie-skill list --play')
    raise typer.Exit()


def _handle_query(
    query: str,
    auto: bool,
    mode: str,
    magnet_dir: Optional[str],
    download_state_dir: Optional[str],
) -> None:
    """Shared dispatch logic for both direct invocation and 'run' subcommand."""
    parsed = parse_intent(query)

    if not parsed.show.strip():
        print_error("抱歉，无法从输入中识别出影视名称")
        print_info("例如: movie-skill \"分步看权力的游戏\"")
        print_info("例如: movie-skill \"下载权力的游戏\"")
        raise typer.Exit(code=1)

    kwargs: dict = {}
    if magnet_dir is not None:
        kwargs["magnet_dir"] = magnet_dir
    if download_state_dir is not None:
        kwargs["download_state_dir"] = download_state_dir

    # Determine mode
    effective_mode = mode
    if auto:
        effective_mode = "auto"
    elif parsed.mode != "auto":
        effective_mode = parsed.mode

    # Create interactor if step mode
    interactive = effective_mode == "step"
    if interactive:
        kwargs["interactor"] = ConsoleInteractor()

    orchestrator = PipelineOrchestrator(**kwargs)

    show_desc = parsed.show
    if parsed.season is not None or parsed.episode is not None:
        parts = [parsed.show]
        if parsed.season is not None:
            parts.append(f"第{parsed.season}季")
        if parsed.episode is not None:
            parts.append(f"第{parsed.episode}集")
        show_desc = " ".join(parts)

    if parsed.intent == IntentType.WATCH:
        print_info(f"准备观看: {show_desc}")
        success = orchestrator.execute_watch(
            parsed.show, parsed.season, parsed.episode, auto=auto,
        )
    elif parsed.intent == IntentType.DOWNLOAD:
        print_info(f"准备下载: {show_desc}")
        success = orchestrator.execute_download(
            parsed.show, parsed.season, parsed.episode, auto=auto,
        )
    elif parsed.intent == IntentType.LIST:
        if interactive:
            orchestrator.execute_list_playable()
        else:
            _show_media_list(kwargs.get("download_state_dir", ".download"))
        success = True
    elif parsed.intent == IntentType.PLAY:
        print_info(f"准备播放: {show_desc}")
        success = orchestrator.execute_play(
            parsed.show, parsed.season, parsed.episode,
        )
    else:
        print_error(f"Unknown intent: {parsed.intent}")
        raise typer.Exit(code=1)

    if not success:
        raise typer.Exit(code=1)


def _show_media_list(download_state_dir: str) -> None:
    """Display a table of downloaded media files (non-interactive)."""
    from movie_skill.downloader.thunder import get_thunder_download_dir, discover_completed_files
    from movie_skill.downloader.state import list_states
    from rich.table import Table as RichTable
    from rich.console import Console as RichConsole
    from movie_skill.skill.pipeline import _format_size

    watch_dir = get_thunder_download_dir()
    files = discover_completed_files(watch_dir)
    if not files:
        print_info("没有找到已下载的媒体文件")
        return

    states = list_states(state_dir=download_state_dir)
    state_by_path = {}
    for s in states:
        dp = getattr(s, "download_path", None)
        if dp:
            state_by_path[dp] = {"show": getattr(s, "show", None), "season": getattr(s, "season", None), "episode": getattr(s, "episode", None)}

    console = RichConsole()
    table = RichTable(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("剧名", max_width=30)
    table.add_column("集数", width=10)
    table.add_column("大小", width=10)
    table.add_column("文件名", max_width=50)

    for i, f in enumerate(files):
        fpath = str(f.get("path", ""))
        meta = state_by_path.get(fpath, {})
        show_n = meta.get("show") or "-"
        season_n = meta.get("season")
        episode_n = meta.get("episode")
        ep_str = f"S{season_n}E{episode_n}" if None not in (season_n, episode_n) else ("-" if season_n is None else f"S{season_n}")
        table.add_row(str(i + 1), show_n[:30], ep_str, _format_size(f.get("size_bytes")), fpath.rsplit("/", 1)[-1][:50])

    console.print(f"\n[bold]已下载资源 ({len(files)} 个):[/]\n")
    console.print(table)
    console.print()
    print_info("使用分步模式可选择并播放: movie-skill \"分步播放列表\"")


@app.command()
def run(
    query: str = typer.Argument(
        ...,
        help="Natural language query (e.g. '分步看权力的游戏')",
    ),
    auto: bool = typer.Option(
        False, "--auto",
        help="Fully automated pipeline (skip all prompts)",
    ),
    mode: str = typer.Option(
        "auto", "--mode",
        help="Execution mode: 'auto' (fully automated) or 'step' (confirm at each stage)",
    ),
    magnet_dir: Optional[str] = typer.Option(
        None, "--magnet-dir",
        help="Magnet file directory (default: .magnet/)",
    ),
    download_state_dir: Optional[str] = typer.Option(
        None, "--download-dir",
        help="Download state directory (default: .download/)",
    ),
):
    """Run the movie pipeline from a natural language query.

    Parses your query into an intent (watch/download/play) and show details,
    then runs the appropriate pipeline steps with status updates.

    Examples:
        movie-skill run "我想看权力的游戏第三季第五集"
        movie-skill run "自动下载权力的游戏"
        movie-skill run "分步看权力的游戏第三季第五集"
        movie-skill run "播放列表"
    """
    _handle_query(query, auto=auto, mode=mode, magnet_dir=magnet_dir, download_state_dir=download_state_dir)


@app.command()
def list(
    play: bool = typer.Option(
        False, "--play", "-p",
        help="After listing, select and play a file",
    ),
    download_state_dir: Optional[str] = typer.Option(
        None, "--download-dir",
        help="Download state directory (default: .download/)",
    ),
):
    """List all downloaded media files.

    Scans the Thunder download directory for completed video files
    and displays them with show name, season, episode, and file size.

    Examples:
        movie-skill list
        movie-skill list --play
    """
    kwargs = {}
    if download_state_dir is not None:
        kwargs["download_state_dir"] = download_state_dir

    interactor = ConsoleInteractor() if play else None
    kwargs["interactor"] = interactor

    orchestrator = PipelineOrchestrator(**kwargs)

    if play:
        orchestrator.execute_list_playable()
    else:
        # Just show the list without interactivity
        from movie_skill.downloader.thunder import get_thunder_download_dir, discover_completed_files
        from movie_skill.downloader.state import list_states
        from rich.table import Table
        from rich.console import Console

        watch_dir = get_thunder_download_dir()
        files = discover_completed_files(watch_dir)
        if not files:
            print_info("没有找到已下载的媒体文件")
            raise typer.Exit()

        states = list_states(state_dir=kwargs.get("download_state_dir", ".download"))
        state_by_path = {}
        for s in states:
            dp = getattr(s, "download_path", None)
            if dp:
                state_by_path[dp] = {
                    "show": getattr(s, "show", None),
                    "season": getattr(s, "season", None),
                    "episode": getattr(s, "episode", None),
                }

        console = Console()
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=4)
        table.add_column("剧名", max_width=30)
        table.add_column("集数", width=10)
        table.add_column("大小", width=10)
        table.add_column("文件名", max_width=50)

        for i, f in enumerate(files):
            fpath = str(f.get("path", ""))
            meta = state_by_path.get(fpath, {})
            show = meta.get("show") or "-"
            season = meta.get("season")
            episode = meta.get("episode")
            ep_str = ""
            if season is not None:
                ep_str += f"S{season}"
            if episode is not None:
                ep_str += f"E{episode}"
            if not ep_str:
                ep_str = "-"

            from movie_skill.skill.pipeline import _format_size
            size_str = _format_size(f.get("size_bytes"))
            name = fpath.rsplit("/", 1)[-1] if "/" in fpath else fpath

            table.add_row(str(i + 1), show[:30], ep_str, size_str, name[:50])

        console.print(f"\n[bold]已下载资源 ({len(files)} 个):[/]\n")
        console.print(table)
        console.print()

# Auto-route bare queries to "run" subcommand (runs at import time for entry point)
# movie-skill "分步看权力的游戏" → movie-skill run "分步看权力的游戏"
import sys as _sys
_sys_argv = _sys.argv[1:]
_KNOWN = {"run", "list", "--help", "--install-completion", "--show-completion", "-h"}
if _sys_argv and not _sys_argv[0].startswith("-") and _sys_argv[0] not in _KNOWN:
    _sys.argv.insert(1, "run")
