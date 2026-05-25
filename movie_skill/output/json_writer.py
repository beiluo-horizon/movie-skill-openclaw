"""Write magnet search results as a task-driven JSON file.

Each search produces ONE file: .magnet/{query}.json containing all results.
This enables the Downloader to process a single search task atomically.

Previous per-btih file format is kept as write_magnet_files() for backward compat.
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from movie_skill.output.schema import MagnetResult, SearchResult

OUTPUT_DIR = ".magnet"
_SCHEMA_VERSION = 2


def _ensure_output_dir(path: Optional[str] = None) -> Path:
    """Ensure the output directory exists, creating if needed.

    Args:
        path: Custom output path. Defaults to OUTPUT_DIR.

    Returns:
        Resolved Path to the output directory.
    """
    dir_path = Path(path or OUTPUT_DIR).resolve()
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _build_magnet_record(
    result: MagnetResult,
    query: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> dict:
    """Build a single magnet record dict for JSON serialization.

    Schema matches the ARCHITECTURE.md specification for .magnet/*.json
    files consumed by Phase 2 (Downloader).
    """
    return {
        "_schema_version": _SCHEMA_VERSION,
        "magnet": result.magnet_uri,
        "title": result.title,
        "size_bytes": result.size_bytes,
        "source": result.source,
        "btih": result.btih or "",
        "resolution": result.resolution,
        "scraped_at": result.scraped_at,
        "show": query,
        "season": season,
        "episode": episode,
    }


def clean_magnet_dir(output_dir: Optional[str] = None) -> int:
    """Remove all files from the magnet output directory.

    Args:
        output_dir: Directory to clean (default: .magnet/).

    Returns:
        Number of files removed.
    """
    dir_path = Path(output_dir or OUTPUT_DIR).resolve()
    if not dir_path.exists():
        return 0
    count = 0
    for f in dir_path.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
    return count


def _safe_filename(query: str) -> str:
    """Convert a search query to a safe filename."""
    safe = "".join(c for c in query if c.isalnum() or c in "._- ").strip()
    return safe[:60] if safe else "search"


def write_search_result(
    search_result: SearchResult,
    output_dir: Optional[str] = None,
) -> int:
    """Write ALL search results to a single task-driven JSON file.

    Produces .magnet/{query}.json with the full SearchResult,
    including all ranked, deduplicated magnet entries.

    Args:
        search_result: Aggregated search results.
        output_dir: Output directory (default: .magnet/).

    Returns:
        Number of results written (same as search_result.total).
    """
    dir_path = Path(output_dir or OUTPUT_DIR).resolve()
    dir_path.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(search_result.query)
    file_path = dir_path / f"{filename}.json"

    data = {
        "_schema_version": _SCHEMA_VERSION,
        "query": search_result.query,
        "season": search_result.season,
        "episode": search_result.episode,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "total": search_result.total,
        "results": [
            {
                "magnet": r.magnet_uri,
                "title": r.title,
                "size_bytes": r.size_bytes,
                "source": r.source,
                "btih": r.btih or "",
                "resolution": r.resolution,
                "scraped_at": r.scraped_at,
            }
            for r in search_result.results
        ],
    }

    tmp_path = dir_path / f"{filename}.json.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)
        return search_result.total
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def write_magnet_files(
    search_result: SearchResult,
    output_dir: Optional[str] = None,
) -> int:
    """Write per-magnet JSON files for all results.

    Each file is named <btih>.json in the output directory.
    If a result has no btih, uses SHA256 of magnet_uri instead.

    Args:
        search_result: Aggregated search results.
        output_dir: Output directory (default: .magnet/).

    Returns:
        Number of files written.

    Raises:
        OSError: If directory cannot be created or files cannot be written.
    """
    dir_path = _ensure_output_dir(output_dir)
    files_written = 0

    for result in search_result.results:
        # Determine filename from btih
        filename = result.btih if result.btih else _fallback_hash(result.magnet_uri)
        if not filename:
            continue

        file_path = dir_path / f"{filename}.json"
        record = _build_magnet_record(
            result,
            query=search_result.query,
            season=search_result.season,
            episode=search_result.episode,
        )

        # Atomic write: write to .tmp then rename
        tmp_path = dir_path / f"{filename}.json.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, file_path)
            files_written += 1
        except Exception:
            # Clean up tmp file on failure
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    return files_written


def _fallback_hash(magnet_uri: str) -> str:
    """Generate a stable fallback filename hash from a magnet URI."""
    import hashlib
    return hashlib.sha256(magnet_uri.encode()).hexdigest()


def read_magnet_file(file_path: str) -> Optional[dict]:
    """Read and return a single magnet JSON file.

    Utility for downstream consumers (Phase 2 Downloader).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
