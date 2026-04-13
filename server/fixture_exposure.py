"""
Fixture exposure engine.

For each remaining fixture involving a manager's starters, estimate how much
that result can swing the gameweek and summarize the match in plain FPL terms.
"""

from datetime import datetime, timezone
import math

import analysis
import db
import match_model


async def gameweek_exposure_report(manager_id: int, event: int | None = None) -> dict:
    """
    For each remaining fixture this GW, compute:
    - which of your starters are involved
    - expected points under the main outcome buckets
    - how much that match can swing the week
    """
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)
        cutoff = datetime.now(timezone.utc)

        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad for manager {manager_id}")

        starters = [s for s in squad if s["squad_position"] <= 11]

        fixtures = await database.execute_fetchall(
            """
            SELECT f.*, th.name as home_name, th.short_name as home_short,
                   ta.name as away_name, ta.short_name as away_short,
                   th.str_attack_home, th.str_defence_home,
                   ta.str_attack_away, ta.str_defence_away
            FROM fixtures f
            JOIN teams th ON f.team_h = th.id
            JOIN teams ta ON f.team_a = ta.id
            WHERE f.event = ? AND f.finished = 0
            """,
            (event,),
        )
        fixtures = [
            fixture
            for fixture in (dict(row) for row in fixtures)
            if _fixture_is_still_ahead(fixture, cutoff)
        ]

        fixture_reports = []
        total_squad_ep = sum(
            (starter.get("ep_next") or 0) * (2 if starter.get("is_captain") else 1)
            for starter in starters
        )

        for fix in fixtures:
            home_id = fix["team_h"]
            away_id = fix["team_a"]

            home_players = [s for s in starters if s["team_id"] == home_id]
            away_players = [s for s in starters if s["team_id"] == away_id]
            involved = home_players + away_players

            if not involved:
                continue

            fix_ep = sum(
                (player.get("ep_next") or 0) * (2 if player.get("is_captain") else 1)
                for player in involved
            )
            fix_ep_pct = (fix_ep / total_squad_ep * 100) if total_squad_ep > 0 else 0

            lambda_home, lambda_away = match_model.goal_rates_from_strengths(fix)
            score_matrix = match_model.build_score_matrix(lambda_home, lambda_away)
            outcome_probs = match_model.outcome_probabilities(score_matrix)

            home_outcomes = _team_outcome_points(home_players, "home", score_matrix, lambda_home)
            away_outcomes = _team_outcome_points(away_players, "away", score_matrix, lambda_away)

            home_win_ep = home_outcomes["home_win"] + away_outcomes["home_win"]
            draw_ep = home_outcomes["draw"] + away_outcomes["draw"]
            away_win_ep = home_outcomes["away_win"] + away_outcomes["away_win"]
            ep_range = max(home_win_ep, away_win_ep, draw_ep) - min(home_win_ep, away_win_ep, draw_ep)
            weighted_mean = (
                outcome_probs["home_win"] * home_win_ep
                + outcome_probs["draw"] * draw_ep
                + outcome_probs["away_win"] * away_win_ep
            )
            outcome_variance = (
                outcome_probs["home_win"] * (home_win_ep - weighted_mean) ** 2
                + outcome_probs["draw"] * (draw_ep - weighted_mean) ** 2
                + outcome_probs["away_win"] * (away_win_ep - weighted_mean) ** 2
            )

            captain_in_fix = any(player.get("is_captain") for player in involved)
            angle = _compute_fixture_angle(
                captain=captain_in_fix,
                n_home=len(home_players),
                n_away=len(away_players),
                hw_ep=home_win_ep,
                aw_ep=away_win_ep,
                d_ep=draw_ep,
                ep_pct=fix_ep_pct,
                home_short=fix["home_short"],
                away_short=fix["away_short"],
            )

            fixture_reports.append(
                {
                    "fixture_id": fix["id"],
                    "home": fix["home_short"],
                    "away": fix["away_short"],
                    "home_name": fix["home_name"],
                    "away_name": fix["away_name"],
                    "home_players": [
                        {
                            "name": s["web_name"],
                            "pos": analysis.POS_NAMES.get(s["pos_type"], "?"),
                            "ep": s.get("ep_next"),
                            "captain": bool(s.get("is_captain")),
                        }
                        for s in home_players
                    ],
                    "away_players": [
                        {
                            "name": s["web_name"],
                            "pos": analysis.POS_NAMES.get(s["pos_type"], "?"),
                            "ep": s.get("ep_next"),
                            "captain": bool(s.get("is_captain")),
                        }
                        for s in away_players
                    ],
                    "total_ep": round(fix_ep, 1),
                    "ep_pct_of_squad": round(fix_ep_pct, 1),
                    "outcomes": {
                        "home_win": round(home_win_ep, 1),
                        "draw": round(draw_ep, 1),
                        "away_win": round(away_win_ep, 1),
                    },
                    "outcome_probabilities": {
                        "home_win": round(outcome_probs["home_win"], 4),
                        "draw": round(outcome_probs["draw"], 4),
                        "away_win": round(outcome_probs["away_win"], 4),
                    },
                    "goal_model": {
                        "lambda_home": round(lambda_home, 3),
                        "lambda_away": round(lambda_away, 3),
                        "total_goals": round(lambda_home + lambda_away, 3),
                    },
                    "ep_range": round(ep_range, 1),
                    "outcome_variance": round(outcome_variance, 2),
                    "ep_std": round(math.sqrt(max(outcome_variance, 0.0)), 2),
                    "captain_involved": captain_in_fix,
                    "angle": angle,
                }
            )

        fixture_reports.sort(key=lambda item: (item.get("outcome_variance", 0), item["ep_range"]), reverse=True)

        return {
            "event": event,
            "kickoff_after": cutoff.isoformat(),
            "total_squad_ep": round(total_squad_ep, 1),
            "fixtures": fixture_reports,
            "summary": _build_summary(fixture_reports),
        }
    finally:
        await database.close()


