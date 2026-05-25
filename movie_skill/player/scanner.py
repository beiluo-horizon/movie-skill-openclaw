"""Media file scanning and ffprobe validation for the player pipeline.

Provides functions for:
- Detecting ffprobe availability on the system
- Probing media files with ffprobe to extract format/stream metadata
- Validating media files (checks for video stream, non-zero duration)
- Scanning the download directory for matching media files
- Checking download status from .download/ state files
- Generating human-readable status messages

Integrates with the downloader's thunder module (find_matching_file) and
state module (list_states) to provide end-to-end media file discovery.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from movie_skill.downloader.state import (
    DownloadState,
    DownloadStatus,
    list_states,
)
from movie_skill.downloader.thunder import (
    find_matching_file,
    get_thunder_download_dir,
)


def ffprobe_available() -> bool:
    """Check if ffprobe is available on the system PATH.

    Returns:
        True if ffprobe binary is found via shutil.which(), False otherwise.
    """
    return shutil.which("ffprobe") is not None


def probe_media(file_path: str) -> Optional[dict]:
    """Run ffprobe on a media file and return parsed JSON output.

    Executes:
        ffprobe -v quiet -print_format json -show_format -show_streams <file_path>

    Uses list-style subprocess args (never shell=True). Returns the parsed
    JSON dict on success, None on any error (ffprobe not found, timeout,
    invalid JSON output).

    Args:
        file_path: Absolute path to the media file to probe.

    Returns:
        Parsed ffprobe JSON dict, or None if probing failed.
    """
    if not ffprobe_available():
        return None

    try:
        result = subprocess.run(
            [
                shutil.which("ffprobe"),
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def validate_media_file(file_path: str) -> tuple[bool, dict]:
    """Validate a media file using ffprobe.

    Checks that the file contains at least one video stream and has a
    non-zero duration. Handles missing ffprobe gracefully (returns
    (False, error_dict), does not crash).

    Args:
        file_path: Absolute path to the media file to validate.

    Returns:
        Tuple of (is_valid: bool, info_or_error: dict).
        On success: (True, {"duration_seconds": float, "size_bytes": int,
                           "has_video": bool, "stream_count": int})
        On failure: (False, {"error": str, ...})
    """
    probe_result = probe_media(file_path)

    if probe_result is None:
        return (False, {"error": "ffprobe failed or unavailable"})

    fmt = probe_result.get("format", {})
    streams = probe_result.get("streams", [])
    stream_count = len(streams)

    # Check duration
    duration_str = fmt.get("duration", "0")
    try:
        duration_seconds = float(duration_str)
    except (ValueError, TypeError):
        duration_seconds = 0.0

    # Check for video stream
    has_video = any(
        s.get("codec_type") == "video" for s in streams
    )

    # Parse size
    size_str = fmt.get("size", "0")
    try:
        size_bytes = int(size_str)
    except (ValueError, TypeError):
        size_bytes = 0

    info = {
        "duration_seconds": duration_seconds,
        "size_bytes": size_bytes,
        "has_video": has_video,
        "stream_count": stream_count,
    }

    if not has_video:
        info["error"] = "No video stream found in media file"
        return (False, info)

    if duration_seconds <= 0:
        info["error"] = "Media file has zero or negative duration"
        return (False, info)

    return (True, info)


def scan_media_file(
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    download_dir: Optional[str] = None,
) -> dict:
    """Scan the download directory for a media file matching show/season/episode.

    Uses find_matching_file from the downloader module to locate files,
    then validates found files with ffprobe.

    Args:
        show: Show name to search for (case-insensitive matching).
        season: Optional season number.
        episode: Optional episode number.
        download_dir: Directory to scan. If None, uses get_thunder_download_dir().

    Returns:
        Dict with keys:
            found (bool): Whether a matching file was found.
            file_path (str|None): Absolute path to the matching file, or None.
            valid (bool): Whether the file passed ffprobe validation.
            info (dict|None): Validation info dict, or None if not found.
            error (str|None): Error message, or None on success.
    """
    if download_dir is not None:
        watch_dir = Path(download_dir)
    else:
        watch_dir = get_thunder_download_dir()

    matched = find_matching_file(watch_dir, show, season, episode)

    if matched is None:
        return {
            "found": False,
            "file_path": None,
            "valid": False,
            "info": None,
            "error": "No matching file found in download directory",
        }

    file_path = str(matched.resolve())
    is_valid, info = validate_media_file(file_path)

    return {
        "found": True,
        "file_path": file_path,
        "valid": is_valid,
        "info": info if is_valid else info,
        "error": None,
    }


def check_download_status(
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    state_dir: str = ".download",
) -> Optional[DownloadState]:
    """Check .download/ state files for a matching download.

    Queries download state files to determine if a matching show/episode
    has been or is being downloaded. Useful for providing meaningful
    status messages when the media file is not found on disk.

    Args:
        show: Show name to match (case-insensitive).
        season: Optional season number to match.
        episode: Optional episode number to match.
        state_dir: Directory for download state files (default: .download/).

    Returns:
        First matching DownloadState, or None if no match found.
    """
    states = list_states(state_dir=state_dir)
    show_lower = show.lower()

    for state in states:
        if state.show.lower() != show_lower:
            continue
        if season is not None and state.season != season:
            continue
        if episode is not None and state.episode != episode:
            continue
        return state

    return None


def get_player_status_message(
    scan_result: dict,
    download_state: Optional[DownloadState],
) -> str:
    """Generate a human-readable status message based on scan and download state.

    Provides Chinese-friendly messages for all pipeline states:
    file found/valid, file corrupt, still downloading, waiting, missing, failed.

    Args:
        scan_result: Dict from scan_media_file().
        download_state: Optional DownloadState from check_download_status().

    Returns:
        Human-readable status message string.
    """
    if scan_result["found"]:
        if scan_result["valid"]:
            return "Ready to play"
        else:
            return "File is corrupt or incomplete"

    # File not found -- check download state
    if download_state is None:
        return "File not found. Run movie-crawl first, then movie-dl"

    status = download_state.status

    if status == DownloadStatus.DOWNLOADING:
        return f"Still downloading (status: downloading)"
    elif status == DownloadStatus.QUEUEING:
        return "Waiting to download"
    elif status == DownloadStatus.PENDING:
        return "Not yet downloaded"
    elif status == DownloadStatus.FAILED:
        return "Download failed"
    elif status == DownloadStatus.DONE:
        return "Download marked done but file not found (may have been moved)"
    elif status == DownloadStatus.SEEDING:
        return "Download complete but file not found (may have been moved)"

    return f"Status: {status.value}"
