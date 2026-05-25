"""Download state types and state file I/O.

Defines the DownloadStatus enum and DownloadState Pydantic model
used throughout Phase 2 for tracking per-magnet download lifecycle.

State files are written to .download/<btih>.json with atomic write
pattern (.tmp rename) per the project convention.
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class DownloadStatus(str, Enum):
    """Download lifecycle states.

    pending:     Not yet processed (new magnet found in .magnet/)
    queueing:    Being opened in Thunder
    downloading: Thunder is actively downloading
    seeding:     Download complete, still seeding
    done:        File found in download directory, verified stable
    failed:      Timed out, no peers, or other non-recoverable error
    """
    PENDING = "pending"
    QUEUEING = "queueing"
    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    DONE = "done"
    FAILED = "failed"


# Default state directory
DEFAULT_DOWNLOAD_DIR = ".download"

# Schema version for forward compatibility
_SCHEMA_VERSION = 1


class DownloadState(BaseModel):
    """Per-magnet download state persisted to .download/<btih>.json.

    This is the source of truth for download progress. On restart,
    the downloader reconciles stored state against filesystem reality.
    """
    schema_version: int = Field(
        default=_SCHEMA_VERSION,
        description="Schema version for forward compatibility",
    )
    btih: str = Field(..., description="BitTorrent info hash")
    magnet_uri: str = Field(..., description="Full magnet URI")
    title: str = Field(..., description="Torrent title")
    status: DownloadStatus = Field(
        default=DownloadStatus.PENDING,
        description="Current download status",
    )
    show: str = Field("", description="Normalized show name")
    season: Optional[int] = Field(None, description="Season number")
    episode: Optional[int] = Field(None, description="Episode number")
    source: str = Field("", description="Source site name")
    resolution: str = Field("unknown", description="Resolution label")
    size_bytes: Optional[int] = Field(None, description="Expected file size in bytes")
    download_path: Optional[str] = Field(None, description="Path to completed file on disk")
    error: Optional[str] = Field(None, description="Error message if status is failed")
    started_at: Optional[str] = Field(None, description="ISO 8601 timestamp when download started")
    completed_at: Optional[str] = Field(None, description="ISO 8601 timestamp when download completed")
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of last update",
    )


def state_path(btih: str, state_dir: str = DEFAULT_DOWNLOAD_DIR) -> Path:
    """Get the path to a specific download state file."""
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{btih}.json"


def write_state(state: DownloadState, state_dir: str = DEFAULT_DOWNLOAD_DIR) -> Path:
    """Write a DownloadState to disk atomically.

    Uses .tmp rename pattern per project convention (see output/json_writer.py).
    Ensures partial writes are never visible to readers.

    Args:
        state: DownloadState instance to persist.
        state_dir: Directory for state files (default: .download/).

    Returns:
        Path to the written state file.
    """
    file_path = state_path(state.btih, state_dir)
    tmp_path = file_path.with_suffix(".json.tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2, exclude_none=True))
        os.replace(tmp_path, file_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return file_path


def read_state(btih: str, state_dir: str = DEFAULT_DOWNLOAD_DIR) -> Optional[DownloadState]:
    """Read a single DownloadState from disk.

    Args:
        btih: BitTorrent info hash identifying the download.
        state_dir: Directory for state files (default: .download/).

    Returns:
        DownloadState if file exists and is valid, None otherwise.
    """
    file_path = state_path(btih, state_dir)
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DownloadState(**data)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return None


def list_states(state_dir: str = DEFAULT_DOWNLOAD_DIR) -> list[DownloadState]:
    """Read all download state files from the state directory.

    Args:
        state_dir: Directory for state files (default: .download/).

    Returns:
        List of valid DownloadState objects. Silently skips corrupt files.
    """
    d = Path(state_dir)
    if not d.exists():
        return []

    states: list[DownloadState] = []
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            states.append(DownloadState(**data))
        except (json.JSONDecodeError, Exception):
            continue
    return states


def delete_state(btih: str, state_dir: str = DEFAULT_DOWNLOAD_DIR) -> bool:
    """Delete a download state file.

    Returns True if file existed and was deleted, False otherwise.
    """
    file_path = state_path(btih, state_dir)
    if file_path.exists():
        file_path.unlink()
        return True
    return False
