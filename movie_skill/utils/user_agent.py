"""User-Agent rotation helper for scraping requests."""

from typing import Optional

# A curated set of modern browser User-Agent strings for rotation
DEFAULT_USER_AGENTS = [
    # Chrome 120 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome 119 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox 121 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari 17.2 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge 120 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


class UserAgentManager:
    """Manages User-Agent rotation for scraping requests.

    Provides round-robin rotation and configurable overrides per site.
    """

    def __init__(self, agents: Optional[list[str]] = None):
        self._agents = agents or DEFAULT_USER_AGENTS.copy()
        self._index = 0

    def get(self, site_name: Optional[str] = None) -> str:
        """Get next User-Agent string (round-robin).

        Args:
            site_name: Optional site name for per-site consistency.
                If provided, uses a consistent UA for that site (hash-based).

        Returns:
            A User-Agent string.
        """
        if site_name:
            # Deterministic selection per site
            idx = hash(site_name) % len(self._agents)
            return self._agents[idx]
        # Round-robin for general use
        ua = self._agents[self._index]
        self._index = (self._index + 1) % len(self._agents)
        return ua

    def add(self, user_agent: str) -> None:
        """Add a custom User-Agent string to the rotation pool."""
        if user_agent not in self._agents:
            self._agents.append(user_agent)
