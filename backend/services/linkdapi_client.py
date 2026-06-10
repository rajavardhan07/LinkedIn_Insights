"""
Low-level async HTTP client for LinkdAPI.

Handles authentication, retries with exponential backoff, and error handling.
This is the ONLY module that talks to LinkdAPI directly.
"""

import asyncio
import httpx
from typing import Any

from config.settings import (
    LINKDAPI_API_KEY,
    LINKDAPI_BASE_URL,
    MAX_RETRIES,
    RETRY_DELAY,
    REQUEST_TIMEOUT,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class LinkdAPIError(Exception):
    """Raised when LinkdAPI returns an error response."""

    def __init__(self, status_code: int, message: str, endpoint: str):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(f"LinkdAPI [{status_code}] {endpoint}: {message}")


class LinkdAPIClient:
    """
    Async HTTP client for LinkdAPI with retry logic.

    Usage:
        async with LinkdAPIClient() as client:
            data = await client.get("/companies/company/posts", params={"id": 1234})
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or LINKDAPI_API_KEY
        self._base_url = LINKDAPI_BASE_URL
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "X-linkdapi-apikey": self._api_key,
                "Accept": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a GET request to LinkdAPI with automatic retry.

        Args:
            endpoint: API path (e.g., "/companies/company/posts").
            params: Query parameters.

        Returns:
            Parsed JSON response as dict.

        Raises:
            LinkdAPIError: On non-retryable API errors.
            Exception: After all retries exhausted.
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"API Request [attempt {attempt}/{MAX_RETRIES}]: "
                    f"GET {endpoint} | params={params}"
                )

                response = await self._client.get(endpoint, params=params)

                # Handle HTTP errors
                if response.status_code == 401:
                    raise LinkdAPIError(401, "Invalid API key", endpoint)
                if response.status_code == 403:
                    raise LinkdAPIError(403, "Access forbidden — check your plan", endpoint)
                if response.status_code == 404:
                    logger.warning(f"Resource not found: {endpoint} params={params}")
                    return {"data": None, "success": False, "message": "Not found"}

                if response.status_code == 429:
                    # Rate limited — wait and retry
                    wait = RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(f"Rate limited. Waiting {wait:.1f}s before retry...")
                    await asyncio.sleep(wait)
                    continue

                if response.status_code >= 500:
                    # Server error — retry
                    wait = RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        f"Server error {response.status_code}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()

                data = response.json()
                logger.info(f"API Response: {endpoint} — success")
                return data

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
                wait = RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Network error: {type(e).__name__}. "
                    f"Retrying in {wait:.1f}s... ({attempt}/{MAX_RETRIES})"
                )
                last_exception = e
                await asyncio.sleep(wait)

            except LinkdAPIError:
                # Non-retryable errors — propagate immediately
                raise

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error: {e}")
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(wait)

        # All retries exhausted
        raise Exception(
            f"Failed after {MAX_RETRIES} attempts for {endpoint}: {last_exception}"
        )
