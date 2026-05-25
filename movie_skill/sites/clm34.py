"""Custom adapter for clm34.top (磁力猫).

The site serves base64-encoded HTML: /search returns a base64-encoded
search results page, and /information/<slug> returns a base64-encoded
detail page containing the actual magnet link.
"""

import base64
import re
import httpx
from parsel import Selector
from typing import Optional
from urllib.parse import quote

from movie_skill.output.schema import MagnetResult
from movie_skill.parsers.magnet import extract_btih, is_valid_magnet
from movie_skill.parsers.resolution import extract_resolution
from movie_skill.utils.retry import fetch_with_retry, MaxRetriesExceeded
from .base import SiteError


def _decode_clm34(body: bytes) -> str:
    """Decode clm34's document.write(decodeURIComponent(atob('...'))) into raw HTML.

    The response is a <script> wrapping: document.write(decodeURIComponent(window.atob("...B64...")))
    The atob() returns URL-encoded HTML; decodeURIComponent converts %XX → raw bytes.
    """
    from urllib.parse import unquote
    text = body.decode("utf-8", errors="replace")
    # Extract the base64 payload
    m = re.search(r'window\.atob\("([^"]+)"\)', text)
    if not m:
        if text.strip().startswith("<") and not text.strip().startswith("<script"):
            return text
        raise SiteError("Could not extract base64 payload from clm34 response")
    payload = m.group(1)
    # atob() → URL-encoded HTML, decodeURIComponent → raw HTML
    url_encoded = base64.b64decode(payload).decode("utf-8", errors="replace")
    return unquote(url_encoded)


def _encode_query(query: str) -> str:
    """Encode a search query for clm34 URL: base64(UTF-8 string)."""
    return base64.b64encode(query.encode("utf-8")).decode("ascii")


class Clm34Adapter:
    """Custom adapter for clm34.top.

    Uses the SiteAdapter protocol (duck-typed, not formally subclassed)
    to integrate with the CrawlerEngine.
    """

    name: str
    enabled: bool

    def __init__(self, name: str, config):
        self.name = name
        self.config = config
        self.enabled = config.enabled

    async def search(
        self,
        query: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> list[MagnetResult]:
        base_url = self.config.base_url.rstrip("/")
        encoded_q = _encode_query(query)
        search_url = f"{base_url}/search?word={encoded_q}&sort=time"

        headers = dict(self.config.headers)
        headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.config.timeout,
            follow_redirects=True,
        ) as client:
            try:
                resp = await fetch_with_retry(
                    client=client,
                    url=search_url,
                    max_retries=self.config.retry.max_retries,
                    base_backoff=self.config.retry.backoff_factor,
                )
            except (MaxRetriesExceeded, httpx.HTTPError) as e:
                raise SiteError(f"HTTP request failed for {self.name}: {e}") from e

            try:
                html = _decode_clm34(resp.content)
            except SiteError:
                raise
            except Exception as e:
                raise SiteError(f"Failed to decode clm34 response: {e}") from e

            sel = Selector(text=html)
            result_links = sel.xpath(
                "//ul[@id='Search_list_wrapper']//a[contains(@class, 'SearchListTitle_result_title')]"
            )

            if not result_links:
                return []

            results: list[MagnetResult] = []
            for link_elem in result_links[:5]:  # Limit to top 5 results
                detail_url = link_elem.xpath("./@href").get()
                title_text = "".join(link_elem.xpath(".//text()").getall()).strip()
                if not detail_url:
                    continue
                full_detail_url = f"{base_url}{detail_url}"

                try:
                    magnet = await self._fetch_magnet(client, full_detail_url, title_text)
                    if magnet:
                        results.append(magnet)
                except Exception:
                    continue

            return results

    async def _fetch_magnet(
        self, client: httpx.AsyncClient, detail_url: str, title: str
    ) -> Optional[MagnetResult]:
        try:
            resp = await client.get(detail_url)
            html = _decode_clm34(resp.content)
            sel = Selector(text=html)

            # Extract magnet from <a class="Information_magnet" id="down-url"> or <input id="Information_copy_text">
            magnet_href = sel.xpath(
                "//a[contains(@class, 'Information_magnet')]/@href"
            ).get()
            if not magnet_href:
                magnet_href = sel.xpath(
                    "//input[@id='Information_copy_text']/@value"
                ).get()

            if not magnet_href or not is_valid_magnet(magnet_href):
                return None

            btih = extract_btih(magnet_href) or ""
            resolution = extract_resolution(title)

            # Extract file size
            size_text = sel.xpath(
                "//div[contains(@class, 'Information_l_content')]//text()"
            ).getall()
            size_bytes = self._parse_size("".join(size_text))

            return MagnetResult(
                magnet_uri=magnet_href,
                title=title,
                size_bytes=size_bytes,
                source=self.name,
                btih=btih,
                resolution=resolution,
                seeders=None,
            )
        except SiteError:
            raise
        except Exception as e:
            # Skip malformed detail pages
            return None

    @staticmethod
    def _parse_size(text: str) -> Optional[int]:
        """Parse file size like '411.27 MB' into bytes."""
        m = re.search(r"([\d.]+)\s*(GB|MB|KB|TB|B)", text, re.IGNORECASE)
        if not m:
            return None
        n = float(m.group(1))
        unit = m.group(2).upper()
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        return int(n * multipliers.get(unit, 1))
