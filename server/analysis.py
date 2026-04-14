"""
Fulcrum analysis engine — the math.

Portfolio theory applied to FPL:
  - Player = security, Gameweek = trading day, Team = portfolio
  - Covariance matrix from structural factors + empirical data + shrinkage
  - Exposure metrics: HHI, ENB, variance decomposition
  - Factor model: team attack/defense loadings per player

Key insight: FPL points are driven by team-level events (goals scored,
goals conceded, clean sheets). Two players on the same team share these
factors. The covariance matrix captures this shared fate.
"""

import numpy as np
from collections import Counter, defaultdict
import db
import projections

# ── Position labels ──────────────────────────────────────────────────
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POS_CS_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}  # clean sheet points by position
POS_GOAL_POINTS = {1: 6, 2: 6, 3: 5, 4: 4}
POS_GC_PENALTY = {1: True, 2: True, 3: False, 4: False}  # -1 per 2 goals conceded
ATTACK_DIFFICULTY_MULTIPLIER = {1: 1.24, 2: 1.1, 3: 1.0, 4: 0.9, 5: 0.8}
DEFENSE_DIFFICULTY_MULTIPLIER = {1: 1.14, 2: 1.06, 3: 1.0, 4: 1.06, 5: 1.14}
HOME_ATTACK_BOOST = 1.04
AWAY_ATTACK_BOOST = 0.98
HOME_DEFENSE_BOOST = 1.03
AWAY_DEFENSE_BOOST = 0.99
FIXTURE_FORECAST_ALPHA = 0.68
HEAD_TO_HEAD_HEDGE = 0.42


# ── Covariance matrix ────────────────────────────────────────────────

async def compute_empirical_covariance(
    player_ids: list[int],
    database,
    min_shared_gws: int = 8,
    decay_rate: float = 0.03,
    lookback: int | None = None,
    max_event: int | None = None,
) -> tuple[np.ndarray, list[int]]:
    """
    Compute empirical covariance matrix from historical gameweek points.

    Uses exponential decay weighting — recent GWs matter more.
    Only includes GWs where a player started (60+ minutes) to avoid
    noise from 1-point cameos.

    Returns (cov_matrix, gw_list).
    """
    n = len(player_ids)

    # fetch history for all players
    histories = {}
    for pid in player_ids:
        h = await db.get_player_history(database, pid)
        # filter to started games only (60+ min)
        histories[pid] = {
            row["event"]: row["total_points"]
            for row in h
            if row["minutes"] >= 60 and (max_event is None or row["event"] <= max_event)
        }

    # find all gameweeks where data exists
    all_gws = sorted(set(gw for h in histories.values() for gw in h))
    if not all_gws:
        return np.eye(n), []

    if lookback is not None and lookback > 0:
        all_gws = all_gws[-lookback:]

    max_gw = max(all_gws)

    # build points matrix: rows = gameweeks, cols = players
    # NaN where player didn't start
    points = np.full((len(all_gws), n), np.nan)
    for j, pid in enumerate(player_ids):
        for i, gw in enumerate(all_gws):
            if gw in histories[pid]:
                points[i, j] = histories[pid][gw]

    # exponential decay weights (most recent GW = weight 1.0)
    weights = np.array([np.exp(-decay_rate * (max_gw - gw)) for gw in all_gws])

    # compute pairwise covariance, handling missing data
    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            # find GWs where both players have data
            mask = ~np.isnan(points[:, i]) & ~np.isnan(points[:, j])
            shared = mask.sum()

            if shared < min_shared_gws:
                # not enough shared data — use 0 covariance (conservative)
                cov[i, j] = 0
                cov[j, i] = 0
                continue

            pi = points[mask, i]
            pj = points[mask, j]
            w = weights[mask]
            w = w / w.sum()

            mean_i = np.average(pi, weights=w)
            mean_j = np.average(pj, weights=w)
            cov_val = np.average((pi - mean_i) * (pj - mean_j), weights=w)

            cov[i, j] = cov_val
            cov[j, i] = cov_val

    return cov, all_gws


def _clip_psd(matrix: np.ndarray, floor: float = 0.0) -> np.ndarray:
    eigvals, eigvecs = np.linalg.eigh(matrix)
    eigvals = np.maximum(eigvals, floor)
    return eigvecs @ np.diag(eigvals) @ eigvecs.T


async def _load_factor_model(
    player_ids: list[int],
    database,
) -> tuple[dict[int, dict], dict[int, dict], dict[int, dict]]:
    players = {}
    for pid in player_ids:
        player = await db.get_player(database, pid)
        if player:
            players[pid] = player

    team_stats = {}
    team_ids = set(player["team_id"] for player in players.values())
    for tid in team_ids:
        matches = await db.get_team_match_results(database, tid)
        if len(matches) < 5:
            team_stats[tid] = _default_team_stats()
            continue

        scored = np.array([match["goals_scored"] for match in matches], dtype=float)
        conceded = np.array([match["goals_conceded"] for match in matches], dtype=float)
        team_stats[tid] = {
            "mean_scored": scored.mean(),
            "mean_conceded": conceded.mean(),
            "var_scored": scored.var(ddof=1) if len(scored) > 1 else 1.0,
            "var_conceded": conceded.var(ddof=1) if len(conceded) > 1 else 1.0,
            "cov_sc": np.cov(scored, conceded)[0, 1] if len(scored) > 1 else 0.0,
            "cs_rate": (conceded == 0).mean(),
        }

    loadings = {}
    for pid in player_ids:
        player = players.get(pid)
        if not player:
            loadings[pid] = {"beta_atk": 0.0, "beta_def": 0.0, "team_id": 0, "pos": 0}
            continue

        pos = player["position"]
        tid = player["team_id"]
        team = team_stats.get(tid, _default_team_stats())
        mins = max(player.get("minutes", 0), 1)

        team_total_xg = max(team["mean_scored"] * (mins / 90), 0.1)
        xgi = player.get("xgi") or 0
        involvement_rate = min(xgi / team_total_xg, 0.8) if team_total_xg > 0 else 0

        beta_atk = involvement_rate * POS_GOAL_POINTS[pos]
        beta_atk += involvement_rate * 3 * 0.3

        cs_pts = POS_CS_POINTS[pos]
        gc_penalty = -0.5 if POS_GC_PENALTY[pos] else 0
        beta_def = cs_pts * team["cs_rate"] + gc_penalty

        loadings[pid] = {
            "beta_atk": float(beta_atk),
            "beta_def": float(beta_def),
            "team_id": tid,
            "pos": pos,
        }

    return players, team_stats, loadings


