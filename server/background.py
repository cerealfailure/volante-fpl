"""
Background automation for Volante.

Runs inside the API process and keeps the local DB warm:
  - polls official FPL core data on a schedule
  - stores append-only availability/news tape rows
  - persists internal projection snapshots to SQLite
  - refreshes live gameweek cache during active matches
  - optionally refreshes configured managers
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os

import db
import fpl
import projections


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(key: str, default: int, minimum: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return max(int(raw), minimum)
    except (TypeError, ValueError):
        return default


def _parse_manager_ids() -> list[int]:
    ids = []
    raw = os.environ.get("VOLANTE_BACKGROUND_MANAGER_IDS", "")
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            continue

    intel_manager = os.environ.get("VOLANTE_INTEL_MANAGER_ID")
    if intel_manager:
        try:
            ids.append(int(intel_manager))
        except ValueError:
            pass

    seen = set()
    ordered = []
    for manager_id in ids:
        if manager_id in seen:
            continue
        seen.add(manager_id)
        ordered.append(manager_id)
    return ordered


def _parse_projection_horizons() -> tuple[int, ...]:
    raw = os.environ.get("VOLANTE_BACKGROUND_PROJECTION_HORIZONS", "1,5")
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(projections.normalize_horizon(int(token)))
        except ValueError:
            continue
    if not values:
        values = [1, 5]
    return tuple(dict.fromkeys(values))


class BackgroundManager:
    def __init__(self):
        self.enabled = _env_bool("VOLANTE_BACKGROUND_ENABLED", True)
        self.core_minutes = _env_int("VOLANTE_BACKGROUND_CORE_MINUTES", 60, 5)
        self.news_minutes = _env_int("VOLANTE_BACKGROUND_NEWS_MINUTES", 15, 3)
        self.news_window_hours = _env_int("VOLANTE_BACKGROUND_NEWS_WINDOW_HOURS", 72, 6)
        self.live_seconds = _env_int("VOLANTE_BACKGROUND_LIVE_SECONDS", 90, 30)
        self.manager_minutes = _env_int("VOLANTE_BACKGROUND_MANAGER_MINUTES", 30, 5)
        self.manager_ttl_hours = _env_int("VOLANTE_BACKGROUND_MANAGER_TTL_HOURS", 24, 1)
        self.projection_delta = float(os.environ.get("VOLANTE_BACKGROUND_PROJECTION_DELTA", "0.2") or 0.2)
        self.pinned_manager_ids = _parse_manager_ids()
        self.projection_horizons = _parse_projection_horizons()
        self.manager_wakeup = asyncio.Event()
        self.tasks: list[asyncio.Task] = []
        self.state = {
            "enabled": self.enabled,
            "started_at": None,
            "active_manager_ids": [],
            "jobs": {},
            "config": {
                "core_minutes": self.core_minutes,
                "news_minutes": self.news_minutes,
                "news_window_hours": self.news_window_hours,
                "live_seconds": self.live_seconds,
                "manager_minutes": self.manager_minutes,
                "manager_ttl_hours": self.manager_ttl_hours,
                "pinned_manager_ids": self.pinned_manager_ids,
                "projection_horizons": list(self.projection_horizons),
                "projection_delta": self.projection_delta,
            },
        }

    def snapshot(self) -> dict:
        data = deepcopy(self.state)
        ready = bool(data["jobs"].get("core", {}).get("last_success"))
        if data.get("active_manager_ids"):
            ready = ready and bool(data["jobs"].get("managers", {}).get("last_success"))
        data["ready"] = ready
        ready_jobs = [job for job, info in data["jobs"].items() if info.get("last_success")]
        data["ready_jobs"] = ready_jobs
        return data

    async def start(self):
        if not self.enabled:
            self.state["started_at"] = _now_iso()
            return
        self.state["started_at"] = _now_iso()
        await self._seed_pinned_managers()
        self.tasks = [
            asyncio.create_task(self._core_loop(), name="volante-bg-core"),
            asyncio.create_task(self._live_loop(), name="volante-bg-live"),
            asyncio.create_task(self._manager_loop(), name="volante-bg-managers"),
        ]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks = []

    async def _mark_job(self, job: str, ok: bool, meta: dict | None = None, error: str | None = None):
        now = _now_iso()
        item = self.state["jobs"].setdefault(job, {"required": job in {"core", "live"}})
        item["last_run"] = now
        if ok:
            item["last_success"] = now
            item["last_meta"] = meta or {}
            item["last_error"] = None
        else:
            item["last_error"] = error
            if meta:
                item["last_meta"] = meta

        conn = await db.get_db()
        try:
            await db.set_sync(conn, f"background:{job}", {
                "ok": ok,
                "error": error,
                **(meta or {}),
            })
            await conn.commit()
        finally:
            await conn.close()

    async def _seconds_until_news_window(self) -> int:
        conn = await db.get_db()
        try:
            current_event = await db.get_current_event(conn)
            next_fixture = await db.get_next_open_fixture(conn, current_event)
        finally:
            await conn.close()
        if not next_fixture or not next_fixture.get("kickoff_time"):
            return self.core_minutes * 60
        try:
            kickoff = datetime.fromisoformat(str(next_fixture["kickoff_time"]).replace("Z", "+00:00"))
        except ValueError:
            return self.core_minutes * 60
        delta_hours = (kickoff - datetime.now(timezone.utc)).total_seconds() / 3600.0
        if delta_hours <= self.news_window_hours:
            return self.news_minutes * 60
        return self.core_minutes * 60

    async def register_manager(self, manager_id: int, source: str = "api", pinned: bool = False):
        if manager_id <= 0:
            return
        conn = await db.get_db()
        try:
            await db.touch_background_manager(conn, manager_id, source=source, pinned=pinned)
            await conn.commit()
        finally:
            await conn.close()

        active = list(self.state.get("active_manager_ids") or [])
        if manager_id not in active:
            active.append(manager_id)
            active.sort()
            self.state["active_manager_ids"] = active
            manager_job = self.state["jobs"].setdefault("managers", {"required": False})
            last_meta = manager_job.get("last_meta") or {}
            warmed_ids = set(last_meta.get("active_manager_ids") or [])
            if manager_id not in warmed_ids:
                manager_job["last_success"] = None
        self.manager_wakeup.set()

    async def _seed_pinned_managers(self):
        if not self.pinned_manager_ids:
            return
        conn = await db.get_db()
        try:
            for manager_id in self.pinned_manager_ids:
                await db.touch_background_manager(conn, manager_id, source="env", pinned=True)
            await conn.commit()
        finally:
            await conn.close()

    async def _load_warm_managers(self) -> list[dict]:
        conn = await db.get_db()
        try:
            rows = await db.list_background_managers(
                conn,
                max_age_hours=self.manager_ttl_hours,
                include_pinned=True,
            )
        finally:
            await conn.close()

        seen = set()
        ordered = []
        for row in rows:
            manager_id = int(row["manager_id"])
            if manager_id in seen:
                continue
            seen.add(manager_id)
            ordered.append(row)
        self.state["active_manager_ids"] = [row["manager_id"] for row in ordered]
        return ordered

    async def _core_loop(self):
        while True:
            try:
                bootstrap = await fpl.sync_bootstrap()
                fixtures = await fpl.sync_fixtures()
                conn = await db.get_db()
                try:
                    current_event = await db.get_current_event(conn)
                    projection_summary = await projections.persist_internal_projection_snapshots(
                        conn,
                        current_event,
                        self.projection_horizons,
                        self.projection_delta,
                    )
                finally:
                    await conn.close()
                await self._mark_job("core", True, {
                    "bootstrap_event": bootstrap.get("current_event"),
                    "fixture_count": fixtures.get("count"),
                    "projection_rows_written": projection_summary.get("rows_written"),
                    "projection_target_event": projection_summary.get("target_event"),
                })
            except Exception as exc:
                await self._mark_job("core", False, error=str(exc))
            await asyncio.sleep(await self._seconds_until_news_window())

    async def _live_loop(self):
        while True:
            try:
                conn = await db.get_db()
                try:
                    current_event = await db.get_current_event(conn)
                    live_event = await db.get_next_open_event(conn, current_event) if current_event else None
                    fixtures = await db.get_event_fixtures(conn, live_event) if live_event else []
                finally:
                    await conn.close()

                now = datetime.now(timezone.utc)
                started = 0
                finished = 0
                for fixture in fixtures:
                    if fixture.get("finished"):
                        started += 1
                        finished += 1
                        continue
                    kickoff = fixture.get("kickoff_time")
                    if kickoff:
                        try:
                            if datetime.fromisoformat(str(kickoff).replace("Z", "+00:00")) <= now:
                                started += 1
                        except ValueError:
                            pass
                is_live = bool(fixtures) and started > 0 and finished < len(fixtures)
                if is_live and live_event is not None:
                    result = await fpl.sync_live_gameweek(live_event)
                    await self._mark_job("live", True, {
                        "event": live_event,
                        "player_count": result.get("player_count"),
                        "cached": result.get("cached", False),
                    })
                else:
                    await self._mark_job("live", True, {
                        "event": live_event,
                        "live": False,
                        "fixtures": len(fixtures),
                    })
            except Exception as exc:
                await self._mark_job("live", False, error=str(exc))
            await asyncio.sleep(self.live_seconds)

    async def _manager_loop(self):
        while True:
            summary = {"managers": [], "active_manager_ids": []}
            ok = True
            try:
                manager_rows = await self._load_warm_managers()
                summary["active_manager_ids"] = [row["manager_id"] for row in manager_rows]
                if not manager_rows:
                    await self._mark_job("managers", True, summary)
                    await self._wait_for_manager_cycle()
                    continue

                warmed_ids = []
                for item in manager_rows:
                    manager_id = item["manager_id"]
                    try:
                        result = await fpl.sync_manager(
                            manager_id,
                            include_histories=False,
                            include_transfers=True,
                        )
                        warmed_ids.append(manager_id)
                        summary["managers"].append({
                            "manager_id": manager_id,
                            "event": result.get("event"),
                            "league_count": result.get("league_count"),
                            "transfer_count": result.get("transfer_count"),
                            "source": item.get("source"),
                            "pinned": bool(item.get("pinned")),
                            "last_seen_at": item.get("last_seen_at"),
                        })
                    except Exception as exc:
                        ok = False
                        summary["managers"].append({
                            "manager_id": manager_id,
                            "source": item.get("source"),
                            "pinned": bool(item.get("pinned")),
                            "error": str(exc),
                        })
                if warmed_ids:
                    conn = await db.get_db()
                    try:
                        await db.mark_background_managers_warmed(conn, warmed_ids)
                        await conn.commit()
                    finally:
                        await conn.close()
                await self._mark_job("managers", ok, summary, None if ok else "one or more manager refreshes failed")
            except Exception as exc:
                await self._mark_job("managers", False, summary, str(exc))
            await self._wait_for_manager_cycle()

    async def _wait_for_manager_cycle(self):
        try:
            await asyncio.wait_for(self.manager_wakeup.wait(), timeout=self.manager_minutes * 60)
        except asyncio.TimeoutError:
            pass
        self.manager_wakeup.clear()


manager = BackgroundManager()
