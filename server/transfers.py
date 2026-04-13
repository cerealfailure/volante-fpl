"""
Transfer recommendation engine — smart replacement suggestions.

When you sell a player, this ranks every affordable replacement using
a composite score: EP delta, fixture run, form trend, xGI, correlation
impact, set piece duties, minutes confidence, price momentum.

Also scores past transfers retroactively and detects bad habits.
"""

import numpy as np
from collections import defaultdict
import db
import analysis
import fpl

# ── Fixture difficulty multipliers (position-aware) ──────────────────
# From PitchIQ research. FDR 1=easy, 5=hard.
ATK_MULT = {1: 1.18, 2: 1.15, 3: 1.00, 4: 0.86, 5: 0.72}
DEF_MULT = {1: 1.15, 2: 1.10, 3: 1.00, 4: 0.90, 5: 0.80}
DECAY = 0.85  # per-GW decay for projections
HORIZON = 5   # default look-ahead GWs


async def recommend_replacements(
    manager_id: int,
    sell_player_ids: list[int],
    event: int | None = None,
    n: int = 5,
) -> dict:
    """
    Given 1+ players to sell, recommend top N replacements for each slot.

    Returns per-slot recommendations with composite scores and breakdown.
    """
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)

        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad for manager {manager_id}")

        # current squad state
        squad_player_ids = {s["player_id"] for s in squad}
        team_counts = defaultdict(int)
        for s in squad:
            team_counts[s["team_id"]] += 1

        # bank from manager info
        mgr_rows = await database.execute_fetchall("SELECT * FROM manager_info WHERE id=?", (manager_id,))
        bank = (dict(mgr_rows[0]).get("bank") or 0) / 10 if mgr_rows else 0

        # load all players for candidate pool
        all_rows = await database.execute_fetchall("""
            SELECT p.*, t.short_name as team_short, t.name as team_name
            FROM players p JOIN teams t ON p.team_id = t.id
            WHERE p.minutes > 0 AND p.status IN ('a', 'd')
        """)
        all_players = {r["id"]: dict(r) for r in all_rows}

        # load fixtures for difficulty scoring
        all_fixtures = await database.execute_fetchall("""
            SELECT * FROM fixtures WHERE event >= ? AND event IS NOT NULL AND finished=0
            ORDER BY event LIMIT 200
        """, (event,))
        fixtures_by_team = defaultdict(list)
        for f in [dict(f) for f in all_fixtures]:
            fixtures_by_team[f["team_h"]].append(f)
            fixtures_by_team[f["team_a"]].append(f)

        results = []
        for sell_id in sell_player_ids:
            sell_player = next((s for s in squad if s["player_id"] == sell_id), None)
            if not sell_player:
                results.append({"sell_id": sell_id, "error": "Not in squad"})
                continue

            pos = sell_player["pos_type"]
            sell_price = (sell_player["now_cost"] or 0) / 10
            # selling price is ~50% of profit rounded down, but for simplicity use current price
            budget = sell_price + bank

            # teams at 3-player cap (excluding the sold player)
            temp_counts = dict(team_counts)
            temp_counts[sell_player["team_id"]] -= 1
            blocked_teams = {t for t, c in temp_counts.items() if c >= 3}

            # filter candidates
            candidates = []
            for p in all_players.values():
                if p["id"] in squad_player_ids and p["id"] != sell_id:
                    continue
                if p["position"] != pos:
                    continue
                if (p["now_cost"] or 0) / 10 > budget:
                    continue
                if p["team_id"] in blocked_teams:
                    continue
                if p.get("chance_next") is not None and p["chance_next"] < 50:
                    continue
                candidates.append(p)

            # score each candidate, enrich with fixture strip
            scored = []
            for c in candidates:
                score, breakdown = _score_candidate(
                    c, sell_player, all_players, fixtures_by_team, event, squad, team_counts
                )
                # fixture strip for candidate
                c_fixtures = fixtures_by_team.get(c["team_id"], [])[:HORIZON]
                fix_strip = []
                for f in c_fixtures:
                    is_home = f["team_h"] == c["team_id"]
                    opp_short = "???"
                    # get opponent short name from DB would be ideal, use team_id for now
                    fdr = f["team_a_difficulty"] if is_home else f["team_h_difficulty"]
                    fix_strip.append({
                        "event": f.get("event"),
                        "difficulty": fdr or 3,
                        "is_home": is_home,
                    })

                # projected EP over horizon (decayed)
                ep_proj = 0
                ep_base = c.get("ep_next") or (c.get("form") or 2)
                mult_map = DEF_MULT if c["position"] in (1, 2) else ATK_MULT
                for i, f in enumerate(c_fixtures):
                    is_home = f["team_h"] == c["team_id"]
                    fdr = (f["team_a_difficulty"] if is_home else f["team_h_difficulty"]) or 3
                    adj = mult_map.get(fdr, 1.0)
                    ep_proj += ep_base * adj * DECAY ** i

                scored.append({
                    "id": c["id"],
                    "web_name": c["web_name"],
                    "team_short": c.get("team_short", "???"),
                    "team_name": c.get("team_name", "???"),
                    "price": (c["now_cost"] or 0) / 10,
                    "total_points": c.get("total_points", 0),
                    "form": c.get("form"),
                    "ep_next": c.get("ep_next"),
                    "xgi": c.get("xgi"),
                    "xgi_per90": round(c.get("xgi", 0) / max(c.get("minutes", 1), 1) * 90, 2),
                    "selected_pct": c.get("selected_pct"),
                    "starts": c.get("starts", 0),
                    "minutes": c.get("minutes", 0),
                    "goals": c.get("goals_scored", 0),
                    "assists": c.get("assists", 0),
                    "clean_sheets": c.get("clean_sheets", 0),
                    "penalties_order": c.get("penalties_order"),
                    "corners_order": c.get("corners_order"),
                    "score": round(score, 2),
                    "breakdown": breakdown,
                    "fixture_strip": fix_strip,
                    "projected_ep": round(ep_proj, 1),
                })

            scored.sort(key=lambda x: x["score"], reverse=True)

            results.append({
                "sell_id": sell_id,
                "sell_name": sell_player["web_name"],
                "sell_team": sell_player.get("team_short", "???"),
                "sell_price": sell_price,
                "position": analysis.POS_NAMES.get(pos, "???"),
                "budget": round(budget, 1),
                "candidates": scored[:n],
                "total_candidates": len(candidates),
            })

        return {"recommendations": results, "bank": bank, "event": event}
    finally:
        await database.close()