async def compute_structural_covariance(
    player_ids: list[int],
    database,
) -> np.ndarray:
    """
    Structural covariance from team-level factors.

    Model: each player's points are driven by their team's
    attack output (goals scored) and defensive output (goals conceded).

    Cov(player_i, player_j) depends on whether they share a team factor.

    This approach works even with limited per-player data because
    it uses match-level team statistics (380+ data points per season).
    """
    n = len(player_ids)
    _, team_stats, loadings = await _load_factor_model(player_ids, database)

    cov = np.zeros((n, n))
    for i, pid_i in enumerate(player_ids):
        for j, pid_j in enumerate(player_ids):
            li = loadings[pid_i]
            lj = loadings[pid_j]

            if li["team_id"] == 0 or lj["team_id"] == 0:
                continue

            if li["team_id"] == lj["team_id"]:
                # same team: share attack and defense factors
                tid = li["team_id"]
                ts = team_stats.get(tid, _default_team_stats())
                cov[i, j] = (
                    li["beta_atk"] * lj["beta_atk"] * ts["var_scored"]
                    + li["beta_def"] * lj["beta_def"] * ts["var_conceded"]
                    + (li["beta_atk"] * lj["beta_def"] + li["beta_def"] * lj["beta_atk"])
                      * ts["cov_sc"]
                )
            else:
                # different teams: zero structural covariance
                # (fixture-specific anti-correlation is handled separately)
                cov[i, j] = 0

    return _clip_psd(cov)


def _fixture_scales(fixture: dict, team_id: int) -> tuple[float, float]:
    difficulty = fixture_difficulty_for_team(fixture, team_id) or 3
    is_home = fixture.get("team_h") == team_id
    attack_scale = ATTACK_DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)
    defense_scale = DEFENSE_DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)
    attack_scale *= HOME_ATTACK_BOOST if is_home else AWAY_ATTACK_BOOST
    defense_scale *= HOME_DEFENSE_BOOST if is_home else AWAY_DEFENSE_BOOST
    return attack_scale, defense_scale


async def compute_forward_fixture_covariance(
    player_ids: list[int],
    database,
    current_event: int,
    future_weeks: int,
) -> np.ndarray:
    """
    Forward-looking covariance for the current XI.

    The estimate uses upcoming fixtures in the selected event window,
    boosts same-team factor risk when match scripts are aligned, and adds
    a hedge term when two of your players face one another.
    """
    n = len(player_ids)
    if future_weeks <= 0:
        return np.eye(n)

    _, team_stats, loadings = await _load_factor_model(player_ids, database)
    team_ids = {loading["team_id"] for loading in loadings.values() if loading["team_id"]}
    end_event = current_event + future_weeks - 1
    weeks_in_scope = max(future_weeks, 1)

    team_profiles = {}
    fixture_index = {}
    for tid in team_ids:
        stats = team_stats.get(tid, _default_team_stats())
        fixtures = await db.get_team_fixtures_in_window(database, tid, current_event, end_event)
        attack_var = 0.0
        defense_var = 0.0
        cov_sc = 0.0

        for fixture in fixtures:
            attack_scale, defense_scale = _fixture_scales(fixture, tid)
            attack_var += stats["var_scored"] * attack_scale
            defense_var += stats["var_conceded"] * defense_scale
            cov_sc += stats["cov_sc"] * np.sqrt(max(attack_scale * defense_scale, 1e-9))
            fixture_index[fixture["id"]] = fixture

        if not fixtures:
            attack_var = stats["var_scored"]
            defense_var = stats["var_conceded"]
            cov_sc = stats["cov_sc"]

        team_profiles[tid] = {
            "attack_var": attack_var / weeks_in_scope,
            "defense_var": defense_var / weeks_in_scope,
            "cov_sc": cov_sc / weeks_in_scope,
        }

    directional_attack_var = defaultdict(float)
    for fixture in fixture_index.values():
        home_id = fixture.get("team_h")
        away_id = fixture.get("team_a")
        if home_id not in team_ids or away_id not in team_ids:
            continue

        home_stats = team_stats.get(home_id, _default_team_stats())
        away_stats = team_stats.get(away_id, _default_team_stats())
        home_attack_scale, _ = _fixture_scales(fixture, home_id)
        away_attack_scale, _ = _fixture_scales(fixture, away_id)

        directional_attack_var[(home_id, away_id)] += (
            home_stats["var_scored"] * home_attack_scale / weeks_in_scope
        )
        directional_attack_var[(away_id, home_id)] += (
            away_stats["var_scored"] * away_attack_scale / weeks_in_scope
        )

    cov = np.zeros((n, n))
    for i, pid_i in enumerate(player_ids):
        li = loadings[pid_i]
        for j, pid_j in enumerate(player_ids):
            lj = loadings[pid_j]
            team_i = li["team_id"]
            team_j = lj["team_id"]

            if team_i == 0 or team_j == 0:
                continue

            if team_i == team_j:
                profile = team_profiles.get(team_i, _default_team_stats())
                cov[i, j] = (
                    li["beta_atk"] * lj["beta_atk"] * profile["attack_var"]
                    + li["beta_def"] * lj["beta_def"] * profile["defense_var"]
                    + (li["beta_atk"] * lj["beta_def"] + li["beta_def"] * lj["beta_atk"])
                      * profile["cov_sc"]
                )
                continue

            attack_i_vs_j = directional_attack_var.get((team_i, team_j), 0.0)
            attack_j_vs_i = directional_attack_var.get((team_j, team_i), 0.0)
            if attack_i_vs_j == 0 and attack_j_vs_i == 0:
                cov[i, j] = 0
                continue

            def_i = li["beta_def"] * (1.0 if li["pos"] in (1, 2) else 0.35)
            def_j = lj["beta_def"] * (1.0 if lj["pos"] in (1, 2) else 0.35)
            cov[i, j] = (
                -HEAD_TO_HEAD_HEDGE * li["beta_atk"] * def_j * attack_i_vs_j
                -HEAD_TO_HEAD_HEDGE * def_i * lj["beta_atk"] * attack_j_vs_i
            )

            if li["pos"] in (3, 4) and lj["pos"] in (3, 4):
                cov[i, j] += 0.08 * li["beta_atk"] * lj["beta_atk"] * min(attack_i_vs_j, attack_j_vs_i)

    return _clip_psd(cov)


