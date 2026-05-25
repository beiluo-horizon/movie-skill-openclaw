"""Output formatting and JSON schema."""

from .schema import MagnetResult, SearchResult
from .json_writer import write_magnet_files, read_magnet_file
from .terminal import print_search_result, print_error, print_warning, print_info

__all__ = [
    "MagnetResult", "SearchResult",
    "write_magnet_files", "read_magnet_file",
    "print_search_result", "print_error", "print_warning", "print_info",
]
