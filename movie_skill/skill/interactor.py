"""Console-based interaction backend for the Movie SKILL pipeline.

Works with both Claude Code and OpenClaw subprocess environments:
both forward stdin/stdout to the child process automatically.
"""

from typing import Optional
from rich.console import Console
from rich.table import Table

from movie_skill.output.schema import SearchResult
from movie_skill.output.terminal import print_info

console = Console()


class ConsoleInteractor:
    """Prompt user for decisions at each pipeline stage via stdin/stdout.

    Claude Code and OpenClaw both run skills as subprocesses,
    so input() / print() work naturally in both environments.
    """

    def ask_mode(self) -> str:
        """Ask user whether to run full-auto or step-by-step.

        Returns:
            "auto" or "step"
        """
        console.print()
        console.print("[bold]选择执行模式:[/]")
        console.print("  [1] 全流程自动（搜索 → 下载 → 播放）")
        console.print("  [2] 分步确认（每阶段手动确认）")
        console.print()
        while True:
            try:
                choice = input("请输入 (1/2，默认为2): ").strip()
                if choice == "1":
                    return "auto"
                if choice in ("", "2"):
                    return "step"
                print("请输入 1 或 2")
            except (EOFError, KeyboardInterrupt):
                return "auto"

    def select_results(self, result: SearchResult) -> Optional[list[int]]:
        """Show search results and let user pick which to download.

        Args:
            result: SearchResult from the crawler.

        Returns:
            List of selected 0-based indices, or None to cancel.
        """
        results = result.results
        if not results:
            print_info("没有找到任何结果")
            return None

        console.print()
        console.print(f"[bold]找到 {len(results)} 个资源:[/]")
        console.print()

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=4)
        table.add_column("标题", max_width=60)
        table.add_column("大小", width=10)
        table.add_column("清晰度", width=8)
        table.add_column("来源", width=10)

        for i, r in enumerate(results):
            size_str = self._format_size(r.size_bytes)
            table.add_row(
                str(i + 1),
                r.title[:60] if r.title else "N/A",
                size_str,
                r.resolution or "N/A",
                r.source or "N/A",
            )

        console.print(table)
        console.print()
        console.print("输入序号下载（如 '1' 或 '1,3'），输入 'all' 全部，'none' 跳过")
        console.print()

        while True:
            try:
                choice = input("选择资源: ").strip().lower()
                if choice == "none" or choice == "":
                    return None
                if choice == "all":
                    return list(range(len(results)))
                indices = []
                for part in choice.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(results):
                            indices.append(idx)
                if indices:
                    return indices
                print(f"请输入有效序号 (1-{len(results)})")
            except (EOFError, KeyboardInterrupt):
                return None

    def confirm_after_download(self, show_desc: str) -> bool:
        """Ask whether to proceed to playback after download completes.

        Args:
            show_desc: Human-readable show description.

        Returns:
            True to play, False to stop.
        """
        console.print()
        console.print(f"[bold]下载完成: {show_desc}[/]")
        while True:
            try:
                choice = input("是否播放? (y/n，默认y): ").strip().lower()
                if choice in ("y", "yes", ""):
                    return True
                if choice in ("n", "no"):
                    return False
                print("请输入 y 或 n")
            except (EOFError, KeyboardInterrupt):
                return True

    def confirm_before_play(self, show_desc: str, file_path: str) -> bool:
        """Show what will be played and confirm before launching player.

        Args:
            show_desc: Human-readable show description.
            file_path: Full path to the media file.

        Returns:
            True to play, False to cancel.
        """
        console.print()
        console.print(f"[bold]即将播放: {show_desc}[/]")
        console.print(f"  文件: {file_path}")
        while True:
            try:
                choice = input("确认播放? (y/n，默认y): ").strip().lower()
                if choice in ("y", "yes", ""):
                    return True
                if choice in ("n", "no"):
                    return False
                print("请输入 y 或 n")
            except (EOFError, KeyboardInterrupt):
                return True

    def select_playable(self, media_list: list[dict]) -> Optional[int]:
        """Show downloaded media files and let user pick one to play.

        Args:
            media_list: List of dicts with keys:
                path, name, size_bytes, show, season, episode

        Returns:
            Selected 0-based index, or None to cancel.
        """
        if not media_list:
            print_info("没有找到已下载的媒体文件")
            return None

        console.print()
        console.print(f"[bold]可播放资源 ({len(media_list)} 个):[/]")
        console.print()

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=4)
        table.add_column("剧名", max_width=30)
        table.add_column("集数", width=10)
        table.add_column("大小", width=10)
        table.add_column("文件名", max_width=40)

        for i, m in enumerate(media_list):
            season = m.get("season")
            episode = m.get("episode")
            ep_str = ""
            if season is not None:
                ep_str += f"S{season}"
            if episode is not None:
                ep_str += f"E{episode}"
            if not ep_str:
                ep_str = "-"

            size_str = self._format_size(m.get("size_bytes"))
            name = m.get("name") or m.get("path", "")
            show = m.get("show") or "-"

            table.add_row(str(i + 1), show[:30], ep_str, size_str, name[:40])

        console.print(table)
        console.print()
        console.print("输入序号播放，或直接回车跳过")
        console.print()

        while True:
            try:
                choice = input("选择资源: ").strip()
                if choice == "":
                    return None
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(media_list):
                        return idx
                print(f"请输入有效序号 (1-{len(media_list)})")
            except (EOFError, KeyboardInterrupt):
                return None

    @staticmethod
    def _format_size(size_bytes: Optional[int]) -> str:
        if size_bytes is None:
            return "N/A"
        size = float(size_bytes)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
