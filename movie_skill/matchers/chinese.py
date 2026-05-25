"""Chinese title fuzzy matching using RapidFuzz and jieba tokenization."""

import re
from typing import Optional
from rapidfuzz import fuzz, utils as rf_utils


# Default similarity threshold (0.0-100.0)
DEFAULT_THRESHOLD = 65.0

# Characters/words to strip from show names during normalization
IGNORE_CHARS = re.compile(r'[^\w\s一-鿿\-\.\'’]')

# Common Chinese punctuation that can be stripped
CN_PUNCTUATION = re.compile(r'[「」『』【】《》（）()、，。：；！？·…—\s]+')


def normalize_show_name(name: str) -> str:
    """Normalize a show name for consistent matching.

    Performs:
    1. Strip outer whitespace
    2. Collapse Chinese punctuation to single space
    3. Remove non-word characters (except hyphens, periods, apostrophes)
    4. Lowercase
    5. Strip again

    Args:
        name: Raw show name (Chinese, English, or mixed)

    Returns:
        Normalized show name string.
    """
    name = name.strip()
    name = CN_PUNCTUATION.sub(' ', name)
    name = IGNORE_CHARS.sub('', name)
    return name.strip().lower()


def match_show(
    query: str,
    candidate: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[bool, float]:
    """Check if a candidate title matches the query using fuzzy matching.

    Uses RapidFuzz token_set_ratio which handles word reordering
    and partial matches — essential for Chinese/English mixed titles.

    Args:
        query: The user's search query (normalized).
        candidate: A torrent title candidate from scraping.
        threshold: Minimum similarity score (0-100) for a match.

    Returns:
        Tuple of (is_match, score) where score is 0-100.
    """
    # Preprocess with RapidFuzz defaults (remove special chars, lower)
    query_clean = rf_utils.default_process(normalize_show_name(query))
    candidate_clean = rf_utils.default_process(normalize_show_name(candidate))

    if not query_clean or not candidate_clean:
        return False, 0.0

    # token_set_ratio handles word/subset matching well for mixed-language titles
    score = fuzz.token_set_ratio(query_clean, candidate_clean)
    return score >= threshold, score


def rank_by_title_similarity(
    query: str,
    candidates: list[tuple[str, object]],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[tuple[object, float]]:
    """Filter and rank candidates by title similarity to the query.

    Args:
        query: User's search query.
        candidates: List of (title, payload) tuples to evaluate.
        threshold: Minimum similarity score.

    Returns:
        List of (payload, score) tuples sorted by score descending.
        Only candidates above threshold are included.
    """
    scored = []
    for title, payload in candidates:
        is_match, score = match_show(query, title, threshold)
        if is_match:
            scored.append((payload, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
