"""Bilingual search strategy — generate search terms in Chinese and English."""

from typing import Optional


def bilingual_search_terms(show_name: str) -> list[str]:
    """Generate search terms for bilingual search strategy.

    If the show name contains Chinese characters, the primary search is
    the original name. The fallback is the original name (no translation).

    For Chinese names, this returns [original_chinese, original_chinese]
    (same — we don't have a translation database; the site needs to handle it).

    For ASCII-only names, returns [original_english].

    Args:
        show_name: The user-provided show name (Chinese, English, or mixed).

    Returns:
        List of search terms to try. First is primary, rest are fallbacks.
    """
    if not show_name or not show_name.strip():
        return []

    name = show_name.strip()

    # Check if name contains Chinese characters
    has_chinese = any('一' <= c <= '鿿' for c in name)

    if has_chinese:
        # Search with Chinese name first, then the raw (may contain English parts)
        return [name, name]
    else:
        # English name only
        return [name]