def ledoit_wolf_shrinkage(empirical: np.ndarray, structural: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """
    Blend empirical and structural covariance matrices.

    Ledoit-Wolf optimal shrinkage estimates alpha from the data,
    but for our case with very few observations per player pair,
    we use a fixed blend favoring structural (alpha=0.5 means
    equal weight; higher = more structural).

    The structural estimate is well-conditioned (built from team-level
    data with 30+ matches), so leaning on it is safe.
    """
    blended = alpha * structural + (1 - alpha) * empirical

    # ensure PSD
    return _clip_psd(blended, floor=1e-6)


# ── Exposure metrics ─────────────────────────────────────────────────

def compute_exposure_metrics(
    player_ids: list[int],
    player_info: list[dict],
    cov_matrix: np.ndarray,
    captain_idx: int | None = None,
) -> dict:
    """
    Compute portfolio-level exposure metrics.

    Args:
        player_ids: ordered list of player IDs (starters only, 11 players)
        player_info: list of dicts with team_id, pos_type, web_name, etc.
        cov_matrix: NxN covariance matrix for starters
        captain_idx: index of captain in player_ids (gets 2x weight)

    Returns dict with:
        - portfolio_variance: total team variance
        - portfolio_std: sqrt of variance (expected points std dev)
        - team_concentration: { team_name: { weight, variance_pct } }
        - hhi: Herfindahl-Hirschman Index of team weights
        - enb: Effective Number of Bets (Meucci)
        - diversification_ratio: Choueifaty-Coignard
        - correlation_matrix: NxN correlation coefficients
        - top_correlations: sorted list of highest player-pair correlations
    """
    n = len(player_ids)

    # weight vector: 1 for all, 2 for captain
    w = np.ones(n)
    if captain_idx is not None and 0 <= captain_idx < n:
        w[captain_idx] = 2

    # portfolio variance: w^T * Sigma * w
    port_var = max(float(w @ cov_matrix @ w), 1e-10)
    port_std = float(np.sqrt(port_var))

    # correlation matrix
    stds = np.sqrt(np.maximum(np.diag(cov_matrix), 1e-10))
    corr = cov_matrix / np.outer(stds, stds)
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1, 1)

    # team concentration (weight-based)
    team_weights = defaultdict(float)
    team_players = defaultdict(list)
    total_weight = w.sum()
    for i, info in enumerate(player_info):
        tid = info.get("team_id") or info.get("team")
        team_weights[tid] += w[i]
        team_players[tid].append(i)

    # variance decomposition by team
    # fraction of portfolio variance attributable to each team's players
    team_var_contrib = {}
    for tid, indices in team_players.items():
        # sum of w_i * w_j * cov(i,j) for all i,j in this team
        contrib = sum(
            w[i] * w[j] * cov_matrix[i, j]
            for i in indices for j in indices
        )
        team_var_contrib[tid] = contrib

    total_var_contrib = sum(team_var_contrib.values())
    # cross-team contributions
    cross_team = port_var - total_var_contrib

    # build team concentration report
    team_concentration = {}
    for tid in team_weights:
        tname = None
        tshort = None
        for info in player_info:
            if (info.get("team_id") or info.get("team")) == tid:
                tname = info.get("team_name", f"Team {tid}")
                tshort = info.get("team_short", "???")
                break
        weight_pct = team_weights[tid] / total_weight * 100
        var_pct = (team_var_contrib.get(tid, 0) / port_var * 100) if port_var > 0 else 0
        team_concentration[tid] = {
            "team_name": tname,
            "team_short": tshort,
            "player_count": len(team_players[tid]),
            "weight_pct": round(weight_pct, 1),
            "variance_pct": round(var_pct, 1),
            "players": [player_info[i]["web_name"] for i in team_players[tid]],
        }

    # HHI: sum of squared weight shares
    shares = np.array([team_weights[tid] / total_weight for tid in team_weights])
    hhi = float(np.sum(shares ** 2))

    # Effective Number of Bets (Meucci) via eigendecomposition
    eigvals_port = np.linalg.eigvalsh(cov_matrix)
    eigvals_port = eigvals_port[eigvals_port > 1e-10]
    if len(eigvals_port) > 0 and port_var > 0:
        # project portfolio weights onto eigenvectors
        eigvals_full, eigvecs_full = np.linalg.eigh(cov_matrix)
        # variance contribution from each PC
        pc_vars = np.array([(w @ eigvecs_full[:, k]) ** 2 * eigvals_full[k] for k in range(n)])
        pc_vars = pc_vars[pc_vars > 1e-10]
        if pc_vars.sum() > 0:
            pc_shares = pc_vars / pc_vars.sum()
            enb = float(np.exp(-np.sum(pc_shares * np.log(pc_shares + 1e-15))))
        else:
            enb = 1.0
    else:
        enb = 1.0

    # diversification ratio: sum(w_i * sigma_i) / sqrt(w^T * Sigma * w)
    weighted_vols = float(np.sum(w * stds))
    div_ratio = weighted_vols / port_std if port_std > 0 else 1.0

    # top correlations (off-diagonal, sorted by absolute value)
    top_corrs = []
    for i in range(n):
        for j in range(i + 1, n):
            top_corrs.append({
                "player_a": player_info[i]["web_name"],
                "player_b": player_info[j]["web_name"],
                "correlation": round(float(corr[i, j]), 3),
                "same_team": (player_info[i].get("team_id") or player_info[i].get("team"))
                             == (player_info[j].get("team_id") or player_info[j].get("team")),
            })
    top_corrs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    return {
        "portfolio_variance": round(port_var, 2),
        "portfolio_std": round(port_std, 2),
        "team_concentration": team_concentration,
        "hhi": round(hhi, 4),
        "hhi_label": _hhi_label(hhi),
        "enb": round(enb, 1),
        "diversification_ratio": round(div_ratio, 2),
        "correlation_matrix": corr.tolist(),
        "top_correlations": top_corrs[:15],
        "cross_team_variance_pct": round(cross_team / port_var * 100, 1) if port_var > 0 else 0,
    }


def _hhi_label(hhi: float) -> str:
    if hhi < 0.10:
        return "Well diversified"
    elif hhi < 0.15:
        return "Moderately concentrated"
    elif hhi < 0.25:
        return "Concentrated"
    else:
        return "Highly concentrated"


