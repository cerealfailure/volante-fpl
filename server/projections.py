"""
Deterministic player projection engine.

Goals:
  - replace raw FPL `ep_next` as the public-facing projection signal
  - convert availability/news into numeric multipliers deterministically
  - calibrate listed probabilities against realized starts/minutes over time
  - keep the transfer planner, squad page, and private intel on one model
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
import re

import db

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POS_CS_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}
POS_GOAL_POINTS = {1: 6, 2: 6, 3: 5, 4: 4}
ATK_MULT = {1: 1.18, 2: 1.11, 3: 1.00, 4: 0.89, 5: 0.78}
DEF_MULT = {1: 1.16, 2: 1.08, 3: 1.00, 4: 0.91, 5: 0.82}
HOME_ATTACK_BOOST = 1.05
AWAY_ATTACK_BOOST = 0.97
HOME_DEFENSE_BOOST = 1.04
AWAY_DEFENSE_BOOST = 0.98
DECAY = 0.86
DEFAULT_HORIZON = 5
SUPPORTED_HORIZONS = (1, 3, 5, 8)
MODEL_VERSION = "volante-projection-v2"
INTERNAL_PROJECTION_SOURCE_KEY = "volante_model"
INTERNAL_PROJECTION_LABEL = "Volante Deterministic xP"

STATUS_PLAY_PROB = {
    "a": 0.98,
    "d": 0.74,
    "i": 0.34,
    "u": 0.24,
    "n": 0.05,
    "s": 0.02,
}

# Exponential recovery time constants in days. Fraction recovered by fixture day T is
# 1 - exp(-T / tau). Set from typical recovery windows: muscle strains clear in ~2
# weeks (tau=6 → ~90% recovered at day 14), knocks in under a week (tau=2.5), major
# injuries (ACL, Achilles) barely move inside a 5-GW window (tau=30). Suspensions use
# a fast curve because most EPL bans are 1–3 games.
RECOVERY_TAU_DAYS = {
    "suspension": 8.0,
    "major_injury": 30.0,
    "muscle_injury": 6.0,
    "impact_injury": 4.5,
    "illness": 1.8,
    "knock": 2.5,
    "assessment": 3.0,
    "rest": 3.5,
    "personal": 3.0,
    "general": 4.5,
    "official_only": 3.5,
    "positive_update": 1.5,
    "healthy": 0.0,
}

NEWS_RULES = [
    ("suspension", ("suspended", "ban", "banned", "red card"), 0.98, 0.05, 0.98, "Suspension signal"),
    ("major_injury", ("acl", "achilles", "surgery", "rupture", "long-term", "long term"), 0.92, 0.18, 0.95, "Major injury signal"),
    ("muscle_injury", ("hamstring", "calf", "groin", "thigh", "muscle"), 0.56, 0.63, 0.87, "Muscle injury signal"),
    ("impact_injury", ("ankle", "foot", "hip", "back", "shoulder", "wrist"), 0.40, 0.77, 0.80, "Impact injury signal"),
    ("illness", ("illness", "virus", "fever", "sick"), 0.42, 0.75, 0.80, "Illness signal"),
    ("knock", ("knock", "minor issue", "minor problem"), 0.30, 0.84, 0.72, "Knock / minor issue"),
    ("assessment", ("late fitness test", "being assessed", "assessment", "scan"), 0.34, 0.83, 0.62, "Assessment signal"),
    ("rest", ("rested", "rotation", "managed", "load"), 0.18, 0.91, 0.56, "Rest / rotation signal"),
    ("personal", ("personal", "bereavement", "compassionate"), 0.46, 0.67, 0.84, "Personal-absence signal"),
]

POSITIVE_NEWS_PHRASES = (
    "available",
    "fit",
    "returns",
    "returned",
    "back in training",
    "back available",
    "cleared",
    "ready",
)

VAGUE_NEWS_PHRASES = (
    "monitor",
    "assessment",
    "assessed",
    "late test",
    "await",
    "scan",
    "check",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fixture_days_ahead(fixture: dict, reference: datetime) -> float:
    kickoff = fixture.get("kickoff_time")
    if not kickoff:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (dt - reference).total_seconds() / 86400.0)


def _recovery_factor(news_category: str, days_ahead: float) -> float:
    """Interpolation weight toward healthy baseline: 0 = still at current availability,
    1 = fully recovered. Exponential approach governed by category-specific tau."""
    if news_category in {"healthy", "positive_update"}:
        return 1.0
    tau = RECOVERY_TAU_DAYS.get(news_category, 4.5)
    if tau is None or tau <= 0 or days_ahead <= 0:
        return 0.0
    return 1.0 - math.exp(-days_ahead / tau)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _availability_compare_fields(row: dict) -> dict:
    return {
        "status": row.get("status"),
        "chance_next": row.get("chance_next"),
        "news": row.get("news"),
        "news_category": row.get("news_category"),
        "news_severity": round(_safe_float(row.get("news_severity")), 4),
        "news_purity": round(_safe_float(row.get("news_purity")), 4),
        "listed_play_prob": round(_safe_float(row.get("listed_play_prob")), 4),
        "listed_start_prob": round(_safe_float(row.get("listed_start_prob")), 4),
        "expected_minutes": round(_safe_float(row.get("expected_minutes")), 2),
        "model_version": row.get("model_version"),
    }


def _availability_changed_fields(previous: dict | None, current: dict) -> list[str]:
    if not previous:
        return list(_availability_compare_fields(current).keys())
    previous_fields = _availability_compare_fields(previous)
    current_fields = _availability_compare_fields(current)
    changed = []
    for key, value in current_fields.items():
        if previous_fields.get(key) != value:
            changed.append(key)
    return changed


def normalize_horizon(horizon: int | None) -> int:
    if horizon is None:
        return DEFAULT_HORIZON
    horizon = max(1, min(8, int(horizon)))
    if horizon in SUPPORTED_HORIZONS:
        return horizon
    return min(SUPPORTED_HORIZONS, key=lambda option: abs(option - horizon))


def player_price(player: dict) -> float:
    if player.get("price") is not None:
        return float(player["price"])
    return _safe_float(player.get("now_cost")) / 10.0


def player_position(player: dict) -> int:
    return int(player.get("position") or player.get("pos_type") or 0)


def chance_bucket(chance_next) -> str:
    if chance_next in (None, ""):
        return "unknown"
    chance = int(float(chance_next))
    if chance <= 25:
        return "0-25"
    if chance <= 50:
        return "26-50"
    if chance <= 75:
        return "51-75"
    if chance < 100:
        return "76-99"
    return "100"


def parse_news_signal(player: dict) -> dict:
    text = str(player.get("news") or "").strip()
    lower = text.lower()
    status = str(player.get("status") or "a").lower()
    chance = player.get("chance_next")

    if not lower:
        return {
            "category": "healthy" if status == "a" else "official_only",
            "label": "No textual news flag",
            "severity": 0.0 if status == "a" else 0.18,
            "purity": 0.34,
            "availability_multiplier": 1.0 if status == "a" else 0.92,
            "text": text,
            "vague": False,
        }

    category = "general"
    label = "General news signal"
    severity = 0.18
    multiplier = 0.92
    purity = 0.52

    for rule_category, phrases, rule_severity, rule_multiplier, rule_purity, rule_label in NEWS_RULES:
        if any(phrase in lower for phrase in phrases):
            category = rule_category
            label = rule_label
            severity = rule_severity
            multiplier = rule_multiplier
            purity = rule_purity
            break

    positive = any(phrase in lower for phrase in POSITIVE_NEWS_PHRASES)
    vague = any(phrase in lower for phrase in VAGUE_NEWS_PHRASES)
    has_date_hint = bool(re.search(r"\b\d{1,2}[/-]\d{1,2}\b", lower) or re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", lower))

    if positive:
        multiplier = max(multiplier, 0.93)
        severity *= 0.72
        purity += 0.08
        if category == "general":
            category = "positive_update"
            label = "Positive availability update"

    if vague:
        purity -= 0.12
        severity += 0.06

    if has_date_hint:
        purity += 0.08

    if chance is not None:
        multiplier *= 0.82 + 0.18 * _clamp(float(chance) / 100.0, 0.0, 1.0)

    purity = _clamp(purity, 0.2, 0.98)
    severity = _clamp(severity, 0.0, 1.0)
    multiplier = _clamp(multiplier, 0.05, 1.08)
    return {
        "category": category,
        "label": label,
        "severity": severity,
        "purity": purity,
        "availability_multiplier": multiplier,
        "text": text,
        "vague": vague,
    }


def _season_start_rate(player: dict, current_event: int | None) -> float:
    starts = _safe_float(player.get("starts"))
    possible = max(min(current_event or 38, 38), 1)
    return _clamp(starts / possible, 0.05, 0.99)


def _average_start_minutes(player: dict) -> float:
    starts = max(_safe_float(player.get("starts")), 1.0)
    minutes = _safe_float(player.get("minutes"))
    if minutes <= 0:
        return 78.0
    return _clamp(minutes / starts, 55.0, 90.0)


def _base_play_probability(status: str, chance_next) -> float:
    if chance_next is not None:
        return _clamp(float(chance_next) / 100.0, 0.02, 0.99)
    return STATUS_PLAY_PROB.get(status, 0.72)


def _base_start_probability(play_prob: float, season_start_rate: float) -> float:
    rotation_factor = 0.32 + 0.68 * season_start_rate
    return _clamp(play_prob * rotation_factor, 0.01, play_prob)


def _official_availability(player: dict, current_event: int | None) -> dict:
    status = str(player.get("status") or "a").lower()
    chance = player.get("chance_next")
    play_prob = _base_play_probability(status, chance)
    start_prob = _base_start_probability(play_prob, _season_start_rate(player, current_event))
    avg_start_minutes = _average_start_minutes(player)
    expected_minutes = start_prob * avg_start_minutes + max(play_prob - start_prob, 0.0) * 18.0
    return {
        "play_prob": play_prob,
        "start_prob": start_prob,
        "expected_minutes": _clamp(expected_minutes, 3.0, 90.0),
    }


def _per90_rate(player: dict, per90_key: str, cumulative_key: str, fallback: float) -> float:
    per90 = player.get(per90_key)
    if per90 is not None and float(per90) > 0:
        return float(per90)
    minutes = _safe_float(player.get("minutes"))
    cumulative = _safe_float(player.get(cumulative_key))
    if minutes > 0 and cumulative > 0:
        return cumulative / minutes * 90.0
    return fallback


def _estimated_appearance_count(player: dict) -> float:
    minutes = _safe_float(player.get("minutes"))
    starts = _safe_float(player.get("starts"))
    if minutes <= 0:
        return max(starts, 1.0)
    cameo_proxy = max((minutes / 22.0) - starts, 0.0) * 0.22
    return max(starts + cameo_proxy, 1.0)


def _fixture_scale(fixture: dict, team_id: int, position: int) -> tuple[float, float]:
    is_home = fixture.get("team_h") == team_id
    difficulty = (fixture.get("team_a_difficulty") if is_home else fixture.get("team_h_difficulty")) or 3
    attack = ATK_MULT.get(difficulty, 1.0)
    defense = DEF_MULT.get(difficulty, 1.0)
    attack *= HOME_ATTACK_BOOST if is_home else AWAY_ATTACK_BOOST
    defense *= HOME_DEFENSE_BOOST if is_home else AWAY_DEFENSE_BOOST
    if position in (1, 2):
        attack *= 0.96
    return attack, defense


def _base_components(player: dict, current_event: int | None) -> dict:
    pos = player_position(player)
    xg_per90 = _per90_rate(player, "xg_per90", "xg", {1: 0.01, 2: 0.03, 3: 0.12, 4: 0.19}.get(pos, 0.08))
    xa_per90 = _per90_rate(player, "xa_per90", "xa", {1: 0.01, 2: 0.04, 3: 0.11, 4: 0.07}.get(pos, 0.05))
    xgc_per90 = _per90_rate(player, "xgc_per90", "xgc", 1.45 if pos in (1, 2) else 1.25)

    set_piece_bonus = 0.0
    penalties_order = player.get("penalties_order")
    corners_order = player.get("corners_order")
    if penalties_order == 1:
        set_piece_bonus += 0.42
    elif penalties_order == 2:
        set_piece_bonus += 0.2
    if corners_order == 1:
        set_piece_bonus += 0.18
    elif corners_order == 2:
        set_piece_bonus += 0.1

    attack_component = POS_GOAL_POINTS.get(pos, 4) * xg_per90 * 0.88 + 3.0 * xa_per90 * 0.84 + set_piece_bonus
    attack_component = max(attack_component, 0.06)

    starts = max(_safe_float(player.get("starts")), 1.0)
    clean_sheet_rate = _clamp(_safe_float(player.get("clean_sheets")) / starts, 0.02, 0.62)
    defense_component = 0.0
    if pos in (1, 2):
        resilience = _clamp(0.24 + 0.62 * clean_sheet_rate + max(0.0, 1.35 - xgc_per90) * 0.12, 0.08, 0.6)
        defense_component = POS_CS_POINTS[pos] * resilience
    elif pos == 3:
        resilience = _clamp(0.18 + 0.55 * clean_sheet_rate + max(0.0, 1.3 - xgc_per90) * 0.08, 0.06, 0.45)
        defense_component = POS_CS_POINTS[pos] * resilience

    minutes = max(_safe_float(player.get("minutes")), 1.0)
    bonus_per90 = _safe_float(player.get("bonus")) / (minutes / 90.0)
    bonus_component = _clamp(bonus_per90 * 0.46, 0.02, 1.35)

    appearances = _estimated_appearance_count(player)
    season_points_per_match = _safe_float(player.get("total_points")) / appearances
    underlying_match = 2.0 + attack_component + defense_component + bonus_component
    conversion_bias = _clamp(season_points_per_match / max(underlying_match, 1.6), 0.78, 1.22)
    form_match = max(_safe_float(player.get("form")), 1.0)
    form_boost = _clamp(1.0 + 0.035 * (form_match - season_points_per_match), 0.9, 1.15)

    return {
        "attack_component": attack_component * conversion_bias * form_boost,
        "defense_component": defense_component * (0.88 + 0.12 * conversion_bias),
        "bonus_component": bonus_component * _clamp(0.86 + 0.22 * conversion_bias, 0.78, 1.18),
        "season_points_per_match": season_points_per_match,
        "underlying_match": underlying_match,
        "conversion_bias": conversion_bias,
        "form_boost": form_boost,
        "official_ep": max(_safe_float(player.get("ep_next")), 0.0),
        "average_start_minutes": _average_start_minutes(player),
        "season_start_rate": _season_start_rate(player, current_event),
        "healthy_play_prob": STATUS_PLAY_PROB["a"],
        "healthy_start_prob": _base_start_probability(
            STATUS_PLAY_PROB["a"],
            _season_start_rate(player, current_event),
        ),
    }


def _profile_lookup_key(team_id: int, status: str, bucket: str, category: str) -> tuple[int, str, str, str]:
    return (int(team_id or 0), status or "a", bucket or "unknown", category or "none")


DEFAULT_PROFILE = {
    "team_id": 0,
    "status": "a",
    "chance_bucket": "unknown",
    "news_category": "any",
    "sample_size": 0,
    "listed_play_rate": 0.82,
    "actual_play_rate": 0.82,
    "listed_start_rate": 0.68,
    "actual_start_rate": 0.68,
    "listed_minutes": 68.0,
    "actual_minutes": 68.0,
    "play_bias": 0.0,
    "start_bias": 0.0,
    "mean_abs_error": 0.18,
    "honesty_score": 0.82,
}


def _select_profile(player: dict, news_signal: dict, availability_state: dict | None) -> dict:
    if not availability_state:
        return DEFAULT_PROFILE

    lookup = availability_state.get("profiles") or {}
    team_id = int(player.get("team_id") or 0)
    status = str(player.get("status") or "a").lower()
    bucket = chance_bucket(player.get("chance_next"))
    category = news_signal["category"]

    candidates = [
        _profile_lookup_key(team_id, status, bucket, category),
        _profile_lookup_key(team_id, status, bucket, "any"),
        _profile_lookup_key(0, status, bucket, category),
        _profile_lookup_key(0, status, bucket, "any"),
    ]
    for key in candidates:
        if key in lookup:
            return lookup[key]
    return DEFAULT_PROFILE


def explain_availability(
    player: dict,
    current_event: int | None,
    availability_state: dict | None = None,
) -> dict:
    status = str(player.get("status") or "a").lower()
    news_signal = parse_news_signal(player)
    official = _official_availability(player, current_event)
    profile = _select_profile(player, news_signal, availability_state)

    purity = news_signal["purity"]
    calibration_strength = min(float(profile.get("sample_size", 0)) / 8.0, 1.0) * max(purity, 0.35)

    play_prob = official["play_prob"] * news_signal["availability_multiplier"]
    start_prob = official["start_prob"] * (0.84 + 0.16 * news_signal["availability_multiplier"])
    play_prob = _clamp(play_prob + calibration_strength * _safe_float(profile.get("play_bias")), 0.01, 0.99)
    start_prob = _clamp(start_prob + calibration_strength * _safe_float(profile.get("start_bias")), 0.01, play_prob)

    avg_start_minutes = _average_start_minutes(player)
    cameo_minutes = 18.0 if status != "a" else 15.0
    expected_minutes = start_prob * avg_start_minutes + max(play_prob - start_prob, 0.0) * cameo_minutes
    expected_minutes = _clamp(expected_minutes, 2.0, 90.0)
    sixty_plus_prob = _clamp(start_prob * min(1.0, expected_minutes / 62.0), 0.0, play_prob)
    minutes_factor = _clamp(expected_minutes / 82.0, 0.05, 1.08)

    honesty_score = _clamp(_safe_float(profile.get("honesty_score"), 0.82), 0.35, 0.98)
    distortion_rate = _clamp(1.0 - honesty_score, 0.02, 0.65)
    uncertainty = _clamp(
        0.18
        + 0.42 * (1.0 - play_prob)
        + 0.22 * distortion_rate
        + 0.16 * purity * news_signal["severity"]
        + 0.12 * _safe_float(profile.get("mean_abs_error"), 0.18),
        0.05,
        0.98,
    )

    return {
        "play_probability": round(play_prob, 4),
        "start_probability": round(start_prob, 4),
        "sixty_plus_probability": round(sixty_plus_prob, 4),
        "expected_minutes": round(expected_minutes, 2),
        "minutes_factor": round(minutes_factor, 4),
        "listed_play_probability": round(official["play_prob"], 4),
        "listed_start_probability": round(official["start_prob"], 4),
        "reliability_score": round(honesty_score, 4),
        "distortion_rate": round(distortion_rate, 4),
        "play_bias": round(_safe_float(profile.get("play_bias")), 4),
        "start_bias": round(_safe_float(profile.get("start_bias")), 4),
        "profile_samples": int(profile.get("sample_size", 0) or 0),
        "news_category": news_signal["category"],
        "news_label": news_signal["label"],
        "news_severity": round(news_signal["severity"], 4),
        "news_purity": round(news_signal["purity"], 4),
        "news_multiplier": round(news_signal["availability_multiplier"], 4),
        "uncertainty": round(uncertainty, 4),
        "chance_bucket": chance_bucket(player.get("chance_next")),
    }


def project_player(
    player: dict,
    fixtures_by_team: dict[int, list[dict]],
    horizon: int,
    current_event: int | None,
    availability_state: dict | None = None,
) -> dict:
    horizon = normalize_horizon(horizon)
    team_id = int(player.get("team_id") or 0)
    target_event = (
        int(availability_state.get("target_event"))
        if availability_state and availability_state.get("target_event") is not None
        else int(current_event or 1)
    )
    window_end_event = target_event + horizon - 1
    fixtures = list(fixtures_by_team.get(team_id, []))
    relevant_fixtures = [
        fixture
        for fixture in fixtures
        if int(fixture.get("event") or target_event) <= window_end_event
    ]
    fixtures_in_target_event = max(sum(1 for fixture in relevant_fixtures if fixture.get("event") == target_event), 1)

    availability = explain_availability(player, current_event, availability_state)
    base = _base_components(player, current_event)
    official_next = base["official_ep"]
    position = player_position(player)
    news_category = str(availability.get("news_category") or "healthy")
    healthy_play = base["healthy_play_prob"]
    healthy_start = base["healthy_start_prob"]
    now_utc = datetime.now(timezone.utc)

    per_fixture = []
    event_counts: dict[int, int] = defaultdict(int)
    next_event_total = 0.0
    horizon_total = 0.0

    for idx, fixture in enumerate(relevant_fixtures):
        fixture_event = int(fixture.get("event") or target_event)
        same_event_index = event_counts[fixture_event]
        event_counts[fixture_event] += 1

        attack_mult, defense_mult = _fixture_scale(fixture, team_id, position)
        opponent = fixture.get("away_short") if fixture.get("team_h") == team_id else fixture.get("home_short")
        is_home = fixture.get("team_h") == team_id
        event_gap = max(fixture_event - target_event, 0)
        fatigue_drag = max(0.76, 1.0 - 0.12 * same_event_index - 0.02 * event_gap)
        play_drag = max(0.8, 1.0 - 0.08 * same_event_index)

        days_ahead = _fixture_days_ahead(fixture, now_utc)
        recovery = _recovery_factor(news_category, days_ahead)
        recovered_play = availability["play_probability"] + (healthy_play - availability["play_probability"]) * recovery
        recovered_start = availability["start_probability"] + (healthy_start - availability["start_probability"]) * recovery

        fixture_play_prob = _clamp(recovered_play * play_drag, 0.01, 0.99)
        fixture_start_prob = _clamp(recovered_start * fatigue_drag, 0.01, fixture_play_prob)
        expected_minutes = _clamp(
            fixture_start_prob * base["average_start_minutes"] + max(fixture_play_prob - fixture_start_prob, 0.0) * 18.0,
            2.0,
            90.0,
        )
        sixty_plus_prob = _clamp(fixture_start_prob * min(1.0, expected_minutes / 62.0), 0.0, fixture_play_prob)
        appearance_points = fixture_play_prob + sixty_plus_prob

        attack_points = base["attack_component"] * attack_mult * (expected_minutes / 90.0)
        defense_points = base["defense_component"] * defense_mult * sixty_plus_prob
        bonus_points = base["bonus_component"] * math.sqrt(max(fixture_play_prob * max(sixty_plus_prob, 0.25), 0.0))

        raw_ep = appearance_points + attack_points + defense_points + bonus_points
        if fixture_event == target_event and official_next > 0:
            official_anchor = official_next / fixtures_in_target_event
            raw_ep = 0.92 * raw_ep + 0.08 * _clamp(official_anchor, raw_ep * 0.72, raw_ep * 1.28)

        decay_mult = DECAY ** event_gap
        decayed_ep = raw_ep * decay_mult
        next_event_total += raw_ep if fixture_event == target_event else 0.0
        horizon_total += decayed_ep
        per_fixture.append({
            "event": fixture_event,
            "opponent": opponent,
            "is_home": bool(is_home),
            "difficulty": (fixture.get("team_a_difficulty") if is_home else fixture.get("team_h_difficulty")) or 3,
            "ep": round(raw_ep, 2),
            "decayed_ep": round(decayed_ep, 2),
            "expected_minutes": round(expected_minutes, 1),
            "play_probability": round(fixture_play_prob, 4),
            "sixty_plus_probability": round(sixty_plus_prob, 4),
            "decay": round(decay_mult, 4),
            "days_ahead": round(days_ahead, 2),
            "recovery_factor": round(recovery, 4),
            "play_probability_baseline": round(availability["play_probability"], 4),
            "play_probability_recovered": round(recovered_play, 4),
        })

    if not per_fixture:
        if fixtures:
            next_event_total = 0.0
            horizon_total = 0.0
        else:
            fallback_ep = max(base["season_points_per_match"] * availability["minutes_factor"], 1.0)
            next_event_total = fallback_ep
            horizon_total = fallback_ep

    expected_minutes_next = sum(item["expected_minutes"] for item in per_fixture if item["event"] == target_event)
    next_minutes_factor = expected_minutes_next / max(90.0 * fixtures_in_target_event, 1.0)

    return {
        "model_version": MODEL_VERSION,
        "target_event": target_event,
        "horizon": horizon,
        "official_ep_next": round(official_next, 2),
        "next_event_ep": round(next_event_total, 2),
        "horizon_ep": round(horizon_total, 2),
        "expected_minutes_next": round(expected_minutes_next, 1),
        "next_minutes_factor": round(_clamp(next_minutes_factor, 0.02, 1.1), 4),
        "official_gap": round(official_next - next_event_total, 2),
        "availability": availability,
        "base_components": {
            "attack_component": round(base["attack_component"], 3),
            "defense_component": round(base["defense_component"], 3),
            "bonus_component": round(base["bonus_component"], 3),
            "season_points_per_match": round(base["season_points_per_match"], 3),
            "underlying_match": round(base["underlying_match"], 3),
            "conversion_bias": round(base["conversion_bias"], 3),
            "form_boost": round(base["form_boost"], 3),
        },
        "per_fixture": per_fixture,
    }


def project_player_ep(
    player: dict,
    fixtures_by_team: dict[int, list[dict]],
    horizon: int,
    current_event: int | None,
    availability_state: dict | None = None,
) -> float:
    return float(project_player(player, fixtures_by_team, horizon, current_event, availability_state)["horizon_ep"])


async def snapshot_current_availability(
    conn,
    current_event: int | None = None,
    snapshot_kind: str = "poll",
    snapshot_reason: str | None = None,
    force_history: bool = False,
) -> dict:
    if current_event is None:
        current_event = await db.get_current_event(conn)
    if current_event is None:
        current_event = 1
    target_event = await db.get_next_open_event(conn, current_event) or current_event
    previous_rows = await db.get_latest_availability_snapshots(conn, target_event)

    rows = await conn.execute_fetchall("""
        SELECT id, team_id, status, chance_next, news, starts, minutes
        FROM players
    """)
    snapshot_at = datetime.now(timezone.utc).isoformat()
    payload = []
    history_rows = []
    changed_players = 0
    for row in (dict(item) for item in rows):
        signal = parse_news_signal(row)
        official = _official_availability(row, current_event)
        current_row = {
            "target_event": target_event,
            "player_id": row["id"],
            "snapshot_at": snapshot_at,
            "team_id": row["team_id"],
            "status": row.get("status"),
            "chance_next": row.get("chance_next"),
            "news": row.get("news"),
            "news_category": signal["category"],
            "news_severity": signal["severity"],
            "news_purity": signal["purity"],
            "listed_play_prob": official["play_prob"],
            "listed_start_prob": official["start_prob"],
            "expected_minutes": official["expected_minutes"],
            "model_version": MODEL_VERSION,
        }
        payload.append(current_row)
        changed_fields = _availability_changed_fields(previous_rows.get(row["id"]), current_row)
        if changed_fields or force_history:
            changed_players += 1
            history_rows.append({
                **current_row,
                "snapshot_kind": snapshot_kind,
                "snapshot_reason": snapshot_reason,
                "changed_fields": changed_fields,
            })

    await db.upsert_availability_snapshots(conn, payload)
    await db.append_availability_tape(conn, history_rows)
    await conn.commit()
    return {
        "target_event": target_event,
        "count": len(payload),
        "history_rows": len(history_rows),
        "changed_players": changed_players,
        "snapshot_at": snapshot_at,
        "snapshot_kind": snapshot_kind,
    }


async def rebuild_availability_profiles(conn, as_of_event: int, lookback_events: int = 12) -> list[dict]:
    min_event = max(as_of_event - max(lookback_events, 1), 1)
    rows = await conn.execute_fetchall("""
        WITH actuals AS (
            SELECT
                player_id,
                event,
                SUM(minutes) AS actual_minutes,
                MAX(CASE WHEN minutes > 0 THEN 1 ELSE 0 END) AS actual_play,
                MAX(CASE WHEN starts > 0 OR minutes >= 60 THEN 1 ELSE 0 END) AS actual_start
            FROM player_gws
            GROUP BY player_id, event
        )
        SELECT
            s.team_id,
            COALESCE(NULLIF(s.status, ''), 'a') AS status,
            s.chance_next,
            COALESCE(NULLIF(s.news_category, ''), 'none') AS news_category,
            COALESCE(s.listed_play_prob, 0) AS listed_play_prob,
            COALESCE(s.listed_start_prob, 0) AS listed_start_prob,
            COALESCE(s.expected_minutes, 0) AS expected_minutes,
            COALESCE(a.actual_play, 0) AS actual_play,
            COALESCE(a.actual_start, 0) AS actual_start,
            COALESCE(a.actual_minutes, 0) AS actual_minutes
        FROM player_availability_snapshots s
        LEFT JOIN actuals a
          ON a.player_id = s.player_id
         AND a.event = s.target_event
        WHERE s.target_event < ?
          AND s.target_event >= ?
    """, (as_of_event, min_event))
    history = [dict(row) for row in rows]
    if not history:
        return []

    aggregates: dict[tuple[int, str, str, str], dict] = {}

    def _bump(team_id: int, status: str, bucket: str, category: str, row: dict):
        key = _profile_lookup_key(team_id, status, bucket, category)
        agg = aggregates.setdefault(key, {
            "team_id": team_id,
            "status": status,
            "chance_bucket": bucket,
            "news_category": category,
            "sample_size": 0,
            "listed_play_rate": 0.0,
            "actual_play_rate": 0.0,
            "listed_start_rate": 0.0,
            "actual_start_rate": 0.0,
            "listed_minutes": 0.0,
            "actual_minutes": 0.0,
            "abs_error_sum": 0.0,
        })
        agg["sample_size"] += 1
        agg["listed_play_rate"] += _safe_float(row.get("listed_play_prob"))
        agg["actual_play_rate"] += _safe_float(row.get("actual_play"))
        agg["listed_start_rate"] += _safe_float(row.get("listed_start_prob"))
        agg["actual_start_rate"] += _safe_float(row.get("actual_start"))
        agg["listed_minutes"] += _safe_float(row.get("expected_minutes"))
        agg["actual_minutes"] += _safe_float(row.get("actual_minutes"))
        agg["abs_error_sum"] += abs(_safe_float(row.get("actual_play")) - _safe_float(row.get("listed_play_prob")))

    for row in history:
        status = str(row.get("status") or "a").lower()
        bucket = chance_bucket(row.get("chance_next"))
        category = str(row.get("news_category") or "none")
        team_id = int(row.get("team_id") or 0)
        _bump(team_id, status, bucket, category, row)
        _bump(team_id, status, bucket, "any", row)
        _bump(0, status, bucket, category, row)
        _bump(0, status, bucket, "any", row)

    payload = []
    for agg in aggregates.values():
        sample_size = agg["sample_size"]
        if sample_size < 2:
            continue
        listed_play = agg["listed_play_rate"] / sample_size
        actual_play = agg["actual_play_rate"] / sample_size
        listed_start = agg["listed_start_rate"] / sample_size
        actual_start = agg["actual_start_rate"] / sample_size
        listed_minutes = agg["listed_minutes"] / sample_size
        actual_minutes = agg["actual_minutes"] / sample_size
        mean_abs_error = agg["abs_error_sum"] / sample_size
        honesty_score = _clamp(1.0 - mean_abs_error, 0.35, 0.98)
        payload.append({
            "team_id": agg["team_id"],
            "status": agg["status"],
            "chance_bucket": agg["chance_bucket"],
            "news_category": agg["news_category"],
            "sample_size": sample_size,
            "listed_play_rate": round(listed_play, 4),
            "actual_play_rate": round(actual_play, 4),
            "listed_start_rate": round(listed_start, 4),
            "actual_start_rate": round(actual_start, 4),
            "listed_minutes": round(listed_minutes, 2),
            "actual_minutes": round(actual_minutes, 2),
            "play_bias": round(actual_play - listed_play, 4),
            "start_bias": round(actual_start - listed_start, 4),
            "mean_abs_error": round(mean_abs_error, 4),
            "honesty_score": round(honesty_score, 4),
        })

    await db.upsert_availability_profiles(conn, as_of_event, payload)
    await conn.commit()
    return payload


async def build_projection_context(conn, current_event: int | None, horizon: int) -> dict:
    horizon = normalize_horizon(horizon)
    if current_event is None:
        current_event = await db.get_current_event(conn)
    if current_event is None:
        current_event = 1
    target_event = await db.get_next_open_event(conn, current_event) or current_event

    fixture_rows = await conn.execute_fetchall("""
        SELECT
            f.*,
            th.short_name as home_short,
            ta.short_name as away_short
        FROM fixtures f
        JOIN teams th ON f.team_h = th.id
        JOIN teams ta ON f.team_a = ta.id
        WHERE f.event >= ?
          AND f.event IS NOT NULL
          AND f.finished = 0
        ORDER BY f.event, f.kickoff_time, f.id
        LIMIT 300
    """, (target_event,))

    fixtures_by_team: dict[int, list[dict]] = defaultdict(list)
    for fixture in (dict(row) for row in fixture_rows):
        fixtures_by_team[fixture["team_h"]].append(fixture)
        fixtures_by_team[fixture["team_a"]].append(fixture)

    await rebuild_availability_profiles(conn, target_event)
    profiles = await db.get_availability_profiles(conn, target_event)
    profile_lookup = {
        _profile_lookup_key(
            row.get("team_id", 0),
            row.get("status"),
            row.get("chance_bucket"),
            row.get("news_category"),
        ): row
        for row in profiles
    }
    return {
        "current_event": current_event,
        "target_event": target_event,
        "horizon": horizon,
        "fixtures_by_team": fixtures_by_team,
        "profiles": profile_lookup,
        "profile_rows": profiles,
        "model_version": MODEL_VERSION,
    }


async def persist_internal_projection_snapshots(
    conn,
    current_event: int | None = None,
    horizons: tuple[int, ...] = (1, 5),
    changed_threshold: float = 0.2,
) -> dict:
    if current_event is None:
        current_event = await db.get_current_event(conn)
    if current_event is None:
        current_event = 1

    await db.upsert_signal_source(
        conn,
        INTERNAL_PROJECTION_SOURCE_KEY,
        INTERNAL_PROJECTION_LABEL,
        "system",
        1.0,
        True,
        {"model_version": MODEL_VERSION},
    )

    player_rows = await conn.execute_fetchall("""
        SELECT *
        FROM players
        WHERE minutes > 0 OR total_points > 0
    """)
    players = [dict(row) for row in player_rows]
    snapshot_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "snapshot_at": snapshot_at,
        "target_event": None,
        "horizons": {},
        "rows_written": 0,
    }

    for horizon in tuple(dict.fromkeys(normalize_horizon(h) for h in horizons)):
        context = await build_projection_context(conn, current_event, horizon)
        target_event = context["target_event"]
        summary["target_event"] = target_event
        previous_rows = {
            row["player_id"]: row
            for row in await db.get_latest_projection_rows(
                conn,
                target_event,
                horizon,
                source_key=INTERNAL_PROJECTION_SOURCE_KEY,
            )
        }

        rows_to_write = []
        for player in players:
            projection = project_player(player, context["fixtures_by_team"], horizon, current_event, context)
            player_id = int(player["id"])
            current_row = {
                "player_id": player_id,
                "expected_points": round(float(projection["horizon_ep"]), 3),
                "xg": _safe_float(player.get("xg")),
                "xa": _safe_float(player.get("xa")),
                "xgi": _safe_float(player.get("xgi")),
                "expected_minutes": round(float(projection["expected_minutes_next"]), 2),
                "selected_pct": _safe_float(player.get("selected_pct")),
                "raw": {
                    "next_event_ep": projection["next_event_ep"],
                    "official_ep_next": projection["official_ep_next"],
                    "official_gap": projection["official_gap"],
                    "availability": projection["availability"],
                    "base_components": projection["base_components"],
                    "model_version": projection["model_version"],
                },
            }
            previous = previous_rows.get(player_id)
            previous_ep = _safe_float(previous.get("expected_points")) if previous else None
            previous_minutes = _safe_float(previous.get("expected_minutes")) if previous else None
            previous_raw = previous.get("raw") if previous else None
            if previous is not None:
                delta_ep = abs(current_row["expected_points"] - previous_ep)
                delta_minutes = abs(current_row["expected_minutes"] - previous_minutes)
                prev_gap = _safe_float(previous_raw.get("official_gap")) if isinstance(previous_raw, dict) else 0.0
                gap_change = abs(_safe_float(current_row["raw"]["official_gap"]) - prev_gap)
                if delta_ep < changed_threshold and delta_minutes < 3.0 and gap_change < 0.25:
                    continue
            rows_to_write.append(current_row)

        if rows_to_write:
            await db.upsert_projection_snapshot(
                conn,
                INTERNAL_PROJECTION_SOURCE_KEY,
                snapshot_at,
                target_event,
                horizon,
                rows_to_write,
            )
        summary["horizons"][horizon] = {
            "target_event": target_event,
            "rows_written": len(rows_to_write),
            "player_count": len(players),
        }
        summary["rows_written"] += len(rows_to_write)

    await conn.commit()
    return summary


def project_players(players: list[dict], context: dict, horizon: int | None = None) -> dict[int, dict]:
    target_horizon = normalize_horizon(horizon or context.get("horizon"))
    fixtures_by_team = context.get("fixtures_by_team") or {}
    current_event = context.get("current_event")
    return {
        int(player.get("player_id") or player.get("id")): project_player(
            player,
            fixtures_by_team,
            target_horizon,
            current_event,
            context,
        )
        for player in players
    }