def _fixture_is_still_ahead(fixture: dict, cutoff: datetime) -> bool:
    kickoff = fixture.get("kickoff_time")
    if not kickoff:
        return True
    try:
        return datetime.fromisoformat(str(kickoff).replace("Z", "+00:00")) > cutoff
    except ValueError:
        return True


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _availability_factor(player: dict) -> float:
    chance_next = player.get("chance_next")
    if isinstance(chance_next, (int, float)) and float(chance_next) >= 0:
        return _clamp(float(chance_next) / 100.0, 0.15, 1.0)
    status = str(player.get("status") or "").lower()
    if status in {"a", ""}:
        return 1.0
    if status == "d":
        return 0.7
    return 0.45


def _expected_minutes(player: dict) -> float:
    availability = _availability_factor(player)
    minutes = float(player.get("minutes") or 0.0)
    starts = float(player.get("starts") or 0.0)
    if minutes <= 0:
        return 72.0 * availability

    starts_proxy = max(starts, 1.0)
    avg_start_minutes = minutes / starts_proxy
    appearance_proxy = max(minutes / 90.0, 1.0)
    start_share = _clamp(starts / appearance_proxy, 0.2, 1.0)
    blended = 0.55 * _clamp(avg_start_minutes, 35.0, 90.0) + 0.45 * (55.0 + 30.0 * start_share)
    return _clamp(blended * availability, 10.0, 90.0)


def _per90_rate(player: dict, cumulative_key: str, per90_key: str, fallback: float) -> float:
    per90 = player.get(per90_key)
    if isinstance(per90, (int, float)) and float(per90) > 0:
        return float(per90)

    minutes = float(player.get("minutes") or 0.0)
    cumulative = float(player.get(cumulative_key) or 0.0)
    if minutes > 0 and cumulative > 0:
        return cumulative / minutes * 90.0
    return fallback


def _raw_player_points(
    player: dict,
    *,
    goals_for: int,
    goals_against: int,
    baseline_goals: float,
) -> float:
    pos = int(player.get("pos_type") or 0)
    minutes = _expected_minutes(player)
    minutes_share = _clamp(minutes / 90.0, 0.15, 1.0)
    scale = goals_for / max(baseline_goals, 0.35)

    goal_rate = _per90_rate(player, "xg", "xg_per90", {1: 0.01, 2: 0.03, 3: 0.12, 4: 0.18}.get(pos, 0.08))
    assist_rate = _per90_rate(player, "xa", "xa_per90", {1: 0.01, 2: 0.04, 3: 0.10, 4: 0.07}.get(pos, 0.05))

    penalties_order = player.get("penalties_order")
    if penalties_order == 1:
        goal_rate += 0.09
    elif penalties_order == 2:
        goal_rate += 0.04

    corners_order = player.get("corners_order")
    if corners_order == 1:
        assist_rate += 0.06
    elif corners_order == 2:
        assist_rate += 0.03

    appearance_points = 1.0 + (1.0 if minutes >= 60 else minutes / 60.0)
    expected_goals = goal_rate * minutes_share * scale
    expected_assists = assist_rate * minutes_share * scale
    goal_points = analysis.POS_GOAL_POINTS.get(pos, 4) * expected_goals
    assist_points = 3.0 * expected_assists
    clean_sheet_points = float(analysis.POS_CS_POINTS.get(pos, 0)) if goals_against == 0 else 0.0
    goals_conceded_penalty = -float(goals_against // 2) if analysis.POS_GC_PENALTY.get(pos, False) else 0.0
    bonus_points = min(
        3.0,
        0.16 * (goal_points + assist_points) + (0.45 if goals_against == 0 and pos in (1, 2) else 0.0),
    )
    save_points = 0.25 * max(goals_against, 0) if pos == 1 else 0.0
    return appearance_points + goal_points + assist_points + clean_sheet_points + goals_conceded_penalty + bonus_points + save_points


def _team_outcome_points(
    players: list[dict],
    side: str,
    score_matrix,
    baseline_goals: float,
) -> dict[str, float]:
    masks = match_model.score_masks(score_matrix.shape)
    bucket_probs = {
        "home_win": float(score_matrix[masks["home_win"]].sum()),
        "draw": float(score_matrix[masks["draw"]].sum()),
        "away_win": float(score_matrix[masks["away_win"]].sum()),
    }

    totals = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}
    for player in players:
        raw_matrix = score_matrix * 0.0
        for home_goals in range(score_matrix.shape[0]):
            for away_goals in range(score_matrix.shape[1]):
                goals_for = home_goals if side == "home" else away_goals
                goals_against = away_goals if side == "home" else home_goals
                raw_matrix[home_goals, away_goals] = _raw_player_points(
                    player,
                    goals_for=goals_for,
                    goals_against=goals_against,
                    baseline_goals=baseline_goals,
                )

        unconditional = float((raw_matrix * score_matrix).sum())
        anchor_ep = float(player.get("ep_next") or 0.0)
        if anchor_ep <= 0:
            anchor_ep = unconditional
        scale = _clamp(anchor_ep / max(unconditional, 0.75), 0.55, 1.65) if unconditional > 0 else 1.0

        for outcome, mask in (
            ("home_win", masks["home_win"]),
            ("draw", masks["draw"]),
            ("away_win", masks["away_win"]),
        ):
            prob = bucket_probs[outcome]
            if prob <= 0:
                continue
            conditional = float((raw_matrix[mask] * score_matrix[mask]).sum()) / prob
            totals[outcome] += conditional * scale

    return totals


