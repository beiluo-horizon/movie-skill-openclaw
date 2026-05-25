"""Pydantic models for magnet search results and output schema.

These types are consumed by all downstream phases (parsers, engine, CLI).
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class MagnetResult(BaseModel):
    """A single magnet link found by a site adapter.

    Serialized to JSON for per-magnet output files and downstream consumption.
    """
    magnet_uri: str = Field(..., description="Full magnet URI (magnet:?xt=urn:btih:...)")
    title: str = Field(..., description="Torrent title as displayed on the source site")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    source: str = Field("", description="Name of the source site (e.g. 'dytt')")
    btih: str = Field("", description="BitTorrent info hash extracted from magnet_uri")
    resolution: str = Field("unknown", description="Extracted resolution label (4K, 1080p, 720p, etc.)")
    seeders: Optional[int] = Field(None, description="Number of seeders (if available)")
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of when this result was scraped",
    )


class SearchResult(BaseModel):
    """Aggregated search results from all sites.

    After deduplication and ranking, this is the final output.
    """
    query: str = Field(..., description="The original search query")
    season: Optional[int] = Field(None, description="Season number (if applicable)")
    episode: Optional[int] = Field(None, description="Episode number (if applicable)")
    results: list[MagnetResult] = Field(default_factory=list, description="All unique, ranked magnet results")
    total: int = Field(default=0, description="Total number of unique results")
    errors: list[str] = Field(default_factory=list, description="Per-site error messages (non-fatal)")

    def model_post_init(self, __context) -> None:
        """Auto-compute total from results list."""
        self.total = len(self.results)

    def best(self) -> Optional[MagnetResult]:
        """Return the highest-ranked result, or None if empty."""
        return self.results[0] if self.results else None
