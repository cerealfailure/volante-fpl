"""
Shared soccer match-model helpers for fixture conditioning.

The model does two jobs:
  - derive a score grid from FPL team strength inputs
  - map scoreline buckets into coherent outcome probabilities

That lets Volante condition squad EP on coherent match outcomes instead of
flat multipliers.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

DEFAULT_HOME_GOALS = 1.42
DEFAULT_AWAY_GOALS = 1.18
DEFAULT_TOTAL_GOALS = DEFAULT_HOME_GOALS + DEFAULT_AWAY_GOALS
DEFAULT_HOME_SHARE = DEFAULT_HOME_GOALS / DEFAULT_TOTAL_GOALS
LOW_DRAW_TOTAL = 2.35
LEAGUE_STRENGTH_ANCHOR = 1100.0
MAX_GOALS = 8
LINE_RE = re.compile(r"(\d+(?:\.\d+)?)")
TEAM_ALIAS_FIXES = {
    "man city": "manchester city",
    "man utd": "manchester united",
    "spurs": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "newcastle": "newcastle united",
    "forest": "nottingham forest",
    "brighton": "brighton and hove albion",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_team_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", str(name or "").lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned == "draw":
        return "draw"
    return TEAM_ALIAS_FIXES.get(cleaned, cleaned)


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_term = math.exp(-value)
        return 1.0 / (1.0 + exp_term)
    exp_term = math.exp(value)
    return exp_term / (1.0 + exp_term)


def _logit(value: float) -> float:
    clipped = _clamp(value, 1e-6, 1 - 1e-6)
    return math.log(clipped / (1.0 - clipped))


def _poisson_cdf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    pmf = math.exp(-lam)
    total = pmf
    for idx in range(1, k + 1):
        pmf *= lam / idx
        total += pmf
    return _clamp(total, 0.0, 1.0)


def _poisson_vector(lam: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    lam = _clamp(float(lam), 0.05, 8.0)
    probs = [math.exp(-lam)]
    for idx in range(1, max_goals):
        probs.append(probs[-1] * lam / idx)
    tail = max(0.0, 1.0 - sum(probs))
    probs.append(tail)
    return np.array(probs, dtype=float)


def build_score_matrix(
    lambda_home: float,
    lambda_away: float,
    *,
    max_goals: int = MAX_GOALS,
) -> np.ndarray:
    """Independent-Poisson score grid with a final tail bucket."""
    return np.outer(
        _poisson_vector(lambda_home, max_goals=max_goals),
        _poisson_vector(lambda_away, max_goals=max_goals),
    )


def score_masks(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    home = np.arange(shape[0])[:, None]
    away = np.arange(shape[1])[None, :]
    return {
        "home_win": home > away,
        "draw": home == away,
        "away_win": home < away,
        "totals": home + away,
    }


def outcome_probabilities(matrix: np.ndarray) -> dict[str, float]:
    masks = score_masks(matrix.shape)
    return {
        "home_win": float(matrix[masks["home_win"]].sum()),
        "draw": float(matrix[masks["draw"]].sum()),
        "away_win": float(matrix[masks["away_win"]].sum()),
    }


def totals_event_probability(total_goals: float, side: str, line: float) -> float:
    line = float(line)
    if abs(line - round(line)) < 1e-9:
        push_line = int(round(line))
        if side == "over":
            return 1.0 - _poisson_cdf(push_line, total_goals)
        return _poisson_cdf(push_line - 1, total_goals)

    cutoff = math.floor(line + 1e-9)
    if side == "over":
        return 1.0 - _poisson_cdf(cutoff, total_goals)
    return _poisson_cdf(cutoff, total_goals)


def parse_line(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "")
    match = LINE_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def h2h_side(leg: dict[str, Any]) -> str | None:
    outcome = normalize_team_name(str(leg.get("outcome_name") or ""))
    if outcome == "draw":
        return "draw"

    home = normalize_team_name(str(leg.get("match_home") or ""))
    away = normalize_team_name(str(leg.get("match_away") or ""))
    if outcome and outcome == home:
        return "home"
    if outcome and outcome == away:
        return "away"
    return None


def describe_leg(leg: dict[str, Any]) -> dict[str, Any] | None:
    leg_type = str(leg.get("type") or "").lower()
    if leg_type == "h2h":
        side = h2h_side(leg)
        if not side:
            return None
        return {"family": "h2h", "side": side}

    if leg_type in {"totals_over", "totals_under"}:
        line = parse_line(leg.get("line") or leg.get("outcome_name"))
        if line is None:
            return None
        return {
            "family": "totals",
            "side": "over" if leg_type.endswith("over") else "under",
            "line": float(line),
        }

    if leg_type == "totals":
        line = parse_line(leg.get("line") or leg.get("outcome_name"))
        outcome_name = str(leg.get("outcome_name") or "").lower()
        if line is None or not outcome_name:
            return None
        if "over" in outcome_name:
            side = "over"
        elif "under" in outcome_name:
            side = "under"
        else:
            return None
        return {"family": "totals", "side": side, "line": float(line)}

    return None


def supports_score_model(leg: dict[str, Any]) -> bool:
    return describe_leg(leg) is not None


def leg_probability(leg: dict[str, Any], matrix: np.ndarray) -> float | None:
    desc = describe_leg(leg)
    if not desc:
        return None

    masks = score_masks(matrix.shape)
    if desc["family"] == "h2h":
        if desc["side"] == "home":
            return float(matrix[masks["home_win"]].sum())
        if desc["side"] == "draw":
            return float(matrix[masks["draw"]].sum())
        if desc["side"] == "away":
            return float(matrix[masks["away_win"]].sum())
        return None

    totals = masks["totals"]
    line = float(desc["line"])
    if abs(line - round(line)) < 1e-9:
        integer_line = int(round(line))
        if desc["side"] == "over":
            return float(matrix[totals > integer_line].sum())
        return float(matrix[totals < integer_line].sum())
    if desc["side"] == "over":
        return float(matrix[totals > line].sum())
    return float(matrix[totals < line].sum())


def joint_leg_probability(legs: list[dict[str, Any]], matrix: np.ndarray) -> float:
    mask = np.ones(matrix.shape, dtype=bool)
    for leg in legs:
        desc = describe_leg(leg)
        if not desc:
            continue
        masks = score_masks(matrix.shape)
        if desc["family"] == "h2h":
            if desc["side"] == "home":
                mask &= masks["home_win"]
            elif desc["side"] == "draw":
                mask &= masks["draw"]
            else:
                mask &= masks["away_win"]
            continue

        totals = masks["totals"]
        line = float(desc["line"])
        if abs(line - round(line)) < 1e-9:
            integer_line = int(round(line))
            if desc["side"] == "over":
                mask &= totals > integer_line
            else:
                mask &= totals < integer_line
        elif desc["side"] == "over":
            mask &= totals > line
        else:
            mask &= totals < line
    return float(matrix[mask].sum())


def event_correlation(leg_a: dict[str, Any], leg_b: dict[str, Any], matrix: np.ndarray) -> float | None:
    p_a = leg_probability(leg_a, matrix)
    p_b = leg_probability(leg_b, matrix)
    if p_a is None or p_b is None:
        return None

    p_ab = joint_leg_probability([leg_a, leg_b], matrix)
    denom = math.sqrt(max(p_a * (1.0 - p_a) * p_b * (1.0 - p_b), 1e-12))
    return _clamp((p_ab - p_a * p_b) / denom, -0.999, 0.999)


def goal_rates_from_strengths(fixture: dict[str, Any]) -> tuple[float, float]:
    """Convert FPL strength ratings into a plausible Poisson baseline."""
    home_attack = float(fixture.get("str_attack_home") or LEAGUE_STRENGTH_ANCHOR)
    away_attack = float(fixture.get("str_attack_away") or LEAGUE_STRENGTH_ANCHOR)
    home_def = float(fixture.get("str_defence_home") or LEAGUE_STRENGTH_ANCHOR)
    away_def = float(fixture.get("str_defence_away") or LEAGUE_STRENGTH_ANCHOR)

    home_ratio = (
        math.log(max(home_attack, 1.0) / LEAGUE_STRENGTH_ANCHOR)
        - math.log(max(away_def, 1.0) / LEAGUE_STRENGTH_ANCHOR)
    )
    away_ratio = (
        math.log(max(away_attack, 1.0) / LEAGUE_STRENGTH_ANCHOR)
        - math.log(max(home_def, 1.0) / LEAGUE_STRENGTH_ANCHOR)
    )

    lambda_home = DEFAULT_HOME_GOALS * math.exp(0.45 * home_ratio)
    lambda_away = DEFAULT_AWAY_GOALS * math.exp(0.45 * away_ratio)
    total = lambda_home + lambda_away
    scaled_total = _clamp(total, 1.8, 4.0)
    scale = scaled_total / max(total, 1e-9)
    return (
        _clamp(lambda_home * scale, 0.35, 3.4),
        _clamp(lambda_away * scale, 0.25, 3.0),
    )

