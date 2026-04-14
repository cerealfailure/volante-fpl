"""
Private transfer intelligence layer.

This module is intentionally backend-first:
  - ingests optional local/third-party projection snapshots
  - blends them with Volante's internal xP engine
  - runs a higher-conviction transfer/risk analyzer
  - persists alerts and can deliver them to a local outbox or webhook

The analyzer is designed to remain useful with zero external APIs:
drop CSVs in manually, or run with the internal model only.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
try:
    import aiohttp
except ModuleNotFoundError:  # pragma: no cover - optional transport
    aiohttp = None

import analysis
import db
import projections
import transfers

MODEL_VERSION = "transfer-intel-v2"
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_IMPORT_ROOT = ROOT_DIR / "data" / "external"

DEFAULT_SIGNAL_SOURCES = [
    {
        "key": "fpl_internal",
        "label": "Volante Internal xP",
        "source_type": "system",
        "weight": 0.62,
        "meta": {"description": "Fixture-adjusted internal xP engine."},
    },
    {
        "key": "manual_csv",
        "label": "Manual CSV Import",
        "source_type": "manual",
        "weight": 0.24,
        "meta": {"description": "Local CSV imports from xG/projection sites."},
    },
    {
        "key": "market_manual",
        "label": "Manual External Overlay",
        "source_type": "manual",
        "weight": 0.14,
        "meta": {"description": "Optional ownership and projection overlays."},
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_outbox_path() -> Path:
    return Path(os.environ.get("VOLANTE_ALERT_OUTBOX", Path.home() / ".volante-fpl" / "intel-alerts.ndjson"))


def _allowed_import_roots() -> list[Path]:
    roots = [DEFAULT_IMPORT_ROOT]
    extra = os.environ.get("VOLANTE_INTEL_IMPORT_ROOTS", "")
    for raw in extra.split(os.pathsep):
        raw = raw.strip()
        if not raw:
            continue
        roots.append(Path(raw).expanduser())
    resolved = []
    for root in roots:
        try:
            resolved.append(root.resolve())
        except FileNotFoundError:
            resolved.append(root)
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_import_path(csv_path: str) -> Path:
    raw_path = Path(csv_path).expanduser()
    path = raw_path if raw_path.is_absolute() else (ROOT_DIR / raw_path)
    path = path.resolve()

    allowed_roots = _allowed_import_roots()
    if not any(_is_relative_to(path, root) for root in allowed_roots):
        allowed = ", ".join(str(root) for root in allowed_roots)
        raise ValueError(
            "Projection imports must live under an allowed directory. "
            f"Place the file under one of: {allowed}"
        )
    return path


def _parse_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _csv_value(row: dict, *keys: str):
    for key in keys:
        if key in row and row[key] not in ("", None):
            return row[key]
    return None


def _severity(score: float, high: float = 7.0, medium: float = 4.5) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "info"


async def ensure_intel_defaults(database):
    for source in DEFAULT_SIGNAL_SOURCES:
        await db.upsert_signal_source(
            database,
            source["key"],
            source["label"],
            source["source_type"],
            source["weight"],
            True,
            source.get("meta"),
        )

    await db.upsert_alert_delivery_target(
        database,
        "local_outbox",
        "file",
        True,
        {"path": str(_default_outbox_path())},
    )

    if os.environ.get("VOLANTE_ALERT_STDOUT") == "1":
        await db.upsert_alert_delivery_target(database, "stdout", "stdout", True, {})

    webhook = os.environ.get("VOLANTE_ALERT_WEBHOOK")
    if webhook and aiohttp is not None:
        await db.upsert_alert_delivery_target(
            database,
            "webhook",
            "webhook",
            True,
            {"url": webhook},
        )


async def import_projection_csv(
    csv_path: str,
    source_key: str,
    label: str | None = None,
    event: int | None = None,
    horizon: int = 5,
) -> dict:
    path = _resolve_import_path(csv_path)
    if not path.exists():
        raise ValueError(f"Projection file not found: {path}")

    database = await db.get_db()
    try:
        await ensure_intel_defaults(database)
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")

        label = label or source_key.replace("_", " ").title()
        await db.upsert_signal_source(database, source_key, label, "manual", 0.24, True, {"imported_from": str(path)})

        player_rows = await database.execute_fetchall("""
            SELECT p.id, p.web_name, p.first_name, p.second_name, t.short_name as team_short
            FROM players p
            JOIN teams t ON p.team_id = t.id
        """)
        name_index = defaultdict(list)
        for row in player_rows:
            item = {
                "id": row["id"],
                "web_name": (row["web_name"] or "").strip().lower(),
                "full_name": " ".join(
                    part.strip() for part in (row["first_name"] or "", row["second_name"] or "") if part and part.strip()
                ).lower(),
                "team_short": (row["team_short"] or "").strip().lower(),
            }
            for key in {
                item["web_name"],
                item["full_name"],
                f"{item['web_name']}|{item['team_short']}" if item["team_short"] else "",
                f"{item['full_name']}|{item['team_short']}" if item["team_short"] and item["full_name"] else "",
            }:
                if key:
                    name_index[key].append(item)
        snapshot_at = _now_iso()

        imported_rows = []
        skipped_rows = 0
        ambiguous_rows = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw_row in reader:
                pid_value = _csv_value(raw_row, "player_id", "id")
                player_id = int(pid_value) if pid_value not in (None, "") else None
                if player_id is None:
                    name = _csv_value(raw_row, "web_name", "player", "name")
                    if not name:
                        skipped_rows += 1
                        continue
                    team_hint = str(_csv_value(raw_row, "team_short", "team") or "").strip().lower()
                    name_key = str(name).strip().lower()
                    lookup_keys = []
                    if team_hint:
                        lookup_keys.extend([f"{name_key}|{team_hint}"])
                    lookup_keys.append(name_key)

                    matches = []
                    for lookup_key in lookup_keys:
                        matches = name_index.get(lookup_key, [])
                        if matches:
                            break
                    if len(matches) == 1:
                        player_id = matches[0]["id"]
                    elif len(matches) > 1:
                        ambiguous_rows += 1
                        continue
                if player_id is None:
                    skipped_rows += 1
                    continue

                xg = _parse_float(_csv_value(raw_row, "xg", "expected_goals"))
                xa = _parse_float(_csv_value(raw_row, "xa", "expected_assists"))
                xgi = _parse_float(_csv_value(raw_row, "xgi", "expected_goal_involvements"))
                if xgi is None and xg is not None and xa is not None:
                    xgi = xg + xa

                imported_rows.append({
                    "player_id": player_id,
                    "expected_points": _parse_float(_csv_value(raw_row, "expected_points", "xp", "xP")),
                    "xg": xg,
                    "xa": xa,
                    "xgi": xgi,
                    "expected_minutes": _parse_float(_csv_value(raw_row, "expected_minutes", "minutes")),
                    "selected_pct": _parse_float(_csv_value(raw_row, "selected_pct", "ownership")),
                    "anytime_return_prob": _parse_float(_csv_value(raw_row, "anytime_return_prob", "return_prob")),
                    "clean_sheet_prob": _parse_float(_csv_value(raw_row, "clean_sheet_prob", "cs_prob")),
                    "raw": raw_row,
                })

        if not imported_rows:
            raise ValueError("No valid projection rows found. Include `player_id` or `web_name` in the CSV.")

        await db.upsert_projection_snapshot(database, source_key, snapshot_at, event, horizon, imported_rows)
        await database.commit()
        return {
            "ok": True,
            "source_key": source_key,
            "event": event,
            "horizon": horizon,
            "snapshot_at": snapshot_at,
            "rows_imported": len(imported_rows),
            "rows_skipped": skipped_rows,
            "rows_ambiguous": ambiguous_rows,
            "path": str(path),
        }
    finally:
        await database.close()


def _source_expected_points(player: dict, row: dict) -> tuple[float | None, bool]:
    direct = row.get("expected_points")
    if direct is not None:
        return float(direct), False

    xg = row.get("xg")
    xa = row.get("xa")
    xgi = row.get("xgi")
    cs_prob = row.get("clean_sheet_prob")
    if xg is None and xa is None and xgi is not None:
        xg = xgi * 0.65
        xa = xgi * 0.35
    if xg is None and xa is None:
        return None, True

    pos = player["position"]
    base = 2.0
    goal_component = analysis.POS_GOAL_POINTS.get(pos, 4) * float(xg or 0)
    assist_component = 3.0 * float(xa or 0)
    cs_component = analysis.POS_CS_POINTS.get(pos, 0) * float(cs_prob or 0)
    return base + goal_component + assist_component + cs_component, True


def _weight_for_source(source: dict | None, external_xp: float, internal_xp: float, derived: bool) -> float:
    base = float(source.get("weight", 0.2) if source else 0.2)
    drift = abs(external_xp - internal_xp)
    reliability = max(0.35, 1.0 - min(drift / 6.5, 0.55))
    if derived:
        reliability *= 0.82
    return base * reliability


def _blend_projection_values(values: list[dict], internal_xp: float) -> tuple[float, float, float]:
    if not values:
        return internal_xp, 0.35 * max(internal_xp, 1.0), 0.0

    weights = np.array([max(value["weight"], 1e-6) for value in values], dtype=float)
    xp = np.array([value["xp"] for value in values], dtype=float)
    weights = weights / weights.sum()

    consensus = float(np.average(xp, weights=weights))
    spread = float(np.sqrt(np.average((xp - consensus) ** 2, weights=weights)))
    disagreement = float(abs(consensus - internal_xp))
    uncertainty = spread + 0.28 * disagreement + 0.08 * max(len(values) - 1, 0)
    return consensus, uncertainty, disagreement


def _correlation_pressures(context: dict) -> dict[int, float]:
    if not context["starters"]:
        return {}
    corr = np.array(context["exposure"]["correlation_matrix"], dtype=float)
    pressures = {}
    for idx, player in enumerate(context["starters"]):
        row = np.abs(corr[idx])
        pressure = float((row.sum() - 1.0) / max(len(row) - 1, 1))
        if player.get("is_captain"):
            pressure *= 1.18
        pressures[player["player_id"]] = round(pressure, 3)
    return pressures


def _team_fixture_scores(squad: list[dict], fixtures_by_team: dict[int, list[dict]], horizon: int) -> dict[int, float]:
    scores = {}
    for player in squad:
        team_id = player["team_id"]
        if team_id in scores:
            continue
        scores[team_id] = transfers._fixture_run_score(
            fixtures_by_team.get(team_id, [])[:horizon],
            team_id,
            player.get("pos_type", player.get("position")) in (1, 2),
        )
    return scores


def _position_anomaly_scores(cards: list[dict]):
    by_pos = defaultdict(list)
    for card in cards:
        by_pos[card["position"]].append(card)

    for pos_cards in by_pos.values():
        if not pos_cards:
            continue
        feature_matrix = np.array([
            [
                card["consensus_xp"],
                card["xp_edge"],
                card["uncertainty"],
                card["fixture_score"],
                card["correlation_pressure"],
            ]
            for card in pos_cards
        ], dtype=float)
        mu = feature_matrix.mean(axis=0)
        sigma = feature_matrix.std(axis=0)
        sigma = np.where(sigma < 1e-6, 1.0, sigma)
        weights = np.array([0.7, 1.1, 1.0, 0.6, 1.0], dtype=float)
        z = (feature_matrix - mu) / sigma
        scores = np.sqrt(((z ** 2) * weights).sum(axis=1))
        for card, score in zip(pos_cards, scores):
            card["anomaly_score"] = round(float(score), 2)


def _build_market_radar(cards: list[dict], squad_lookup: dict[int, dict], bank: float, team_counts: Counter) -> list[dict]:
    position_caps = defaultdict(float)
    for player in squad_lookup.values():
        pos = player["pos_type"]
        position_caps[pos] = max(position_caps[pos], (player.get("now_cost") or 0) / 10.0 + bank)

    radar = []
    for card in cards:
        if card["player_id"] in squad_lookup:
            continue
        if card["price"] > position_caps.get(card["position"], bank) + 0.1:
            continue
        team_penalty = 0.35 * max(team_counts.get(card["team_id"], 0) - 1, 0)
        score = (
            card["xp_edge"] * 1.35
            + max(card["fixture_score"], 0) * 0.18
            + max(card.get("anomaly_score", 0) - 1.3, 0) * 0.15
            - card["uncertainty"] * 0.22
            - team_penalty
        )
        if score <= 0.45:
            continue
        radar.append({
            "player_id": card["player_id"],
            "web_name": card["web_name"],
            "team_short": card["team_short"],
            "position": analysis.POS_NAMES.get(card["position"], "???"),
            "price": round(card["price"], 1),
            "consensus_xp": round(card["consensus_xp"], 2),
            "xp_edge": round(card["xp_edge"], 2),
            "fixture_score": round(card["fixture_score"], 2),
            "uncertainty": round(card["uncertainty"], 2),
            "market_score": round(score, 2),
        })
    radar.sort(key=lambda row: (row["market_score"], row["consensus_xp"]), reverse=True)
    return radar[:5]


def _eigen_share(cov: np.ndarray) -> float:
    eigvals = np.linalg.eigvalsh(cov)
    eigvals = eigvals[eigvals > 1e-9]
    if eigvals.size == 0:
        return 0.0
    return float(eigvals[-1] / eigvals.sum())


def _make_alert(
    manager_id: int,
    event: int,
    horizon: int,
    category: str,
    title: str,
    detail: str,
    score: float,
    dedupe_key: str,
    payload: dict | None = None,
) -> dict:
    return {
        "manager_id": manager_id,
        "event": event,
        "horizon": horizon,
        "category": category,
        "severity": _severity(score),
        "title": title,
        "detail": detail,
        "score": round(score, 2),
        "dedupe_key": dedupe_key,
        "payload": payload or {},
        "created_at": _now_iso(),
    }


async def run_transfer_intelligence(
    manager_id: int,
    event: int | None = None,
    horizon: int = 5,
    persist: bool = True,
    deliver: bool = True,
) -> dict:
    database = await db.get_db()
    try:
        await ensure_intel_defaults(database)
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")
        await projections.snapshot_current_availability(
            database,
            event,
            snapshot_kind="intel_run",
            snapshot_reason=f"manager:{manager_id}",
            force_history=True,
        )
        projection_context = await projections.build_projection_context(database, event, horizon)
        projection_event = projection_context["target_event"]

        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad found for manager {manager_id} GW{event}")

        mgr_rows = await database.execute_fetchall("SELECT * FROM manager_info WHERE id=?", (manager_id,))
        manager = dict(mgr_rows[0]) if mgr_rows else {}
        bank = (manager.get("bank") or 0) / 10.0

        all_rows = await database.execute_fetchall("""
            SELECT p.*, t.short_name as team_short, t.name as team_name
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE p.minutes > 0 AND p.status IN ('a', 'd')
        """)
        all_players = [dict(row) for row in all_rows]
        squad_lookup = {player["player_id"]: player for player in squad}
        team_counts = Counter(player["team_id"] for player in squad)
        fixtures_by_team = projection_context["fixtures_by_team"]

        context = await transfers._compute_plan_context(database, squad, projection_event, horizon)
        correlation_pressures = _correlation_pressures(context)
        team_fixture_scores = _team_fixture_scores(squad, fixtures_by_team, horizon)
        source_defs = {source["key"]: source for source in await db.get_signal_sources(database, enabled_only=False)}
        external_rows = await db.get_latest_projection_rows(database, projection_event, horizon)
        external_by_player = defaultdict(list)
        for row in external_rows:
            external_by_player[row["player_id"]].append(row)

        cards = []
        for player in all_players:
            pos = player["position"]
            player_id = player["id"]
            projection = projections.project_player(player, fixtures_by_team, horizon, event, projection_context)
            internal_xp = projection["horizon_ep"]
            availability = projection["availability"]

            source_values = [{
                "source_key": "fpl_internal",
                "xp": internal_xp,
                "weight": float(source_defs.get("fpl_internal", {}).get("weight", 0.62)),
            }]
            raw_sources = []

            for row in external_by_player.get(player_id, []):
                source_xp, derived = _source_expected_points(player, row)
                if source_xp is None:
                    continue
                source_key = row["source_key"]
                weight = _weight_for_source(source_defs.get(source_key), source_xp, internal_xp, derived)
                source_values.append({"source_key": source_key, "xp": source_xp, "weight": weight})
                raw_sources.append({
                    "source_key": source_key,
                    "xp": round(source_xp, 2),
                    "derived": derived,
                })

            consensus_xp, source_uncertainty, disagreement = _blend_projection_values(source_values, internal_xp)
            uncertainty = source_uncertainty + float(availability.get("uncertainty", 0)) * 0.55
            fixture_score = transfers._fixture_run_score(
                fixtures_by_team.get(player["team_id"], [])[:horizon],
                player["team_id"],
                pos in (1, 2),
            )
            correlation_pressure = correlation_pressures.get(player_id, 0.0)
            minutes_risk = max(0.0, 1.0 - float(availability.get("play_probability", 0)))
            squad_count = team_counts.get(player["team_id"], 0)
            price = (player.get("now_cost") or 0) / 10.0
            signal_gap = abs(float(projection.get("official_gap", 0)))

            transfer_pressure = (
                max(0.0, 4.0 - consensus_xp) * 1.12
                + max(0.0, -fixture_score) * 0.13
                + correlation_pressure * 2.1
                + uncertainty * 0.95
                + minutes_risk * 2.4
                + max(squad_count - 1, 0) * 0.38
                + max(signal_gap - 1.5, 0.0) * 0.35
            )
            if player_id in squad_lookup and squad_lookup[player_id]["squad_position"] > 11:
                transfer_pressure += max(price - 4.5, 0) * 0.55

            cards.append({
                "player_id": player_id,
                "web_name": player["web_name"],
                "team_id": player["team_id"],
                "team_short": player["team_short"],
                "team_name": player["team_name"],
                "position": pos,
                "price": price,
                "status": player.get("status"),
                "chance_next": player.get("chance_next"),
                "internal_xp": round(internal_xp, 2),
                "modeled_next_xp": round(projection["next_event_ep"], 2),
                "official_ep_next": round(projection["official_ep_next"], 2),
                "official_gap": round(projection["official_gap"], 2),
                "projection_event": projection_event,
                "consensus_xp": round(consensus_xp, 2),
                "xp_edge": round(consensus_xp - internal_xp, 2),
                "uncertainty": round(uncertainty, 2),
                "source_disagreement": round(disagreement, 2),
                "source_count": len(source_values),
                "fixture_score": round(fixture_score, 2),
                "correlation_pressure": round(correlation_pressure, 3),
                "minutes_risk": round(minutes_risk, 3),
                "availability_reliability": round(float(availability.get("reliability_score", 0)), 3),
                "distortion_rate": round(float(availability.get("distortion_rate", 0)), 3),
                "news_category": availability.get("news_category"),
                "news_purity": round(float(availability.get("news_purity", 0)), 3),
                "expected_minutes_next": round(float(projection.get("expected_minutes_next", 0)), 1),
                "transfer_pressure": round(transfer_pressure, 2),
                "sources": raw_sources,
            })

        _position_anomaly_scores(cards)

        squad_cards = []
        for player in squad:
            card = next(card for card in cards if card["player_id"] == player["player_id"])
            squad_cards.append({
                **card,
                "squad_position": player["squad_position"],
                "is_starter": player["squad_position"] <= 11,
                "is_captain": bool(player.get("is_captain")),
            })

        squad_cards.sort(key=lambda card: card["transfer_pressure"], reverse=True)
        market_radar = _build_market_radar(cards, squad_lookup, bank, team_counts)
        pc1_share = _eigen_share(context["cov"])

        alerts = []
        for card in squad_cards[:2]:
            if card["transfer_pressure"] < 4.2:
                continue
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "sell_pressure",
                f"{card['web_name']} is carrying transfer pressure",
                (
                    f"{card['consensus_xp']:.1f} consensus xP over the next {horizon} GWs, "
                    f"{card['uncertainty']:.1f} xP uncertainty, correlation pressure {card['correlation_pressure']:.2f}, "
                    f"fixture score {card['fixture_score']:+.1f}."
                ),
                card["transfer_pressure"],
                f"sell-pressure:{card['player_id']}",
                {
                    "player_id": card["player_id"],
                    "consensus_xp": card["consensus_xp"],
                    "uncertainty": card["uncertainty"],
                    "correlation_pressure": card["correlation_pressure"],
                    "fixture_score": card["fixture_score"],
                },
            ))

        disagreement = [
            card for card in squad_cards
            if card["source_count"] >= 2 and card["uncertainty"] >= 1.1
        ]
        if disagreement:
            card = max(disagreement, key=lambda row: row["uncertainty"])
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "projection_disagreement",
                f"Sources disagree hard on {card['web_name']}",
                (
                    f"Internal xP is {card['internal_xp']:.1f}, consensus is {card['consensus_xp']:.1f}, "
                    f"and uncertainty sits at {card['uncertainty']:.1f}. This is a volatility pocket, not a clean hold."
                ),
                4.8 + card["uncertainty"],
                f"projection-disagreement:{card['player_id']}",
                {"player_id": card["player_id"], "sources": card["sources"]},
            ))

        availability_dissonance = [
            card for card in squad_cards
            if abs(card.get("official_gap", 0)) >= 2.0
            or (card.get("distortion_rate", 0) >= 0.22 and card.get("news_purity", 0) >= 0.55)
        ]
        if availability_dissonance:
            card = max(
                availability_dissonance,
                key=lambda row: (abs(row.get("official_gap", 0)), row.get("distortion_rate", 0)),
            )
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "availability_signal",
                f"Availability model distrusts the surface signal on {card['web_name']}",
                (
                    f"Official next-GW EP is {card['official_ep_next']:.1f}, modeled next-GW xP is {card['modeled_next_xp']:.1f}, "
                    f"and similar {card['team_short']} availability cases carry a {card['availability_reliability'] * 100:.0f}% truth score "
                    f"with {card['distortion_rate'] * 100:.0f}% distortion."
                ),
                4.7 + abs(card.get("official_gap", 0)) + card.get("distortion_rate", 0) * 4.0,
                f"availability-signal:{card['player_id']}",
                {
                    "player_id": card["player_id"],
                    "official_ep_next": card["official_ep_next"],
                    "modeled_next_xp": card["modeled_next_xp"],
                    "distortion_rate": card["distortion_rate"],
                    "news_category": card["news_category"],
                },
            ))

        expensive_bench = [
            card for card in squad_cards
            if not card["is_starter"] and card["price"] >= 5.0 and card["consensus_xp"] <= 3.0
        ]
        if expensive_bench:
            card = max(expensive_bench, key=lambda row: (row["price"], row["transfer_pressure"]))
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "bench_capital",
                "Cash is trapped on the bench",
                f"{card['web_name']} ties up £{card['price']:.1f}m for only {card['consensus_xp']:.1f} consensus xP. That is usable funding, not idle cover.",
                5.0 + (card["price"] - 5.0),
                f"bench-capital:{card['player_id']}",
                {"player_id": card["player_id"], "price": card["price"], "consensus_xp": card["consensus_xp"]},
            ))

        lead_team = max(
            context["exposure"]["team_concentration"].values(),
            key=lambda item: item.get("variance_pct", 0),
            default=None,
        )
        if lead_team:
            lead_team_id = next(
                (player["team_id"] for player in squad if player["team_short"] == lead_team["team_short"]),
                None,
            )
            fixture_drag = team_fixture_scores.get(lead_team_id, 0.0) if lead_team_id is not None else 0.0
            if lead_team.get("variance_pct", 0) >= 34 and fixture_drag < 0:
                alerts.append(_make_alert(
                    manager_id,
                    event,
                    horizon,
                    "cluster_stress",
                    f"{lead_team['team_short']} is the regime risk",
                    (
                        f"{lead_team['variance_pct']:.0f}% of variance sits on {lead_team['team_short']}, "
                        f"and the fixture score is {fixture_drag:+.1f}. The stack is now structural risk, not just taste."
                    ),
                    5.4 + lead_team["variance_pct"] / 20.0,
                    f"cluster-stress:{lead_team['team_short']}",
                    {"team_short": lead_team["team_short"], "variance_pct": lead_team["variance_pct"], "fixture_score": fixture_drag},
                ))

        if market_radar:
            target = market_radar[0]
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "market_radar",
                f"{target['web_name']} is a live external-overlay target",
                (
                    f"{target['consensus_xp']:.1f} consensus xP with a {target['xp_edge']:+.1f} edge over the internal model. "
                    f"The price is £{target['price']:.1f}m and the fixture score is {target['fixture_score']:+.1f}."
                ),
                4.8 + target["market_score"],
                f"market-radar:{target['player_id']}",
                target,
            ))

        weird_owned = max(squad_cards, key=lambda row: row.get("anomaly_score", 0), default=None)
        if weird_owned and weird_owned.get("anomaly_score", 0) >= 2.7:
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "weird_math",
                f"Weird-math flag: {weird_owned['web_name']}",
                (
                    f"Position-relative anomaly score {weird_owned['anomaly_score']:.2f}. "
                    f"This player is an unusual mix of xP, uncertainty, fixture pressure, and correlation load."
                ),
                4.6 + weird_owned["anomaly_score"],
                f"weird-math:{weird_owned['player_id']}",
                {
                    "player_id": weird_owned["player_id"],
                    "anomaly_score": weird_owned["anomaly_score"],
                    "consensus_xp": weird_owned["consensus_xp"],
                    "uncertainty": weird_owned["uncertainty"],
                },
            ))

        if pc1_share >= 0.46:
            alerts.append(_make_alert(
                manager_id,
                event,
                horizon,
                "spectral_concentration",
                "One hidden factor is driving too much of the XI",
                f"The first covariance eigenfactor explains {pc1_share * 100:.0f}% of squad variance. The team is leaning on one match-script regime.",
                5.2 + pc1_share * 5.0,
                "spectral-concentration",
                {"pc1_share": round(pc1_share, 4)},
            ))

        summary = {
            "manager_id": manager_id,
            "event": event,
            "projection_event": projection_event,
            "horizon": horizon,
            "model_version": MODEL_VERSION,
            "alerts_count": len(alerts),
            "top_transfer_pressure": squad_cards[0]["web_name"] if squad_cards else None,
            "pc1_share": round(pc1_share, 4),
            "enb": context["exposure"]["enb"],
            "hhi": context["exposure"]["hhi"],
            "top_market_target": market_radar[0]["web_name"] if market_radar else None,
            "sources_available": len({row["source_key"] for row in external_rows}),
        }

        if persist:
            run_id = await db.insert_intel_run(database, manager_id, event, horizon, summary, MODEL_VERSION)
            for alert in alerts:
                alert["run_id"] = run_id
            await db.upsert_intel_alerts(database, alerts)
            await database.commit()

        delivery = None
        if deliver and persist and alerts:
            delivery = await deliver_pending_alerts(manager_id, database)

        return {
            "summary": summary,
            "alerts": alerts,
            "market_radar": market_radar,
            "top_squad_pressures": squad_cards[:5],
            "delivery": delivery,
        }
    finally:
        await database.close()


async def list_alerts(manager_id: int, status: str | None = None, limit: int = 50) -> list[dict]:
    database = await db.get_db()
    try:
        return await db.get_intel_alerts(database, manager_id, status, limit)
    finally:
        await database.close()


async def deliver_pending_alerts(manager_id: int, database=None) -> dict:
    own_conn = database is None
    if own_conn:
        database = await db.get_db()
    try:
        await ensure_intel_defaults(database)
        alerts = await db.get_intel_alerts(database, manager_id, "pending", 50)
        if not alerts:
            return {"delivered": 0, "attempted": 0, "channels": []}

        targets = await db.get_alert_delivery_targets(database, enabled_only=True)
        channels = []
        attempted = 0
        delivered = 0

        session = None
        try:
            for target in targets:
                if target["target_type"] == "webhook" and aiohttp is not None:
                    session = session or aiohttp.ClientSession()
                channels.append(target["name"])

            for alert in alerts:
                payload = {
                    "id": alert["id"],
                    "manager_id": alert["manager_id"],
                    "event": alert["event"],
                    "severity": alert["severity"],
                    "title": alert["title"],
                    "detail": alert["detail"],
                    "score": alert["score"],
                    "payload": alert.get("payload") or {},
                    "created_at": alert["created_at"],
                }
                alert_delivered = False
                attempted += 1

                for target in targets:
                    try:
                        if target["target_type"] == "file":
                            path = Path((target.get("config") or {}).get("path", _default_outbox_path()))
                            path = path.expanduser()
                            path.parent.mkdir(parents=True, exist_ok=True)
                            with path.open("a", encoding="utf-8") as handle:
                                handle.write(json.dumps(payload, sort_keys=True) + "\n")
                            alert_delivered = True
                        elif target["target_type"] == "stdout":
                            print(f"[transfer-intel] {payload['title']}: {payload['detail']}")
                            alert_delivered = True
                        elif target["target_type"] == "webhook":
                            if aiohttp is None:
                                continue
                            url = (target.get("config") or {}).get("url")
                            if not url or session is None:
                                continue
                            async with session.post(url, json=payload, timeout=10) as resp:
                                if 200 <= resp.status < 300:
                                    alert_delivered = True
                    except Exception:
                        continue

                if alert_delivered:
                    delivered += 1
                    await db.mark_intel_alert_delivered(database, alert["id"], "delivered")

            await database.commit()
        finally:
            if session is not None:
                await session.close()

        return {"delivered": delivered, "attempted": attempted, "channels": channels}
    finally:
        if own_conn:
            await database.close()


async def run_intel_loop(manager_id: int, horizon: int = 5, interval_minutes: int = 60):
    wait_seconds = max(interval_minutes, 5) * 60
    while True:
        try:
            await run_transfer_intelligence(manager_id, horizon=horizon, persist=True, deliver=True)
        except Exception as exc:
            print(f"[transfer-intel] loop error: {exc}")
        await asyncio.sleep(wait_seconds)
