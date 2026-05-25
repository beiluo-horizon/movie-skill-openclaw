"""Site adapter protocol and base class definitions.

Every scraping target implements this protocol. The engine iterates
adapters, not sites. This is the isolation boundary — if a site breaks,
only its adapter changes.
"""

from typing import Protocol, Optional
from abc import abstractmethod

from movie_skill.output.schema import MagnetResult


class SiteError(Exception):
    """Raised when a site adapter encounters a non-recoverable error.

    Caught by CrawlerEngine which logs the warning and continues
    with other adapters (per D-06).
    """
    pass


class SiteAdapter(Protocol):
    """Interface every site adapter must implement.

    Implementations can be config-driven (GenericAdapter) or
    custom-coded for complex sites with JS rendering or auth.
    """

    name: str
    enabled: bool

    @abstractmethod
    async def search(
        self,
        query: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> list[MagnetResult]:
        """Search the site and return matching magnet results.

        Args:
            query: The show/movie name to search for.
            season: Optional season number.
            episode: Optional episode number.

        Returns:
            List of MagnetResult found on this site.

        Raises:
            SiteError: On unrecoverable errors (timeout, parse failure, etc.).
                These are caught by CrawlerEngine.
        """
        ...
