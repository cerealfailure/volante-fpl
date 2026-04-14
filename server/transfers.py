"""
Transfer recommendation engine — smart replacement suggestions.

The planner is horizon-aware and treats a transfer plan as a joint
allocation problem, not a set of isolated 1-for-1 swaps:
  - never offers selected outgoing players back as buys
  - expands slot pools so premium targets can be funded elsewhere
  - searches the full transfer set (practically tuned up to 6 outs)
  - scores plans on projected points, fixture swing, xGI, budget use,
    and actual combined correlation / exposure impact

Also scores past transfers retroactively and detects bad habits.
"""

import numpy as np
from collections import Counter, defaultdict
import db
import analysis
import fpl
import projections

# ── Fixture difficulty multipliers (position-aware) ──────────────────
# From PitchIQ research. FDR 1=easy, 5=hard.
ATK_MULT = projections.ATK_MULT
DEF_MULT = projections.DEF_MULT
DECAY = projections.DECAY
DEFAULT_HORIZON = projections.DEFAULT_HORIZON
SUPPORTED_HORIZONS = projections.SUPPORTED_HORIZONS
MAX_PLAN_POOL = 16
MAX_PLAN_RESULTS = 5
MAX_BEAM_WIDTH = 120
MAX_EXACT_PLAN_EVALS = 24


def _normalize_horizon(horizon: int | None) -> int:
    return projections.normalize_horizon(horizon)


def _player_price(player: dict) -> float:
    if player.get("price") is not None:
        return float(player["price"])
    return ((player.get("now_cost") or 0) / 10.0)


def _player_position(player: dict) -> int:
    return int(player.get("position") or player.get("pos_type") or 0)


def _player_xgi_per90(player: dict) -> float:
    if player.get("xgi_per90") is not None:
        return float(player["xgi_per90"])
    minutes = max(player.get("minutes") or 1, 1)
    return float((player.get("xgi") or 0) / minutes * 90)


def _minutes_factor(player: dict, event: int | None, availability_state: dict | None = None) -> float:
    availability = projections.explain_availability(player, event, availability_state)
    return float(availability["minutes_factor"])


def _projection_base(player: dict, event: int | None, availability_state: dict | None = None) -> float:
    projection = projections.project_player(
        player,
        {player["team_id"]: []},
        1,
        event,
        availability_state,
    )
    per_fixture = projection["per_fixture"][0]["ep"] if projection["per_fixture"] else projection["next_event_ep"]
    return max(float(per_fixture), 0.5)


def _project_player_ep(
    player: dict,
    fixtures_by_team: dict[int, list[dict]],
    horizon: int,
    event: int | None,
    availability_state: dict | None = None,
) -> float:
    return projections.project_player_ep(player, fixtures_by_team, horizon, event, availability_state)


def _fixture_run_score(fixtures: list[dict], team_id: int, is_def: bool) -> float:
    """Score a fixture run: positive = easy, negative = hard."""
    if not fixtures:
        return 0.0
    mult = DEF_MULT if is_def else ATK_MULT
    total = 0.0
    for i, fixture in enumerate(fixtures):
        is_home = fixture["team_h"] == team_id
        difficulty = fixture["team_a_difficulty"] if is_home else fixture["team_h_difficulty"]
        difficulty = difficulty or 3
        total += (mult.get(difficulty, 1.0) - 1.0) * (DECAY ** i)
    return total * 10


def _build_fixture_strip(
    player: dict,
    fixtures_by_team: dict[int, list[dict]],
    team_lookup: dict[int, dict],
    horizon: int,
) -> list[dict]:
    strip = []
    for fixture in fixtures_by_team.get(player["team_id"], [])[:horizon]:
        is_home = fixture["team_h"] == player["team_id"]
        opp_id = fixture["team_a"] if is_home else fixture["team_h"]
        opp = team_lookup.get(opp_id, {})
        strip.append({
            "event": fixture.get("event"),
            "difficulty": (fixture["team_a_difficulty"] if is_home else fixture["team_h_difficulty"]) or 3,
            "is_home": is_home,
            "opponent": opp.get("short_name", "???"),
        })
    return strip


