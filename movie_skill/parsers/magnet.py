"""Parse and extract information from magnet URIs."""

import re
import hashlib
from typing import Optional

# Regex to extract btih (BitTorrent info hash) from magnet URI
# Format: magnet:?xt=urn:btih:<40-char-hex-hash>&...
BTIH_PATTERN = re.compile(r'xt=urn:btih:([a-fA-F0-9]{32,40})')

# Magnet URI validation pattern (loose)
MAGNET_PATTERN = re.compile(r'^magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}')


def extract_btih(magnet_uri: str) -> Optional[str]:
    """Extract the BitTorrent info hash from a magnet URI.

    Args:
        magnet_uri: Full magnet URI, e.g. 'magnet:?xt=urn:btih:abc123def...'

    Returns:
        Lowercase btih hex string, or None if not found.
    """
    m = BTIH_PATTERN.search(magnet_uri)
    if m:
        return m.group(1).lower()
    return None


def is_valid_magnet(magnet_uri: str) -> bool:
    """Check whether a string is a valid magnet URI.

    Validates format: magnet:?xt=urn:btih:<hash>
    """
    return bool(MAGNET_PATTERN.match(magnet_uri.strip()))


def magnet_hash(magnet_uri: str) -> str:
    """Generate a stable content hash from a magnet URI for filename use.

    Uses the btih directly as a unique identifier. Falls back to SHA256
    of the full URI if btih cannot be extracted.
    """
    btih = extract_btih(magnet_uri)
    if btih:
        return btih
    return hashlib.sha256(magnet_uri.encode()).hexdigest()
