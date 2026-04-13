"""
Typed FPL upstream client.

Separates raw HTTP concerns from the cache/sync layer:
  - timeouts
  - retries / backoff
  - explicit error classes
  - stable fetch helpers per endpoint
"""

import asyncio
import ssl
from typing import Any

import aiohttp
import certifi

BASE = "https://fantasy.premierleague.com/api"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=5, sock_connect=5, sock_read=15)
MAX_RETRIES = 3
USER_AGENT = "volante/0.3"

_ssl_ctx = ssl.create_default_context(cafile=certifi.where())


class FplError(RuntimeError):
    """Base exception for FPL upstream failures."""


class FplNotFound(FplError):
    """The requested FPL resource does not exist."""


class FplBadResponse(FplError):
    """The FPL API returned an unexpected non-retryable response."""


class FplUpstreamUnavailable(FplError):
    """The FPL API could not be reached or kept failing upstream."""


class FplRateLimited(FplUpstreamUnavailable):
    """The FPL API rate-limited the request."""


def _session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(ssl=_ssl_ctx)
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    return aiohttp.ClientSession(connector=connector, headers=headers, timeout=REQUEST_TIMEOUT)


def _backoff_delay(attempt: int) -> float:
    return min(0.5 * (2 ** attempt), 4.0)


async def _request_json(session: aiohttp.ClientSession, path: str) -> dict | list:
    url = f"{BASE}/{path.lstrip('/')}"
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url) as resp:
                if resp.status == 404:
                    raise FplNotFound(f"FPL resource not found: {path}")

                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else _backoff_delay(attempt)
                    last_error = FplRateLimited(f"FPL rate limited request: {path}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                        continue
                    raise last_error

                if resp.status >= 500:
                    last_error = FplUpstreamUnavailable(f"FPL upstream error {resp.status}: {path}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(_backoff_delay(attempt))
                        continue
                    raise last_error

                if resp.status != 200:
                    body = (await resp.text()).strip()
                    snippet = body[:200] if body else resp.reason
                    raise FplBadResponse(f"FPL API {resp.status} for {path}: {snippet}")

                return await resp.json()

        except FplNotFound:
            raise
        except FplBadResponse:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = FplUpstreamUnavailable(f"FPL upstream unavailable for {path}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(_backoff_delay(attempt))
                continue
            raise last_error from exc

    if last_error:
        raise last_error
    raise FplUpstreamUnavailable(f"FPL upstream unavailable for {path}")


async def fetch_bootstrap(session: aiohttp.ClientSession) -> dict[str, Any]:
    data = await _request_json(session, "bootstrap-static/")
    if not isinstance(data, dict):
        raise FplBadResponse("bootstrap-static returned a non-object payload")
    return data


async def fetch_fixtures(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    data = await _request_json(session, "fixtures/")
    if not isinstance(data, list):
        raise FplBadResponse("fixtures returned a non-array payload")
    return data


async def fetch_player_history(session: aiohttp.ClientSession, player_id: int) -> dict[str, Any]:
    data = await _request_json(session, f"element-summary/{player_id}/")
    if not isinstance(data, dict):
        raise FplBadResponse(f"element-summary/{player_id} returned a non-object payload")
    return data


async def fetch_manager(session: aiohttp.ClientSession, manager_id: int) -> dict[str, Any]:
    data = await _request_json(session, f"entry/{manager_id}/")
    if not isinstance(data, dict):
        raise FplBadResponse(f"entry/{manager_id} returned a non-object payload")
    return data


async def fetch_manager_picks(session: aiohttp.ClientSession, manager_id: int, event: int) -> dict[str, Any]:
    data = await _request_json(session, f"entry/{manager_id}/event/{event}/picks/")
    if not isinstance(data, dict):
        raise FplBadResponse(f"entry/{manager_id}/event/{event}/picks returned a non-object payload")
    return data


async def fetch_manager_history(session: aiohttp.ClientSession, manager_id: int) -> dict[str, Any]:
    data = await _request_json(session, f"entry/{manager_id}/history/")
    if not isinstance(data, dict):
        raise FplBadResponse(f"entry/{manager_id}/history returned a non-object payload")
    return data


async def fetch_league_standings(session: aiohttp.ClientSession, league_id: int, page: int = 1) -> dict[str, Any]:
    data = await _request_json(session, f"leagues-classic/{league_id}/standings/?page_standings={page}")
    if not isinstance(data, dict):
        raise FplBadResponse(f"leagues-classic/{league_id}/standings returned a non-object payload")
    return data


async def fetch_manager_transfers(session: aiohttp.ClientSession, manager_id: int) -> list[dict[str, Any]]:
    data = await _request_json(session, f"entry/{manager_id}/transfers/")
    if not isinstance(data, list):
        raise FplBadResponse(f"entry/{manager_id}/transfers returned a non-array payload")
    return data


async def fetch_live_gameweek(session: aiohttp.ClientSession, event_id: int) -> dict[str, Any]:
    """Fetch live gameweek scores for all players in a given event."""
    data = await _request_json(session, f"event/{event_id}/live/")
    if not isinstance(data, dict):
        raise FplBadResponse(f"event/{event_id}/live returned a non-object payload")
    return data
