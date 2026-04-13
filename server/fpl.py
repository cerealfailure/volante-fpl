"""
FPL sync/cache orchestration.

This module sits above the raw FPL client and below the FastAPI routes.
It owns:
  - TTL policy
  - cache sync keys
  - DB persistence for upstream FPL resources
  - manager/bootstrap/league refresh jobs
"""

import asyncio
from datetime import datetime, timedelta, timezone

import db
import fpl_client

CONCURRENCY = 5
BATCH_DELAY = 0.1

CORE_DATA_TTL = timedelta(hours=6)
MANAGER_TTL = timedelta(minutes=30)
MANAGER_LEAGUES_TTL = timedelta(hours=6)
MANAGER_TRANSFERS_TTL = timedelta(minutes=15)
LEAGUE_PAGE_TTL = timedelta(minutes=15)

FplError = fpl_client.FplError
FplNotFound = fpl_client.FplNotFound
FplBadResponse = fpl_client.FplBadResponse
FplUpstreamUnavailable = fpl_client.FplUpstreamUnavailable
FplRateLimited = fpl_client.FplRateLimited

_session = fpl_client._session
fetch_bootstrap = fpl_client.fetch_bootstrap
fetch_fixtures = fpl_client.fetch_fixtures
fetch_player_history = fpl_client.fetch_player_history
fetch_manager = fpl_client.fetch_manager
fetch_manager_picks = fpl_client.fetch_manager_picks
fetch_manager_history = fpl_client.fetch_manager_history
fetch_league_standings = fpl_client.fetch_league_standings
fetch_manager_transfers = fpl_client.fetch_manager_transfers
fetch_live_gameweek = fpl_client.fetch_live_gameweek


def manager_sync_key(manager_id: int) -> str:
    return f"manager:{manager_id}"


def manager_leagues_sync_key(manager_id: int) -> str:
    return f"manager_leagues:{manager_id}"


def manager_transfers_sync_key(manager_id: int) -> str:
    return f"manager_transfers:{manager_id}"


def league_page_sync_key(league_id: int, page: int) -> str:
    return f"league:{league_id}:page:{page}"


def is_stale(sync: dict | None, ttl: timedelta) -> bool:
    if not sync:
        return True
    synced = datetime.fromisoformat(sync["synced_at"])
    return datetime.now(timezone.utc) - synced > ttl


async def ensure_core_data(force: bool = False):
    conn = await db.get_db()
    try:
        bootstrap_sync = await db.get_sync(conn, "bootstrap")
        fixtures_sync = await db.get_sync(conn, "fixtures")
    finally:
        await conn.close()

    if force or is_stale(bootstrap_sync, CORE_DATA_TTL):
        await sync_bootstrap()
    if force or is_stale(fixtures_sync, CORE_DATA_TTL):
        await sync_fixtures()


async def _persist_manager_snapshot(conn, manager_id: int, info: dict) -> list[dict]:
    await db.upsert_manager(conn, info)
    classic_leagues = ((info.get("leagues") or {}).get("classic") or [])
    await db.replace_manager_leagues(conn, manager_id, classic_leagues)
    await db.set_sync(conn, manager_leagues_sync_key(manager_id), {
        "count": len(classic_leagues),
    })
    return classic_leagues


# ── Sync pipeline ────────────────────────────────────────────────────