def _score_candidate(
    candidate: dict,
    sell_player: dict,
    fixtures_by_team: dict[int, list[dict]],
    event: int,
    base_team_counts: dict[int, int],
    horizon: int,
    availability_state: dict | None = None,
) -> tuple[float, dict]:
    """Composite transfer score with horizon-aware breakdown."""
    pos = _player_position(candidate)
    is_def = pos in (1, 2)

    projection_in = projections.project_player(candidate, fixtures_by_team, horizon, event, availability_state)
    projection_out = projections.project_player(sell_player, fixtures_by_team, horizon, event, availability_state)
    ep_delta = float(projection_in["next_event_ep"]) - float(projection_out["next_event_ep"])

    projected_in = float(projection_in["horizon_ep"])
    projected_out = float(projection_out["horizon_ep"])
    projected_gain = projected_in - projected_out

    fix_in = fixtures_by_team.get(candidate["team_id"], [])[:horizon]
    fix_out = fixtures_by_team.get(sell_player["team_id"], [])[:horizon]
    fixture_delta = _fixture_run_score(fix_in, candidate["team_id"], is_def) - _fixture_run_score(
        fix_out, sell_player["team_id"], is_def
    )

    form_delta = float(candidate.get("form") or 0) - float(sell_player.get("form") or 0)
    xgi_delta = _player_xgi_per90(candidate) - _player_xgi_per90(sell_player)

    team_count = base_team_counts.get(candidate["team_id"], 0)
    diversification = 0.9 if team_count == 0 else (0.25 if team_count == 1 else -0.65)
    team_fixture_pressure = _fixture_run_score(fix_in, candidate["team_id"], is_def)
    if team_count >= 1 and team_fixture_pressure < 0:
        diversification += team_fixture_pressure / 12.0

    set_piece_bonus = 0.0
    if candidate.get("penalties_order") and candidate["penalties_order"] <= 2:
        set_piece_bonus += 1.8
    if candidate.get("corners_order") and candidate["corners_order"] <= 2:
        set_piece_bonus += 0.45

    minutes_score = (
        _minutes_factor(candidate, event, availability_state)
        - _minutes_factor(sell_player, event, availability_state)
    ) * 4.0

    score = (
        projected_gain * 1.45
        + ep_delta * 0.55
        + fixture_delta * 0.28
        + form_delta * 0.24
        + xgi_delta * 2.2
        + diversification * 0.75
        + set_piece_bonus * 0.35
        + minutes_score * 0.45
    )

    breakdown = {
        "projected_gain": round(projected_gain, 2),
        "ep_delta": round(ep_delta, 2),
        "fixture_run": round(fixture_delta, 2),
        "form_trend": round(form_delta, 2),
        "xgi_per90_delta": round(xgi_delta, 2),
        "diversification": round(diversification, 2),
        "set_pieces": round(set_piece_bonus, 2),
        "minutes_confidence": round(minutes_score, 2),
    }
    return score, breakdown


def _build_candidate_record(
    candidate: dict,
    sell_player: dict,
    fixtures_by_team: dict[int, list[dict]],
    team_lookup: dict[int, dict],
    event: int,
    base_team_counts: dict[int, int],
    horizon: int,
    slot_budget: float,
    availability_state: dict | None = None,
) -> dict:
    score, breakdown = _score_candidate(
        candidate,
        sell_player,
        fixtures_by_team,
        event,
        base_team_counts,
        horizon,
        availability_state,
    )
    projection = projections.project_player(candidate, fixtures_by_team, horizon, event, availability_state)
    projected_ep = projection["horizon_ep"]
    price = _player_price(candidate)
    return {
        "id": candidate["id"],
        "player_id": candidate["id"],
        "web_name": candidate["web_name"],
        "team_id": candidate["team_id"],
        "team_short": candidate.get("team_short", "???"),
        "team_name": candidate.get("team_name", "???"),
        "price": round(price, 1),
        "total_points": candidate.get("total_points", 0),
        "form": candidate.get("form"),
        "ep_next": candidate.get("ep_next"),
        "projected_ep_next": round(projection["next_event_ep"], 1),
        "projected_ep": round(projected_ep, 1),
        "expected_minutes_next": projection["expected_minutes_next"],
        "availability": projection["availability"],
        "projection": projection,
        "xgi": candidate.get("xgi"),
        "xgi_per90": round(_player_xgi_per90(candidate), 2),
        "selected_pct": candidate.get("selected_pct"),
        "starts": candidate.get("starts", 0),
        "minutes": candidate.get("minutes", 0),
        "goals": candidate.get("goals_scored", 0),
        "assists": candidate.get("assists", 0),
        "clean_sheets": candidate.get("clean_sheets", 0),
        "penalties_order": candidate.get("penalties_order"),
        "corners_order": candidate.get("corners_order"),
        "score": round(score, 2),
        "breakdown": breakdown,
        "fixture_strip": _build_fixture_strip(candidate, fixtures_by_team, team_lookup, horizon),
        "requires_plan_budget": price > slot_budget + 1e-9,
        "over_slot_budget": round(max(0.0, price - slot_budget), 1),
    }


def _candidate_is_eligible(candidate: dict, keep_player_ids: set[int], removed_player_ids: set[int], base_team_counts: dict[int, int], pos: int) -> bool:
    if candidate["id"] in keep_player_ids:
        return False
    if candidate["id"] in removed_player_ids:
        return False
    if _player_position(candidate) != pos:
        return False
    if base_team_counts.get(candidate["team_id"], 0) >= 3:
        return False
    if candidate.get("chance_next") is not None and candidate["chance_next"] < 50:
        return False
    return True


def _build_plan_pool(candidates: list[dict]) -> list[dict]:
    if len(candidates) <= MAX_PLAN_POOL:
        return candidates

    chosen = []
    seen = set()
    buckets = [
        candidates[:10],
        sorted(candidates, key=lambda row: row["projected_ep"], reverse=True)[:6],
        sorted(candidates, key=lambda row: row["breakdown"]["projected_gain"], reverse=True)[:6],
        sorted(candidates, key=lambda row: row["price"])[:4],
    ]

    for bucket in buckets:
        for row in bucket:
            if row["id"] in seen:
                continue
            chosen.append(row)
            seen.add(row["id"])
            if len(chosen) >= MAX_PLAN_POOL:
                return chosen

    return chosen[:MAX_PLAN_POOL]


