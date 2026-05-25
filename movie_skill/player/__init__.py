"""macOS media player integration, playback state tracking, media scanning, and CLI.

Provides PlayState model for persisting playback position, player
detection/invocation for IINA, VLC, and mpv on macOS, media file scanning
with ffprobe validation, and the movie-play CLI.
"""

from .player import (
    PlayerName,
    detect_players,
    build_player_args,
    play_file,
    play_best,
    PLAYER_PRIORITY,
)
from .scanner import (
    scan_media_file,
    validate_media_file,
    ffprobe_available,
    probe_media,
    check_download_status,
    get_player_status_message,
)
from .state import (
    DEFAULT_PLAYER_DIR,
    PlayState,
    write_state,
    read_state,
    list_states,
    delete_state,
)
from .cli import app

__all__ = [
    "DEFAULT_PLAYER_DIR",
    "PLAYER_PRIORITY",
    "PlayState",
    "PlayerName",
    "app",
    "build_player_args",
    "check_download_status",
    "delete_state",
    "detect_players",
    "ffprobe_available",
    "get_player_status_message",
    "list_states",
    "play_best",
    "play_file",
    "probe_media",
    "read_state",
    "scan_media_file",
    "validate_media_file",
    "write_state",
]
