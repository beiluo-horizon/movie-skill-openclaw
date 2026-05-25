"""Download queue manager.

Manages the lifecycle of magnet downloads through macOS Thunder.
Processes magnets sequentially (one by default), tracking state
through the machine: pending -> queueing -> downloading -> done/failed.

Per ARCHITECTURE.md state machine:
    pending -> queueing -> downloading -> seeding -> done
                                    -> failed

Features:
- Sequential processing (max 1 concurrent by default)
- Per-magnet state tracking via .download/<btih>.json
- caffeinate lifecycle management (start/stop around active downloads)
- Timeout detection for dead/timed-out magnets
- Crash-resilient: re-run picks up where it left off
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from movie_skill.downloader.state import (
    DownloadStatus,
    DownloadState,
    write_state,
    read_state,
    DEFAULT_DOWNLOAD_DIR,
)
from movie_skill.downloader.thunder import (
    open_in_thunder,
    start_caffeinate,
    stop_caffeinate,
    wait_for_completion,
    find_matching_file,
    get_thunder_download_dir,
)
from movie_skill.downloader.scanner import (
    scan_magnet_files,
    filter_unprocessed,
    filter_by_show,
)

# Default maximum concurrent downloads
MAX_CONCURRENT_DEFAULT = 1

# Default download timeout (seconds) -- 2 hours
DOWNLOAD_TIMEOUT_DEFAULT = 7200

# Default magnet directory (matches Phase 1 output)
MAGNET_DIR_DEFAULT = ".magnet"


class DownloadQueue:
    """Manages sequential download of magnets through Thunder.

    Usage:
        queue = DownloadQueue()
        results = queue.run(show="权力的游戏", season=3, episode=5, wait=True)
        for state in results:
            print(f"{state.btih}: {state.status.value}")
    """

    def __init__(
        self,
        magnet_dir: str = MAGNET_DIR_DEFAULT,
        state_dir: str = DEFAULT_DOWNLOAD_DIR,
        thunder_dir: Optional[str] = None,
        download_timeout: int = DOWNLOAD_TIMEOUT_DEFAULT,
        poll_interval: int = 15,
        stability_seconds: int = 30,
    ):
        """Initialize the download queue.

        Args:
            magnet_dir: Path to .magnet/ directory with crawler output.
            state_dir: Path to .download/ directory for state files.
            thunder_dir: Thunder download directory. Auto-detected if None.
            download_timeout: Max seconds to wait for each download.
            poll_interval: Seconds between completion polls.
            stability_seconds: Seconds for file size stability check.
        """
        self.magnet_dir = magnet_dir
        self.state_dir = state_dir
        self.thunder_dir = Path(thunder_dir) if thunder_dir else get_thunder_download_dir()
        self.download_timeout = download_timeout
        self.poll_interval = poll_interval
        self.stability_seconds = stability_seconds

    def process_magnet(self, magnet_record: dict, wait: bool = True) -> DownloadState:
        """Process a single magnet through its full lifecycle.

        State transitions:
            1. Create PENDING state, write to disk
            2. Start caffeinate (prevent sleep)
            3. Open magnet in Thunder (transition to QUEUEING)
            4. If open succeeded, transition to DOWNLOADING
            5. Poll download directory for completion
            6. If file found and stable -> DONE
            7. If timeout -> FAILED

        Args:
            magnet_record: Magnet record dict from scan_magnet_files().

        Returns:
            Final DownloadState (DONE or FAILED).
        """
        btih = magnet_record.get("btih", "")
        magnet_uri = magnet_record.get("magnet", "")
        title = magnet_record.get("title", "")
        show = magnet_record.get("show", "")
        season = magnet_record.get("season")
        episode = magnet_record.get("episode")
        source = magnet_record.get("source", "")
        resolution = magnet_record.get("resolution", "unknown")
        size_bytes = magnet_record.get("size_bytes")

        # Check existing state (for resume handling)
        existing = read_state(btih, state_dir=self.state_dir)
        if existing is not None and existing.status in (
            DownloadStatus.DOWNLOADING,
            DownloadStatus.QUEUEING,
        ):
            # Resume: check if file already exists
            matched = find_matching_file(
                self.thunder_dir, show, season, episode
            )
            if matched and matched.exists():
                existing.status = DownloadStatus.DONE
                existing.download_path = str(matched)
                existing.completed_at = datetime.now(timezone.utc).isoformat()
                write_state(existing, state_dir=self.state_dir)
                return existing

            # Reset to pending for reprocessing
            state = DownloadState(
                btih=btih,
                magnet_uri=magnet_uri,
                title=title,
                status=DownloadStatus.PENDING,
                show=show,
                season=season,
                episode=episode,
                source=source,
                resolution=resolution,
                size_bytes=size_bytes,
            )
        else:
            # Fresh state
            state = DownloadState(
                btih=btih,
                magnet_uri=magnet_uri,
                title=title,
                status=DownloadStatus.PENDING,
                show=show,
                season=season,
                episode=episode,
                source=source,
                resolution=resolution,
                size_bytes=size_bytes,
            )

        write_state(state, state_dir=self.state_dir)

        # Start caffeinate
        caff_proc = start_caffeinate()

        try:
            # Transition to QUEUEING
            state.status = DownloadStatus.QUEUEING
            state.started_at = datetime.now(timezone.utc).isoformat()
            state.updated_at = datetime.now(timezone.utc).isoformat()
            write_state(state, state_dir=self.state_dir)

            # Open magnet in Thunder
            opened = open_in_thunder(magnet_uri)

            if not opened:
                state.status = DownloadStatus.FAILED
                state.error = "Failed to open magnet in Thunder"
                state.updated_at = datetime.now(timezone.utc).isoformat()
                write_state(state, state_dir=self.state_dir)
                return state

            # Transition to DOWNLOADING
            state.status = DownloadStatus.DOWNLOADING
            state.updated_at = datetime.now(timezone.utc).isoformat()
            write_state(state, state_dir=self.state_dir)

            # Wait for completion (only if wait mode)
            if wait:
                completed_file = wait_for_completion(
                    watch_dir=self.thunder_dir,
                    show=show,
                    season=season,
                    episode=episode,
                    timeout=self.download_timeout,
                    poll_interval=self.poll_interval,
                    stability_seconds=self.stability_seconds,
                )

                if completed_file is not None:
                    state.status = DownloadStatus.DONE
                    state.download_path = str(completed_file)
                    state.completed_at = datetime.now(timezone.utc).isoformat()
                    state.updated_at = datetime.now(timezone.utc).isoformat()
                else:
                    state.status = DownloadStatus.FAILED
                    state.error = f"Download timed out after {self.download_timeout}s"
                    state.updated_at = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            state.status = DownloadStatus.FAILED
            state.error = f"Unexpected error: {e}"
            state.updated_at = datetime.now(timezone.utc).isoformat()
        finally:
            write_state(state, state_dir=self.state_dir)
            stop_caffeinate(caff_proc)

        return state

    def run(
        self,
        show: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        wait: bool = True,
        max_results: Optional[int] = None,
    ) -> list[DownloadState]:
        """Run the download queue: scan, filter, process.

        Args:
            show: Optional show name to filter by.
            season: Optional season number to filter by.
            episode: Optional episode number to filter by.
            wait: If True (default), process all magnets with --wait behavior.
                  If False, process only the first magnet and return.
            max_results: Optional max number of magnets to process.

        Returns:
            List of final DownloadState objects for processed magnets.
        """
        # 1. Scan all magnet files
        all_magnets = scan_magnet_files(self.magnet_dir)

        if not all_magnets:
            return []

        # 2. Filter out already-processed magnets
        unprocessed = filter_unprocessed(all_magnets, state_dir=self.state_dir)

        if not unprocessed:
            return []

        # 3. Filter by show/season/episode if provided
        if show:
            unprocessed = filter_by_show(unprocessed, show, season, episode)

        if not unprocessed:
            return []

        # 4. Apply max_results limit
        if max_results is not None and max_results > 0:
            unprocessed = unprocessed[:max_results]

        # 5. Process magnets sequentially
        results: list[DownloadState] = []
        for i, magnet in enumerate(unprocessed):
            final_state = self.process_magnet(magnet, wait=wait)
            results.append(final_state)

            # If not wait mode, only process the first magnet
            if not wait:
                break

        return results