def _recommended_horizon(
    squad: list[dict],
    sell_players: list[dict],
    fixtures_by_team: dict[int, list[dict]],
) -> tuple[int, str]:
    flagged = [player for player in squad if player.get("status") not in (None, "a") or (player.get("chance_next") is not None and player["chance_next"] < 75)]
    if flagged:
        return 3, "Flags or minutes risk make the next 3 GWs the cleanest decision window."

    team_groups = defaultdict(list)
    for player in squad:
        team_groups[player["team_id"]].append(player)

    sharp_turn = None
    for players in team_groups.values():
        if len(players) < 2:
            continue
        total = 0.0
        for player in players:
            total += _fixture_run_score(
                fixtures_by_team.get(player["team_id"], [])[:3],
                player["team_id"],
                player.get("pos_type") in (1, 2),
            )
        if sharp_turn is None or total < sharp_turn:
            sharp_turn = total

    if sharp_turn is not None and sharp_turn < -5:
        return 3, "A concentrated fixture turn hits quickly, so short-run planning matters most."
    if len(sell_players) >= 4:
        return 5, "A broader reshuffle usually pays best over 5 GWs before the forecast gets noisier."
    return 5, "Most transfer edge sits in the next 5 GWs before fixture uncertainty compounds."


def _build_transfer_alerts(
    squad: list[dict],
    sell_players: list[dict],
    recommendations: list[dict],
    fixtures_by_team: dict[int, list[dict]],
    horizon: int,
    planning_reason: str,
) -> list[dict]:
    alerts = []
    sell_ids = {player["player_id"] for player in sell_players}
    by_team = defaultdict(list)
    for player in squad:
        by_team[player["team_id"]].append(player)

    top_slot = None
    best_gain = -999.0
    for row in recommendations:
        if row.get("error") or not row.get("candidates"):
            continue
        gain = row["candidates"][0]["breakdown"]["projected_gain"]
        if gain > best_gain:
            best_gain = gain
            top_slot = row
    if top_slot and best_gain >= 1.5:
        best_pick = top_slot["candidates"][0]
        alerts.append({
            "priority": 100,
            "severity": "high" if best_gain >= 3 else "medium",
            "title": f"{top_slot['sell_name']} is the cleanest exit",
            "detail": (
                f"{best_pick['web_name']} projects {best_gain:+.1f} points better over the next {horizon} GWs. "
                f"{'This move needs funding from the wider plan.' if best_pick['requires_plan_budget'] else 'It fits cleanly on its own.'}"
            ),
        })

    flagged = [
        player for player in squad
        if player["player_id"] in sell_ids and (
            player.get("status") not in (None, "a")
            or (player.get("chance_next") is not None and player["chance_next"] < 75)
        )
    ]
    flagged.sort(key=lambda player: player.get("chance_next") if player.get("chance_next") is not None else 101)
    if flagged:
        player = flagged[0]
        chance = player.get("chance_next")
        chance_text = "minutes are unstable" if chance is None else f"{chance}% chance of playing next GW"
        alerts.append({
            "priority": 95,
            "severity": "high",
            "title": f"{player['web_name']} is forcing the move",
            "detail": f"{chance_text}. Injury and minutes risk should outrank softer correlation tweaks.",
        })

    worst_team = None
    worst_score = 0.0
    for players in by_team.values():
        if len(players) < 2:
            continue
        score = 0.0
        for player in players:
            score += _fixture_run_score(
                fixtures_by_team.get(player["team_id"], [])[:horizon],
                player["team_id"],
                player.get("pos_type") in (1, 2),
            )
        if score < worst_score:
            worst_score = score
            worst_team = players
    if worst_team:
        names = ", ".join(player["web_name"] for player in worst_team[:3])
        alerts.append({
            "priority": 85,
            "severity": "high" if worst_score < -7 else "medium",
            "title": f"{worst_team[0]['team_short']} fixture turn is stressing the squad",
            "detail": f"{names} all carry a poor {horizon}-GW run. If you are starting the reshuffle somewhere, start here.",
        })

    expensive_bench = [
        player for player in squad
        if player["squad_position"] > 11 and _player_price(player) >= 5.0 and (player.get("ep_next") or 0) <= 2.8
    ]
    if expensive_bench:
        player = sorted(expensive_bench, key=_player_price, reverse=True)[0]
        alerts.append({
            "priority": 70,
            "severity": "medium",
            "title": "Cash is parked on the bench",
            "detail": f"{player['web_name']} ties up £{_player_price(player):.1f}m without much near-term output. That money can fund a stronger front-line move.",
        })

    alerts.append({
        "priority": 50,
        "severity": "info",
        "title": f"Plan through the next {horizon} GWs",
        "detail": planning_reason,
    })

    if len(sell_players) > 6:
        alerts.append({
            "priority": 40,
            "severity": "info",
            "title": "Search is widest up to 6 transfers",
            "detail": "The engine will still rank larger plans, but the search and scoring are tuned most aggressively for 1 to 6 exits.",
        })

    alerts.sort(key=lambda alert: alert["priority"], reverse=True)
    return [{k: v for k, v in alert.items() if k != "priority"} for alert in alerts[:4]]


async def _compute_plan_context(database, squad: list[dict], event: int, horizon: int) -> dict:
    starters = [player for player in squad if player["squad_position"] <= 11]
    starter_ids = [player["player_id"] for player in starters]
    captain_idx = next((idx for idx, player in enumerate(starters) if player.get("is_captain")), None)

    emp_cov, gws_used = await analysis.compute_empirical_covariance(starter_ids, database)
    struct_cov = await analysis.compute_structural_covariance(starter_ids, database)
    alpha = 0.6 if len(gws_used) < 15 else 0.4
    cov = analysis.ledoit_wolf_shrinkage(emp_cov, struct_cov, alpha)
    if horizon > 0:
        fixture_cov = await analysis.compute_forward_fixture_covariance(starter_ids, database, event, horizon)
        cov = analysis.ledoit_wolf_shrinkage(cov, fixture_cov, analysis.FIXTURE_FORECAST_ALPHA)
    exposure = analysis.compute_exposure_metrics(starter_ids, starters, cov, captain_idx)
    return {
        "starters": starters,
        "starter_ids": starter_ids,
        "captain_idx": captain_idx,
        "cov": cov,
        "exposure": exposure,
    }


