"""Magnet file scanner and state filter.

Reads .magnet/<btih>.json files produced by Phase 1 (Crawler) and
filters them against .download/ state files to determine which
magnets need processing.

Per ARCHITECTURE.md: The downloader scans .magnet/ for unprocessed
files, matching against .download/ state to skip duplicates.
This makes it crash-safe -- re-run and it picks up where it left off.
"""

import json
from pathlib import Path
from typing import Optional

from movie_skill.downloader.state import (
    DownloadState,
    list_states,
    read_state,
    DEFAULT_DOWNLOAD_DIR,
)

# Default magnet output directory (matches Phase 1 OUTPUT_DIR)
DEFAULT_MAGNET_DIR = ".magnet"


def scan_magnet_files(magnet_dir: str = DEFAULT_MAGNET_DIR) -> list[dict]:
    """Read all magnet records from .magnet/ directory.

    Supports two formats:
    - Schema v2: Single task file .magnet/{query}.json with 'results' array
    - Schema v1: Multiple .magnet/<btih>.json files, one per magnet

    Args:
        magnet_dir: Path to the .magnet/ directory (default: .magnet/).

    Returns:
        List of parsed magnet record dicts.
        Each dict has keys: magnet, title, size_bytes, source, btih,
        resolution, show, season, episode.
        Returns empty list if directory does not exist or no files found.
    """
    d = Path(magnet_dir)
    if not d.exists():
        return []

    records: list[dict] = []
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue

            # Schema v2: task-driven single file with results array
            if data.get("_schema_version") == 2 and "results" in data:
                query = data.get("query", "")
                season = data.get("season")
                episode = data.get("episode")
                for r in data["results"]:
                    records.append({
                        "magnet": r.get("magnet", ""),
                        "title": r.get("title", ""),
                        "size_bytes": r.get("size_bytes"),
                        "source": r.get("source", ""),
                        "btih": r.get("btih", ""),
                        "resolution": r.get("resolution", ""),
                        "show": query,
                        "season": season,
                        "episode": episode,
                    })
            else:
                # Schema v1: per-magnet file
                records.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return records


def filter_unprocessed(
    magnet_records: list[dict],
    state_dir: str = DEFAULT_DOWNLOAD_DIR,
) -> list[dict]:
    """Filter magnet records to exclude already-processed ones.

    A magnet is "processed" if a state file exists for its btih
    with status of DOWNLOADING, DONE, SEEDING, or FAILED.
    Magnets with PENDING or QUEUEING status are also returned
    (they may have been interrupted and need reprocessing).

    Args:
        magnet_records: List of magnet record dicts from scan_magnet_files().
        state_dir: Directory for download state files (default: .download/).

    Returns:
        List of magnet records that need processing.
    """
    if not magnet_records:
        return []

    state_dir_path = Path(state_dir)
    if not state_dir_path.exists():
        # No state directory yet -- all magnets are unprocessed
        return magnet_records

    # Build set of btihs that are in terminal/completing states
    skipped_states = {"downloading", "done", "seeding", "failed"}
    skip_btihs: set[str] = set()

    for p in sorted(state_dir_path.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            btih = data.get("btih", "")
            status = data.get("status", "")
            if btih and status in skipped_states:
                skip_btihs.add(btih)
        except (json.JSONDecodeError, OSError):
            continue

    if not skip_btihs:
        return magnet_records

    return [
        rec for rec in magnet_records
        if rec.get("btih", "") not in skip_btihs
    ]


def filter_by_show(
    magnet_records: list[dict],
    show: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> list[dict]:
    """Filter magnet records by show name, season, and/or episode.

    Performs case-insensitive matching of show name.
    If season is specified, only returns records matching that season.
    If episode is specified, only returns records matching that episode.

    Args:
        magnet_records: List of magnet record dicts from scan_magnet_files().
        show: Show name to filter by (case-insensitive).
        season: Optional season number to filter by.
        episode: Optional episode number to filter by.

    Returns:
        Filtered list of magnet records.
    """
    if not magnet_records:
        return []

    show_lower = show.lower()

    def _matches(rec: dict) -> bool:
        record_show = (rec.get("show") or "").lower()
        if show_lower not in record_show:
            return False
        if season is not None and rec.get("season") != season:
            return False
        if episode is not None and rec.get("episode") != episode:
            return False
        return True

    return [rec for rec in magnet_records if _matches(rec)]


def get_magnet_record_by_btih(
    magnet_records: list[dict],
    btih: str,
) -> Optional[dict]:
    """Find a magnet record by its btih.

    Args:
        magnet_records: List of magnet record dicts.
        btih: BitTorrent info hash to find.

    Returns:
        Matching record dict, or None if not found.
    """
    for rec in magnet_records:
        if rec.get("btih") == btih:
            return rec
    return None
