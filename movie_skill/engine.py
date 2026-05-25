"""CrawlerEngine — orchestrates multi-site search, deduplication, and ranking.

This is the central coordinator. It:
1. Loads and validates site configs
2. Creates adapters from config
3. Runs concurrent searches across all adapters
4. Deduplicates results by btih
5. Ranks by resolution (4K > 1080p > 720p) then file size
6. Returns a SearchResult with best result + all ranked results
"""

import asyncio
import logging
from typing import Optional

from movie_skill.output.schema import MagnetResult, SearchResult
from movie_skill.config.loader import load_config, ConfigError
from movie_skill.config.schema import SitesConfig
from movie_skill.sites.factory import create_adapter
from movie_skill.sites.base import SiteAdapter, SiteError
from movie_skill.parsers.magnet import extract_btih
from movie_skill.parsers.resolution import extract_resolution, Resolution
from movie_skill.parsers.episode import ParsedQuery

logger = logging.getLogger(__name__)


class CrawlerEngine:
    """Orchestrates multi-site search for magnet links.

    Usage:
        engine = CrawlerEngine()
        result = await engine.search("权力的游戏", season=3, episode=5)
        print(result.best())
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path
        self._config: Optional[SitesConfig] = None
        self._adapters: Optional[list[SiteAdapter]] = None

    def load_config(self) -> SitesConfig:
        """Load and return the site configuration."""
        if self._config is None:
            self._config = load_config(self._config_path)
        return self._config

    def load_adapters(self) -> list[SiteAdapter]:
        """Create adapters from the loaded configuration.

        Only enabled sites get adapters. Skips sites that fail to
        create (bad config) with a warning — per D-06.

        Returns:
            List of enabled SiteAdapter instances.
        """
        if self._adapters is not None:
            return self._adapters

        config = self.load_config()
        adapters: list[SiteAdapter] = []

        for site_name, site_cfg in config.sites.items():
            if not site_cfg.enabled:
                continue
            try:
                # Convert Pydantic model to dict for factory
                cfg_dict = site_cfg.model_dump()
                adapter = create_adapter(site_name, cfg_dict)
                adapters.append(adapter)
            except Exception as e:
                logger.warning("Failed to create adapter for '%s': %s", site_name, e)

        self._adapters = adapters
        return adapters

    async def search(
        self,
        query: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> SearchResult:
        """Search all sites concurrently, collect and rank results.

        Per D-06: Individual site failures produce warnings but do not
        stop other sites from running.

        Per D-05: Results are ranked by resolution (4K > 1080p > 720p)
        then file size (larger first).

        Per D-07: If all sites fail, SearchResult.errors lists all failures.

        Args:
            query: Show/movie name to search for.
            season: Optional season number.
            episode: Optional episode number.

        Returns:
            SearchResult with ranked, deduplicated results.
        """
        adapters = self.load_adapters()

        if not adapters:
            return SearchResult(
                query=query,
                season=season,
                episode=episode,
                errors=["No enabled site adapters configured"],
            )

        # Run all searches concurrently
        tasks = [
            self._safe_search(adapter, query, season, episode)
            for adapter in adapters
        ]

        results_per_site = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        return self._aggregate(query, season, episode, adapters, results_per_site)

    async def _safe_search(
        self,
        adapter: SiteAdapter,
        query: str,
        season: Optional[int],
        episode: Optional[int],
    ) -> list[MagnetResult]:
        """Wrap adapter.search so exceptions propagate to gather.

        Per D-06: Individual failures are caught by asyncio.gather
        (return_exceptions=True) and reported in _aggregate as errors.
        This allows D-07 to list all failures when every site fails.
        """
        return await adapter.search(query, season, episode)

    def _aggregate(
        self,
        query: str,
        season: Optional[int],
        episode: Optional[int],
        adapters: list[SiteAdapter],
        results_per_site: list,
    ) -> SearchResult:
        """Combine, deduplicate, and rank results from all sites.

        Deduplication (per CRAWL-06): Results with identical btih are
        collapsed into one — the first occurrence wins.

        Ranking (per CRAWL-04, D-05): Sorted by resolution descending
        (4K > 1080p > 720p) then file size descending.
        """
        all_results: list[MagnetResult] = []
        seen_btihs: set[str] = set()
        errors: list[str] = []

        for i, results in enumerate(results_per_site):
            adapter = adapters[i] if i < len(adapters) else None
            adapter_name = adapter.name if adapter else f"site_{i}"

            if isinstance(results, Exception):
                logger.warning("Site adapter '%s' failed: %s", adapter_name, results)
                errors.append(f"{adapter_name}: {results}")
                continue

            if isinstance(results, list):
                for result in results:
                    # Ensure btih is populated
                    if not result.btih and result.magnet_uri:
                        result.btih = extract_btih(result.magnet_uri) or ""

                    # Deduplicate by btih
                    if result.btih and result.btih in seen_btihs:
                        continue
                    if result.btih:
                        seen_btihs.add(result.btih)

                    # Ensure resolution label
                    if result.resolution == "unknown" and result.title:
                        res = extract_resolution(result.title)
                        result.resolution = self._resolution_label(res)

                    all_results.append(result)
            else:
                errors.append(f"{adapter_name}: unexpected result type {type(results).__name__}")

        # Rank by resolution (descending), then file size (descending)
        ranked = self._rank_results(all_results)

        return SearchResult(
            query=query,
            season=season,
            episode=episode,
            results=ranked,
            total=len(ranked),
            errors=errors,
        )

    def _rank_results(self, results: list[MagnetResult]) -> list[MagnetResult]:
        """Rank results by resolution (highest first), then file size (largest first)."""
        def sort_key(r: MagnetResult) -> tuple:
            res = extract_resolution(r.title).value if r.title else Resolution.UNKNOWN.value
            size = r.size_bytes or 0
            return (-res, -size)

        return sorted(results, key=sort_key)

    @staticmethod
    def _resolution_label(res: Resolution) -> str:
        """Get human-readable resolution label."""
        labels = {
            Resolution._4K: "4K",
            Resolution._2K: "2K",
            Resolution._1080P: "1080p",
            Resolution._720P: "720p",
            Resolution._480P: "480p",
            Resolution._360P: "360p",
            Resolution.UNKNOWN: "unknown",
        }
        return labels.get(res, "unknown")
