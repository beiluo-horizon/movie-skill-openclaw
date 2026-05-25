"""Pydantic models for ~/.movie_skill/sites.yaml configuration."""

from pydantic import BaseModel, Field, model_validator
from typing import Optional
from urllib.parse import urlparse


class FieldSelector(BaseModel):
    """Configuration for extracting a single field from a search result element."""
    selector: str = Field(..., description="CSS or XPath selector string")
    selector_type: str = Field("xpath", description="One of 'xpath' or 'css'")
    parse: Optional[str] = Field(None, description="Optional named parser function, e.g. 'size_in_bytes'")


class SearchConfig(BaseModel):
    """Configuration for the search endpoint of a site."""
    url_template: str = Field(..., description="Search URL with {query} placeholder, e.g. 'https://example.com/search?q={query}'")
    method: str = Field("GET", description="HTTP method: GET or POST")
    result_list: FieldSelector = Field(..., description="Selector for the list of search result elements")
    fields: dict[str, FieldSelector] = Field(..., description="Per-field selectors relative to each result element")
    pagination: Optional[dict] = Field(None, description="Optional pagination config (reserved for future use)")


class RetryConfig(BaseModel):
    """Retry configuration for HTTP requests to this site."""
    max_retries: int = Field(default=3, ge=0, description="Maximum number of retry attempts")
    backoff_factor: float = Field(default=1.0, gt=0, description="Exponential backoff multiplier in seconds")


class SiteConfig(BaseModel):
    """Configuration for a single search site."""
    type: str = Field(default="generic", description="Adapter type: 'generic', 'clm34', 'dygod', etc.")
    enabled: bool = Field(default=True, description="Whether this site is active")
    base_url: str = Field(..., description="Site base URL, e.g. 'https://example.com'")
    encoding: str = Field(default="utf-8", description="Character encoding for this site, e.g. 'utf-8', 'gbk'")
    timeout: int = Field(default=30, ge=5, description="HTTP request timeout in seconds")
    search: SearchConfig = Field(..., description="Search endpoint configuration")
    headers: dict[str, str] = Field(default_factory=lambda: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }, description="Custom HTTP headers for requests to this site")
    retry: RetryConfig = Field(default_factory=RetryConfig, description="Retry configuration")

    @model_validator(mode="after")
    def validate_base_url(self) -> "SiteConfig":
        """Ensure base_url is a valid URL with scheme."""
        parsed = urlparse(self.base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid base_url: {self.base_url}. Must include scheme and host.")
        return self


class SitesConfig(BaseModel):
    """Root config model holding all site configurations."""
    sites: dict[str, SiteConfig] = Field(..., description="Site configurations keyed by site name")

    def enabled_sites(self) -> dict[str, SiteConfig]:
        """Return only enabled sites."""
        return {name: cfg for name, cfg in self.sites.items() if cfg.enabled}
