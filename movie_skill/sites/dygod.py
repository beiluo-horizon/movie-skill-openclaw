"""Custom adapter for dygod.vip / dygod.net (电影天堂).

Empire CMS-based movie site. Uses POST search with GBK encoding.
Search results link to detail pages containing magnet/ftp links.
"""

import re
import httpx
from parsel import Selector
from typing import Optional
from urllib.parse import quote, urljoin

from movie_skill.output.schema import MagnetResult
from movie_skill.parsers.magnet import extract_btih, is_valid_magnet
from movie_skill.parsers.resolution import extract_resolution
from movie_skill.utils.retry import fetch_with_retry, MaxRetriesExceeded
from .base import SiteError


class DygodAdapter:
    """Custom adapter for dygod.vip (电影天堂).

    Duck-typed to the SiteAdapter protocol for CrawlerEngine integration.
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
        search_url = f"{base_url}/e/search/index.php"

        headers = dict(self.config.headers)
        headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        headers.setdefault("Referer", base_url + "/")

        # Encode keyword in GBK (the site's native encoding)
        try:
            gbk_query = query.encode("gbk")
        except UnicodeEncodeError:
            gbk_query = query.encode("gbk", errors="replace")

        # URL-encode the GBK bytes for form submission
        form_body = (
            f"keyboard={quote(gbk_query, safe='')}"
            f"&classid=0"
            f"&show=title,smalltext"
            f"&tempid=1"
        )

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.config.timeout,
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.post(search_url, content=form_body.encode("ascii"))
                resp.raise_for_status()
            except (MaxRetriesExceeded, httpx.HTTPError) as e:
                raise SiteError(f"HTTP request failed for {self.name}: {e}") from e

            try:
                html = resp.content.decode(self.config.encoding, errors="replace")
            except Exception as e:
                raise SiteError(f"Failed to decode dygod response: {e}") from e

            # Check for "no results" page
            if "没有搜索到相关的内容" in html:
                return []

            sel = Selector(text=html)
            # Filter: only detail page links (paths like /html/gndy/dyzz/20260506/131821.html)
            all_links = sel.xpath("//a[contains(@href, '/html/') and contains(@href, '.html')]")
            result_links = []
            for link in all_links:
                href = link.xpath("./@href").get() or ""
                if re.search(r'/html/(gndy|tv|dongman|zongyi|game|3gp)\S*/\d+\.html', href):
                    result_links.append(link)

            if not result_links:
                return []

            results: list[MagnetResult] = []
            for link_elem in result_links[:5]:
                detail_path = link_elem.xpath("./@href").get()
                title_text = "".join(link_elem.xpath(".//text()").getall()).strip()
                if not detail_path:
                    continue

                full_detail_url = urljoin(base_url, detail_path)

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
            html = resp.content.decode(self.config.encoding, errors="replace")
            sel = Selector(text=html)

            # Try to find magnet links (hidden by 2-hour JS delay, rarely present)
            magnet_links = sel.xpath("//a[contains(@href, 'magnet:')]/@href").getall()

            # Fallback: extract ftp:// from jianpian:// protocol links
            if not magnet_links:
                jianpian = sel.xpath(
                    "//a[contains(@href, 'jianpian://')]/@href"
                ).getall()
                ftp_links = []
                for link_url in jianpian:
                    # jianpian://pathtype=url&path=ftp://...
                    m = re.search(r'path=(ftp://[^&]+)', link_url)
                    if m:
                        from urllib.parse import unquote
                        ftp_links.append(unquote(m.group(1)))

                if not ftp_links:
                    # Also try direct ftp links
                    ftp_links = sel.xpath(
                        "//a[contains(@href, 'ftp://')]/@href"
                    ).getall()

                if not magnet_links and not ftp_links:
                    return None

            magnet_uri = magnet_links[0] if magnet_links else (ftp_links[0] if ftp_links else "")
            if not magnet_uri:
                return None

            btih = extract_btih(magnet_uri) or ""
            resolution = extract_resolution(title)

            size_bytes = self._parse_page_size(html)

            return MagnetResult(
                magnet_uri=magnet_uri,
                title=title,
                size_bytes=size_bytes,
                source=self.name,
                btih=btih,
                resolution=resolution,
                seeders=None,
            )
        except Exception:
            return None

    @staticmethod
    def _parse_page_size(html: str) -> Optional[int]:
        """Try to extract file size from dygod detail page."""
        m = re.search(r"([\d.]+)\s*(GB|MB|KB|TB)\b", html, re.IGNORECASE)
        if not m:
            return None
        n = float(m.group(1))
        unit = m.group(2).upper()
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        return int(n * multipliers.get(unit, 1))