def _team_stack_verdict(total_pts: float, count: int) -> str:
    avg_pts = total_pts / max(count, 1)
    if avg_pts >= 5.0 or total_pts >= max(12, count * 5):
        return "boom"
    if avg_pts <= 2.25:
        return "bust"
    return "neutral"


def _team_stack_explanation(players: list[dict], rows: list[dict]) -> str:
    if not players:
        return "No stack data for this week."

    defenders = [p for p in players if p.get("pos_type") in (1, 2)]
    clean_sheets = [r for r in rows if (r.get("clean_sheets") or 0) > 0]
    scorers = [r for r in rows if (r.get("goals_scored") or 0) > 0]
    creators = [r for r in rows if (r.get("assists") or 0) > 0]
    blanks = [r for r in rows if (r.get("total_points") or 0) <= 2]

    if len(defenders) >= 2 and len(clean_sheets) >= len(defenders):
        names = ", ".join(p["web_name"] for p in defenders)
        return f"{names} landed the clean-sheet points together."
    if scorers or creators:
        beats = []
        for row in scorers[:2]:
            beats.append(f"{row['web_name']} scored")
        for row in creators[:2]:
            if len(beats) >= 3:
                break
            beats.append(f"{row['web_name']} assisted")
        return ", ".join(beats) + "."
    if len(blanks) == len(players):
        return "No returns from the stack this week."
    if len(defenders) >= 2:
        return "The defensive stack moved together, but without the clean-sheet payoff."
    return "This stack moved on the same match script without a full boom."


def _build_pair_explanation(
    player_a: dict,
    player_b: dict,
    shared_events: list[int],
    pts_a: np.ndarray,
    pts_b: np.ndarray,
    rho: float,
) -> str:
    if not shared_events:
        return "Too little shared history in the window."

    booms = [gw for gw, pa, pb in zip(shared_events, pts_a, pts_b) if pa >= 4 and pb >= 4]
    busts = [gw for gw, pa, pb in zip(shared_events, pts_a, pts_b) if pa <= 2 and pb <= 2]
    diverges = [
        gw
        for gw, pa, pb in zip(shared_events, pts_a, pts_b)
        if (pa >= 4 and pb <= 2) or (pb >= 4 and pa <= 2)
    ]
    same_team = player_a.get("team_id") == player_b.get("team_id")
    team_short = player_a.get("team_short", "same-team")

    if rho >= 0.2:
        if same_team and booms and busts:
            return f"Both {team_short} assets boomed in GW{booms[0]} and blanked together in GW{busts[0]}."
        if same_team and booms:
            return f"Both {team_short} picks hit together in GW{booms[0]}."
        if booms and busts:
            return f"They rose together in GW{booms[0]} and cooled off together in GW{busts[0]}."
        if booms:
            return f"They shared the same upside in GW{booms[0]}."
        return "Their returns mostly rose and fell on the same weeks."

    if rho <= -0.1:
        if diverges:
            return f"They hedged each other in GW{diverges[0]} when one returned and the other blanked."
        return "Their returns tended to offset one another across the window."

    return "The link was mild across the lookback."


def _make_concentration_context(
    starters: list[dict],
    exposure: dict,
) -> list[dict]:
    items = []
    team_concentration = sorted(
        exposure["team_concentration"].values(),
        key=lambda team: team.get("variance_pct", 0),
        reverse=True,
    )

    if team_concentration:
        lead = team_concentration[0]
        variance_pct = lead.get("variance_pct", 0)
        if variance_pct >= 40:
            items.append({
                "severity": "high",
                "title": f"{lead['team_short']} drives the week",
                "detail": f"{variance_pct:.0f}% of your variance sits on {lead['team_short']} from {lead['player_count']} picks.",
                "recommendation": "Break the stack if the fixture turns.",
            })
        elif variance_pct >= 28:
            items.append({
                "severity": "medium",
                "title": f"{lead['team_short']} is the hinge",
                "detail": f"{variance_pct:.0f}% of variance rides on that club. Good if you love the fixture, dangerous if you do not.",
            })

    if exposure["enb"] < 4.5:
        items.append({
            "severity": "high" if exposure["enb"] < 4 else "medium",
            "title": f"Only {exposure['enb']} real outcomes",
            "detail": "Correlation has compressed the XI into a small number of independent outcomes.",
            "recommendation": "Use one transfer to spread the risk more cleanly.",
        })

    top_pair = next(
        (pair for pair in exposure["top_correlations"] if abs(pair["correlation"]) >= 0.3),
        None,
    )
    if top_pair:
        sign = "+" if top_pair["correlation"] > 0 else ""
        pair_detail = "Same team, same match script." if top_pair["same_team"] else "The pair still moves together."
        items.append({
            "severity": "info" if abs(top_pair["correlation"]) < 0.45 else "medium",
            "title": f"{top_pair['player_a']} ↔ {top_pair['player_b']}",
            "detail": f"ρ={sign}{top_pair['correlation']:.2f}. {pair_detail}",
        })

    if not items:
        captain = next((player for player in starters if player.get("is_captain")), starters[0] if starters else None)
        if captain:
            items.append({
                "severity": "info",
                "title": "Spread looks under control",
                "detail": f"No single stack dominates the window. {captain['web_name']} is still the lever through captaincy.",
            })

    return items[:3]