def _score_candidate(candidate, sell_player, all_players, fixtures_by_team, event, squad, team_counts) -> tuple[float, dict]:
    """Composite transfer score with full breakdown."""
    pos = candidate["position"]
    is_def = pos in (1, 2)

    # 1. EP delta
    ep_in = candidate.get("ep_next") or 0
    ep_out = sell_player.get("ep_next") or 0
    ep_delta = ep_in - ep_out

    # 2. Fixture run (next HORIZON GWs)
    fix_in = fixtures_by_team.get(candidate["team_id"], [])[:HORIZON]
    fix_out = fixtures_by_team.get(sell_player["team_id"], [])[:HORIZON]
    fix_score_in = _fixture_run_score(fix_in, candidate["team_id"], is_def)
    fix_score_out = _fixture_run_score(fix_out, sell_player["team_id"], is_def)
    fixture_delta = fix_score_in - fix_score_out

    # 3. Form trend
    form_in = candidate.get("form") or 0
    form_out = sell_player.get("form") or 0
    form_delta = form_in - form_out

    # 4. xGI delta
    xgi_in = candidate.get("xgi") or 0
    xgi_out = sell_player.get("xgi") or 0
    mins_in = max(candidate.get("minutes") or 1, 1)
    mins_out = max(sell_player.get("minutes") or 1, 1)
    xgi_per90_in = xgi_in / mins_in * 90
    xgi_per90_out = xgi_out / mins_out * 90
    xgi_delta = (xgi_per90_in - xgi_per90_out) * 10

    # 5. Correlation improvement
    in_team_count = team_counts.get(candidate["team_id"], 0)
    corr_score = 1.0 if in_team_count == 0 else (0.3 if in_team_count == 1 else -0.5)

    # 6. Set piece / penalty bonus
    sp_bonus = 0
    if candidate.get("penalties_order") and candidate["penalties_order"] <= 2:
        sp_bonus += 2.0
    if candidate.get("corners_order") and candidate["corners_order"] <= 2:
        sp_bonus += 0.5

    # 7. Minutes confidence
    starts = candidate.get("starts") or 0
    possible_gws = max((event or 32), 1)
    start_rate = starts / possible_gws if possible_gws > 0 else 0
    mins_score = 1.0 if start_rate > 0.85 else (0.3 if start_rate > 0.65 else -1.0)

    # 8. Price momentum
    price_change = (candidate.get("now_cost") or 0) - (candidate.get("now_cost") or 0)  # need season start cost
    price_score = 0.0  # simplified — would need cost_change_start from API

    # Weighted composite
    score = (
        0.40 * ep_delta
        + 0.15 * fixture_delta
        + 0.12 * form_delta
        + 0.12 * xgi_delta
        + 0.06 * corr_score
        + 0.05 * sp_bonus
        + 0.05 * mins_score
        + 0.05 * price_score
    )

    breakdown = {
        "ep_delta": round(ep_delta, 2),
        "fixture_run": round(fixture_delta, 2),
        "form_trend": round(form_delta, 2),
        "xgi_quality": round(xgi_delta, 2),
        "diversification": round(corr_score, 2),
        "set_pieces": round(sp_bonus, 2),
        "minutes_confidence": round(mins_score, 2),
    }

    return score, breakdown


