"""Natural language movie/show intent parser.

Parses Chinese natural language queries into structured intents
(WATCH, DOWNLOAD, PLAY) with extracted show name, season, and episode.

Examples:
    "我想看权力的游戏第三季第五集" → WATCH, show="权力的游戏", season=3, episode=5
    "下载权力的游戏"               → DOWNLOAD, show="权力的游戏"
    "播放权力的游戏"               → PLAY, show="权力的游戏"
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from movie_skill.parsers.episode import EPISODE_PATTERNS, parse_episode


class IntentType(str, Enum):
    """Intent type classified from natural language query prefix."""

    WATCH = "watch"
    DOWNLOAD = "download"
    PLAY = "play"
    LIST = "list"


@dataclass
class ParsedIntent:
    """Structured intent parsed from a natural language query."""

    intent: IntentType
    show: str
    season: Optional[int] = None
    episode: Optional[int] = None
    mode: str = "auto"  # "auto" or "step"
    raw_query: str = ""


# Mode prefix patterns — matched BEFORE intent patterns.
# After extraction, the mode word is stripped from the query.
MODE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"自动"), "auto"),
    (re.compile(r"分步|逐步|手动"), "step"),
]

# Ordered intent prefix patterns -- first match wins.
INTENT_PATTERNS: list[tuple[re.Pattern, IntentType]] = [
    (re.compile(r"(?:我)?(?:想(?:要)?|要)看"), IntentType.WATCH),
    (re.compile(r"下载"), IntentType.DOWNLOAD),
    (re.compile(r"播放(?:列表|资源|历史)|列出|已下载|可播放"), IntentType.LIST),
    (re.compile(r"播放"), IntentType.PLAY),
]


def _find_episode_position(text: str) -> Optional[int]:
    """Find the start position of the first episode pattern in text.

    Uses EPISODE_PATTERNS to locate where season/episode info begins.
    Returns None if no episode pattern is found.
    """
    for pattern, _has_season, _has_episode in EPISODE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.start()
    return None


def parse_intent(query: str) -> ParsedIntent:
    """Parse a natural language movie/show query into a structured intent.

    Args:
        query: Natural language query string (e.g. "我想看权力的游戏第三季第五集").

    Returns:
        ParsedIntent with classified intent type, show name, and optional
        season/episode numbers.
    """
    raw_query = query
    query = query.strip()

    # Empty or whitespace-only query
    if not query:
        return ParsedIntent(
            intent=IntentType.WATCH,
            show="",
            raw_query=raw_query,
        )

    # Detect mode prefix (default: auto)
    mode: str = "auto"
    for pattern, mode_val in MODE_PATTERNS:
        m = pattern.match(query)
        if m:
            mode = mode_val
            query = query[m.end():].strip()
            break

    # Detect intent prefix
    matched_intent = IntentType.WATCH  # default
    prefix_end = 0

    for pattern, intent_type in INTENT_PATTERNS:
        m = pattern.match(query)
        if m:
            matched_intent = intent_type
            prefix_end = m.end()
            break

    # Remaining text after prefix removal
    remaining = query[prefix_end:].strip()

    # Parse episode info from remaining text
    season, episode = parse_episode(remaining)

    # Extract show name
    if season is not None or episode is not None:
        # Find where episode pattern starts and take text before it
        ep_pos = _find_episode_position(remaining)
        if ep_pos is not None:
            show = remaining[:ep_pos].strip()
        else:
            show = remaining
    else:
        show = remaining

    return ParsedIntent(
        intent=matched_intent,
        show=show,
        season=season,
        episode=episode,
        mode=mode,
        raw_query=raw_query,
    )
