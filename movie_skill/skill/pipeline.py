"""Pipeline orchestrator for the movie-skill entry point.

Orchestrates the crawl-download-play pipeline with per-step status reporting.
Each pipeline stage handles its own errors cleanly (catch, report, return
failure) — exceptions do not propagate to the caller.

The three entry points mirror the three main use cases:
    - execute_watch:  search → download → play (full pipeline)
    - execute_download:  search → download
    - execute_play:  play only
"""

import asyncio
from typing import Optional

from rich.console import Console

from movie_skill.engine import CrawlerEngine
from movie_skill.output.json_writer import write_magnet_files, write_search_result, clean_magnet_dir
from movie_skill.output.schema import SearchResult, MagnetResult
from movie_skill.output.terminal import print_info, print_error, print_warning
from movie_skill.downloader.queue import DownloadQueue
from movie_skill.downloader.thunder import get_thunder_download_dir, discover_completed_files
from movie_skill.downloader.state import list_states, DownloadStatus
from movie_skill.player.scanner import scan_media_file, check_download_status
from movie_skill.player.player import play_best
from movie_skill.skill.interactor import ConsoleInteractor

console = Console()

# Status messages in Chinese for user-facing output
_SEARCHING_MSG = "正在搜索..."
_SEARCH_FOUND_MSG = "找到 {} 个结果"
_SEARCH_EMPTY_MSG = "未找到相关资源"
_DOWNLOAD_START_MSG = "开始下载..."
_DOWNLOAD_DONE_MSG = "下载完成"
_DOWNLOAD_FAILED_MSG = "下载失败"
_DOWNLOAD_NO_MAGNET_MSG = "没有可下载的磁力链接"
_PLAY_READY_MSG = "准备播放!"
_PLAY_FILE_NOT_FOUND_MSG = "未找到已下载的文件"
_PLAY_CORRUPT_WARNING_MSG = "文件可能已损坏，仍尝试播放"
_PLAY_PROGRESS_MSG = "正在使用 {} 播放"
_DIVIDER = "[bold]---[/]"