async def _compute_proposed_exposure(database, starters: list[dict], event: int, horizon: int, captain_idx: int | None) -> tuple[dict, np.ndarray]:
    starter_ids = [player["player_id"] for player in starters]
    emp_cov, gws_used = await analysis.compute_empirical_covariance(starter_ids, database)
    struct_cov = await analysis.compute_structural_covariance(starter_ids, database)
    alpha = 0.6 if len(gws_used) < 15 else 0.4
    cov = analysis.ledoit_wolf_shrinkage(emp_cov, struct_cov, alpha)
    if horizon > 0:
        fixture_cov = await analysis.compute_forward_fixture_covariance(starter_ids, database, event, horizon)
        cov = analysis.ledoit_wolf_shrinkage(cov, fixture_cov, analysis.FIXTURE_FORECAST_ALPHA)
    return analysis.compute_exposure_metrics(starter_ids, starters, cov, captain_idx), cov


def _top_correlation_changes(
    current_starters: list[dict],
    proposed_starters: list[dict],
    current_corr: list[list[float]],
    proposed_corr: list[list[float]],
    changed_indices: set[int],
) -> list[dict]:
    if not changed_indices:
        return []
    changes = []
    for i in range(len(current_starters)):
        for j in range(i + 1, len(current_starters)):
            if i not in changed_indices and j not in changed_indices:
                continue
            delta = round(float(proposed_corr[i][j]) - float(current_corr[i][j]), 3)
            changes.append({
                "player_a": proposed_starters[i]["web_name"],
                "player_b": proposed_starters[j]["web_name"],
                "delta": delta,
                "current": round(float(current_corr[i][j]), 3),
                "proposed": round(float(proposed_corr[i][j]), 3),
            })
    changes.sort(key=lambda row: abs(row["delta"]), reverse=True)
    return changes[:6]


async def _simulate_transfer_plan(
    database,
    squad: list[dict],
    context: dict,
    picks_by_sell_id: dict[int, dict],
    event: int,
    horizon: int,
    projection_context: dict | None = None,
) -> dict:
    current_exposure = context["exposure"]
    current_cov = context["cov"]
    starters = context["starters"]
    captain_idx = context["captain_idx"]

    changed_indices = set()
    proposed_starters = list(starters)
    sell_lookup = {player["player_id"]: player for player in squad}

    for idx, starter in enumerate(starters):
        candidate = picks_by_sell_id.get(starter["player_id"])
        if not candidate:
            continue
        changed_indices.add(idx)
        proposed_starters[idx] = {
            **starter,
            "player_id": candidate["id"],
            "web_name": candidate["web_name"],
            "team_id": candidate["team_id"],
            "team_name": candidate["team_name"],
            "team_short": candidate["team_short"],
            "pos_type": candidate["position"],
            "now_cost": int(round(candidate["price"] * 10)),
            "total_points": candidate.get("total_points", 0),
            "form": candidate.get("form"),
            "ep_next": candidate.get("ep_next"),
            "selected_pct": candidate.get("selected_pct"),
            "xg": candidate.get("xg", 0),
            "xa": candidate.get("xa", 0),
            "xgi": candidate.get("xgi"),
            "minutes": candidate.get("minutes", 0),
            "starts": candidate.get("starts", 0),
        }

    if changed_indices:
        proposed_exposure, proposed_cov = await _compute_proposed_exposure(
            database,
            proposed_starters,
            event,
            horizon,
            captain_idx,
        )
    else:
        proposed_exposure = current_exposure
        proposed_cov = current_cov

    ep_next_delta = 0.0
    for sell_id, candidate in picks_by_sell_id.items():
        sold = sell_lookup[sell_id]
        if projection_context is not None:
            sold_projection = projections.project_player(
                sold,
                projection_context["fixtures_by_team"],
                1,
                event,
                projection_context,
            )
            ep_next_delta += float(candidate.get("projected_ep_next") or candidate.get("ep_next") or 0) - float(
                sold_projection["next_event_ep"]
            )
        else:
            ep_next_delta += float(candidate.get("ep_next") or 0) - float(sold.get("ep_next") or 0)

    return {
        "current": current_exposure,
        "proposed": proposed_exposure,
        "delta": {
            "portfolio_std": round(proposed_exposure["portfolio_std"] - current_exposure["portfolio_std"], 2),
            "hhi": round(proposed_exposure["hhi"] - current_exposure["hhi"], 4),
            "enb": round(proposed_exposure["enb"] - current_exposure["enb"], 1),
            "diversification_ratio": round(
                proposed_exposure["diversification_ratio"] - current_exposure["diversification_ratio"], 2
            ),
            "ep_next": round(ep_next_delta, 1),
        },
        "correlation_changes": _top_correlation_changes(
            starters,
            proposed_starters,
            current_exposure["correlation_matrix"],
            proposed_exposure["correlation_matrix"],
            changed_indices,
        ),
        "callouts": analysis.generate_risk_callouts(proposed_starters, proposed_exposure, proposed_cov),
    }


def _plan_budget_bonus(spent: float, budget: float) -> float:
    if budget <= 0:
        return 0.0
    left = max(budget - spent, 0.0)
    usage = spent / budget
    bonus = usage * 0.85
    if left >= 1.5:
        bonus -= min(left, 4.0) * 0.18
    return bonus


