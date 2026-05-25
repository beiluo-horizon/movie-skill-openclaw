"""Custom adapter for u3c3u3c3.u3c3u3c3u3c3.com — Gazelle-based BitTorrent tracker.

Search requires a dynamic anti-bot token embedded in the homepage's inline JS.
The token is extracted from: var nmefafej = "TOKEN" (non-commented line).
"""

import re
import httpx
from parsel import Selector
from typing import Optional
from urllib.parse import quote, urljoin

from movie_skill.output.schema import MagnetResult
from movie_skill.parsers.magnet import extract_btih, is_valid_magnet
from movie_skill.parsers.resolution import extract_resolution
from .base import SiteError


class U3c3Adapter:
    """Custom adapter for the u3c3 Gazelle-based tracker.

    Duck-typed to the SiteAdapter protocol for CrawlerEngine integration.
    """

    name: str
    enabled: bool

    def __init__(self, name: str, config):
        self.name = name
        self.config = config
        self.enabled = config.enabled

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        """Fetch homepage and extract the dynamic search token.

        The token is embedded in inline JS as:
            var nmefafej = "TOKEN";
        We must skip the commented-out line above it.
        """
        base_url = self.config.base_url.rstrip("/")
        resp = await client.get(base_url)
        for line in resp.text.split("\n"):
            stripped = line.strip()
            if "var nmefafej" in stripped and not stripped.startswith("//"):
                m = re.search(r'"([^"]+)"', stripped)
                if m:
                    return m.group(1)
        raise SiteError(f"Could not extract search token from {self.name}")

    async def search(
        self,
        query: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> list[MagnetResult]:
        base_url = self.config.base_url.rstrip("/")

        headers = dict(self.config.headers)
        headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.config.timeout,
            follow_redirects=True,
            verify=False,
        ) as client:
            try:
                # Step 1: get dynamic token from homepage
                token = await self._get_token(client)
                # Step 2: search with token
                encoded_q = quote(query, safe="")
                search_url = f"{base_url}/?search2={token}&search={encoded_q}"
                headers["Referer"] = base_url + "/"
                resp = await client.get(search_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise SiteError(f"HTTP request failed for {self.name}: {e}") from e

            html = resp.content.decode(self.config.encoding, errors="replace")
            sel = Selector(text=html)

            results: list[MagnetResult] = []

            # Each result is a <tr> containing magnet/torrent links
            for tr in sel.xpath("//tr"):
                magnet_links = tr.xpath('.//a[contains(@href, "magnet:")]/@href').getall()
                torrent_links = tr.xpath('.//a[contains(@href, "/torrent/")]/@href').getall()

                if not magnet_links and not torrent_links:
                    continue

                # Extract title from the row
                title_el = tr.xpath('.//a[contains(@href, "/view/")]/text()').get()
                if not title_el:
                    # fallback: first td text
                    tds = tr.xpath(".//td//text()").getall()
                    title_el = next((t.strip() for t in tds if len(t.strip()) > 5), None)
                if not title_el:
                    continue

                title = title_el.strip()

                # Get magnet URI
                magnet_uri = magnet_links[0] if magnet_links else ""
                if not magnet_uri and torrent_links:
                    # Build magnet from torrent hash
                    t_path = torrent_links[0]
                    m = re.search(r"torrent/([a-fA-F0-9]{40})", t_path)
                    if m:
                        magnet_uri = f"magnet:?xt=urn:btih:{m.group(1)}"

                if not magnet_uri:
                    continue

                btih = extract_btih(magnet_uri) or ""
                resolution = extract_resolution(title)

                # Extract size from tds
                size_bytes = None
                tds = tr.xpath(".//td//text()").getall()
                for td in tds:
                    size_bytes = self._parse_size(td.strip())
                    if size_bytes:
                        break

                results.append(
                    MagnetResult(
                        magnet_uri=magnet_uri,
                        title=title,
                        size_bytes=size_bytes,
                        source=self.name,
                        btih=btih,
                        resolution=resolution,
                        seeders=None,
                    )
                )

            return results

    @staticmethod
    def _parse_size(text: str) -> Optional[int]:
        """Parse file size like '4.5GB', '500MB', '1.2TB' into bytes."""
        m = re.search(r"([\d.]+)\s*(GB|MB|KB|TB|B)\b", text, re.IGNORECASE)
        if not m:
            return None
        n = float(m.group(1))
        unit = m.group(2).upper()
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        return int(n * multipliers.get(unit, 1))