class PipelineOrchestrator:
    """Orchestrates the crawl-download-play pipeline with status reporting.

    Each pipeline stage (search, download, play) is a separate method.
    The execute_* methods chain stages together with failure-aware logic:
    if any stage fails, subsequent stages are skipped.
    """

    def __init__(
        self,
        magnet_dir: str = ".magnet",
        download_state_dir: str = ".download",
        thunder_dir: Optional[str] = None,
        interactor: Optional[ConsoleInteractor] = None,
    ):
        """Initialize the pipeline orchestrator.

        Args:
            magnet_dir: Directory for crawler magnet output files.
            download_state_dir: Directory for download state files.
            thunder_dir: Thunder download directory (auto-detected if None).
            interactor: Optional interactor for step-by-step mode.
                        None means fully automatic (backward compatible).
        """
        self.magnet_dir = magnet_dir
        self.download_state_dir = download_state_dir
        self.thunder_dir = thunder_dir
        self.interactor = interactor

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _show_desc(show: str, season: Optional[int], episode: Optional[int]) -> str:
        """Build human-readable show description."""
        parts = []
        if season is not None:
            parts.append(f"第{season}季")
        if episode is not None:
            parts.append(f"第{episode}集")
        if parts:
            return f"{show} {' '.join(parts)}"
        return show

    def _write_selected_magnets(
        self, result: SearchResult, indices: list[int]
    ) -> None:
        """Write only selected magnet results to .magnet/ directory."""
        selected = [result.results[i] for i in indices if i < len(result.results)]
        if selected:
            write_search_result(
                SearchResult(
                    query=result.query,
                    season=result.season,
                    episode=result.episode,
                    results=selected,
                    total=len(selected),
                ),
                output_dir=self.magnet_dir,
            )

    # ------------------------------------------------------------------
    # Internal pipeline stages
    # ------------------------------------------------------------------

    def _search(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> Optional[SearchResult]:
        """Search for magnets using CrawlerEngine.

        Args:
            show: Show name to search for.
            season: Optional season number.
            episode: Optional episode number.

        Returns:
            SearchResult on success, None on failure.
        """
        try:
            # Build status message with optional season/episode
            search_label = show
            parts = []
            if season is not None:
                parts.append(f"第{season}季")
            if episode is not None:
                parts.append(f"第{episode}集")
            if parts:
                search_label = f"{show} {' '.join(parts)}"

            print_info(f"{_SEARCHING_MSG} {search_label}")

            # Clean previous search results before new search
            clean_magnet_dir(self.magnet_dir)

            engine = CrawlerEngine()
            result = asyncio.run(engine.search(show, season, episode))

            if result.total == 0:
                for err in result.errors:
                    print_error(err)
                print_info(_SEARCH_EMPTY_MSG)
                return None

            best = result.best()
            if best:
                size_str = _format_size(best.size_bytes)
                print_info(
                    _SEARCH_FOUND_MSG.format(result.total)
                )
                console.print(f"  最佳结果: [bold]{best.title}[/]")
                console.print(f"  清晰度: {best.resolution}  大小: {size_str}")
            else:
                print_info(_SEARCH_FOUND_MSG.format(result.total))

            return result

        except Exception as e:
            print_error(f"搜索失败: {e}")
            return None

    def _download(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        wait: bool = True,
    ) -> bool:
        """Download magnets using DownloadQueue.

        Args:
            show: Show name to filter by.
            season: Optional season number.
            episode: Optional episode number.
            wait: If True, wait for download completion.

        Returns:
            True if download succeeded, False otherwise.
        """
        try:
            print_info(_DOWNLOAD_START_MSG)

            queue = DownloadQueue(
                magnet_dir=self.magnet_dir,
                state_dir=self.download_state_dir,
                thunder_dir=self.thunder_dir,
            )
            results = queue.run(
                show=show,
                season=season,
                episode=episode,
                wait=wait,
                max_results=1,
            )

            if not results:
                print_info(_DOWNLOAD_NO_MAGNET_MSG)
                return False

            # Check results for success/failure
            all_failed = True
            for state in results:
                if state.status.value == "done":
                    print_info(_DOWNLOAD_DONE_MSG)
                    return True
                if state.status.value == "failed":
                    error_msg = getattr(state, "error", None)
                    if error_msg:
                        print_error(f"{_DOWNLOAD_FAILED_MSG}: {error_msg}")

            if all_failed:
                print_error(_DOWNLOAD_FAILED_MSG)
                return False

            return True

        except Exception as e:
            print_error(f"下载出错: {e}")
            return False

    def _play(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> bool:
        """Scan for media file and play it.

        Args:
            show: Show name to scan for.
            season: Optional season number.
            episode: Optional episode number.

        Returns:
            True if playback started successfully, False otherwise.
        """
        try:
            print_info(_PLAY_READY_MSG)

            scan_result = scan_media_file(show, season=season, episode=episode)

            if not scan_result["found"]:
                # Check download status for a better error message
                dl_state = check_download_status(
                    show, season=season, episode=episode,
                    state_dir=self.download_state_dir,
                )
                if dl_state is not None:
                    print_error(
                        f"{_PLAY_FILE_NOT_FOUND_MSG} (下载状态: {dl_state.status.value})"
                    )
                else:
                    print_error(_PLAY_FILE_NOT_FOUND_MSG)
                return False

            file_path = scan_result["file_path"]
            if not scan_result["valid"]:
                print_warning(_PLAY_CORRUPT_WARNING_MSG)

            if not file_path:
                print_error(_PLAY_FILE_NOT_FOUND_MSG)
                return False

            player_name, process = play_best(
                file_path=file_path, start_position=0.0, fullscreen=True
            )
            print_info(_PLAY_PROGRESS_MSG.format(player_name))

            # Block until player exits
            process.wait()
            return True

        except Exception as e:
            print_error(f"播放出错: {e}")
            return False

    # ------------------------------------------------------------------
    # Public pipeline entry points
    # ------------------------------------------------------------------

    def execute_watch(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        auto: bool = False,
    ) -> bool:
        """Full pipeline: search → download → play.

        Args:
            show: Show name.
            season: Optional season number.
            episode: Optional episode number.
            auto: If True (or interactor absent), run fully automatic.
                  If False and interactor present, run step-by-step.

        Returns:
            True if all pipeline stages succeed, False otherwise.
        """
        interactor = self.interactor
        show_desc = self._show_desc(show, season, episode)

        # Determine mode
        mode = "auto"
        if interactor is not None and not auto:
            mode = interactor.ask_mode()

        # --- Full auto path ---
        if mode == "auto":
            return self._execute_watch_auto(show, season, episode)

        # --- Step-by-step path ---
        # Step 1: Search
        console.print(_DIVIDER)
        result = self._search(show, season, episode)
        if result is None:
            print_error("搜索阶段失败，流程已停止")
            return False

        # Step 1b: User selects results
        selected = interactor.select_results(result)
        if selected is None or len(selected) == 0:
            print_info("已跳过下载")
            return False

        self._write_selected_magnets(result, selected)

        # Step 2: Download
        console.print(_DIVIDER)
        if not self._download(show, season, episode):
            print_error("下载阶段失败，流程已停止")
            return False

        # Step 2b: Ask user whether to play
        if not interactor.confirm_after_download(show_desc):
            print_info("跳过播放，流程完成")
            console.print(_DIVIDER)
            return True

        # Step 3: Play with confirmation
        console.print(_DIVIDER)
        scan_result = scan_media_file(show, season=season, episode=episode)
        if not scan_result["found"] or not scan_result["file_path"]:
            print_error(_PLAY_FILE_NOT_FOUND_MSG)
            return False

        if not interactor.confirm_before_play(show_desc, scan_result["file_path"]):
            print_info("已取消播放")
            return True

        return self._play(show, season, episode)

    def _execute_watch_auto(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> bool:
        """Full-auto pipeline: search → download → play (no user interaction)."""
        # Step 1: Search + write all magnets
        console.print(_DIVIDER)
        result = self._search(show, season, episode)
        if result is None:
            print_error("搜索阶段失败，流程已停止")
            return False

        write_search_result(result, output_dir=self.magnet_dir)

        # Step 2: Download
        console.print(_DIVIDER)
        if not self._download(show, season, episode):
            print_error("下载阶段失败，流程已停止")
            return False

        # Step 3: Play
        console.print(_DIVIDER)
        if not self._play(show, season, episode):
            print_error("播放阶段失败，流程已停止")
            return False

        console.print(_DIVIDER)
        print_info("全部完成!")
        return True

    def execute_download(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        auto: bool = False,
    ) -> bool:
        """Search and download only (no playback).

        Args:
            show: Show name.
            season: Optional season number.
            episode: Optional episode number.
            auto: If True, skip interaction.

        Returns:
            True if all stages succeed, False otherwise.
        """
        console.print(_DIVIDER)
        result = self._search(show, season, episode)
        if result is None:
            print_error("搜索阶段失败，流程已停止")
            return False

        # Write all magnets for download
        write_search_result(result, output_dir=self.magnet_dir)

        console.print(_DIVIDER)
        if not self._download(show, season, episode):
            print_error("下载阶段失败，流程已停止")
            return False

        console.print(_DIVIDER)
        print_info("下载任务完成!")
        return True

    def execute_play(
        self,
        show: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> bool:
        """Play only (assumes content already downloaded).

        Args:
            show: Show name.
            season: Optional season number.
            episode: Optional episode number.

        Returns:
            True if playback succeeds, False otherwise.
        """
        console.print(_DIVIDER)
        result = self._play(show, season, episode)
        if not result:
            print_error("播放失败")
            return False

        return True

    def execute_list_playable(self) -> bool:
        """Scan downloaded media and let user pick one to play.

        Shows a table of all completed downloads with show name,
        season/episode info, and file sizes. User selects one to play.

        Requires an interactor to be set.

        Returns:
            True if a file was selected and played, False otherwise.
        """
        if self.interactor is None:
            print_error("播放列表模式需要交互器，请使用 --mode step")
            return False

        # Scan Thunder download directory
        watch_dir = get_thunder_download_dir()
        files = discover_completed_files(watch_dir)
        if not files:
            print_info("没有找到已下载的媒体文件")
            return False

        # Enrich with download state metadata
        states = list_states(state_dir=self.download_state_dir)
        state_by_path: dict[str, dict] = {}
        for s in states:
            dp = getattr(s, "download_path", None)
            if dp:
                state_by_path[dp] = {
                    "show": getattr(s, "show", None),
                    "season": getattr(s, "season", None),
                    "episode": getattr(s, "episode", None),
                    "status": getattr(s, "status", None),
                }

        media_list: list[dict] = []
        for f in files:
            fpath = str(f.get("path", ""))
            meta = state_by_path.get(fpath, {})
            entry = {
                "path": fpath,
                "name": fpath.rsplit("/", 1)[-1] if "/" in fpath else fpath,
                "size_bytes": f.get("size_bytes"),
                "show": meta.get("show"),
                "season": meta.get("season"),
                "episode": meta.get("episode"),
            }
            media_list.append(entry)

        # Let user pick
        selected_idx = self.interactor.select_playable(media_list)
        if selected_idx is None:
            return False

        entry = media_list[selected_idx]
        file_path = entry["path"]
        show_desc = self._show_desc(
            entry.get("show") or entry["name"],
            entry.get("season"),
            entry.get("episode"),
        )

        # Confirm then play
        if not self.interactor.confirm_before_play(show_desc, file_path):
            return False

        try:
            _, process = play_best(file_path=file_path, start_position=0.0, fullscreen=True)
            process.wait()
            return True
        except Exception as e:
            print_error(f"播放出错: {e}")
            return False


def _format_size(size_bytes: Optional[int]) -> str:
    """Format bytes to human-readable size string."""
    if size_bytes is None:
        return "N/A"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