def _plan_score(state: dict, sim: dict, plan_budget: float) -> float:
    projected = state["projected_gain"] * 1.45
    immediate = (sim["delta"]["ep_next"] or 0) * 0.3
    correlation = (
        (sim["delta"]["enb"] or 0) * 1.8
        - (sim["delta"]["portfolio_std"] or 0) * 0.28
        - (sim["delta"]["hhi"] or 0) * 52
    )
    fixtures = state["fixture_swing"] * 0.3
    xgi = state["xgi_gain"] * 0.45
    budget = _plan_budget_bonus(state["spent"], plan_budget)
    return projected + immediate + correlation + fixtures + xgi + budget


def _describe_plan(state: dict, sim: dict, horizon: int, plan_budget: float) -> str:
    parts = [
        f"{state['projected_gain']:+.1f} projected pts over {horizon} GWs",
    ]
    if sim["delta"]["enb"] > 0.2 or sim["delta"]["hhi"] < -0.01:
        parts.append("cleans up correlation")
    elif sim["delta"]["enb"] < -0.2 or sim["delta"]["hhi"] > 0.01:
        parts.append("adds correlation risk")

    if state["fixture_swing"] > 1.5:
        parts.append("leans into the better fixture run")
    if plan_budget - state["spent"] <= 0.5:
        parts.append("uses almost all of the budget")
    elif plan_budget - state["spent"] >= 1.5:
        parts.append(f"leaves £{plan_budget - state['spent']:.1f}m unused")
    return ". ".join(parts[:3]) + "."


async def _optimize_transfer_plans(
    database,
    squad: list[dict],
    sell_players: list[dict],
    slot_plan_pools: list[dict],
    base_team_counts: dict[int, int],
    event: int,
    horizon: int,
    plan_budget: float,
    projection_context: dict | None = None,
    limit: int = MAX_PLAN_RESULTS,
) -> list[dict]:
    if not slot_plan_pools:
        return []

    ordered_slots = sorted(slot_plan_pools, key=lambda row: (len(row["plan_pool"]), row["sell_name"]))
    suffix_min_cost = [0.0] * (len(ordered_slots) + 1)
    for idx in range(len(ordered_slots) - 1, -1, -1):
        slot_min = min(candidate["price"] for candidate in ordered_slots[idx]["plan_pool"])
        suffix_min_cost[idx] = suffix_min_cost[idx + 1] + slot_min

    beam = [{
        "picks": {},
        "selected_ids": set(),
        "team_adds": Counter(),
        "spent": 0.0,
        "approx_score": 0.0,
        "projected_gain": 0.0,
        "fixture_swing": 0.0,
        "xgi_gain": 0.0,
        "uses_plan_budget": False,
    }]

    beam_width = MAX_BEAM_WIDTH if len(ordered_slots) <= 6 else 80

    for idx, slot in enumerate(ordered_slots):
        next_beam = []
        remaining_min = suffix_min_cost[idx + 1]
        for state in beam:
            for candidate in slot["plan_pool"]:
                if candidate["id"] in state["selected_ids"]:
                    continue
                if base_team_counts.get(candidate["team_id"], 0) + state["team_adds"][candidate["team_id"]] >= 3:
                    continue
                new_spent = state["spent"] + candidate["price"]
                if new_spent > plan_budget + 1e-9:
                    continue
                if new_spent + remaining_min > plan_budget + 1e-9:
                    continue

                team_adds = state["team_adds"].copy()
                team_adds[candidate["team_id"]] += 1
                picks = dict(state["picks"])
                picks[slot["sell_id"]] = candidate

                next_beam.append({
                    "picks": picks,
                    "selected_ids": set(state["selected_ids"]) | {candidate["id"]},
                    "team_adds": team_adds,
                    "spent": new_spent,
                    "approx_score": (
                        state["approx_score"]
                        + candidate["score"]
                        + _plan_budget_bonus(new_spent, plan_budget) * 0.1
                    ),
                    "projected_gain": state["projected_gain"] + candidate["breakdown"]["projected_gain"],
                    "fixture_swing": state["fixture_swing"] + candidate["breakdown"]["fixture_run"],
                    "xgi_gain": state["xgi_gain"] + candidate["breakdown"]["xgi_per90_delta"],
                    "uses_plan_budget": state["uses_plan_budget"] or candidate["requires_plan_budget"],
                })

        next_beam.sort(
            key=lambda row: (
                row["approx_score"],
                row["projected_gain"],
                -row["spent"],
            ),
            reverse=True,
        )
        beam = next_beam[:beam_width]

    forecast_event = projection_context["target_event"] if projection_context is not None else event
    context = await _compute_plan_context(database, squad, forecast_event, horizon)
    exact_candidates = beam[:MAX_EXACT_PLAN_EVALS]
    evaluated = []
    sell_lookup = {player["player_id"]: player for player in sell_players}

    for state in exact_candidates:
        forecast_event = projection_context["target_event"] if projection_context is not None else event
        sim = await _simulate_transfer_plan(
            database,
            squad,
            context,
            state["picks"],
            forecast_event,
            horizon,
            projection_context,
        )
        score = _plan_score(state, sim, plan_budget)
        slots = []
        for sell_player in sell_players:
            candidate = state["picks"].get(sell_player["player_id"])
            if not candidate:
                continue
            slots.append({
                "sell_id": sell_player["player_id"],
                "sell_name": sell_player["web_name"],
                "sell_team": sell_player.get("team_short", "???"),
                "sell_price": round(_player_price(sell_player), 1),
                "candidate": candidate,
            })
        evaluated.append({
            "score": round(score, 2),
            "spent": round(state["spent"], 1),
            "budget": round(plan_budget, 1),
            "budget_left": round(max(plan_budget - state["spent"], 0.0), 1),
            "budget_usage_pct": round((state["spent"] / plan_budget) * 100, 1) if plan_budget > 0 else 0.0,
            "projected_ep_gain": round(state["projected_gain"], 1),
            "fixture_swing": round(state["fixture_swing"], 2),
            "xgi_gain": round(state["xgi_gain"], 2),
            "uses_plan_budget": state["uses_plan_budget"],
            "slots": slots,
            "summary": _describe_plan(state, sim, horizon, plan_budget),
            "current": {
                "portfolio_std": context["exposure"]["portfolio_std"],
                "hhi": context["exposure"]["hhi"],
                "enb": context["exposure"]["enb"],
                "diversification_ratio": context["exposure"]["diversification_ratio"],
            },
            "proposed": {
                "portfolio_std": sim["proposed"]["portfolio_std"],
                "hhi": sim["proposed"]["hhi"],
                "enb": sim["proposed"]["enb"],
                "diversification_ratio": sim["proposed"]["diversification_ratio"],
            },
            "delta": sim["delta"],
            "correlation_changes": sim["correlation_changes"][:4],
            "callouts": sim["callouts"][:3],
        })

    evaluated.sort(
        key=lambda row: (
            row["score"],
            row["projected_ep_gain"],
            -row["budget_left"],
        ),
        reverse=True,
    )
    return evaluated[:limit]