async def compute_correlation_attribution(
    manager_id: int,
    lookback: int | None = None,
    event: int | None = None,
) -> dict:
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")
        projection_context = await projections.build_projection_context(database, event, 1)
        projection_event = projection_context["target_event"]

        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad found for manager {manager_id} GW{event}")

        starters = [s for s in squad if s["squad_position"] <= 11]
        starter_ids = [s["player_id"] for s in starters]
        histories = {}
        started_points = {}
        all_events = set()

        for starter in starters:
            history_rows = await db.get_player_history(database, starter["player_id"])
            row_map = {row["event"]: row for row in history_rows}
            histories[starter["player_id"]] = row_map
            started_points[starter["player_id"]] = {
                row["event"]: row["total_points"]
                for row in history_rows
                if row.get("minutes", 0) >= 60
            }
            all_events.update(row_map.keys())

        selected_events = sorted(all_events)
        if lookback is not None and lookback > 0:
            selected_events = selected_events[-lookback:]

        emp_cov, gws_used = await compute_empirical_covariance(starter_ids, database, lookback=lookback)
        struct_cov = await compute_structural_covariance(starter_ids, database)
        alpha = 0.6 if len(gws_used) < 15 else 0.4
        cov_matrix = ledoit_wolf_shrinkage(emp_cov, struct_cov, alpha=alpha)
        captain_idx = next((i for i, s in enumerate(starters) if s["is_captain"]), None)
        exposure = compute_exposure_metrics(starter_ids, starters, cov_matrix, captain_idx)

        weeks = []
        stack_rollups = defaultdict(lambda: {"weeks": 0, "boom": 0, "bust": 0, "def_paid": 0, "def_bust": 0})
        current_captain = next((starter for starter in starters if starter["is_captain"]), starters[0] if starters else None)

        for gw in reversed(selected_events):
            total_points = 0
            team_groups = defaultdict(list)
            position_breakdown = {pos: {"total": 0} for pos in POS_NAMES.values()}

            for starter in starters:
                row = histories[starter["player_id"]].get(gw)
                raw_points = row["total_points"] if row else 0
                multiplier = 2 if starter["is_captain"] else 1
                weighted_points = raw_points * multiplier
                total_points += weighted_points
                position_breakdown[POS_NAMES.get(starter["pos_type"], "MID")]["total"] += weighted_points
                team_groups[starter["team_short"]].append({
                    "player": starter,
                    "row": row or {"total_points": 0, "minutes": 0, "clean_sheets": 0, "goals_scored": 0, "assists": 0},
                })

            team_stacks = []
            for team_short, group in team_groups.items():
                if len(group) < 2:
                    continue
                players = [item["player"] for item in group]
                rows = [{**item["row"], "web_name": item["player"]["web_name"]} for item in group]
                raw_total = sum(item["row"].get("total_points", 0) for item in group)
                weighted_total = sum(
                    item["row"].get("total_points", 0) * (2 if item["player"]["is_captain"] else 1)
                    for item in group
                )
                verdict = _team_stack_verdict(raw_total, len(group))
                team_stacks.append({
                    "team_short": team_short,
                    "count": len(group),
                    "total_pts": weighted_total,
                    "verdict": verdict,
                    "explanation": _team_stack_explanation(players, rows),
                })

                stack_rollups[team_short]["weeks"] += 1
                if verdict == "boom":
                    stack_rollups[team_short]["boom"] += 1
                elif verdict == "bust":
                    stack_rollups[team_short]["bust"] += 1

                defenders = [item for item in group if item["player"].get("pos_type") in (1, 2)]
                if len(defenders) >= 2:
                    if all((item["row"].get("clean_sheets") or 0) > 0 for item in defenders):
                        stack_rollups[team_short]["def_paid"] += 1
                    elif any((item["row"].get("minutes") or 0) > 0 for item in defenders):
                        stack_rollups[team_short]["def_bust"] += 1

            weeks.append({
                "event": gw,
                "total_points": total_points,
                "captain_name": current_captain["web_name"] if current_captain else "",
                "captain_pts": histories.get(current_captain["player_id"], {}).get(gw, {}).get("total_points", 0) if current_captain else 0,
                "team_stacks": sorted(team_stacks, key=lambda stack: (-stack["count"], -stack["total_pts"], stack["team_short"])),
                "position_breakdown": position_breakdown,
            })

        patterns = []
        total_weeks = len(selected_events)
        threshold = 2 if total_weeks >= 4 else 1
        for team_short, summary in stack_rollups.items():
            if summary["boom"] >= threshold:
                patterns.append({
                    "type": "positive",
                    "title": f"{team_short} stack paid {summary['boom']} of {total_weeks}",
                    "detail": f"That club delivered repeated upside across the window instead of a one-week spike.",
                })
            if summary["bust"] >= threshold:
                patterns.append({
                    "type": "negative",
                    "title": f"{team_short} stack missed {summary['bust']} of {total_weeks}",
                    "detail": "The same-club downside showed up often enough to matter.",
                })
            if summary["def_paid"] >= threshold:
                patterns.append({
                    "type": "positive",
                    "title": f"Clean-sheet correlation paid {summary['def_paid']} of {total_weeks}",
                    "detail": f"Your {team_short} defensive stack won together when the clean sheet landed.",
                })
            elif summary["def_bust"] >= threshold and summary["def_paid"] == 0:
                patterns.append({
                    "type": "negative",
                    "title": f"{team_short} clean-sheet stack never paid",
                    "detail": "The defensive stack shared the downside without giving you the ceiling back.",
                })

        if not patterns and total_weeks:
            patterns.append({
                "type": "info",
                "title": "No repeat stack pattern yet",
                "detail": "The window was noisy rather than driven by one persistent same-team script.",
            })

        explanations = []
        min_shared = 3 if len(selected_events) >= 5 else 2
        for i, player_a in enumerate(starters):
            for j in range(i + 1, len(starters)):
                player_b = starters[j]
                shared_events = sorted(
                    set(started_points[player_a["player_id"]]).intersection(started_points[player_b["player_id"]])
                )
                if lookback is not None and lookback > 0:
                    shared_events = [gw for gw in shared_events if gw in set(selected_events)]
                if len(shared_events) < min_shared:
                    continue

                pts_a = np.array([started_points[player_a["player_id"]][gw] for gw in shared_events], dtype=float)
                pts_b = np.array([started_points[player_b["player_id"]][gw] for gw in shared_events], dtype=float)
                if np.std(pts_a) < 1e-9 or np.std(pts_b) < 1e-9:
                    rho = 0.0
                else:
                    rho = float(np.corrcoef(pts_a, pts_b)[0, 1])
                if np.isnan(rho):
                    rho = 0.0

                explanations.append({
                    "player_a": player_a["web_name"],
                    "player_b": player_b["web_name"],
                    "rho": round(rho, 3),
                    "explanation": _build_pair_explanation(player_a, player_b, shared_events, pts_a, pts_b, rho),
                    "same_team": player_a.get("team_id") == player_b.get("team_id"),
                })

        explanations.sort(key=lambda pair: abs(pair["rho"]), reverse=True)

        return {
            "lookback": len(selected_events),
            "concentration_context": _make_concentration_context(starters, exposure),
            "weeks": weeks,
            "patterns": patterns[:5],
            "explanations": explanations[:5],
        }
    finally:
        await database.close()


# ── Risk callouts ────────────────────────────────────────────────────

