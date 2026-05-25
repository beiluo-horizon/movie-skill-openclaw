"""Generic config-driven site adapter.

Uses YAML-configured selectors to scrape any site. No code changes
needed when a site redesigns — just update the YAML config.
"""

import httpx
from parsel import Selector
from typing import Optional

from movie_skill.output.schema import MagnetResult
from movie_skill.config.schema import SiteConfig
from movie_skill.parsers.magnet import extract_btih, is_valid_magnet
from movie_skill.parsers.resolution import extract_resolution, resolution_label
from movie_skill.utils.retry import fetch_with_retry, MaxRetriesExceeded
from movie_skill.utils.user_agent import UserAgentManager
from .base import SiteError


_ua_manager = UserAgentManager()


class GenericAdapter:
    """A site adapter driven entirely by YAML configuration.

    All scraping rules (URL template, selectors, headers, encoding)
    come from sites.yaml. This is the primary adapter type per D-01.
    """

    def __init__(self, name: str, config: SiteConfig):
        self.name = name
        self.config = config
        self.enabled = config.enabled

    async def search(
        self,
        query: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> list[MagnetResult]:
        """Search the site and extract magnet links using YAML-configured selectors.

        Process:
        1. Build search URL from template
        2. Fetch page with retry
        3. Parse HTML with parsel using configured selectors
        4. Extract per-result fields
        5. Build MagnetResult objects (valid magnet URIs only)

        Args:
            query: Search query string.
            season: Optional season number (not used in search URL, but available).
            episode: Optional episode number (not used in search URL, but available).

        Returns:
            List of MagnetResult objects.

        Raises:
            SiteError: On HTTP failure, parse failure, or empty page.
        """
        cfg = self.config
        search_cfg = cfg.search

        # Build full URL (join base_url with relative path template)
        base_url = cfg.base_url.rstrip("/")
        url_template = search_cfg.url_template.replace("{query}", query)
        if url_template.startswith("http://") or url_template.startswith("https://"):
            url = url_template
        else:
            url = f"{base_url}{url_template}"

        # Build headers
        headers = dict(cfg.headers)
        if "User-Agent" not in headers:
            headers["User-Agent"] = _ua_manager.get(self.name)

        # Create HTTP client with per-site settings
        async with httpx.AsyncClient(
            headers=headers,
            http2=True,
            timeout=cfg.timeout,
        ) as client:
            try:
                response = await fetch_with_retry(
                    client=client,
                    url=url,
                    max_retries=cfg.retry.max_retries,
                    base_backoff=cfg.retry.backoff_factor,
                )
            except (MaxRetriesExceeded, httpx.HTTPError) as e:
                raise SiteError(f"HTTP request failed for {self.name}: {e}") from e

            # Decode with site encoding
            try:
                html_text = response.content.decode(cfg.encoding)
            except (LookupError, UnicodeDecodeError) as e:
                raise SiteError(
                    f"Failed to decode response from {self.name} with encoding {cfg.encoding}: {e}"
                ) from e

            # Parse HTML
            sel = Selector(text=html_text)

            # Find result list elements
            result_list_cfg = search_cfg.result_list
            if result_list_cfg.selector_type == "xpath":
                result_elements = sel.xpath(result_list_cfg.selector)
            else:
                result_elements = sel.css(result_list_cfg.selector)

            if not result_elements:
                return []  # No results, not an error

            # Extract fields from each result element
            results: list[MagnetResult] = []
            for elem in result_elements:
                try:
                    result = self._extract_result(elem)
                    if result is not None:
                        results.append(result)
                except Exception:
                    # Skip malformed result elements
                    continue

            return results

    def _extract_result(self, element: Selector) -> Optional[MagnetResult]:
        """Extract a single MagnetResult from a parsed result element."""
        fields = {}
        for field_name, field_cfg in self.config.search.fields.items():
            try:
                if field_cfg.selector_type == "xpath":
                    raw = element.xpath(field_cfg.selector).get()
                else:
                    raw = element.css(field_cfg.selector).get()

                if raw is not None:
                    raw = raw.strip()
                fields[field_name] = raw
            except Exception:
                fields[field_name] = None

        magnet_uri = fields.get("magnet_link", "") or ""
        title = fields.get("title", "") or ""

        if not magnet_uri or not title:
            return None

        # Validate magnet URI
        magnet_uri = magnet_uri.strip()
        if not is_valid_magnet(magnet_uri):
            return None

        # Parse size if available
        size_str = fields.get("size", "")
        size_bytes = self._parse_size(size_str) if size_str else None

        # Parse seeders
        seeders_str = fields.get("seeders", "")
        seeders = None
        if seeders_str:
            try:
                seeders = int(seeders_str)
            except (ValueError, TypeError):
                seeders = None

        btih = extract_btih(magnet_uri) or ""
        resolution = extract_resolution(title)

        return MagnetResult(
            magnet_uri=magnet_uri,
            title=title,
            size_bytes=size_bytes,
            source=self.name,
            btih=btih,
            resolution=resolution_label(resolution),
            seeders=seeders,
        )

    @staticmethod
    def _parse_size(size_str: str) -> Optional[int]:
        """Parse a human-readable file size string to bytes.

        Handles: '2.5 GB', '1.2 GiB', '500 MB', '1024 KB', '1TB'.
        """
        import re
        size_str = size_str.strip().upper()
        m = re.match(r'([\d.]+)\s*(TB|GB|MB|KB|TIB|GIB|MIB|KIB|B)?', size_str)
        if not m:
            return None
        try:
            value = float(m.group(1))
        except ValueError:
            return None
        unit = m.group(2) or 'B'

        multipliers = {
            'TB': 1_000_000_000_000, 'TIB': 1_099_511_627_776,
            'GB': 1_000_000_000, 'GIB': 1_073_741_824,
            'MB': 1_000_000, 'MIB': 1_048_576,
            'KB': 1_000, 'KIB': 1_024,
            'B': 1,
        }
        mult = multipliers.get(unit, 1)
        return int(value * mult)
