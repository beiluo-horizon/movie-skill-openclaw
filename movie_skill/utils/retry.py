"""HTTP request retry logic with exponential backoff.

Handles transient failures (429, 5xx, connection errors) with
configurable retries and backoff. Designed for httpx.AsyncClient.
"""

import asyncio
from typing import Optional

import httpx


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 30.0


class MaxRetriesExceeded(Exception):
    """Raised when all retry attempts have been exhausted."""


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_backoff: float = DEFAULT_BASE_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    retryable_statuses: Optional[set[int]] = None,
) -> httpx.Response:
    """Fetch a URL with exponential backoff retry logic.

    Retries on:
    - HTTP 429 (Too Many Requests) with Retry-After header support
    - HTTP 5xx (Server Error)
    - Connection errors (ConnectError, ConnectTimeout, RemoteProtocolError, ReadTimeout)

    Args:
        client: An httpx.AsyncClient instance.
        url: The URL to fetch.
        max_retries: Maximum number of retry attempts (default 3).
        base_backoff: Base backoff time in seconds (default 1.0).
        max_backoff: Maximum backoff time in seconds (default 30.0).
        retryable_statuses: Set of HTTP status codes to retry on.
            Defaults to {429, 500, 502, 503, 504}.

    Returns:
        The httpx.Response object.

    Raises:
        MaxRetriesExceeded: If all attempts fail.
        httpx.HTTPStatusError: If a non-retryable error status is received.
    """
    if retryable_statuses is None:
        retryable_statuses = RETRYABLE_STATUSES

    last_exception: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            response = await client.get(url, timeout=None)

            # Handle 429 with Retry-After
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = min(base_backoff * (2 ** attempt), max_backoff)
                else:
                    wait = min(base_backoff * (2 ** attempt), max_backoff)
                await asyncio.sleep(wait)
                last_exception = httpx.HTTPStatusError(
                    f"HTTP 429 (attempt {attempt + 1}/{max_retries})",
                    request=response.request,
                    response=response,
                )
                continue

            # Handle other retryable statuses
            if response.status_code in retryable_statuses:
                wait = min(base_backoff * (2 ** attempt), max_backoff)
                await asyncio.sleep(wait)
                last_exception = httpx.HTTPStatusError(
                    f"HTTP {response.status_code} (attempt {attempt + 1}/{max_retries})",
                    request=response.request,
                    response=response,
                )
                continue

            # Non-retryable error
            response.raise_for_status()
            return response

        except (httpx.ConnectError, httpx.ConnectTimeout,
                httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait = min(base_backoff * (2 ** attempt), max_backoff)
                await asyncio.sleep(wait)
                continue
            raise MaxRetriesExceeded(
                f"Connection failed after {max_retries} attempts: {e}"
            ) from e

    # If we exhausted retries on retryable statuses
    if last_exception:
        raise MaxRetriesExceeded(
            f"Request failed after {max_retries} attempts"
        ) from last_exception

    raise MaxRetriesExceeded("Max retries exceeded (unknown error)")
