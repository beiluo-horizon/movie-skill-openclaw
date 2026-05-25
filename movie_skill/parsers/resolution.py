"""Extract resolution information from torrent title strings."""

import re
from enum import IntEnum


class Resolution(IntEnum):
    """Ordered resolution values for ranking. Higher = better quality."""
    UNKNOWN = 0
    _360P = 360
    _480P = 480
    _720P = 720
    _1080P = 1080
    _2K = 1440
    _4K = 2160


RESOLUTION_PATTERNS = [
    (re.compile(r'4K|2160[PpIi]|UHD|Ultra\s*HD'), Resolution._4K),
    (re.compile(r'1440[PpIi]|2K|QHD'), Resolution._2K),
    (re.compile(r'1080[PpIi]|FHD|Full\s*HD'), Resolution._1080P),
    (re.compile(r'720[PpIi]|HD|High\s*Def'), Resolution._720P),
    (re.compile(r'480[PpIi]|SD|Standard\s*Def'), Resolution._480P),
    (re.compile(r'360[PpIi]'), Resolution._360P),
]


# Label mapping for human-readable output
RESOLUTION_LABELS = {
    Resolution._4K: "4K",
    Resolution._2K: "2K",
    Resolution._1080P: "1080p",
    Resolution._720P: "720p",
    Resolution._480P: "480p",
    Resolution._360P: "360p",
    Resolution.UNKNOWN: "unknown",
}


def extract_resolution(title: str) -> Resolution:
    """Extract resolution from a torrent title string.

    Args:
        title: The torrent filename or title to scan.

    Returns:
        Resolution enum value. Returns Resolution.UNKNOWN if no pattern matches.
    """
    for pattern, res in RESOLUTION_PATTERNS:
        if pattern.search(title):
            return res
    return Resolution.UNKNOWN


def resolution_label(res: Resolution) -> str:
    """Get human-readable label for a resolution value."""
    return RESOLUTION_LABELS.get(res, "unknown")