def _fixture_run_score(fixtures: list, team_id: int, is_def: bool) -> float:
    """Score a fixture run: positive = easy, negative = hard."""
    if not fixtures:
        return 0.0
    mult = DEF_MULT if is_def else ATK_MULT
    total = 0
    for i, f in enumerate(fixtures):
        is_home = f["team_h"] == team_id
        fdr = f["team_a_difficulty"] if is_home else f["team_h_difficulty"]
        fdr = fdr or 3
        adj = mult.get(fdr, 1.0)
        total += (adj - 1.0) * DECAY ** i
    return total * 10  # scale up


async def _ensure_manager_event_snapshot(database, manager_id: int, event: int) -> list[dict]:
    squad = await db.get_manager_squad(database, manager_id, event)
    if squad:
        return squad

    async with fpl._session() as session:
        picks_data = await fpl.fetch_manager_picks(session, manager_id, event)
    picks = picks_data.get("picks") or []
    if not picks:
        return []

    await db.upsert_manager_picks(database, manager_id, event, picks)
    await database.commit()
    return await db.get_manager_squad(database, manager_id, event)


async def _ensure_player_histories(database, player_ids: list[int]):
    missing = []
    for pid in sorted(set(player_ids)):
        history = await db.get_player_history(database, pid)
        if not history:
            missing.append(pid)
    if missing:
        await fpl.sync_player_histories(missing)


async def _exposure_snapshot(players: list[dict], database, cutoff_event: int) -> dict:
    player_ids = [player["player_id"] for player in players]
    captain_idx = next((idx for idx, player in enumerate(players) if player.get("is_captain")), None)
    emp_cov, gws = await analysis.compute_empirical_covariance(
        player_ids,
        database,
        max_event=cutoff_event,
    )
    struct_cov = await analysis.compute_structural_covariance(player_ids, database)
    alpha = 0.6 if len(gws) < 15 else 0.4
    cov = analysis.ledoit_wolf_shrinkage(emp_cov, struct_cov, alpha)
    return analysis.compute_exposure_metrics(player_ids, players, cov, captain_idx)


def _matrix_direction(enb_delta: float, hhi_delta: float) -> str:
    if enb_delta >= 0.3 or hhi_delta <= -0.015:
        return "improved"
    if enb_delta <= -0.3 or hhi_delta >= 0.015:
        return "worsened"
    return "flat"