def generate_risk_callouts(
    player_info: list[dict],
    exposure: dict,
    cov_matrix: np.ndarray,
) -> list[dict]:
    """
    Generate plain-English risk insights.

    Each callout: { severity: "high"|"medium"|"info", title, detail }
    """
    callouts = []
    n = len(player_info)

    # 1. Team over-concentration
    for tid, tc in exposure["team_concentration"].items():
        if tc["variance_pct"] > 40:
            callouts.append({
                "severity": "high",
                "title": f"{tc['team_short']} dominates your variance",
                "detail": f"{tc['variance_pct']}% of portfolio variance from {tc['player_count']} {tc['team_short']} players ({', '.join(tc['players'])}). A bad week for {tc['team_name']} hits hard.",
            })
        elif tc["variance_pct"] > 25 and tc["player_count"] >= 3:
            callouts.append({
                "severity": "medium",
                "title": f"Heavy {tc['team_short']} exposure",
                "detail": f"{tc['player_count']} players contributing {tc['variance_pct']}% of variance. Consider if fixtures justify the concentration.",
            })

    # 2. Highly correlated pairs
    for pair in exposure["top_correlations"][:5]:
        if pair["correlation"] > 0.45:
            callouts.append({
                "severity": "medium",
                "title": f"{pair['player_a']} ↔ {pair['player_b']}: ρ = {pair['correlation']}",
                "detail": f"These players' returns are highly correlated{' (same team)' if pair['same_team'] else ''}. They boom and bust together — limited diversification benefit.",
            })

    # 3. Low ENB
    if exposure["enb"] < 4:
        callouts.append({
            "severity": "high",
            "title": f"Only {exposure['enb']} effective independent outcomes",
            "detail": f"Despite picking 11 players, correlation reduces your effective diversification to {exposure['enb']} independent outcomes. Your team is leaning hard on a few match scripts.",
        })
    elif exposure["enb"] < 6:
        callouts.append({
            "severity": "info",
            "title": f"{exposure['enb']} effective independent outcomes",
            "detail": "Moderate diversification. Typical for teams with 2-3 player stacks.",
        })

    # 4. Defensive correlation (multiple defenders from same team)
    team_defs = defaultdict(list)
    for info in player_info:
        if info.get("pos_type") in (1, 2):  # GK or DEF
            tid = info.get("team_id") or info.get("team")
            team_defs[tid].append(info["web_name"])
    for tid, defs in team_defs.items():
        if len(defs) >= 2:
            tc = exposure["team_concentration"].get(tid, {})
            team_short = tc.get("team_short", "???")
            callouts.append({
                "severity": "medium",
                "title": f"Clean sheet stack: {', '.join(defs)}",
                "detail": f"{len(defs)} {team_short} defensive assets. Clean sheet points are perfectly correlated — all earn 4pts or all earn 0. High variance play.",
            })

    # 5. Captain amplification
    w = np.ones(n)
    captain_idx = None
    for i, info in enumerate(player_info):
        if info.get("is_captain"):
            captain_idx = i
            w[i] = 2
            break

    if captain_idx is not None and 0 <= captain_idx < n:
        cap_info = player_info[captain_idx]
        # captain's contribution to total variance
        cap_var_contrib = sum(2 * w[j] * cov_matrix[captain_idx, j] for j in range(n))
        cap_var_pct = cap_var_contrib / max(exposure["portfolio_variance"], 1e-10) * 100
        if cap_var_pct > 35:
            callouts.append({
                "severity": "info",
                "title": f"Captain {cap_info['web_name']} drives {cap_var_pct:.0f}% of variance",
                "detail": "Captaincy doubles weight, amplifying both expected return and risk from this player's outcomes.",
            })

    # 6. Diversification ratio
    if exposure["diversification_ratio"] < 1.3:
        callouts.append({
            "severity": "medium",
            "title": "Low diversification ratio",
            "detail": f"DR = {exposure['diversification_ratio']}. Your team acts almost like a single concentrated stack. Spreading across more teams would reduce risk without necessarily reducing expected points.",
        })

    return callouts


# ── Fixture outlook ──────────────────────────────────────────────────

async def compute_fixture_outlook(
    player_info: list[dict],
    database,
    current_event: int,
    n_weeks: int = 6,
) -> list[dict]:
    """
    Build fixture outlook for each player in the squad.

    Returns list of { player, fixtures: [{ event, opponent, difficulty, is_home }] }
    """
    outlook = []
    seen_teams = {}

    for info in player_info:
        tid = info.get("team_id") or info.get("team")

        if tid not in seen_teams:
            fixtures = await db.get_upcoming_fixtures(database, tid, current_event, n_weeks)
            seen_teams[tid] = fixtures

        team_fixtures = seen_teams[tid]
        player_fixtures = []
        for f in team_fixtures:
            is_home = f["team_h"] == tid
            opp_short = f["away_short"] if is_home else f["home_short"]
            difficulty = fixture_difficulty_for_team(f, tid)
            player_fixtures.append({
                "event": f["event"],
                "opponent": opp_short,
                "difficulty": difficulty,
                "is_home": is_home,
            })

        outlook.append({
            "player_id": info.get("player_id"),
            "web_name": info["web_name"],
            "team_short": info.get("team_short", "???"),
            "pos": POS_NAMES.get(info.get("pos_type"), "???"),
            "fixtures": player_fixtures,
        })

    return outlook


# ── Team X-ray orchestrator ──────────────────────────────────────────

