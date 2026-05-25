"""Episode, resolution, and magnet parsers."""

from .episode import parse_episode, detect_input_mode, ParsedQuery
from .resolution import extract_resolution, resolution_label, Resolution
from .magnet import extract_btih, is_valid_magnet, magnet_hash

__all__ = [
    "parse_episode", "detect_input_mode", "ParsedQuery",
    "extract_resolution", "resolution_label", "Resolution",
    "extract_btih", "is_valid_magnet", "magnet_hash",
]