async def _historical_transfer_correlation_effect(database, manager_id: int, transfer: dict) -> dict:
    gw = transfer.get("event") or 0
    in_id = transfer.get("in_id") or transfer.get("element_in")
    out_id = transfer.get("out_id") or transfer.get("element_out")

    if gw <= 1 or not in_id or not out_id:
        return {"available": False, "reason": "missing_transfer_context"}

    post_squad = await _ensure_manager_event_snapshot(database, manager_id, gw)
    if not post_squad:
        return {"available": False, "reason": "missing_event_snapshot"}

    post_starters = [player for player in post_squad if player["squad_position"] <= 11]
    swap_idx = next((idx for idx, player in enumerate(post_starters) if player["player_id"] == in_id), None)
    if swap_idx is None:
        return {"available": False, "reason": "incoming_not_in_xi"}
    if post_starters[swap_idx].get("is_captain"):
        return {"available": False, "reason": "incoming_was_captain"}

    out_player = await db.get_player(database, out_id)
    if not out_player:
        return {"available": False, "reason": "missing_outgoing_player"}

    out_team = await db.get_team(database, out_player["team_id"])
    pre_starters = list(post_starters)
    pre_starters[swap_idx] = {
        **post_starters[swap_idx],
        "player_id": out_id,
        "web_name": out_player["web_name"],
        "team_id": out_player["team_id"],
        "team_name": out_team["name"] if out_team else "???",
        "team_short": out_team["short_name"] if out_team else "???",
        "pos_type": out_player["position"],
        "now_cost": out_player["now_cost"],
        "total_points": out_player["total_points"],
        "form": out_player["form"],
        "ep_next": out_player["ep_next"],
        "selected_pct": out_player["selected_pct"],
        "xg": out_player["xg"],
        "xa": out_player["xa"],
        "xgi": out_player["xgi"],
        "status": out_player["status"],
        "chance_next": out_player["chance_next"],
        "minutes": out_player["minutes"],
        "starts": out_player["starts"],
    }

    await _ensure_player_histories(
        database,
        [player["player_id"] for player in pre_starters] + [player["player_id"] for player in post_starters],
    )

    cutoff_event = gw - 1
    pre_exposure = await _exposure_snapshot(pre_starters, database, cutoff_event)
    post_exposure = await _exposure_snapshot(post_starters, database, cutoff_event)

    enb_delta = round(post_exposure["enb"] - pre_exposure["enb"], 1)
    hhi_delta = round(post_exposure["hhi"] - pre_exposure["hhi"], 4)
    std_delta = round(post_exposure["portfolio_std"] - pre_exposure["portfolio_std"], 2)

    return {
        "available": True,
        "direction": _matrix_direction(enb_delta, hhi_delta),
        "delta": {
            "enb": enb_delta,
            "hhi": hhi_delta,
            "portfolio_std": std_delta,
        },
        "pre": {
            "enb": pre_exposure["enb"],
            "hhi": pre_exposure["hhi"],
            "portfolio_std": pre_exposure["portfolio_std"],
        },
        "post": {
            "enb": post_exposure["enb"],
            "hhi": post_exposure["hhi"],
            "portfolio_std": post_exposure["portfolio_std"],
        },
    }


def _scorecard_group(rows: list[dict]) -> dict:
    if not rows:
        return {"count": 0, "avg_alpha": None, "win_rate": None}
    wins = sum(1 for row in rows if row["pts_delta"] > 0)
    return {
        "count": len(rows),
        "avg_alpha": round(sum(row["pts_delta"] for row in rows) / len(rows), 1),
        "win_rate": round(wins / len(rows) * 100, 1),
    }


def _build_correlation_scorecard(rows: list[dict]) -> dict:
    tracked = [row for row in rows if row.get("correlation_tradeoff", {}).get("available")]
    improved = [row for row in tracked if row["correlation_tradeoff"]["direction"] == "improved"]
    worsened = [row for row in tracked if row["correlation_tradeoff"]["direction"] == "worsened"]
    flat = [row for row in tracked if row["correlation_tradeoff"]["direction"] == "flat"]

    if not tracked:
        return {
            "tracked_transfers": 0,
            "headline": "No starter-level historical snapshots yet for matrix scoring.",
            "improved": _scorecard_group([]),
            "worsened": _scorecard_group([]),
            "flat": _scorecard_group([]),
        }

    improved_avg = _scorecard_group(improved)["avg_alpha"]
    worsened_avg = _scorecard_group(worsened)["avg_alpha"]
    if improved_avg is None:
        headline = "Matrix-aware starter snapshots are available, but none of the transfers improved diversification."
    elif worsened_avg is None:
        headline = f"Transfers that improved ENB or reduced concentration averaged {improved_avg:+.1f} points."
    else:
        headline = (
            f"Transfers that improved ENB or reduced concentration averaged {improved_avg:+.1f} points, "
            f"versus {worsened_avg:+.1f} when the matrix got worse."
        )

    return {
        "tracked_transfers": len(tracked),
        "headline": headline,
        "improved": _scorecard_group(improved),
        "worsened": _scorecard_group(worsened),
        "flat": _scorecard_group(flat),
    }


# ── Past transfer analysis ───────────────────────────────────────────

