"""macOS media player detection and invocation.

Provides functions for:
- Detecting installed media players (IINA, VLC, mpv) in priority order
- Building correct CLI arguments for each player (start position, fullscreen, auto-exit)
- Launching the detected player with subprocess.Popen (non-blocking)

Per STATE.md: IINA is the primary player on the target Mac mini.
Per PITFALLS.md: subprocess.Popen with list args (never shell=True).
Per threat model T-03-02: file_path validated to exist before launch.

IINA specific (per docs/IINA-全屏播放.md):
- IINA's fullscreen flag is --mpv-fs=yes (not --fs or --fullscreen)
- Must call the iina binary directly, never `open -a IINA`
  (open -a triggers a startup screen / middle window)
- Flags go after file path: iina file.mkv --mpv-fs=yes
"""

import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

# Type alias for supported player names
PlayerName = Literal["iina", "vlc", "mpv", "quicktime", "open"]

# Player priority: IINA > VLC > mpv > open (system default, works with MKV if codec available)
PLAYER_PRIORITY: list[PlayerName] = ["iina", "vlc", "mpv", "open"]

# Binary names for shutil.which() lookup
_PLAYER_BINARIES: dict[PlayerName, str] = {
    "iina": "iina",
    "vlc": "VLC",
    "mpv": "mpv",
}

# Application bundle paths for macOS detection
# NOTE: IINA must use the binary directly (not open -a) per docs/IINA-全屏播放.md
_PLAYER_APP_PATHS: dict[PlayerName, Path] = {
    "iina": Path("/Applications/IINA.app/Contents/MacOS/iina"),
    "vlc": Path("/Applications/VLC.app"),
}


def _get_player_binary(player: PlayerName) -> tuple[str, list[str]]:
    """Get the executable and base arguments for a player.

    Returns (executable, base_args) suitable for subprocess.Popen.
    IINA and VLC on macOS may need `open -a <App>` if the binary
    is not directly on PATH.

    Args:
        player: Player name (iina, vlc, or mpv).

    Returns:
        Tuple of (executable_path_or_name, list_of_base_arguments).
    """
    if player == "iina":
        # Check /Applications bundle first (most reliable, avoids open -a) per docs/IINA-全屏播放.md
        iina_app = _PLAYER_APP_PATHS["iina"]
        if iina_app.exists():
            return (str(iina_app), [])
        # Also check PATH (e.g. symlinked by user)
        iina_bin = shutil.which("iina")
        if iina_bin is not None:
            return (iina_bin, [])
        # Do NOT fall back to `open -a IINA`. The open command does not pass
        # --mpv-fs=yes correctly and triggers IINA's startup screen.
        raise RuntimeError(
            "IINA not found. Install IINA from https://iina.io or check "
            f"that {_PLAYER_APP_PATHS['iina']} exists."
        )

    if player == "vlc":
        # VLC on macOS is typically launched via `open -a VLC`
        return ("open", ["-a", "VLC"])

    if player == "quicktime":
        return ("open", ["-a", "QuickTime Player"])

    # open — system default handler for the file type
    if player == "open":
        return ("open", [])

    # mpv - typically on PATH via Homebrew
    mpv_bin = shutil.which("mpv")
    if mpv_bin is not None:
        return (mpv_bin, [])
    return ("mpv", [])


def detect_players(available_only: bool = True) -> list[PlayerName]:
    """Detect installed media players on the system.

    Checks each player in priority order (IINA, VLC, mpv).

    Detection method per player:
    - IINA: `shutil.which("iina")` or `/Applications/IINA.app/Contents/MacOS/iina` exists
    - VLC: `shutil.which("VLC")` or `/Applications/VLC.app` exists
    - mpv: `shutil.which("mpv")`

    Args:
        available_only: If True (default), returns only detected players.
                        If False, returns all players in priority order (for tests).

    Returns:
        List of player names in priority order, filtered by availability.
    """
    if not available_only:
        return list(PLAYER_PRIORITY)

    available: list[PlayerName] = []
    for player in PLAYER_PRIORITY:
        if _is_player_available(player):
            available.append(player)
    return available