async def team_xray(
    manager_id: int,
    event: int | None = None,
    lookback: int | None = None,
    future_weeks: int | None = None,
) -> dict:
    """
    Full team analysis for a manager.

    Pipeline:
      1. Load squad from DB
      2. Compute empirical covariance (from GW history)
      3. Compute structural covariance (from team factors)
      4. Blend via shrinkage
      5. Compute exposure metrics
      6. Generate risk callouts
      7. Build fixture outlook
      8. Package everything for the frontend
    """
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")
        projection_horizon = future_weeks if future_weeks is not None and future_weeks > 0 else 1
        projection_context = await projections.build_projection_context(database, event, projection_horizon)
        projection_event = projection_context["target_event"]

        # 1. load squad
        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad found for manager {manager_id} GW{event}")

        # separate starters (position 1-11) from bench (12-15)
        starters = [s for s in squad if s["squad_position"] <= 11]
        bench = [s for s in squad if s["squad_position"] > 11]

        starter_ids = [s["player_id"] for s in starters]
        captain_idx = None
        for i, s in enumerate(starters):
            if s["is_captain"]:
                captain_idx = i
                break

        # 2. empirical covariance
        emp_cov, gws_used = await compute_empirical_covariance(starter_ids, database, lookback=lookback)

        # 3. structural covariance
        struct_cov = await compute_structural_covariance(starter_ids, database)

        # 4. shrinkage blend
        # more structural weight when we have fewer shared GWs
        alpha = 0.6 if len(gws_used) < 15 else 0.4
        cov_matrix = ledoit_wolf_shrinkage(emp_cov, struct_cov, alpha=alpha)
        window_type = "history"
        window_label = f"{len(gws_used)} GWs"
        window_summary = f"Historical covariance over {len(gws_used)} shared gameweeks."
        forecast_alpha = None
        if future_weeks is not None and future_weeks > 0:
            fixture_cov = await compute_forward_fixture_covariance(
                starter_ids,
                database,
                projection_event,
                future_weeks,
            )
            cov_matrix = ledoit_wolf_shrinkage(cov_matrix, fixture_cov, alpha=FIXTURE_FORECAST_ALPHA)
            window_type = "future"
            window_label = f"Next {future_weeks} GWs"
            window_summary = f"Fixture-adjusted forecast from GW{projection_event} to GW{projection_event + future_weeks - 1}."
            forecast_alpha = FIXTURE_FORECAST_ALPHA

        # 5. exposure metrics
        exposure = compute_exposure_metrics(starter_ids, starters, cov_matrix, captain_idx)

        # 6. risk callouts
        callouts = generate_risk_callouts(starters, exposure, cov_matrix)

        # 7. fixture outlook (all 15 players)
        fixture_outlook = await compute_fixture_outlook(squad, database, projection_event)

        # 8. load manager info
        mgr_rows = await database.execute_fetchall(
            "SELECT * FROM manager_info WHERE id=?", (manager_id,)
        )
        mgr_info = dict(mgr_rows[0]) if mgr_rows else {}

        player_projections = projections.project_players(squad, projection_context, projection_horizon)

        # build player cards
        player_cards = []
        for s in squad:
            projection = player_projections.get(s["player_id"], {})
            availability = projection.get("availability", {})
            card = {
                "id": s["player_id"],
                "web_name": s["web_name"],
                "team_name": s["team_name"],
                "team_short": s["team_short"],
                "team_id": s["team_id"],
                "position": POS_NAMES.get(s["pos_type"], "???"),
                "pos_type": s["pos_type"],
                "price": s["now_cost"] / 10 if s["now_cost"] else 0,
                "total_points": s["total_points"],
                "form": s["form"],
                "ep_next": s["ep_next"],
                "projected_ep_next": projection.get("next_event_ep"),
                "projected_ep_window": projection.get("horizon_ep"),
                "projection_event": projection_event,
                "expected_minutes_next": projection.get("expected_minutes_next"),
                "projection_model": projection.get("model_version"),
                "projection_uncertainty": availability.get("uncertainty"),
                "projection_availability": availability,
                "projection_fixtures": projection.get("per_fixture", []),
                "selected_pct": s["selected_pct"],
                "xg": s["xg"],
                "xa": s["xa"],
                "xgi": s["xgi"],
                "xgc": s.get("xgc"),
                "xg_per90": s.get("xg_per90"),
                "xa_per90": s.get("xa_per90"),
                "xgi_per90": s.get("xgi_per90"),
                "minutes": s["minutes"],
                "starts": s.get("starts", 0),
                "goals": s["goals_scored"],
                "assists": s["assists"],
                "clean_sheets": s["clean_sheets"],
                "goals_conceded": s.get("goals_conceded", 0),
                "bonus": s.get("bonus", 0),
                "influence": s.get("influence"),
                "creativity": s.get("creativity"),
                "threat": s.get("threat"),
                "ict_index": s.get("ict_index"),
                "penalties_order": s.get("penalties_order"),
                "corners_order": s.get("corners_order"),
                "is_captain": bool(s["is_captain"]),
                "is_vice_captain": bool(s["is_vice_captain"]),
                "is_starter": s["squad_position"] <= 11,
                "squad_position": s["squad_position"],
                "status": s["status"],
                "chance_next": s.get("chance_next"),
                "news": s["news"],
            }
            player_cards.append(card)

        return {
            "manager": {
                "id": manager_id,
                "name": mgr_info.get("team_name", ""),
                "player_name": mgr_info.get("player_name", ""),
                "overall_points": mgr_info.get("overall_points"),
                "overall_rank": mgr_info.get("overall_rank"),
                "bank": (mgr_info.get("bank") or 0) / 10,
                "team_value": (mgr_info.get("team_value") or 0) / 10,
            },
            "event": event,
            "projection_event": projection_event,
            "players": player_cards,
            "exposure": exposure,
            "callouts": callouts,
            "fixture_outlook": fixture_outlook,
            "meta": {
                "gameweeks_used": len(gws_used),
                "history_gameweeks_used": len(gws_used),
                "shrinkage_alpha": alpha,
                "forecast_alpha": forecast_alpha,
                "window_type": window_type,
                "window_label": window_label,
                "window_summary": window_summary,
                "future_weeks": future_weeks,
                "window_start_event": projection_event if future_weeks else projection_event,
                "window_end_event": (projection_event + future_weeks - 1) if future_weeks else projection_event,
                "projection_event": projection_event,
                "projection_horizon": projection_horizon,
                "projection_model": projection_context["model_version"],
                "starters": len(starters),
                "bench": len(bench),
            },
        }
    finally:
        await database.close()