async def analyze_past_transfers(manager_id: int) -> dict:
    """
    Score every past transfer and detect habit patterns.
    """
    database = await db.get_db()
    try:
        transfers = await db.get_manager_transfers(database, manager_id)
        if not transfers:
            return {"transfers": [], "habits": [], "summary": {}}

        current_event = await db.get_current_event(database) or 38

        scored = []
        total_alpha = 0
        hits_taken = 0
        hit_gws = set()
        knee_jerks = 0
        total_trf = len(transfers)

        # group transfers by GW to detect hits
        by_gw = defaultdict(list)
        for t in transfers:
            by_gw[t.get("event") or 0].append(t)

        for gw, gw_transfers in by_gw.items():
            # more than 1 transfer per GW = hit(s)
            free_transfers = 1  # simplified, normally 1 per GW
            extra = max(len(gw_transfers) - free_transfers, 0)
            hit_cost = extra * 4

            if extra > 0:
                hits_taken += extra
                hit_gws.add(gw)

            for t in gw_transfers:
                in_id = t.get("in_id") or t.get("element_in")
                out_id = t.get("out_id") or t.get("element_out")
                in_name = t.get("in_name", f"#{in_id}")
                out_name = t.get("out_name", f"#{out_id}")

                # get subsequent points for both players
                in_history = await db.get_player_history(database, in_id) if in_id else []
                out_history = await db.get_player_history(database, out_id) if out_id else []

                in_pts_after = sum(h["total_points"] for h in in_history if h["event"] >= gw)
                out_pts_after = sum(h["total_points"] for h in out_history if h["event"] >= gw)

                pts_delta = in_pts_after - out_pts_after
                gws_remaining = max(current_event - gw + 1, 1)
                per_gw_alpha = pts_delta / gws_remaining

                # knee-jerk detection: sold player had good xGI but bad last GW
                is_knee_jerk = False
                if out_history:
                    last_before = [h for h in out_history if h["event"] == gw - 1]
                    avg_pts = np.mean([h["total_points"] for h in out_history if h["event"] < gw]) if out_history else 0
                    if last_before and last_before[0]["total_points"] <= 1 and avg_pts > 3.5:
                        is_knee_jerk = True
                        knee_jerks += 1

                total_alpha += pts_delta
                correlation_tradeoff = await _historical_transfer_correlation_effect(database, manager_id, t)

                scored.append({
                    "event": gw,
                    "in_name": in_name,
                    "out_name": out_name,
                    "in_pts_after": in_pts_after,
                    "out_pts_after": out_pts_after,
                    "pts_delta": pts_delta,
                    "per_gw_alpha": round(per_gw_alpha, 2),
                    "was_hit": gw in hit_gws,
                    "is_knee_jerk": is_knee_jerk,
                    "verdict": "good" if pts_delta > 5 else ("bad" if pts_delta < -5 else "neutral"),
                    "correlation_tradeoff": correlation_tradeoff,
                })

        # habit summary
        habits = []
        if total_trf > 0:
            knee_rate = knee_jerks / total_trf
            if knee_rate > 0.2:
                habits.append({
                    "type": "knee_jerker",
                    "severity": "high" if knee_rate > 0.35 else "medium",
                    "detail": f"{knee_jerks}/{total_trf} transfers ({knee_rate*100:.0f}%) were knee-jerk reactions to a single bad gameweek. The sold player often had good underlying stats.",
                })

            hit_rate = hits_taken / max(current_event, 1)
            if hit_rate > 0.25:
                habits.append({
                    "type": "hit_addict",
                    "severity": "high" if hit_rate > 0.4 else "medium",
                    "detail": f"Took {hits_taken} hits across {len(hit_gws)} GWs ({hit_rate*100:.0f}% of weeks). Each hit costs 4 points — only worth it if the transfer gains 8+ over remaining GWs.",
                })

            avg_alpha = total_alpha / total_trf
            if avg_alpha < -1:
                habits.append({
                    "type": "negative_alpha",
                    "severity": "high",
                    "detail": f"Transfers averaged {avg_alpha:.1f} points each. The players you sold outscored the ones you bought. Consider fewer, higher-conviction moves.",
                })
            elif avg_alpha > 2:
                habits.append({
                    "type": "sharp_trader",
                    "severity": "info",
                    "detail": f"Transfers averaged +{avg_alpha:.1f} points each. Your transfer decisions are generating alpha.",
                })

        # sort by most impactful
        scored.sort(key=lambda x: abs(x["pts_delta"]), reverse=True)

        return {
            "transfers": scored,
            "habits": habits,
            "correlation_scorecard": _build_correlation_scorecard(scored),
            "summary": {
                "total_transfers": total_trf,
                "total_alpha": round(total_alpha, 0),
                "avg_alpha": round(total_alpha / max(total_trf, 1), 1),
                "hits_taken": hits_taken,
                "hit_cost": hits_taken * 4,
                "knee_jerks": knee_jerks,
                "best_transfer": max(scored, key=lambda x: x["pts_delta"]) if scored else None,
                "worst_transfer": min(scored, key=lambda x: x["pts_delta"]) if scored else None,
            },
        }
    finally:
        await database.close()
