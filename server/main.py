"""
Volante API server — FastAPI, default dev port 8556.

Endpoints:
  POST /api/sync                 — trigger full FPL data sync
  POST /api/sync/manager         — sync a specific manager
  GET  /api/xray/{id}            — full team X-ray analysis
  GET  /api/xray/{id}/attribution — multi-week correlation attribution
  GET  /api/xray/{id}/player/{pid} — single player deep dive
  POST /api/xray/{id}/simulate   — transfer impact simulation
  GET  /api/players              — browse/search all players
  GET  /api/manager/{id}/leagues — cached leagues for a manager
  GET  /api/leagues/{id}         — cached league standings
  GET  /api/manager/{id}/transfers — cached manager transfers
  GET  /api/manager/{id}/transfer-analysis — score past transfers vs outcomes
  GET  /api/status               — data freshness
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import os
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import db
import fpl
import fpl_auth
import analysis
import fixture_exposure
import intel as intel_engine
import transfers as transfers_engine
import background

VOLANTE_MODE = os.environ.get("VOLANTE_MODE", "fpl_only").strip().lower()
if VOLANTE_MODE not in {"fpl_only", "overall"}:
    VOLANTE_MODE = "fpl_only"
INTEL_HTTP_TOKEN = os.environ.get("VOLANTE_INTEL_TOKEN")
ALLOW_ANY_ORIGIN_REGEX = r"^https?://[^/]+(?::\d+)?$"


def _internal_mode_enabled() -> bool:
    return VOLANTE_MODE == "overall"


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "").strip()
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def _require_intel_access(request: Request):
    if not _internal_mode_enabled():
        raise HTTPException(404, "Private transfer intelligence is disabled in fpl_only mode")
    if INTEL_HTTP_TOKEN:
        provided = request.headers.get("x-volante-token") or _extract_bearer_token(request)
        if not provided or not hmac.compare_digest(provided, INTEL_HTTP_TOKEN):
            raise HTTPException(403, "Missing or invalid transfer-intel token")
        return
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(
            403,
            "Private transfer intelligence is local-only unless VOLANTE_INTEL_TOKEN is configured",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await background.manager.start()
    if _internal_mode_enabled():
        conn = await db.get_db()
        try:
            await intel_engine.ensure_intel_defaults(conn)
            await conn.commit()
        finally:
            await conn.close()

    intel_task = None
    intel_manager_id = os.environ.get("VOLANTE_INTEL_MANAGER_ID")
    if _internal_mode_enabled() and intel_manager_id:
        horizon = int(os.environ.get("VOLANTE_INTEL_HORIZON", "5"))
        interval_minutes = int(os.environ.get("VOLANTE_INTEL_INTERVAL_MINUTES", "60"))
        intel_task = asyncio.create_task(
            intel_engine.run_intel_loop(int(intel_manager_id), horizon=horizon, interval_minutes=interval_minutes)
        )

    try:
        yield
    finally:
        await background.manager.stop()
        if intel_task is not None:
            intel_task.cancel()
            try:
                await intel_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Volante", version="0.2.0", lifespan=lifespan)

DEFAULT_ALLOW_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://[::1]:5173",
    "http://localhost:5555",
    "http://127.0.0.1:5555",
    "http://[::1]:5555",
    "http://localhost:5556",
    "http://127.0.0.1:5556",
    "http://[::1]:5556",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://[::1]:4173",
]

allow_origins = [
    origin.strip()
    for origin in os.environ.get("VOLANTE_ALLOW_ORIGINS", ",".join(DEFAULT_ALLOW_ORIGINS)).split(",")
    if origin.strip()
]
allow_origin_regex = os.environ.get("VOLANTE_ALLOW_ORIGIN_REGEX", ALLOW_ANY_ORIGIN_REGEX)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ───────────────────────────────────────────────────────────

class SyncManagerRequest(BaseModel):
    manager_id: int


class FplCookieRequest(BaseModel):
    # Raw pasted cookie text. Either a full cookie header (PingOne accounts:
    # "access_token=...; refresh_token=...; datadome=..."; legacy accounts:
    # "pl_profile=...; sessionid=...") or a bare credential value treated as
    # access_token. Parsed server-side.
    raw: str

class TransferSimRequest(BaseModel):
    player_out: int
    player_in: int


class IntelImportRequest(BaseModel):
    path: str
    source_key: str
    label: str | None = None
    event: int | None = None
    horizon: int = 5


class TransferPlanPick(BaseModel):
    sell_id: int
    buy_id: int


class TransferPlanSimRequest(BaseModel):
    picks: list[TransferPlanPick]
    event: int | None = None
    horizon: int = 5


def _http_from_fpl_error(exc: Exception) -> HTTPException:
    if isinstance(exc, fpl.FplNotFound):
        return HTTPException(404, str(exc))
    return HTTPException(503, str(exc))


async def _ensure_core_cache():
    conn = await db.get_db()
    try:
        bootstrap_sync = await db.get_sync(conn, "bootstrap")
        fixtures_sync = await db.get_sync(conn, "fixtures")
    finally:
        await conn.close()

    try:
        await fpl.ensure_core_data()
    except fpl.FplError as exc:
        if not bootstrap_sync or not fixtures_sync:
            raise _http_from_fpl_error(exc)


def _synced_at(sync: dict | None) -> str | None:
    return sync["synced_at"] if sync else None


async def _register_background_manager(manager_id: int, source: str):
    try:
        await background.manager.register_manager(manager_id, source=source)
    except Exception:
        pass


# ── Sync ─────────────────────────────────────────────────────────────

@app.post("/api/sync")
async def sync_all():
    try:
        result = await fpl.sync_all()
        return {"ok": True, "message": "Bootstrap + fixtures synced", **result}
    except fpl.FplError as e:
        raise _http_from_fpl_error(e)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/sync/manager")
async def sync_manager(req: SyncManagerRequest):
    try:
        await _ensure_core_cache()
        result = await fpl.sync_manager(req.manager_id)
        await _register_background_manager(req.manager_id, "sync_manager")
        return {"ok": True, **result}
    except fpl.FplError as e:
        raise _http_from_fpl_error(e)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── X-Ray ────────────────────────────────────────────────────────────

@app.get("/api/xray/{manager_id}")
async def team_xray(
    manager_id: int,
    event: int | None = None,
    lookback: int | None = Query(default=None, ge=1),
    future_weeks: int | None = Query(default=None, ge=1),
    refresh: bool = Query(default=False),
):
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current = await db.get_current_event(conn)
            squad = await db.get_manager_squad(conn, manager_id, event or current) if current else []
            mgr_sync = await db.get_sync(conn, fpl.manager_sync_key(manager_id))
        finally:
            await conn.close()

        if refresh or not squad or fpl.is_stale(mgr_sync, fpl.MANAGER_TTL):
            try:
                await fpl.sync_manager(manager_id)
            except fpl.FplError as exc:
                if not squad:
                    raise _http_from_fpl_error(exc)

        result = await analysis.team_xray(
            manager_id,
            event,
            lookback=lookback,
            future_weeks=future_weeks,
        )
        await _register_background_manager(manager_id, "xray")
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/xray/{manager_id}/suggest-captain")
async def suggest_captain(manager_id: int, event: int | None = None):
    """Recommend the captain pick for the upcoming gameweek."""
    try:
        await _ensure_core_cache()
        return await analysis.suggest_captain(manager_id, event)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/xray/{manager_id}/attribution")
async def correlation_attribution(
    manager_id: int,
    event: int | None = None,
    lookback: int | None = Query(default=10, ge=1),
):
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current = await db.get_current_event(conn)
            squad = await db.get_manager_squad(conn, manager_id, event or current) if current else []
            mgr_sync = await db.get_sync(conn, fpl.manager_sync_key(manager_id))
        finally:
            await conn.close()

        if not squad or fpl.is_stale(mgr_sync, fpl.MANAGER_TTL):
            try:
                await fpl.sync_manager(manager_id)
            except fpl.FplError as exc:
                if not squad:
                    raise _http_from_fpl_error(exc)

        result = await analysis.compute_correlation_attribution(manager_id, lookback=lookback, event=event)
        await _register_background_manager(manager_id, "attribution")
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/xray/{manager_id}/player/{player_id}")
async def player_deep_dive(manager_id: int, player_id: int, event: int | None = None):
    """Single player analysis within the context of a manager's squad."""
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current = await db.get_current_event(conn)
            ev = event or current
            squad = await db.get_manager_squad(conn, manager_id, ev) if ev else []
            player = await db.get_player(conn, player_id)
            history = await db.get_player_history(conn, player_id)
            team_id = player["team_id"] if player else None
            fixtures = await db.get_upcoming_fixtures(conn, team_id, ev, 8) if team_id and ev else []
        finally:
            await conn.close()

        if player and not history:
            try:
                await fpl.sync_player_histories([player_id])
                conn = await db.get_db()
                try:
                    history = await db.get_player_history(conn, player_id)
                finally:
                    await conn.close()
            except fpl.FplError:
                pass

        if not player:
            raise HTTPException(404, f"Player {player_id} not found")

        # per-GW points timeline
        gw_points = [{"event": h["event"], "points": h["total_points"], "minutes": h["minutes"],
                       "goals": h["goals_scored"], "assists": h["assists"], "cs": h["clean_sheets"],
                       "bonus": h["bonus"], "xg": h["xg"], "xa": h["xa"]}
                      for h in history if h["minutes"] > 0]

        # correlation with each squad member (if in squad context)
        correlations = []
        if squad:
            starter_ids = [s["player_id"] for s in squad if s["squad_position"] <= 11]
            if player_id in starter_ids:
                database = await db.get_db()
                try:
                    emp_cov, _ = await analysis.compute_empirical_covariance(starter_ids, database)
                    stds = __import__("numpy").sqrt(__import__("numpy").maximum(__import__("numpy").diag(emp_cov), 1e-10))
                    corr = emp_cov / __import__("numpy").outer(stds, stds)
                    idx = starter_ids.index(player_id)
                    for j, sid in enumerate(starter_ids):
                        if j != idx:
                            mate = next((s for s in squad if s["player_id"] == sid), None)
                            if mate:
                                correlations.append({
                                    "player_id": sid,
                                    "web_name": mate["web_name"],
                                    "team_short": mate["team_short"],
                                    "correlation": round(float(corr[idx, j]), 3),
                                })
                finally:
                    await database.close()
                correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        # upcoming fixtures
        fix_outlook = []
        for f in fixtures:
            is_home = f["team_h"] == team_id
            fix_outlook.append({
                "event": f["event"],
                "opponent": f["away_short"] if is_home else f["home_short"],
                "difficulty": analysis.fixture_difficulty_for_team(f, team_id),
                "is_home": is_home,
            })

        result = {
            "player": {
                "id": player["id"],
                "web_name": player["web_name"],
                "team_id": player["team_id"],
                "position": analysis.POS_NAMES.get(player["position"], "???"),
                "price": player["now_cost"] / 10 if player["now_cost"] else 0,
                "total_points": player["total_points"],
                "form": player["form"],
                "ep_next": player["ep_next"],
                "selected_pct": player["selected_pct"],
                "xg": player["xg"], "xa": player["xa"], "xgi": player["xgi"],
                "minutes": player["minutes"], "starts": player["starts"],
                "goals": player["goals_scored"], "assists": player["assists"],
                "clean_sheets": player["clean_sheets"],
                "bonus": player["bonus"],
                "influence": player["influence"], "creativity": player["creativity"],
                "threat": player["threat"], "ict_index": player["ict_index"],
                "status": player["status"], "news": player["news"],
            },
            "gw_history": gw_points,
            "correlations": correlations,
            "fixtures": fix_outlook,
        }
        await _register_background_manager(manager_id, "player_deep_dive")
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.post("/api/xray/{manager_id}/simulate")
async def simulate_transfer(manager_id: int, req: TransferSimRequest, event: int | None = None):
    """Simulate swapping one player for another — returns variance/exposure delta."""
    try:
        result = await analysis.simulate_transfer(manager_id, req.player_out, req.player_in, event)
        await _register_background_manager(manager_id, "simulate_transfer")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.post("/api/xray/{manager_id}/simulate-plan")
