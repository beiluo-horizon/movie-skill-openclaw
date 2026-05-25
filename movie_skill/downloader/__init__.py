"""Downloader subpackage -- Thunder download management.

Reads .magnet/*.json files from Phase 1 (Crawler), invokes macOS
Thunder client to download, manages download queue, tracks state
via .download/<btih>.json files.
"""

from .state import (
    DownloadStatus,
    DownloadState,
    write_state,
    read_state,
    list_states,
    delete_state,
    DEFAULT_DOWNLOAD_DIR,
)
from .queue import DownloadQueue
from .scanner import scan_magnet_files, filter_unprocessed, filter_by_show

__all__ = [
    "DownloadStatus",
    "DownloadState",
    "write_state",
    "read_state",
    "list_states",
    "delete_state",
    "DEFAULT_DOWNLOAD_DIR",
    "DownloadQueue",
    "scan_magnet_files",
    "filter_unprocessed",
    "filter_by_show",
]