async def simulate_transfer(
    manager_id: int,
    player_out_id: int,
    player_in_id: int,
    event: int | None = None,
) -> dict:
    """
    Simulate replacing one player with another.
    Returns current vs proposed metrics + delta.
    """
    database = await db.get_db()
    try:
        if event is None:
            event = await db.get_current_event(database)
        if event is None:
            raise ValueError("No current event found — sync data first")

        squad = await db.get_manager_squad(database, manager_id, event)
        if not squad:
            raise ValueError(f"No squad for manager {manager_id} GW{event}")

        out_player = next((s for s in squad if s["player_id"] == player_out_id), None)
        if out_player is None:
            raise ValueError(f"Player {player_out_id} not in squad")
        if player_in_id == player_out_id:
            raise ValueError("Choose a different incoming player")
        if any(s["player_id"] == player_in_id for s in squad):
            raise ValueError(f"Player {player_in_id} is already in squad")

        # fetch player_in info
        player_in = await db.get_player(database, player_in_id)
        if not player_in:
            raise ValueError(f"Player {player_in_id} not found")
        if player_in["position"] != out_player["pos_type"]:
            raise ValueError("Incoming player must match the outgoing player's position")

        player_in_team = await db.get_team(database, player_in["team_id"])
        team_counts = Counter(s["team_id"] for s in squad if s["player_id"] != player_out_id)
        if team_counts[player_in["team_id"]] >= 3:
            team_short = player_in_team["short_name"] if player_in_team else f"team {player_in['team_id']}"
            raise ValueError(f"Transfer would exceed the 3-player limit for {team_short}")

        starters = [s for s in squad if s["squad_position"] <= 11]
        starter_ids = [s["player_id"] for s in starters]
        captain_idx = next((i for i, s in enumerate(starters) if s["is_captain"]), None)
        out_is_starter = out_player["squad_position"] <= 11
        swap_idx = None

        # current covariance + metrics
        emp_cov_cur, gws = await compute_empirical_covariance(starter_ids, database)
        struct_cov_cur = await compute_structural_covariance(starter_ids, database)
        alpha = 0.6 if len(gws) < 15 else 0.4
        cov_cur = ledoit_wolf_shrinkage(emp_cov_cur, struct_cov_cur, alpha)
        exp_cur = compute_exposure_metrics(starter_ids, starters, cov_cur, captain_idx)

        # proposed: swap player
        proposed_ids = list(starter_ids)
        proposed_starters = list(starters)
        cov_new = cov_cur
        exp_new = exp_cur
        if out_is_starter:
            history = await db.get_player_history(database, player_in_id)
            if not history:
                await database.close()
                database = None
                await __import__("fpl").sync_player_histories([player_in_id])
                database = await db.get_db()
                history = await db.get_player_history(database, player_in_id)
            if not history:
                raise ValueError(f"No history available for player {player_in_id}")

            swap_idx = proposed_ids.index(player_out_id)
            proposed_ids[swap_idx] = player_in_id
            proposed_starters[swap_idx] = {
                **starters[swap_idx],
                "player_id": player_in_id,
                "web_name": player_in["web_name"],
                "team_id": player_in["team_id"],
                "team_name": player_in_team["name"] if player_in_team else "???",
                "team_short": player_in_team["short_name"] if player_in_team else "???",
                "pos_type": player_in["position"],
                "now_cost": player_in["now_cost"],
                "total_points": player_in["total_points"],
                "form": player_in["form"],
                "ep_next": player_in["ep_next"],
                "selected_pct": player_in["selected_pct"],
                "xg": player_in["xg"],
                "xa": player_in["xa"],
                "xgi": player_in["xgi"],
            }

            emp_cov_new, _ = await compute_empirical_covariance(proposed_ids, database)
            struct_cov_new = await compute_structural_covariance(proposed_ids, database)
            cov_new = ledoit_wolf_shrinkage(emp_cov_new, struct_cov_new, alpha)
            exp_new = compute_exposure_metrics(proposed_ids, proposed_starters, cov_new, captain_idx)

        # compute deltas
        player_in_projection = projections.project_player(
            player_in,
            projection_context["fixtures_by_team"],
            1,
            event,
            projection_context,
        )
        out_player_projection = projections.project_player(
            out_player,
            projection_context["fixtures_by_team"],
            1,
            event,
            projection_context,
        )
        ep_delta = player_in_projection["next_event_ep"] - out_player_projection["next_event_ep"]
        correlation_changes = []
        if out_is_starter and swap_idx is not None:
            current_corr = exp_cur["correlation_matrix"]
            proposed_corr = exp_new["correlation_matrix"]
            for j, starter in enumerate(starters):
                if j == swap_idx:
                    continue
                delta_corr = round(proposed_corr[swap_idx][j] - current_corr[swap_idx][j], 3)
                correlation_changes.append({
                    "player_a": proposed_starters[swap_idx]["web_name"],
                    "player_b": proposed_starters[j]["web_name"],
                    "delta": delta_corr,
                    "current": round(float(current_corr[swap_idx][j]), 3),
                    "proposed": round(float(proposed_corr[swap_idx][j]), 3),
                })
            correlation_changes.sort(key=lambda pair: abs(pair["delta"]), reverse=True)

        return {
            "player_out": {
                "id": player_out_id,
                "web_name": out_player["web_name"],
                "team_short": out_player["team_short"],
                "price": out_player["now_cost"] / 10 if out_player["now_cost"] else 0,
                "ep_next": out_player.get("ep_next"),
                "projected_ep_next": out_player_projection["next_event_ep"],
            },
            "player_in": {
                "id": player_in_id,
                "web_name": player_in["web_name"],
                "team_short": player_in_team["short_name"] if player_in_team else "???",
                "price": player_in["now_cost"] / 10 if player_in["now_cost"] else 0,
                "ep_next": player_in.get("ep_next"),
                "projected_ep_next": player_in_projection["next_event_ep"],
            },
            "current": {
                "portfolio_std": exp_cur["portfolio_std"],
                "hhi": exp_cur["hhi"],
                "enb": exp_cur["enb"],
                "diversification_ratio": exp_cur["diversification_ratio"],
            },
            "proposed": {
                "portfolio_std": exp_new["portfolio_std"],
                "hhi": exp_new["hhi"],
                "enb": exp_new["enb"],
                "diversification_ratio": exp_new["diversification_ratio"],
            },
            "delta": {
                "portfolio_std": round(exp_new["portfolio_std"] - exp_cur["portfolio_std"], 2),
                "hhi": round(exp_new["hhi"] - exp_cur["hhi"], 4),
                "enb": round(exp_new["enb"] - exp_cur["enb"], 1),
                "diversification_ratio": round(exp_new["diversification_ratio"] - exp_cur["diversification_ratio"], 2),
                "ep_next": round(ep_delta, 1) if ep_delta else 0,
            },
            "projection_event": projection_event,
            "correlation_changes": correlation_changes[:6],
            "callouts": generate_risk_callouts(proposed_starters, exp_new, cov_new),
        }
    finally:
        if database is not None:
            await database.close()


def fixture_difficulty_for_team(fixture: dict, team_id: int) -> int | None:
    if fixture.get("team_h") == team_id:
        return fixture.get("team_h_difficulty")
    if fixture.get("team_a") == team_id:
        return fixture.get("team_a_difficulty")
    return None


def _default_team_stats():
    return {
        "mean_scored": 1.3,
        "mean_conceded": 1.3,
        "var_scored": 1.5,
        "var_conceded": 1.5,
        "cov_sc": 0.0,
        "cs_rate": 0.3,
    }
