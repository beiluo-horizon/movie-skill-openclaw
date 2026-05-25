"""macOS Thunder client integration.

Provides functions for:
- Opening magnet URIs in Thunder via macOS protocol handler
- Preventing Mac mini sleep via caffeinate
- Polling Thunder's download directory for completion detection

Per ARCHITECTURE.md: Protocol handler (open "magnet:...") is the
primary approach. AppleScript GUI automation is the fallback.

Per PITFALLS.md: Completion detection uses stability polling (file
size unchanged over interval) -- no Thunder API dependency.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

# Common video file extensions Thunder may produce
SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".webm")

# Thunder temp file extensions (incomplete downloads)
THUNDER_TEMP_EXTENSIONS = (".td", ".xltd", ".part", ".bc!")

# Default Thunder download directory candidates (checked in order)
_DEFAULT_THUNDER_DIRS = [
    "~/Downloads/迅雷下载",
    "~/Downloads/ThunderDownload",
    "~/Downloads/Thunder",
    "~/Downloads",
]


def open_in_thunder(magnet_uri: str) -> bool:
    """Open a magnet URI in Thunder via macOS protocol handler.

    Calls `open "magnet:?xt=urn:btih:<hash>"` which invokes Thunder
    if it is registered as the magnet: protocol handler.

    Args:
        magnet_uri: Full magnet URI (e.g. "magnet:?xt=urn:btih:abc123").

    Returns:
        True if the `open` command succeeded (returncode 0).
    """
    try:
        result = subprocess.run(
            ["open", magnet_uri],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def start_caffeinate() -> Optional[subprocess.Popen]:
    """Start caffeinate to prevent Mac mini sleep during downloads.

    Uses -dimsu flags to prevent display sleep, idle sleep, and
    system sleep while the process lives.

    Returns:
        subprocess.Popen handle to the caffeinate process, or None if failed.
    """
    try:
        return subprocess.Popen(
            ["caffeinate", "-dimsu"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        return None


def stop_caffeinate(process: Optional[subprocess.Popen]) -> None:
    """Stop a running caffeinate process.

    First attempts graceful terminate(), then force kill after 2s timeout.

    Args:
        process: subprocess.Popen handle from start_caffeinate().
    """
    if process is None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    except ProcessLookupError:
        pass  # Already dead


def get_thunder_download_dir() -> Path:
    """Discover Thunder's download directory.

    Checks common paths in order and returns the first existing one.
    Falls back to ~/Downloads if none found.

    Returns:
        Path to the likely Thunder download directory.
    """
    for candidate in _DEFAULT_THUNDER_DIRS:
        p = Path(candidate).expanduser().resolve()
        if p.exists():
            return p
    return Path("~/Downloads").expanduser().resolve()


def is_download_stable(
    file_path: Path,
    stability_seconds: int = 30,
) -> bool:
    """Check if a file's size has stabilized (download likely complete).

    Compares file size at two points separated by stability_seconds.
    If the size is unchanged and the file is over 10MB, considers it stable.

    Args:
        file_path: Path to the video file to check.
        stability_seconds: Seconds to wait between size checks (default: 30).

    Returns:
        True if file exists, size unchanged, and > 10MB.
    """
    try:
        if not file_path.exists():
            return False

        size1 = file_path.stat().st_size
        if size1 < 10 * 1024 * 1024:  # Less than 10MB -- too small
            return False

        time.sleep(stability_seconds)

        if not file_path.exists():
            return False

        size2 = file_path.stat().st_size
        return size2 == size1
    except OSError:
        return False


def find_matching_file(
    watch_dir: Path,
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> Optional[Path]:
    """Find a video file in watch_dir matching show/season/episode.

    Performs case-insensitive matching of the show name against
    filenames and directory names. Scans recursively for video
    files with SUPPORTED_VIDEO_EXTENSIONS extensions.

    Args:
        watch_dir: Directory to scan for completed files.
        show: Show name to match (case-insensitive).
        season: Optional season number to match (e.g. S01, S1, 第1季).
        episode: Optional episode number to match (e.g. E01, E1, 第1集).

    Returns:
        Path to the first matching video file, or None if no match.
    """
    if not watch_dir.exists():
        return None

    show_lower = show.lower()

    for f in watch_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            continue

        # Check show name in file path
        path_str = str(f).lower()
        if show_lower not in path_str:
            continue

        # If season specified, check season match
        if season is not None:
            season_strs = [
                f"s{season:02d}",
                f"s{season}",
                f"season{season}",
                f"第{season}季",
            ]
            if not any(s in path_str for s in season_strs):
                # Also check parent directory
                parent_path = str(f.parent).lower()
                if not any(s in parent_path for s in season_strs):
                    continue

        # If episode specified, check episode match
        if episode is not None:
            episode_strs = [
                f"e{episode:02d}",
                f"e{episode}",
                f"episode{episode}",
                f"第{episode}集",
                f"ep{episode}",
            ]
            if not any(s in path_str for s in episode_strs):
                continue

        # Check if temp files exist (incomplete download)
        parent_dir = f.parent
        stem = f.stem
        has_temp = any(
            (parent_dir / f"{stem}{temp_ext}").exists()
            for temp_ext in THUNDER_TEMP_EXTENSIONS
        )
        if has_temp:
            continue  # Temp file still exists -- not complete

        return f

    return None


def discover_completed_files(watch_dir: Path) -> list[dict]:
    """Scan watch_dir for all completed video files.

    Returns metadata for each video file found (no show/season filtering).

    Returns:
        List of dicts with keys: path (str), size_bytes (int), modified_at (str).
    """
    if not watch_dir.exists():
        return []

    results: list[dict] = []
    for f in sorted(watch_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            continue

        results.append({
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "modified_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(f.stat().st_mtime)
            ),
        })

    return results


def wait_for_completion(
    watch_dir: Path,
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    timeout: int = 7200,
    poll_interval: int = 15,
    stability_seconds: int = 30,
) -> Optional[Path]:
    """Poll download directory until a matching file appears and stabilizes.

    Polls every poll_interval seconds. When a matching file is found,
    checks stability (size unchanged over stability_seconds).
    Returns the file path if stable, None if timeout reached.

    Args:
        watch_dir: Directory to poll for completed downloads.
        show: Show name to match.
        season: Optional season number.
        episode: Optional episode number.
        timeout: Maximum seconds to wait (default: 7200 = 2 hours).
        poll_interval: Seconds between polls (default: 15).
        stability_seconds: Seconds for stability check (default: 30).

    Returns:
        Path to completed file, or None if timed out.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        matched = find_matching_file(watch_dir, show, season, episode)
        if matched is not None and is_download_stable(matched, stability_seconds):
            return matched

        time.sleep(poll_interval)

    # Final check before giving up
    matched = find_matching_file(watch_dir, show, season, episode)
    if matched is not None and is_download_stable(matched, stability_seconds):
        return matched

    return None