async def simulate_transfer_plan(manager_id: int, req: TransferPlanSimRequest):
    """Simulate an exact multi-transfer plan."""
    try:
        result = await transfers_engine.simulate_transfer_plan(
            manager_id,
            [pick.model_dump() for pick in req.picks],
            event=req.event,
            horizon=req.horizon,
        )
        await _register_background_manager(manager_id, "simulate_plan")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


# ── Player Browser ───────────────────────────────────────────────────

@app.get("/api/players")
async def browse_players(
    pos: int | None = None,
    team: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_form: float | None = None,
    status: str | None = None,
    sort: str = "total_points",
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
):
    """Browse/search all players with filters."""
    await _ensure_core_cache()
    conn = await db.get_db()
    try:
        where = ["1=1"]
        params = []

        if pos:
            where.append("p.position = ?")
            params.append(pos)
        if team:
            where.append("p.team_id = ?")
            params.append(team)
        if min_price is not None:
            where.append("p.now_cost >= ?")
            params.append(min_price)
        if max_price is not None:
            where.append("p.now_cost <= ?")
            params.append(max_price)
        if min_form is not None:
            where.append("p.form >= ?")
            params.append(min_form)
        if status:
            where.append("p.status = ?")
            params.append(status)
        if search:
            where.append("(p.web_name LIKE ? OR p.second_name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        # validate sort column
        valid_sorts = {"total_points", "form", "now_cost", "xgi", "xg", "xa",
                       "selected_pct", "ep_next", "minutes", "ict_index", "goals_scored", "assists"}
        sort_col = sort if sort in valid_sorts else "total_points"

        query = f"""
            SELECT p.id, p.web_name, p.first_name, p.second_name,
                   p.team_id, p.position, p.now_cost, p.total_points,
                   p.form, p.ep_next, p.selected_pct, p.minutes, p.starts,
                   p.goals_scored, p.assists, p.clean_sheets, p.bonus,
                   p.xg, p.xa, p.xgi, p.xgc,
                   p.xg_per90, p.xa_per90, p.xgi_per90,
                   p.influence, p.creativity, p.threat, p.ict_index,
                   p.status, p.news, p.chance_next,
                   p.penalties_order, p.corners_order,
                   t.name as team_name, t.short_name as team_short
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE {' AND '.join(where)}
            ORDER BY p.{sort_col} DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await conn.execute_fetchall(query, params)
        players = []
        for r in rows:
            d = dict(r)
            d["price"] = d["now_cost"] / 10 if d["now_cost"] else 0
            d["pos_name"] = analysis.POS_NAMES.get(d["position"], "???")
            players.append(d)

        # total count for pagination
        count_q = f"SELECT count(*) as c FROM players p WHERE {' AND '.join(where)}"
        count_rows = await conn.execute_fetchall(count_q, params[:-2])
        total = count_rows[0]["c"]

        return {"players": players, "total": total, "limit": limit, "offset": offset}
    finally:
        await conn.close()


# ── Info ─────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status(manager_id: int | None = None):
    conn = await db.get_db()
    try:
        bootstrap_sync = await db.get_sync(conn, "bootstrap")
        fixtures_sync = await db.get_sync(conn, "fixtures")
        counts = {}
        for table in [
            "teams", "players", "fixtures", "player_gws", "manager_picks",
            "manager_leagues", "league_pages", "league_standings", "manager_transfers",
            "ep_snapshots", "live_gw_cache", "projection_snapshots",
            "player_availability_snapshots", "player_availability_tape", "availability_profiles",
            "background_manager_registry",
        ]:
            rows = await conn.execute_fetchall(f"SELECT count(*) as c FROM {table}")
            counts[table] = rows[0]["c"]
        payload = {
            "mode": {
                "name": VOLANTE_MODE,
                "intel_http_enabled": _internal_mode_enabled(),
                "intel_token_required": bool(INTEL_HTTP_TOKEN),
            },
            "synced": {
                "bootstrap": _synced_at(bootstrap_sync),
                "fixtures": _synced_at(fixtures_sync),
                "current_event": bootstrap_sync["meta"].get("current_event") if bootstrap_sync and bootstrap_sync.get("meta") else None,
                "bootstrap_stale": fpl.is_stale(bootstrap_sync, fpl.CORE_DATA_TTL),
                "fixtures_stale": fpl.is_stale(fixtures_sync, fpl.CORE_DATA_TTL),
            },
            "counts": counts,
            "background": background.manager.snapshot(),
        }
        if manager_id is not None:
            manager_sync = await db.get_sync(conn, fpl.manager_sync_key(manager_id))
            leagues_sync = await db.get_sync(conn, fpl.manager_leagues_sync_key(manager_id))
            transfers_sync = await db.get_sync(conn, fpl.manager_transfers_sync_key(manager_id))
            payload["manager"] = {
                "id": manager_id,
                "syncs": {
                    "manager": _synced_at(manager_sync),
                    "leagues": _synced_at(leagues_sync),
                    "transfers": _synced_at(transfers_sync),
                },
                "stale": {
                    "manager": fpl.is_stale(manager_sync, fpl.MANAGER_TTL),
                    "leagues": fpl.is_stale(leagues_sync, fpl.MANAGER_LEAGUES_TTL),
                    "transfers": fpl.is_stale(transfers_sync, fpl.MANAGER_TRANSFERS_TTL),
                },
            }
        return payload
    finally:
        await conn.close()


@app.get("/api/teams")
async def list_teams():
    conn = await db.get_db()
    try:
        teams = await db.get_all_teams(conn)
        return {"teams": teams}
    finally:
        await conn.close()


# ── Leagues ──────────────────────────────────────────────────────────

@app.get("/api/manager/{manager_id}/leagues")
async def manager_leagues(manager_id: int, refresh: bool = False):
    """Get cached leagues a manager belongs to."""
    try:
        conn = await db.get_db()
        try:
            sync = await db.get_sync(conn, fpl.manager_leagues_sync_key(manager_id))
            leagues = await db.get_manager_leagues(conn, manager_id)
        finally:
            await conn.close()

        stale = refresh or fpl.is_stale(sync, fpl.MANAGER_LEAGUES_TTL)
        if not leagues or stale:
            try:
                await fpl.sync_manager_leagues(manager_id)
                conn = await db.get_db()
                try:
                    sync = await db.get_sync(conn, fpl.manager_leagues_sync_key(manager_id))
                    leagues = await db.get_manager_leagues(conn, manager_id)
                finally:
                    await conn.close()
                stale = False
            except fpl.FplError as exc:
                if not leagues:
                    raise _http_from_fpl_error(exc)
                stale = True

        result = {
            "leagues": leagues,
            "stale": stale,
            "synced_at": _synced_at(sync),
        }
        await _register_background_manager(manager_id, "manager_leagues")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/leagues/{league_id}")
async def league_standings(league_id: int, page: int = Query(default=1, ge=1), refresh: bool = False):
    """Get cached league standings with basic manager info."""
    try:
        conn = await db.get_db()
        try:
            sync = await db.get_sync(conn, fpl.league_page_sync_key(league_id, page))
            cached = await db.get_league_page(conn, league_id, page)
        finally:
            await conn.close()

        stale = refresh or fpl.is_stale(sync, fpl.LEAGUE_PAGE_TTL)
        if not cached or stale:
            try:
                await fpl.sync_league_page(league_id, page)
                conn = await db.get_db()
                try:
                    sync = await db.get_sync(conn, fpl.league_page_sync_key(league_id, page))
                    cached = await db.get_league_page(conn, league_id, page)
                finally:
                    await conn.close()
                stale = False
            except fpl.FplError as exc:
                if not cached:
                    raise _http_from_fpl_error(exc)
                stale = True

        league_info = cached.get("league", {}) if cached else {}
        entries = cached.get("standings", []) if cached else []
        return {
            "league": {
                "id": league_info.get("id"),
                "name": league_info.get("name"),
                "type": league_info.get("league_type"),
                "last_updated_data": league_info.get("last_updated_data"),
            },
            "page": cached.get("page", page) if cached else page,
            "standings": entries,
            "has_next": cached.get("has_next", False) if cached else False,
            "stale": stale,
            "synced_at": _synced_at(sync),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── FPL session cookie + live team (authenticated pass-through) ─────

_LIVE_CACHE: dict[int, tuple[float, dict]] = {}
# 30s matches FPL's own poll cadence and keeps us well under the 1 req/s
# informal rate ceiling (see docs/research/fpl-auth-2026.md).
_LIVE_TTL_SECONDS = 30.0


def _require_loopback(request: Request):
    """Fail cookie-writing endpoints unless called from 127.0.0.1/::1."""
    host = (request.client.host if request.client else "") or ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "FPL cookie endpoints are loopback-only")


def _live_cache_get(manager_id: int) -> dict | None:
    import time
    hit = _LIVE_CACHE.get(manager_id)
    if not hit:
        return None
    fetched_at, payload = hit
    if time.monotonic() - fetched_at > _LIVE_TTL_SECONDS:
        _LIVE_CACHE.pop(manager_id, None)
        return None
    return payload


def _live_cache_set(manager_id: int, payload: dict):
    import time
    _LIVE_CACHE[manager_id] = (time.monotonic(), payload)


def _shape_my_team(manager_id: int, raw: dict) -> dict:
    """
    Extract only the fields the UI needs. Anything opaque to us stays out of
    the response so we never echo unknown account data back.
    """
    transfers_node = raw.get("transfers") or {}
    chips_node = raw.get("chips") or []
    picks = raw.get("picks") or []
    # bank / value are returned in tenths of £m (bank=35 → £3.5m). Kept as-is
    # because the rest of Volante expects tenths — see manager_info schema.
    t_limit = transfers_node.get("limit")
    t_made = transfers_node.get("made")
    t_remaining = (
        max(0, t_limit - t_made)
        if isinstance(t_limit, int) and isinstance(t_made, int)
        else None
    )
    return {
        "manager_id": manager_id,
        "event": (raw.get("entry_history") or {}).get("event"),
        "picks": [
            {
                "element": p.get("element"),
                "position": p.get("position"),
                "multiplier": p.get("multiplier"),
                "is_captain": p.get("is_captain"),
                "is_vice_captain": p.get("is_vice_captain"),
                "selling_price": p.get("selling_price"),
                "purchase_price": p.get("purchase_price"),
            }
            for p in picks
        ],
        "transfers": {
            "made": t_made,
            "limit": t_limit,
            "remaining": t_remaining,
            "bank": transfers_node.get("bank"),
            "value": transfers_node.get("value"),
            "cost": transfers_node.get("cost"),
            # "unlimited" signals an active wildcard/free-hit window —
            # the only reliable pending-chip flag FPL exposes via my-team.
            "status": transfers_node.get("status"),
        },
        "chips_staged": [
            c.get("name") for c in chips_node
            if isinstance(c, dict) and c.get("status_for_entry") in {"active", "selected"}
        ],
    }


async def _validate_cookie_for_account(jar: dict[str, str]) -> int:
    """
    Ping /me/ to confirm the cookie is valid, and return the owning entry id.
    Raises FplAuthRequired if /me/ doesn't yield a usable entry id — covers
    both explicit 401/403 and silent "bogus cookie → anonymous JSON" cases
    DataDome sometimes produces.
    """
    me = await fpl.fetch_me(jar)
    player = me.get("player") or {}
    entry = player.get("entry")
    if not isinstance(entry, int):
        # Older shape: me["entry"] directly.
        entry = me.get("entry")
    if not isinstance(entry, int):
        # Cookie passed HTTP but response doesn't identify a user.
        # Treat as auth failure so the UI can prompt a re-paste.
        raise fpl.FplAuthRequired("cookie accepted by FPL but /me/ returned no entry id")
    return entry


@app.post("/api/settings/fpl-cookie")
async def settings_set_fpl_cookie(req: FplCookieRequest, request: Request):
    """
    Paste FPL cookie, validate with a live /me/ ping, and store locally.
    Loopback only. Cookie value is never returned in the response.
    """
    _require_loopback(request)
    parsed = fpl_auth.parse_cookie_input(req.raw)
    if not fpl_auth.has_credential(parsed):
        raise HTTPException(
            400,
            "Cookie input must include access_token (new auth flow) "
            "or pl_profile (legacy accounts).",
        )
    try:
        account_id = await _validate_cookie_for_account(parsed)
    except fpl.FplAuthRequired:
        raise HTTPException(401, "Cookie rejected by FPL — expired or invalid")
    except fpl.FplError as e:
        raise HTTPException(503, f"Could not validate with FPL: {e}")
    fpl_auth.save_cookies(parsed, account_id=account_id)
    fpl_auth.audit("/me/", account_id, 200)
    return fpl_auth.get_status()


@app.get("/api/settings/fpl-status")
async def settings_fpl_status():
    return fpl_auth.get_status()


@app.delete("/api/settings/fpl-cookie")
async def settings_clear_fpl_cookie(request: Request):
    _require_loopback(request)
    fpl_auth.clear_cookies()
    _LIVE_CACHE.clear()
    return {"ok": True}


@app.get("/api/live/{manager_id}/squad")
async def live_squad(manager_id: int):
    """
    Live (pre-deadline) squad for the given manager. Returns 428 with a
    typed reason if cookie is missing, expired, or for a different account.
    """
    cached = _live_cache_get(manager_id)
    if cached:
        return cached

    jar = fpl_auth.get_cookie_jar()
    if not jar:
        raise HTTPException(428, detail={
            "reason": "no_cookie",
            "message": "Paste your FPL cookie in Settings to see live data.",
        })

    stored = fpl_auth.load_cookies() or {}
    stored_account = stored.get("account_id")
    if isinstance(stored_account, int) and stored_account != manager_id:
        raise HTTPException(428, detail={
            "reason": "account_mismatch",
            "message": (
                f"Stored cookie belongs to manager #{stored_account}, not #{manager_id}."
            ),
            "stored_account_id": stored_account,
        })

    try:
        raw = await fpl.fetch_my_team(jar, manager_id)
    except fpl.FplAuthRequired:
        fpl_auth.audit(f"/my-team/{manager_id}/", manager_id, 401)
        raise HTTPException(428, detail={
            "reason": "expired",
            "message": "Your FPL cookie has expired. Re-paste it in Settings.",
        })
    except fpl.FplNotFound:
        fpl_auth.audit(f"/my-team/{manager_id}/", manager_id, 404)
        raise HTTPException(404, f"Manager #{manager_id} not found on FPL")
    except fpl.FplError as e:
        fpl_auth.audit(f"/my-team/{manager_id}/", manager_id, "error")
        raise _http_from_fpl_error(e)

    fpl_auth.audit(f"/my-team/{manager_id}/", manager_id, 200)
    fpl_auth.mark_validated(manager_id)
    result = _shape_my_team(manager_id, raw)
    _live_cache_set(manager_id, result)
    return result


@app.get("/api/manager/{manager_id}/transfers")
async def manager_transfers(manager_id: int, refresh: bool = False):
    """Get a manager's cached transfer history."""
    try:
        conn = await db.get_db()
        try:
            sync = await db.get_sync(conn, fpl.manager_transfers_sync_key(manager_id))
            transfers = await db.get_manager_transfers(conn, manager_id)
        finally:
            await conn.close()

        stale = refresh or fpl.is_stale(sync, fpl.MANAGER_TRANSFERS_TTL)
        if not transfers or stale:
            try:
                await fpl.sync_manager_transfers(manager_id)
                conn = await db.get_db()
                try:
                    sync = await db.get_sync(conn, fpl.manager_transfers_sync_key(manager_id))
                    transfers = await db.get_manager_transfers(conn, manager_id)
                finally:
                    await conn.close()
                stale = False
            except fpl.FplError as exc:
                if not transfers:
                    raise _http_from_fpl_error(exc)
                stale = True

        result = {
            "transfers": transfers,
            "stale": stale,
            "synced_at": _synced_at(sync),
        }
        await _register_background_manager(manager_id, "manager_transfers")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Live Gameweek ───────────────────────────────────────────────────


@app.get("/api/live/{manager_id}")
async def live_gameweek(manager_id: int):
    """
    Live gameweek dashboard: live points and fixture statuses.
    Only meaningful during a live gameweek.
    """
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current_event = await db.get_current_event(conn)
            if not current_event:
                return {"is_live": False, "reason": "no_current_event"}

            fixtures = await db.get_event_fixtures(conn, current_event)
            squad = await db.get_manager_squad(conn, manager_id, current_event)
            mgr_rows = await conn.execute_fetchall(
                "SELECT * FROM manager_info WHERE id=?", (manager_id,)
            )
            mgr_info = dict(mgr_rows[0]) if mgr_rows else {}
        finally:
            await conn.close()

        if not squad:
            try:
                await fpl.sync_manager(manager_id)
                conn = await db.get_db()
                try:
                    squad = await db.get_manager_squad(conn, manager_id, current_event)
                    mgr_rows = await conn.execute_fetchall(
                        "SELECT * FROM manager_info WHERE id=?", (manager_id,)
                    )
                    mgr_info = dict(mgr_rows[0]) if mgr_rows else {}
                finally:
                    await conn.close()
            except fpl.FplError as exc:
                raise _http_from_fpl_error(exc)

        # Classify fixtures
        now = datetime.now(timezone.utc)
        started = 0
        in_progress = 0
        finished_count = 0
        upcoming = 0
        fixture_details = []
        for f in fixtures:
            ko_str = f.get("kickoff_time")
            ko = datetime.fromisoformat(ko_str.replace("Z", "+00:00")) if ko_str else None
            if f.get("finished"):
                status = "finished"
                finished_count += 1
                started += 1
            elif ko and ko <= now:
                status = "in_progress"
                in_progress += 1
                started += 1
            else:
                status = "upcoming"
                upcoming += 1

            # Estimate minutes played
            minutes_est = 0
            if status == "in_progress" and ko:
                elapsed = (now - ko).total_seconds() / 60
                minutes_est = min(int(elapsed), 95)
            elif status == "finished":
                minutes_est = 90

            fixture_details.append({
                **f,
                "status": status,
                "minutes_est": minutes_est,
            })

        is_live = started > 0 and finished_count < len(fixtures)
        has_started = started > 0

        # If nothing has started yet, still return gameweek info
        if not has_started:
            # Snapshot EP before GW starts
            player_ids = [s["player_id"] for s in squad]
            await fpl.snapshot_ep_for_event(current_event, player_ids)
            return {
                "is_live": False,
                "has_started": False,
                "event": current_event,
                "gw_status": {
                    "total_fixtures": len(fixtures),
                    "started": 0, "in_progress": 0,
                    "finished": 0, "upcoming": upcoming,
                },
            }

        # Live data: sync live scores
        try:
            await fpl.sync_live_gameweek(current_event)
        except fpl.FplError:
            pass

        player_ids = [s["player_id"] for s in squad]
        # Snapshot EP (idempotent — only writes if not already stored)
        await fpl.snapshot_ep_for_event(current_event, player_ids)

        conn = await db.get_db()
        try:
            live_data = await db.get_live_gw(conn, current_event, player_ids)
            ep_snaps = await db.get_ep_snapshots(conn, current_event, player_ids)
        finally:
            await conn.close()

        # Build player live cards
        starters = [s for s in squad if s["squad_position"] <= 11]
        bench = [s for s in squad if s["squad_position"] > 11]
        live_players = []
        total_live_pts = 0
        captain_live_pts = 0

        for s in squad:
            pid = s["player_id"]
            live = live_data.get(pid, {})
            live_pts = live.get("total_points", 0)
            multiplier = s.get("multiplier", 1)
            effective_pts = live_pts * multiplier

            # Find which fixture this player is in
            team_id = s["team_id"]
            player_fixture = None
            player_fixture_status = "upcoming"
            for fd in fixture_details:
                if fd["team_h"] == team_id or fd["team_a"] == team_id:
                    is_home = fd["team_h"] == team_id
                    opp_short = fd["away_short"] if is_home else fd["home_short"]
                    h_score = fd.get("team_h_score") or 0
                    a_score = fd.get("team_a_score") or 0
                    player_fixture = {
                        "home": fd["home_short"],
                        "away": fd["away_short"],
                        "home_score": h_score,
                        "away_score": a_score,
                        "opponent": opp_short,
                        "is_home": is_home,
                        "minutes_est": fd["minutes_est"],
                    }
                    player_fixture_status = fd["status"]
                    break

            pre_ep = ep_snaps.get(pid, s.get("ep_next") or s.get("form") or 0)

            card = {
                "id": pid,
                "web_name": s["web_name"],
                "team_short": s["team_short"],
                "position": analysis.POS_NAMES.get(s["pos_type"], "???"),
                "pos_type": s["pos_type"],
                "is_captain": bool(s["is_captain"]),
                "is_starter": s["squad_position"] <= 11,
                "multiplier": multiplier,
                "live_points": live_pts,
                "effective_points": effective_pts,
                "pre_gw_ep": round(pre_ep, 1) if pre_ep else None,
                "minutes": live.get("minutes", 0),
                "goals": live.get("goals_scored", 0),
                "assists": live.get("assists", 0),
                "bonus": live.get("bonus", 0),
                "bps": live.get("bps", 0),
                "clean_sheets": live.get("clean_sheets", 0),
                "saves": live.get("saves", 0),
                "yellow_cards": live.get("yellow_cards", 0),
                "red_cards": live.get("red_cards", 0),
                "fixture_status": player_fixture_status,
                "fixture": player_fixture,
                "status": s["status"],
            }
            live_players.append(card)

            if s["squad_position"] <= 11:
                total_live_pts += effective_pts
                if s["is_captain"]:
                    captain_live_pts = effective_pts

        # Pre-GW total EP for comparison
        pre_gw_total_ep = sum(
            (ep_snaps.get(s["player_id"], s.get("ep_next") or s.get("form") or 2))
            * (2 if s["is_captain"] else 1)
            for s in starters
        )

        # Build fixture summary with squad context
        fixture_summary = []
        for fd in fixture_details:
            squad_in_match = [
                p for p in live_players
                if p["fixture"] and p["fixture"]["home"] == fd["home_short"]
                and p["fixture"]["away"] == fd["away_short"]
            ]
            your_pts = sum(p["effective_points"] for p in squad_in_match if p["is_starter"])
            fixture_summary.append({
                "id": fd["id"],
                "home": fd["home_short"],
                "away": fd["away_short"],
                "home_score": fd.get("team_h_score"),
                "away_score": fd.get("team_a_score"),
                "status": fd["status"],
                "minutes_est": fd["minutes_est"],
                "kickoff": fd.get("kickoff_time"),
                "squad_players": [{"name": p["web_name"], "pts": p["effective_points"],
                                    "captain": p["is_captain"]} for p in squad_in_match if p["is_starter"]],
                "your_points": your_pts,
            })

        result = {
            "is_live": is_live,
            "has_started": has_started,
            "event": current_event,
            "manager": {
                "id": manager_id,
                "name": mgr_info.get("team_name", ""),
                "player_name": mgr_info.get("player_name", ""),
                "overall_points": mgr_info.get("overall_points"),
                "overall_rank": mgr_info.get("overall_rank"),
            },
            "gw_status": {
                "total_fixtures": len(fixtures),
                "started": started,
                "in_progress": in_progress,
                "finished": finished_count,
                "upcoming": upcoming,
            },
            "live_points": {
                "total": total_live_pts,
                "captain_points": captain_live_pts,
                "pre_gw_ep": round(pre_gw_total_ep, 1),
            },
            "players": live_players,
            "fixtures": fixture_summary,
        }
        await _register_background_manager(manager_id, "live_gameweek")
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/live/{manager_id}/accuracy")
async def prediction_accuracy(manager_id: int, weeks: int = Query(default=6, ge=1, le=20)):
    """Compare pre-GW EP predictions vs actual points for past gameweeks."""
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current_event = await db.get_current_event(conn)
            if not current_event:
                return {"weeks": [], "summary": None}

            # Get all EP snapshots for this manager's squad across recent GWs
            results = []
            for ev in range(max(1, current_event - weeks), current_event + 1):
                squad = await db.get_manager_squad(conn, manager_id, ev)
                if not squad:
                    continue
                starters = [s for s in squad if s["squad_position"] <= 11]
                starter_ids = [s["player_id"] for s in starters]

                ep_snaps = await db.get_ep_snapshots(conn, ev, starter_ids)
                if not ep_snaps:
                    continue

                # Get actual points from player_gws
                actual_data = await conn.execute_fetchall(
                    f"""SELECT player_id, total_points FROM player_gws
                        WHERE event=? AND player_id IN ({','.join('?' * len(starter_ids))})""",
                    [ev] + starter_ids,
                )
                actual_by_pid = {r["player_id"]: r["total_points"] for r in actual_data}

                predicted_total = 0.0
                actual_total = 0
                player_details = []
                for s in starters:
                    pid = s["player_id"]
                    ep = ep_snaps.get(pid)
                    actual = actual_by_pid.get(pid)
                    if ep is None or actual is None:
                        continue
                    mult = 2 if s["is_captain"] else 1
                    predicted_total += ep * mult
                    actual_total += actual * mult
                    player_details.append({
                        "web_name": s["web_name"],
                        "team_short": s["team_short"],
                        "predicted": round(ep, 1),
                        "actual": actual,
                        "diff": round(actual - ep, 1),
                        "captain": bool(s["is_captain"]),
                    })

                if player_details:
                    results.append({
                        "event": ev,
                        "predicted": round(predicted_total, 1),
                        "actual": actual_total,
                        "diff": round(actual_total - predicted_total, 1),
                        "accuracy_pct": round(min(actual_total, predicted_total) / max(actual_total, predicted_total, 0.1) * 100, 1),
                        "players": sorted(player_details, key=lambda p: abs(p["diff"]), reverse=True),
                    })

            # Summary stats
            summary = None
            if results:
                diffs = [r["diff"] for r in results]
                abs_diffs = [abs(d) for d in diffs]
                summary = {
                    "weeks_tracked": len(results),
                    "mean_diff": round(sum(diffs) / len(diffs), 1),
                    "mean_abs_error": round(sum(abs_diffs) / len(abs_diffs), 1),
                    "avg_accuracy_pct": round(sum(r["accuracy_pct"] for r in results) / len(results), 1),
                    "best_week": min(results, key=lambda r: abs(r["diff"])),
                    "worst_week": max(results, key=lambda r: abs(r["diff"])),
                }

            result = {"weeks": results, "summary": summary}
            await _register_background_manager(manager_id, "prediction_accuracy")
            return result
        finally:
            await conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/gameweek-status")
async def gameweek_status():
    """Quick check: is the current gameweek live?"""
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current_event = await db.get_current_event(conn)
            if not current_event:
                return {"is_live": False, "event": None}
            fixtures = await db.get_event_fixtures(conn, current_event)
        finally:
            await conn.close()

        now = datetime.now(timezone.utc)
        started = 0
        finished_count = 0
        for f in fixtures:
            if f.get("finished"):
                started += 1
                finished_count += 1
            elif f.get("kickoff_time"):
                ko = datetime.fromisoformat(f["kickoff_time"].replace("Z", "+00:00"))
                if ko <= now:
                    started += 1

        next_event = min(current_event + 1, 38)

        return {
            "is_live": started > 0 and finished_count < len(fixtures),
            "all_finished": finished_count == len(fixtures),
            "event": current_event,
            "next_event": next_event,
            "started": started,
            "finished": finished_count,
            "total": len(fixtures),
        }
    except Exception as e:
        return {"is_live": False, "event": None, "error": str(e)}


# ── Transfer Lab ─────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    sell_ids: list[int]
    n: int = 5
    horizon: int = 5


@app.post("/api/xray/{manager_id}/recommend")
async def recommend_transfers(manager_id: int, req: RecommendRequest):
    """Get smart replacement recommendations for 1+ players."""
    try:
        result = await transfers_engine.recommend_replacements(
            manager_id, req.sell_ids, n=req.n, horizon=req.horizon,
        )
        await _register_background_manager(manager_id, "recommend_transfers")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/xray/{manager_id}/suggest")
async def suggest_transfers(manager_id: int, n: int = Query(default=5, ge=1, le=15)):
    """Proactive top-N transfer suggestions across the whole squad."""
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current = await db.get_current_event(conn)
            squad = await db.get_manager_squad(conn, manager_id, current) if current else []
            mgr_sync = await db.get_sync(conn, fpl.manager_sync_key(manager_id))
        finally:
            await conn.close()

        if not squad or fpl.is_stale(mgr_sync, fpl.MANAGER_TTL):
            try:
                await fpl.sync_manager(manager_id)
            except fpl.FplError as exc:
                if not squad:
                    raise _http_from_fpl_error(exc)

        result = await transfers_engine.suggest_best_transfers(manager_id, n=n)
        await _register_background_manager(manager_id, "suggest_transfers")
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/manager/{manager_id}/transfer-analysis")
async def transfer_analysis(manager_id: int):
    """Analyze past transfers: score each, detect habit patterns."""
    try:
        await _ensure_core_cache()
        # ensure transfer data is synced
        conn = await db.get_db()
        try:
            sync = await db.get_sync(conn, fpl.manager_transfers_sync_key(manager_id))
            has_data = await db.get_manager_transfers(conn, manager_id)
        finally:
            await conn.close()
        if not has_data or fpl.is_stale(sync, fpl.MANAGER_TRANSFERS_TTL):
            try:
                await fpl.sync_manager_transfers(manager_id)
            except fpl.FplError:
                if not has_data:
                    raise

        result = await transfers_engine.analyze_past_transfers(manager_id)
        await _register_background_manager(manager_id, "transfer_analysis")
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


@app.post("/api/intel/import-csv", include_in_schema=_internal_mode_enabled())
async def import_intel_csv(req: IntelImportRequest, request: Request):
    """Import a local CSV snapshot of external projections into the intel DB."""
    try:
        _require_intel_access(request)
        return await intel_engine.import_projection_csv(
            req.path,
            req.source_key,
            label=req.label,
            event=req.event,
            horizon=req.horizon,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


@app.post("/api/intel/{manager_id}/run", include_in_schema=_internal_mode_enabled())
async def run_private_intel(
    manager_id: int,
    request: Request,
    horizon: int = Query(default=5, ge=1, le=8),
    event: int | None = None,
    deliver: bool = True,
):
    """Run the private transfer intelligence analyzer and persist alerts."""
    try:
        _require_intel_access(request)
        await _ensure_core_cache()
        result = await intel_engine.run_transfer_intelligence(
            manager_id,
            event=event,
            horizon=horizon,
            persist=True,
            deliver=deliver,
        )
        await _register_background_manager(manager_id, "intel_run")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


@app.get("/api/intel/{manager_id}/alerts", include_in_schema=_internal_mode_enabled())
async def get_private_intel_alerts(
    manager_id: int,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Read stored private intel alerts for a manager."""
    try:
        _require_intel_access(request)
        alerts = await intel_engine.list_alerts(manager_id, status=status, limit=limit)
        await _register_background_manager(manager_id, "intel_alerts")
        return {"alerts": alerts}
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


# ── Fixture Exposure ─────────────────────────────────────────────────

@app.get("/api/xray/{manager_id}/fixtures")
async def squad_fixture_exposure(manager_id: int, event: int | None = None):
    """
    For each open GW fixture involving your starters: exposure analysis
    and outcome-conditioned point ranges.
    """
    try:
        await _ensure_core_cache()
        conn = await db.get_db()
        try:
            current = await db.get_current_event(conn)
            squad = await db.get_manager_squad(conn, manager_id, event or current) if current else []
        finally:
            await conn.close()

        if not squad:
            try:
                await fpl.sync_manager(manager_id)
            except fpl.FplError as exc:
                raise _http_from_fpl_error(exc)

        result = await fixture_exposure.gameweek_exposure_report(manager_id, event)
        await _register_background_manager(manager_id, "fixture_exposure")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8556, reload=True)
