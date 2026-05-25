"""Parse Chinese and Western episode number notations into structured data."""

import re
from dataclasses import dataclass
from typing import Optional


# Chinese numeral mapping for episode parsing
CN_DIGITS = {
    '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}


@dataclass
class ParsedQuery:
    """Structured query after parsing user input."""
    show: str
    season: Optional[int] = None
    episode: Optional[int] = None


def _cn_to_int(s: str) -> int:
    """Convert Chinese numeral string to integer.

    Handles: '三' -> 3, '十二' -> 12, '二十' -> 20, '三十三' -> 33.
    """
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in CN_DIGITS:
        return CN_DIGITS[s]
    # Handle compound numerals (十一, 二十三, etc.)
    if '十' in s:
        parts = s.split('十')
        left_str = parts[0] if parts[0] else ''
        right_str = parts[1] if len(parts) > 1 and parts[1] else ''
        left = CN_DIGITS.get(left_str, 1) if left_str else 1
        right = CN_DIGITS.get(right_str, 0) if right_str else 0
        return left * 10 + right
    raise ValueError(f"Cannot parse Chinese numeral: {s}")


EPISODE_PATTERNS = [
    # Chinese: 第X季第Y集 (digits or Chinese numerals)
    (re.compile(r'第(\d+|' + '|'.join(CN_DIGITS.keys()) + r')季第(\d+|' + '|'.join(CN_DIGITS.keys()) + r')集'), True, True),
    # Chinese: 第X季 (season only)
    (re.compile(r'第(\d+|' + '|'.join(CN_DIGITS.keys()) + r')季'), True, False),
    # Chinese: 第X集 / 第X期 (variety show, episode only)
    (re.compile(r'第(\d+|' + '|'.join(CN_DIGITS.keys()) + r')(?:集|期)'), False, True),
    # Western: S01E01, S01E01E02 (multi-episode — returns first)
    (re.compile(r'[Ss](\d+)[Ee](\d+)'), True, True),
    # Western: 1x01
    (re.compile(r'(\d+)x(\d+)'), True, True),
    # Western lowercase: s01e01
    (re.compile(r's(\d+)e(\d+)'), True, True),
    # Season X Episode Y
    (re.compile(r'[Ss]eason\s*(\d+)\s*[Ee]pisode\s*(\d+)'), True, True),
    # E01 (no season — variety show style)
    (re.compile(r'[Ee](\d+)'), False, True),
]

EPISODE_RAW_SEARCH_PATTERNS = [
    # For raw title matching (scraped results), also match these:
    # Season 1 Episode 5
    (re.compile(r'[Ss]eason\s*(\d+)\s*[Ee]pisode\s*(\d+)'), True, True),
    # E01 (no season — variety show style)
    (re.compile(r'[Ee](\d+)'), False, True),
]


def parse_episode(text: str, patterns: Optional[list] = None) -> tuple[Optional[int], Optional[int]]:
    """Parse season and episode from a text string.

    Args:
        text: The string to parse (e.g. '第3季第5集', 'S03E05', '权力3x05')
        patterns: List of (regex, has_season, has_episode) tuples. Defaults to EPISODE_PATTERNS.

    Returns:
        Tuple of (season, episode) or (None, None) if no match.
    """
    if patterns is None:
        patterns = EPISODE_PATTERNS
    for pattern, has_season, has_episode in patterns:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            season_val = None
            episode_val = None
            if has_season and len(groups) >= 2:
                try:
                    season_val = _cn_to_int(groups[0])
                    episode_val = _cn_to_int(groups[1])
                except ValueError:
                    continue
            elif has_season and len(groups) >= 1:
                try:
                    season_val = _cn_to_int(groups[0])
                except ValueError:
                    continue
            elif not has_season and has_episode and len(groups) >= 1:
                try:
                    episode_val = _cn_to_int(groups[0])
                except ValueError:
                    continue
            return (season_val, episode_val)
    return (None, None)


def detect_input_mode(query: str) -> ParsedQuery:
    """Auto-detect whether query is NL (natural language) or already 'show' string.

    Per D-04: Accept both structured params (--show --season --episode)
    and natural language strings. This function handles the NL detection path.

    Strategies tried in order:
    1. Chinese pattern: '权力的游戏第三季第五集' -> show='权力的游戏', season=3, episode=5
    2. Western pattern: 'westworld s03e05' -> show='westworld', season=3, episode=5
    3. Plain show name: '权力的游戏' -> show='权力的游戏'
    """
    if not query or not query.strip():
        return ParsedQuery(show="")

    # Strategy 1: Chinese pattern match
    season, episode = parse_episode(query)
    if season is not None or episode is not None:
        # Extract show name: everything before the first season/episode pattern
        for pattern, has_season, _ in EPISODE_PATTERNS:
            m = pattern.search(query)
            if m:
                show = query[:m.start()].strip()
                # Clean trailing punctuation/whitespace
                show = show.rstrip(' ,._-:;，。、；：')
                show = re.sub(r'[「『【《（]', '', show)  # clean opening brackets
                return ParsedQuery(show=show, season=season, episode=episode)

    # Strategy 2: Western pattern match
    m_western = re.search(r'^(.*?)[\s._-]*[Ss](\d+)[Ee](\d+)', query.strip())
    if m_western:
        show = m_western.group(1).strip().rstrip(' ,._-:;，。、；：')
        return ParsedQuery(show=show, season=int(m_western.group(2)), episode=int(m_western.group(3)))

    # Strategy 3: Plain show name
    return ParsedQuery(show=query.strip())