async def recommend_replacements(
    manager_id: int,
    sell_player_ids: list[int],
    event: int | None = None,
    n: int = 5,
    horizon: int | None = None,
) -> dict:
    """
    Given 1+ players to sell, recommend top replacements for each slot and
    rank the best combined transfer plans across the whole selected set.
    """
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")

        horizon = _normalize_horizon(horizon)
        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad for manager {manager_id}")

        mgr_rows = await database.execute_fetchall("SELECT * FROM manager_info WHERE id=?", (manager_id,))
        bank = (dict(mgr_rows[0]).get("bank") or 0) / 10 if mgr_rows else 0

        team_rows = await database.execute_fetchall("SELECT id, short_name, name FROM teams")
        team_lookup = {row["id"]: dict(row) for row in team_rows}

        all_rows = await database.execute_fetchall("""
            SELECT p.*, t.short_name as team_short, t.name as team_name
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE p.minutes > 0 AND p.status IN ('a', 'd')
        """)
        all_players = {row["id"]: dict(row) for row in all_rows}

        projection_context = await projections.build_projection_context(database, event, horizon)
        fixtures_by_team = projection_context["fixtures_by_team"]
        availability_state = projection_context

        squad_lookup = {player["player_id"]: player for player in squad}
        sell_players = []
        recommendations = []

        for sell_id in sell_player_ids:
            sell_player = squad_lookup.get(sell_id)
            if sell_player:
                sell_players.append(sell_player)
            else:
                recommendations.append({"sell_id": sell_id, "error": "Not in squad"})

        removed_player_ids = {player["player_id"] for player in sell_players}
        keep_player_ids = {player["player_id"] for player in squad if player["player_id"] not in removed_player_ids}
        team_counts = Counter(player["team_id"] for player in squad)
        base_team_counts = Counter(team_counts)
        for player in sell_players:
            base_team_counts[player["team_id"]] -= 1
            if base_team_counts[player["team_id"]] <= 0:
                base_team_counts.pop(player["team_id"], None)

        plan_budget = bank + sum(_player_price(player) for player in sell_players)
        recommended_horizon, planning_reason = _recommended_horizon(squad, sell_players, fixtures_by_team)

        slot_min_costs = {}
        for sell_player in sell_players:
            pos = sell_player["pos_type"]
            min_cost = None
            for candidate in all_players.values():
                if not _candidate_is_eligible(candidate, keep_player_ids, removed_player_ids, base_team_counts, pos):
                    continue
                price = _player_price(candidate)
                if min_cost is None or price < min_cost:
                    min_cost = price
            slot_min_costs[sell_player["player_id"]] = min_cost

        slot_plan_pools = []
        for sell_player in sell_players:
            sell_id = sell_player["player_id"]
            pos = sell_player["pos_type"]
            sell_price = _player_price(sell_player)
            slot_budget = sell_price + bank
            min_other_cost = sum(
                min_cost or 0.0
                for other_sell_id, min_cost in slot_min_costs.items()
                if other_sell_id != sell_id
            )
            max_plan_price = max(slot_budget, plan_budget - min_other_cost)

            scored = []
            for candidate in all_players.values():
                if not _candidate_is_eligible(candidate, keep_player_ids, removed_player_ids, base_team_counts, pos):
                    continue
                if _player_price(candidate) > max_plan_price + 1e-9:
                    continue
                row = _build_candidate_record(
                    candidate,
                    sell_player,
                    fixtures_by_team,
                    team_lookup,
                    event,
                    base_team_counts,
                    horizon,
                    slot_budget,
                    availability_state,
                )
                row["position"] = pos
                row["xg"] = candidate.get("xg")
                row["xa"] = candidate.get("xa")
                scored.append(row)

            scored.sort(
                key=lambda row: (
                    row["score"],
                    row["breakdown"]["projected_gain"],
                    row["projected_ep"],
                ),
                reverse=True,
            )

            recommendations.append({
                "sell_id": sell_id,
                "sell_name": sell_player["web_name"],
                "sell_team": sell_player.get("team_short", "???"),
                "sell_price": round(sell_price, 1),
                "position": analysis.POS_NAMES.get(pos, "???"),
                "slot_budget": round(slot_budget, 1),
                "plan_max_price": round(max_plan_price, 1),
                "sell_projected_ep": round(_project_player_ep(sell_player, fixtures_by_team, horizon, event, availability_state), 1),
                "candidates": scored[:n],
                "total_candidates": len(scored),
            })

            if scored:
                slot_plan_pools.append({
                    "sell_id": sell_id,
                    "sell_name": sell_player["web_name"],
                    "plan_pool": _build_plan_pool(scored),
                })

        recommendations.sort(key=lambda row: sell_player_ids.index(row["sell_id"]) if row.get("sell_id") in sell_player_ids else 999)
        plans = []
        if slot_plan_pools and len(slot_plan_pools) == len(sell_players):
            plans = await _optimize_transfer_plans(
                database,
                squad,
                sell_players,
                slot_plan_pools,
                base_team_counts,
                event,
                horizon,
                plan_budget,
                projection_context,
                limit=min(MAX_PLAN_RESULTS, max(n, 3)),
            )
        alerts = _build_transfer_alerts(
            squad,
            sell_players,
            recommendations,
            fixtures_by_team,
            horizon,
            planning_reason,
        )

        return {
            "recommendations": recommendations,
            "plans": plans,
            "alerts": alerts,
            "planning": {
                "selected_horizon": horizon,
                "recommended_horizon": recommended_horizon,
                "recommended_reason": planning_reason,
                "window_start_event": projection_context["target_event"],
                "window_end_event": projection_context["target_event"] + horizon - 1,
                "supports_full_plan_size": 6,
                "selection_size": len(sell_players),
            },
            "bank": bank,
            "plan_budget": round(plan_budget, 1),
            "event": event,
            "projection_event": projection_context["target_event"],
        }
    finally:
        await database.close()


