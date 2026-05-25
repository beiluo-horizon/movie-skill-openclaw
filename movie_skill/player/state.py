"""Player state types and state file I/O.

Defines the PlayState Pydantic model for tracking media playback position
per show/episode, with atomic state file I/O at .player/<show>.json.

State files track the last known playhead position so playback can resume
from where it left off. Follows the same atomic .tmp rename pattern as
the downloader state module (downloader/state.py).
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# Default state directory for player state files
DEFAULT_PLAYER_DIR = ".player"

# Schema version for forward compatibility
_SCHEMA_VERSION = 1


class PlayState(BaseModel):
    """Per-episode playback position state persisted to .player/<show>.json.

    Tracks the last known playhead position so playback can resume from
    where it left off. Written atomically via .tmp rename pattern.
    """
    schema_version: int = Field(
        default=_SCHEMA_VERSION,
        description="Schema version for forward compatibility",
    )
    show: str = Field(..., description="Normalized show name")
    season: Optional[int] = Field(None, description="Season number")
    episode: Optional[int] = Field(None, description="Episode number")
    file_path: str = Field(..., description="Absolute path to media file")
    position_seconds: float = Field(
        default=0.0,
        description="Last known playhead position in seconds",
    )
    duration_seconds: Optional[float] = Field(
        None,
        description="File duration in seconds (from ffprobe, None if unknown)",
    )
    played_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when playback occurred",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of last update",
    )


def _normalize_show_name(show: str) -> str:
    """Normalize a show name for use in file paths.

    Strips leading/trailing whitespace, replaces non-alphanumeric and
    non-Chinese characters with underscores. Chinese characters (Unicode
    range U+4E00-U+9FFF) are preserved.

    Args:
        show: Raw show name to normalize.

    Returns:
        Normalized show name safe for use in filenames.
    """
    normalized = show.strip()
    normalized = re.sub(r'[^\w一-鿿\s-]', '_', normalized)
    return normalized


def _state_path(
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    state_dir: str = DEFAULT_PLAYER_DIR,
) -> Path:
    """Get the path to a specific player state file.

    Constructs a file path based on the normalized show name and
    optional season/episode suffix. Creates the state directory if
    it does not exist.

    Args:
        show: Show name (will be normalized for filename).
        season: Optional season number for S{suffix}.
        episode: Optional episode number for E{suffix}.
        state_dir: Directory for state files (default: .player/).

    Returns:
        Path to the state file.
    """
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_show_name(show)
    filename = normalized

    if season is not None and episode is not None:
        filename = f"{normalized}_S{season}_E{episode}"
    elif season is not None:
        filename = f"{normalized}_S{season}"

    return d / f"{filename}.json"


def write_state(
    state: PlayState,
    state_dir: str = DEFAULT_PLAYER_DIR,
) -> Path:
    """Write a PlayState to disk atomically.

    Uses .tmp rename pattern to ensure partial writes are never visible
    to readers. Cleans up .tmp file on failure.

    Args:
        state: PlayState instance to persist.
        state_dir: Directory for state files (default: .player/).

    Returns:
        Path to the written state file.
    """
    file_path = _state_path(state.show, state.season, state.episode, state_dir)
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


def read_state(
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    state_dir: str = DEFAULT_PLAYER_DIR,
) -> Optional[PlayState]:
    """Read a single PlayState from disk.

    Args:
        show: Show name identifying the state.
        season: Optional season number.
        episode: Optional episode number.
        state_dir: Directory for state files (default: .player/).

    Returns:
        PlayState if file exists and is valid, None otherwise.
    """
    file_path = _state_path(show, season, episode, state_dir)
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PlayState(**data)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return None


def list_states(state_dir: str = DEFAULT_PLAYER_DIR) -> list[PlayState]:
    """Read all player state files from the state directory.

    Args:
        state_dir: Directory for state files (default: .player/).

    Returns:
        List of valid PlayState objects. Silently skips corrupt files.
    """
    d = Path(state_dir)
    if not d.exists():
        return []

    states: list[PlayState] = []
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            states.append(PlayState(**data))
        except (json.JSONDecodeError, Exception):
            continue
    return states


def delete_state(
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    state_dir: str = DEFAULT_PLAYER_DIR,
) -> bool:
    """Delete a player state file.

    Args:
        show: Show name identifying the state.
        season: Optional season number.
        episode: Optional episode number.
        state_dir: Directory for state files (default: .player/).

    Returns:
        True if file existed and was deleted, False otherwise.
    """
    file_path = _state_path(show, season, episode, state_dir)
    if file_path.exists():
        file_path.unlink()
        return True
    return False