def _is_player_available(player: PlayerName) -> bool:
    """Check if a specific media player is installed.

    Args:
        player: Player name to check.

    Returns:
        True if the player binary or .app bundle exists.
    """
    # quicktime is built into macOS
    if player == "quicktime":
        return True

    # open command is always available on macOS
    if player == "open":
        return True

    binary = _PLAYER_BINARIES.get(player)
    if binary and shutil.which(binary) is not None:
        return True

    app_path = _PLAYER_APP_PATHS.get(player)
    if app_path is not None and app_path.exists():
        return True

    return False


def build_player_args(
    player: PlayerName,
    file_path: str,
    start_position: float = 0.0,
    fullscreen: bool = True,
) -> list[str]:
    """Build CLI argument list for the specified player.

    Constructs the full argument list for subprocess.Popen, including
    player-specific flags for start position, fullscreen, and auto-exit.

    Args:
        player: Target player (iina, vlc, mpv).
        file_path: Absolute path to the media file.
        start_position: Resume position in seconds (0 = start from beginning).
        fullscreen: Ignored for IINA (always fullscreen). Reserved for other players.

    Returns:
        List of CLI arguments suitable for subprocess.Popen.

    Raises:
        ValueError: If player name is not recognised.
        RuntimeError: If IINA is requested but not found.
    """
    if player not in PLAYER_PRIORITY:
        raise ValueError(f"Unknown player: {player}. Expected one of {PLAYER_PRIORITY}")

    executable, base_args = _get_player_binary(player)
    args: list[str] = [executable, *base_args]

    # For `open -a <App>`: append --args first, then file, then app flags
    uses_open = executable == "open"
    if uses_open:
        args.append("--args")

    # Append file path
    args.append(file_path)

    if player == "iina":
        # Per docs/IINA-全屏播放.md: --mpv-fs=yes is the only working fullscreen flag
        # Always force fullscreen — IINA is headless on this machine
        if start_position > 0:
            args.extend(["--start-pos", str(int(start_position))])
        args.append("--mpv-fs=yes")
        args.append("--mpv-keep-open=no")

    elif player == "vlc":
        if start_position > 0:
            args.append(f"--start-time={int(start_position)}")
        if fullscreen:
            args.append("--fullscreen")
        args.append("--play-and-exit")

    elif player == "mpv":
        if start_position > 0:
            args.extend(["--start", str(int(start_position))])
        if fullscreen:
            args.append("--fs")
        args.append("--keep-open=no")

    return args


def play_file(
    player: PlayerName,
    file_path: str,
    start_position: float = 0.0,
    fullscreen: bool = True,
) -> subprocess.Popen:
    """Launch a media player to play the specified file.

    Validates the file exists, builds player-specific CLI args, and
    launches the player as a non-blocking subprocess (no wait()).

    Per threat model T-03-02: uses list args only, never shell=True.
    File path validated to exist before launch.

    Args:
        player: Target player (iina, vlc, mpv).
        file_path: Absolute path to the media file.
        start_position: Resume position in seconds (default: 0).
        fullscreen: Used for VLC/mpv. IINA always launches fullscreen.

    Returns:
        subprocess.Popen handle to the launched player process.

    Raises:
        FileNotFoundError: If file_path does not exist.
        ValueError: If player name is not recognised.
        RuntimeError: If IINA is requested but not found.
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    if player not in PLAYER_PRIORITY:
        raise ValueError(f"Unknown player: {player}. Expected one of {PLAYER_PRIORITY}")

    args = build_player_args(player, file_path, start_position, fullscreen)
    proc = subprocess.Popen(args)
    return proc


def play_best(
    player: Optional[PlayerName] = None,
    file_path: str = "",
    start_position: float = 0.0,
    fullscreen: bool = True,
) -> tuple[PlayerName, subprocess.Popen]:
    """Launch the best available player.

    If a specific player is requested and available, use it. Otherwise
    detect and try each available player in priority order (IINA > VLC > mpv).

    Args:
        player: Optional specific player to use. If None, auto-detect.
        file_path: Absolute path to the media file.
        start_position: Resume position in seconds (default: 0).
        fullscreen: Used for VLC/mpv. IINA always launches fullscreen.

    Returns:
        Tuple of (player_name_used, subprocess.Popen_handle).

    Raises:
        RuntimeError: If no media player is available on the system.
    """
    if player is not None and _is_player_available(player):
        return (player, play_file(player, file_path, start_position, fullscreen))

    available = detect_players(available_only=True)
    if not available:
        raise RuntimeError("No media player found")

    chosen_player = available[0]
    return (chosen_player, play_file(chosen_player, file_path, start_position, fullscreen))