async def simulate_transfer_plan(
    manager_id: int,
    transfer_pairs: list[dict],
    event: int | None = None,
    horizon: int | None = None,
) -> dict:
    """
    Simulate an arbitrary multi-transfer plan exactly.
    Used for manual plans that do not match a suggested optimizer result.
    """
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")
        horizon = _normalize_horizon(horizon)

        if not transfer_pairs:
            raise ValueError("No transfer pairs supplied")

        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad for manager {manager_id}")

        mgr_rows = await database.execute_fetchall("SELECT * FROM manager_info WHERE id=?", (manager_id,))
        bank = (dict(mgr_rows[0]).get("bank") or 0) / 10 if mgr_rows else 0

        team_rows = await database.execute_fetchall("SELECT id, short_name, name FROM teams")
        team_lookup = {row["id"]: dict(row) for row in team_rows}

        all_rows = await database.execute_fetchall("""
            SELECT p.*, t.short_name as team_short, t.name as team_name
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE p.minutes > 0 AND p.status IN ('a', 'd')
        """)
        all_players = {row["id"]: dict(row) for row in all_rows}

        projection_context = await projections.build_projection_context(database, event, horizon)
        fixtures_by_team = projection_context["fixtures_by_team"]
        availability_state = projection_context

        squad_lookup = {player["player_id"]: player for player in squad}
        sell_ids = []
        buy_ids = set()
        sell_players = []
        for pair in transfer_pairs:
            sell_id = int(pair.get("sell_id") or 0)
            buy_id = int(pair.get("buy_id") or 0)
            if not sell_id or not buy_id:
                raise ValueError("Every transfer pair must include `sell_id` and `buy_id`")
            if sell_id in sell_ids:
                raise ValueError(f"Duplicate outgoing player in plan: {sell_id}")
            if buy_id in buy_ids:
                raise ValueError(f"Duplicate incoming player in plan: {buy_id}")
            if buy_id == sell_id:
                raise ValueError("Incoming player must differ from outgoing player")
            sell_player = squad_lookup.get(sell_id)
            if not sell_player:
                raise ValueError(f"Player {sell_id} is not in the squad")
            sell_ids.append(sell_id)
            buy_ids.add(buy_id)
            sell_players.append(sell_player)

        removed_player_ids = set(sell_ids)
        if removed_player_ids & buy_ids:
            raise ValueError("A transfer plan cannot buy back a selected outgoing player")

        keep_player_ids = {player["player_id"] for player in squad if player["player_id"] not in removed_player_ids}
        base_team_counts = Counter(player["team_id"] for player in squad)
        for player in sell_players:
            base_team_counts[player["team_id"]] -= 1
            if base_team_counts[player["team_id"]] <= 0:
                base_team_counts.pop(player["team_id"], None)

        plan_budget = bank + sum(_player_price(player) for player in sell_players)
        team_adds = Counter()
        picks_by_sell_id = {}
        projected_gain = 0.0
        fixture_swing = 0.0
        xgi_gain = 0.0
        spent = 0.0
        uses_plan_budget = False

        for pair in transfer_pairs:
            sell_id = int(pair["sell_id"])
            buy_id = int(pair["buy_id"])
            sell_player = squad_lookup[sell_id]
            candidate = all_players.get(buy_id)
            if not candidate:
                raise ValueError(f"Incoming player {buy_id} not found")
            if candidate["id"] in keep_player_ids:
                raise ValueError(f"{candidate['web_name']} is already in the squad")
            if _player_position(candidate) != sell_player["pos_type"]:
                raise ValueError(f"{candidate['web_name']} does not match {sell_player['web_name']}'s position")
            if candidate.get("chance_next") is not None and candidate["chance_next"] < 50:
                raise ValueError(f"{candidate['web_name']} fails the minutes threshold for recommendation")
            if base_team_counts.get(candidate["team_id"], 0) + team_adds[candidate["team_id"]] >= 3:
                raise ValueError(f"{candidate['team_short']} would exceed the three-player club limit")

            slot_budget = _player_price(sell_player) + bank
            row = _build_candidate_record(
                candidate,
                sell_player,
                fixtures_by_team,
                team_lookup,
                event,
                base_team_counts,
                horizon,
                slot_budget,
                availability_state,
            )
            spent += row["price"]
            if spent > plan_budget + 1e-9:
                raise ValueError(f"Plan is over budget by £{spent - plan_budget:.1f}m")
            team_adds[candidate["team_id"]] += 1
            picks_by_sell_id[sell_id] = row
            projected_gain += row["breakdown"]["projected_gain"]
            fixture_swing += row["breakdown"]["fixture_run"]
            xgi_gain += row["breakdown"]["xgi_per90_delta"]
            uses_plan_budget = uses_plan_budget or row["requires_plan_budget"]

        context = await _compute_plan_context(database, squad, projection_context["target_event"], horizon)
        sim = await _simulate_transfer_plan(
            database,
            squad,
            context,
            picks_by_sell_id,
            projection_context["target_event"],
            horizon,
            projection_context,
        )
        state = {
            "picks": picks_by_sell_id,
            "spent": spent,
            "projected_gain": projected_gain,
            "fixture_swing": fixture_swing,
            "xgi_gain": xgi_gain,
            "uses_plan_budget": uses_plan_budget,
        }
        score = _plan_score(state, sim, plan_budget)
        slots = []
        for sell_player in sell_players:
            candidate = picks_by_sell_id[sell_player["player_id"]]
            slots.append({
                "sell_id": sell_player["player_id"],
                "sell_name": sell_player["web_name"],
                "sell_team": sell_player.get("team_short", "???"),
                "sell_price": round(_player_price(sell_player), 1),
                "candidate": candidate,
            })

        return {
            "score": round(score, 2),
            "spent": round(spent, 1),
            "budget": round(plan_budget, 1),
            "budget_left": round(max(plan_budget - spent, 0.0), 1),
            "budget_usage_pct": round((spent / plan_budget) * 100, 1) if plan_budget > 0 else 0.0,
            "projected_ep_gain": round(projected_gain, 1),
            "fixture_swing": round(fixture_swing, 2),
            "xgi_gain": round(xgi_gain, 2),
            "uses_plan_budget": uses_plan_budget,
            "slots": slots,
            "summary": _describe_plan(state, sim, horizon, plan_budget),
            "current": {
                "portfolio_std": context["exposure"]["portfolio_std"],
                "hhi": context["exposure"]["hhi"],
                "enb": context["exposure"]["enb"],
                "diversification_ratio": context["exposure"]["diversification_ratio"],
            },
            "proposed": {
                "portfolio_std": sim["proposed"]["portfolio_std"],
                "hhi": sim["proposed"]["hhi"],
                "enb": sim["proposed"]["enb"],
                "diversification_ratio": sim["proposed"]["diversification_ratio"],
            },
            "delta": sim["delta"],
            "correlation_changes": sim["correlation_changes"][:6],
            "callouts": sim["callouts"][:4],
            "planning": {
                "selected_horizon": horizon,
                "window_start_event": projection_context["target_event"],
                "window_end_event": projection_context["target_event"] + horizon - 1,
            },
            "event": event,
            "projection_event": projection_context["target_event"],
        }
    finally:
        await database.close()


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
    wins = sum(1 for row in rows if (row.get("net_pts_delta") or row["pts_delta"]) > 0)
    return {
        "count": len(rows),
        "avg_alpha": round(sum(row.get("net_pts_delta", row["pts_delta"]) for row in rows) / len(rows), 1),
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
        headline = f"Transfers that improved ENB or reduced concentration averaged {improved_avg:+.1f} net points after hits."
    else:
        headline = (
            f"Transfers that improved ENB or reduced concentration averaged {improved_avg:+.1f} net points after hits, "
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
                hit_cost_share = hit_cost / max(len(gw_transfers), 1)
                net_pts_delta = pts_delta - hit_cost_share
                net_per_gw_alpha = net_pts_delta / gws_remaining

                # knee-jerk detection: sold player had good xGI but bad last GW
                is_knee_jerk = False
                if out_history:
                    last_before = [h for h in out_history if h["event"] == gw - 1]
                    avg_pts = np.mean([h["total_points"] for h in out_history if h["event"] < gw]) if out_history else 0
                    if last_before and last_before[0]["total_points"] <= 1 and avg_pts > 3.5:
                        is_knee_jerk = True
                        knee_jerks += 1

                total_alpha += net_pts_delta
                correlation_tradeoff = await _historical_transfer_correlation_effect(database, manager_id, t)

                scored.append({
                    "event": gw,
                    "in_name": in_name,
                    "out_name": out_name,
                    "in_pts_after": in_pts_after,
                    "out_pts_after": out_pts_after,
                    "pts_delta": pts_delta,
                    "per_gw_alpha": round(per_gw_alpha, 2),
                    "hit_cost_share": round(hit_cost_share, 2),
                    "net_pts_delta": round(net_pts_delta, 2),
                    "net_per_gw_alpha": round(net_per_gw_alpha, 2),
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