async def sync_bootstrap() -> dict:
    """Sync all players, teams, and event metadata from bootstrap-static."""
    print("Syncing bootstrap data...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            data = await fetch_bootstrap(session)

        await db.upsert_teams(conn, data["teams"])
        await db.upsert_players(conn, data["elements"])

        current_event = None
        for ev in data.get("events", []):
            if ev.get("is_current"):
                current_event = ev["id"]
                break
        if current_event is None:
            for ev in reversed(data.get("events", [])):
                if ev.get("finished"):
                    current_event = ev["id"]
                    break

        meta = {
            "current_event": current_event,
            "total_players": data.get("total_players"),
            "event_count": len(data.get("events", [])),
        }
        await db.set_sync(conn, "bootstrap", meta)
        await conn.commit()
        print(f"  ✓ {len(data['teams'])} teams, {len(data['elements'])} players, GW{current_event}")
        return meta
    finally:
        await conn.close()


async def sync_fixtures() -> dict:
    """Sync all fixtures."""
    print("Syncing fixtures...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            data = await fetch_fixtures(session)

        await db.upsert_fixtures(conn, data)
        meta = {
            "count": len(data),
            "finished": sum(1 for f in data if f.get("finished")),
        }
        await db.set_sync(conn, "fixtures", meta)
        await conn.commit()
        print(f"  ✓ {meta['count']} fixtures ({meta['finished']} finished)")
        return meta
    finally:
        await conn.close()


async def sync_player_histories(player_ids: list[int]) -> dict:
    """
    Fetch per-GW history for specific players.
    Batched with concurrency control.
    """
    unique_ids = sorted(set(player_ids))
    print(f"Syncing history for {len(unique_ids)} players...")
    if not unique_ids:
        return {"requested": 0, "synced": 0, "failed": []}

    conn = await db.get_db()
    sem = asyncio.Semaphore(CONCURRENCY)
    failures: list[dict] = []
    synced_ids: set[int] = set()

    async def _fetch_one(session, pid: int):
        async with sem:
            try:
                data = await fetch_player_history(session, pid)
                await db.upsert_player_gws(conn, pid, data.get("history", []))
                synced_ids.add(pid)
            except FplNotFound:
                failures.append({"player_id": pid, "error": "not_found"})
            except FplError as exc:
                failures.append({"player_id": pid, "error": str(exc)})
            finally:
                await asyncio.sleep(BATCH_DELAY)

    try:
        async with _session() as session:
            tasks = [_fetch_one(session, pid) for pid in unique_ids]
            await asyncio.gather(*tasks)
        await conn.commit()
        print(f"  ✓ history synced for {len(synced_ids)} players")
        return {
            "requested": len(unique_ids),
            "synced": len(synced_ids),
            "failed": failures,
        }
    finally:
        await conn.close()


async def sync_manager_leagues(manager_id: int) -> dict:
    """Fetch and cache a manager's league memberships."""
    print(f"Syncing manager leagues {manager_id}...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            info = await fetch_manager(session, manager_id)
        leagues = await _persist_manager_snapshot(conn, manager_id, info)
        await conn.commit()
        return {"manager_id": manager_id, "count": len(leagues)}
    finally:
        await conn.close()


async def sync_manager_transfers(manager_id: int) -> dict:
    """Fetch and cache a manager's transfer history."""
    print(f"Syncing manager transfers {manager_id}...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            transfers = await fetch_manager_transfers(session, manager_id)
        await db.replace_manager_transfers(conn, manager_id, transfers)
        meta = {"count": len(transfers)}
        await db.set_sync(conn, manager_transfers_sync_key(manager_id), meta)
        await conn.commit()
        return {"manager_id": manager_id, **meta}
    finally:
        await conn.close()


async def sync_league_page(league_id: int, page: int = 1) -> dict:
    """Fetch and cache a single page of league standings."""
    print(f"Syncing league {league_id} page {page}...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            data = await fetch_league_standings(session, league_id, page)
        await db.upsert_league_standings(conn, data)
        standings = data.get("standings", {})
        meta = {
            "count": len(standings.get("results", [])),
            "has_next": bool(standings.get("has_next")),
            "last_updated_data": data.get("last_updated_data"),
        }
        await db.set_sync(conn, league_page_sync_key(league_id, page), meta)
        await conn.commit()
        return {"league_id": league_id, "page": page, **meta}
    finally:
        await conn.close()


async def sync_manager(manager_id: int, include_histories: bool = True, include_transfers: bool = True) -> dict:
    """
    Fetch and store a manager's info, leagues, current team picks, and optionally transfers.
    Returns { manager: {...}, picks: [...], event: int }.
    """
    print(f"Syncing manager {manager_id}...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            info = await fetch_manager(session, manager_id)
            leagues = await _persist_manager_snapshot(conn, manager_id, info)
            event = info.get("current_event")
            if not event:
                raise FplBadResponse(f"Manager {manager_id} missing current_event")

            picks_data = await fetch_manager_picks(session, manager_id, event)
            picks = picks_data.get("picks") or []
            if not picks:
                raise FplBadResponse(f"Manager {manager_id} returned no picks for GW{event}")
            await db.upsert_manager_picks(conn, manager_id, event, picks)

            transfers = []
            if include_transfers:
                transfers = await fetch_manager_transfers(session, manager_id)
                await db.replace_manager_transfers(conn, manager_id, transfers)
                await db.set_sync(conn, manager_transfers_sync_key(manager_id), {
                    "count": len(transfers),
                })

        # Release the initial write transaction before opening a second
        # writer connection inside history sync.
        await conn.commit()

        player_ids = [p["element"] for p in picks]
        history_result = {"requested": 0, "synced": 0, "failed": []}
        if include_histories:
            history_result = await sync_player_histories(player_ids)

        await db.set_sync(conn, manager_sync_key(manager_id), {
            "event": event,
            "player_count": len(player_ids),
            "history_synced": history_result["synced"],
            "history_failed": len(history_result["failed"]),
            "league_count": len(leagues),
            "transfer_count": len(transfers),
        })
        await conn.commit()

        result = {
            "manager": {
                "id": info["id"],
                "name": info.get("name", ""),
                "player_name": f"{info.get('player_first_name','')} {info.get('player_last_name','')}".strip(),
                "overall_points": info.get("summary_overall_points"),
                "overall_rank": info.get("summary_overall_rank"),
                "bank": info.get("last_deadline_bank"),
                "team_value": info.get("last_deadline_value"),
            },
            "picks": picks,
            "event": event,
            "entry_history": picks_data.get("entry_history", {}),
            "history_failed": history_result["failed"],
            "league_count": len(leagues),
            "transfer_count": len(transfers),
        }
        print(f"  ✓ manager {manager_id} synced (GW{event})")
        return result
    finally:
        await conn.close()


LIVE_TTL = timedelta(seconds=90)


async def sync_live_gameweek(event: int) -> dict:
    """Fetch live gameweek scores from FPL and cache them."""
    conn = await db.get_db()
    try:
        live_sync = await db.get_sync(conn, f"live:{event}")
        if not is_stale(live_sync, LIVE_TTL):
            return {"event": event, "cached": True}
    finally:
        await conn.close()

    print(f"Syncing live GW{event}...")
    conn = await db.get_db()
    try:
        async with _session() as session:
            data = await fetch_live_gameweek(session, event)
        elements = data.get("elements", [])
        await db.upsert_live_gw(conn, event, elements)
        await db.set_sync(conn, f"live:{event}", {"player_count": len(elements)})
        await conn.commit()
        print(f"  ✓ live GW{event}: {len(elements)} players")
        return {"event": event, "player_count": len(elements), "cached": False}
    finally:
        await conn.close()


async def snapshot_ep_for_event(event: int, player_ids: list[int]):
    """Snapshot pre-GW expected points for players (idempotent)."""
    conn = await db.get_db()
    try:
        await db.snapshot_ep(conn, event, player_ids)
    finally:
        await conn.close()


async def sync_all() -> dict:
    """Full sync: bootstrap + fixtures."""
    await db.init_db()
    bootstrap = await sync_bootstrap()
    fixtures = await sync_fixtures()
    return {"bootstrap": bootstrap, "fixtures": fixtures}