def _compute_fixture_angle(
    *,
    captain: bool,
    n_home: int,
    n_away: int,
    hw_ep: float,
    aw_ep: float,
    d_ep: float,
    ep_pct: float,
    home_short: str,
    away_short: str,
) -> dict:
    total_players = n_home + n_away
    best_ep = max(hw_ep, aw_ep, d_ep)
    worst_ep = min(hw_ep, aw_ep, d_ep)
    swing = round(best_ep - worst_ep, 0)

    results = {"home_win": hw_ep, "draw": d_ep, "away_win": aw_ep}
    best_result = max(results, key=results.get)
    worst_result = min(results, key=results.get)

    result_labels = {
        "home_win": f"{home_short} win",
        "draw": "a draw",
        "away_win": f"{away_short} win",
    }

    if swing < 3 or ep_pct < 5:
        return {
            "severity": "low",
            "swing": swing,
            "headline": "Low leverage fixture",
            "detail": f"Only {total_players} starter{'s' if total_players != 1 else ''} in this match. The result barely moves your week.",
            "best_result": result_labels[best_result],
            "worst_result": result_labels[worst_result],
        }

    if swing >= 10 and captain:
        return {
            "severity": "high",
            "swing": swing,
            "headline": "Your captain runs through this match",
            "detail": f"{total_players} starters including the armband. {result_labels[best_result].capitalize()} is your best case ({best_ep:.0f} pts) and {result_labels[worst_result]} is the worst ({worst_ep:.0f} pts).",
            "best_result": result_labels[best_result],
            "worst_result": result_labels[worst_result],
        }

    if swing >= 8:
        return {
            "severity": "high",
            "swing": swing,
            "headline": "Big swing fixture",
            "detail": f"You are leaning on {result_labels[best_result]} here. The gap from best to worst case is about {swing:.0f} points.",
            "best_result": result_labels[best_result],
            "worst_result": result_labels[worst_result],
        }

    if swing >= 4:
        return {
            "severity": "medium",
            "swing": swing,
            "headline": "Moderate leverage",
            "detail": f"Your {total_players} starter{'s' if total_players != 1 else ''} prefer {result_labels[best_result]}. Worth watching, but not the whole week.",
            "best_result": result_labels[best_result],
            "worst_result": result_labels[worst_result],
        }

    return {
        "severity": "low",
        "swing": swing,
        "headline": "Small impact",
        "detail": f"This match can move your score by roughly {swing:.0f} points either way.",
        "best_result": result_labels[best_result],
        "worst_result": result_labels[worst_result],
    }


def _build_summary(reports: list[dict]) -> dict:
    total_ep_range = sum(report["ep_range"] for report in reports)
    total_outcome_variance = sum(report.get("outcome_variance", 0.0) for report in reports)
    high_risk = [report for report in reports if report["angle"].get("severity") == "high"]
    medium_risk = [report for report in reports if report["angle"].get("severity") == "medium"]

    biggest = reports[0] if reports else None

    return {
        "fixtures_with_players": len(reports),
        "total_ep_variance": round(total_ep_range, 1),
        "total_outcome_variance": round(total_outcome_variance, 2),
        "portfolio_ep_std": round(math.sqrt(max(total_outcome_variance, 0.0)), 2),
        "high_risk_fixtures": len(high_risk),
        "medium_risk_fixtures": len(medium_risk),
        "biggest_exposure": {
            "fixture": f"{biggest['home']} vs {biggest['away']}" if biggest else None,
            "ep_range": biggest["ep_range"] if biggest else 0,
            "ep_pct": biggest["ep_pct_of_squad"] if biggest else 0,
        }
        if biggest
        else None,
    }
