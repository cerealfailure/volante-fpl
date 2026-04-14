"""
Fulcrum data layer — SQLite storage for FPL data and computed analysis.

Tables:
  teams          — 20 PL clubs with strength ratings
  players        — all ~825 players with current-season aggregates
  fixtures       — all 380 fixtures with scores and difficulty
  player_gws     — per-player per-gameweek stats (the core data for covariance)
  manager_picks  — cached manager team selections
  manager_leagues — cached leagues for a manager
  league_info    — cached league metadata
  league_pages   — cached standings page metadata
  league_standings — cached league standings rows
  manager_transfers — cached transfer history
  sync_log       — track data freshness
"""

import aiosqlite
import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("FULCRUM_DB", Path.home() / ".fulcrum" / "fulcrum.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    short_name  TEXT NOT NULL,
    strength    INTEGER,
    position    INTEGER,
    played      INTEGER DEFAULT 0,
    win         INTEGER DEFAULT 0,
    draw        INTEGER DEFAULT 0,
    loss        INTEGER DEFAULT 0,
    points      INTEGER DEFAULT 0,
    -- granular strength ratings (range ~950-1400)
    str_overall_home  INTEGER,
    str_overall_away  INTEGER,
    str_attack_home   INTEGER,
    str_attack_away   INTEGER,
    str_defence_home  INTEGER,
    str_defence_away  INTEGER
);

CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY,
    code            INTEGER,
    web_name        TEXT NOT NULL,
    first_name      TEXT,
    second_name     TEXT,
    team_id         INTEGER REFERENCES teams(id),
    position        INTEGER,  -- 1=GK, 2=DEF, 3=MID, 4=FWD
    now_cost        INTEGER,  -- price in tenths (60 = 6.0m)
    total_points    INTEGER DEFAULT 0,
    minutes         INTEGER DEFAULT 0,
    goals_scored    INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,
    clean_sheets    INTEGER DEFAULT 0,
    goals_conceded  INTEGER DEFAULT 0,
    bonus           INTEGER DEFAULT 0,
    form            REAL DEFAULT 0,
    points_per_game REAL DEFAULT 0,
    selected_pct    REAL DEFAULT 0,
    -- expected stats
    xg              REAL DEFAULT 0,
    xa              REAL DEFAULT 0,
    xgi             REAL DEFAULT 0,
    xgc             REAL DEFAULT 0,
    -- per-90 rates
    xg_per90        REAL DEFAULT 0,
    xa_per90        REAL DEFAULT 0,
    xgi_per90       REAL DEFAULT 0,
    xgc_per90       REAL DEFAULT 0,
    -- status
    status          TEXT DEFAULT 'a',
    chance_next     INTEGER,
    news            TEXT,
    -- set pieces
    penalties_order INTEGER,
    corners_order   INTEGER,
    -- ict
    influence       REAL DEFAULT 0,
    creativity      REAL DEFAULT 0,
    threat          REAL DEFAULT 0,
    ict_index       REAL DEFAULT 0,
    starts          INTEGER DEFAULT 0,
    ep_this         REAL,
    ep_next         REAL
);

CREATE TABLE IF NOT EXISTS fixtures (
    id              INTEGER PRIMARY KEY,
    event           INTEGER,  -- gameweek number (NULL if unscheduled)
    team_h          INTEGER REFERENCES teams(id),
    team_a          INTEGER REFERENCES teams(id),
    team_h_score    INTEGER,
    team_a_score    INTEGER,
    kickoff_time    TEXT,
    finished        INTEGER DEFAULT 0,
    team_h_difficulty INTEGER,
    team_a_difficulty INTEGER
);

CREATE TABLE IF NOT EXISTS player_gws (
    player_id       INTEGER REFERENCES players(id),
    event           INTEGER,  -- gameweek number
    fixture_id      INTEGER,
    opponent_team   INTEGER,
    was_home        INTEGER,
    total_points    INTEGER,
    minutes         INTEGER,
    goals_scored    INTEGER,
    assists         INTEGER,
    clean_sheets    INTEGER,
    goals_conceded  INTEGER,
    bonus           INTEGER,
    bps             INTEGER,
    influence       REAL,
    creativity      REAL,
    threat          REAL,
    xg              REAL DEFAULT 0,
    xa              REAL DEFAULT 0,
    xgi             REAL DEFAULT 0,
    xgc             REAL DEFAULT 0,
    value           INTEGER,  -- price at that GW (tenths)
    starts          INTEGER DEFAULT 0,
    -- match context (derived from fixtures)
    team_goals_scored   INTEGER,
    team_goals_conceded INTEGER,
    PRIMARY KEY (player_id, event, fixture_id)
);

CREATE TABLE IF NOT EXISTS manager_picks (
    manager_id      INTEGER,
    event           INTEGER,
    player_id       INTEGER,
    position        INTEGER,  -- 1-11 starting, 12-15 bench
    multiplier      INTEGER DEFAULT 1,  -- 2 for captain, 3 for TC
    is_captain      INTEGER DEFAULT 0,
    is_vice_captain INTEGER DEFAULT 0,
    PRIMARY KEY (manager_id, event, player_id)
);

CREATE TABLE IF NOT EXISTS manager_info (
    id              INTEGER PRIMARY KEY,
    team_name       TEXT,
    player_name     TEXT,
    overall_points  INTEGER,
    overall_rank    INTEGER,
    current_event   INTEGER,
    bank            INTEGER,  -- tenths
    team_value      INTEGER  -- tenths
);

CREATE TABLE IF NOT EXISTS manager_leagues (
    manager_id      INTEGER,
    league_id       INTEGER,
    name            TEXT NOT NULL,
    short_name      TEXT,
    created         TEXT,
    closed          INTEGER DEFAULT 0,
    league_type     TEXT,
    scoring         TEXT,
    admin_entry     INTEGER,
    start_event     INTEGER,
    has_cup         INTEGER DEFAULT 0,
    cup_league      INTEGER,
    rank_count      INTEGER,
    entry_percentile_rank INTEGER,
    entry_rank      INTEGER,
    entry_last_rank INTEGER,
    PRIMARY KEY (manager_id, league_id)
);

CREATE TABLE IF NOT EXISTS league_info (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    short_name      TEXT,
    created         TEXT,
    closed          INTEGER DEFAULT 0,
    max_entries     INTEGER,
    league_type     TEXT,
    scoring         TEXT,
    admin_entry     INTEGER,
    start_event     INTEGER,
    code_privacy    TEXT,
    has_cup         INTEGER DEFAULT 0,
    cup_league      INTEGER,
    rank            INTEGER,
    last_updated_data TEXT
);

CREATE TABLE IF NOT EXISTS league_pages (
    league_id       INTEGER,
    page            INTEGER,
    has_next        INTEGER DEFAULT 0,
    results_count   INTEGER DEFAULT 0,
    PRIMARY KEY (league_id, page)
);

CREATE TABLE IF NOT EXISTS league_standings (
    league_id       INTEGER,
    page            INTEGER,
    rank            INTEGER,
    last_rank       INTEGER,
    rank_sort       INTEGER,
    total           INTEGER,
    event_total     INTEGER,
    entry_id        INTEGER,
    entry_name      TEXT,
    player_name     TEXT,
    has_played      INTEGER DEFAULT 0,
    club_badge_src  TEXT,
    PRIMARY KEY (league_id, page, entry_id)
);

CREATE TABLE IF NOT EXISTS manager_transfers (
    manager_id       INTEGER,
    event            INTEGER,
    time             TEXT,
    element_in       INTEGER,
    element_in_cost  INTEGER,
    element_out      INTEGER,
    element_out_cost INTEGER,
    PRIMARY KEY (manager_id, time, element_in, element_out)
);

CREATE TABLE IF NOT EXISTS sync_log (
    key         TEXT PRIMARY KEY,
    synced_at   TEXT NOT NULL,
    meta        TEXT  -- JSON blob for extra info
);

CREATE TABLE IF NOT EXISTS ep_snapshots (
    player_id   INTEGER,
    event       INTEGER,
    ep_value    REAL,
    snapped_at  TEXT NOT NULL,
    PRIMARY KEY (player_id, event)
);

CREATE TABLE IF NOT EXISTS live_gw_cache (
    event           INTEGER,
    player_id       INTEGER,
    minutes         INTEGER DEFAULT 0,
    total_points    INTEGER DEFAULT 0,
    goals_scored    INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,
    clean_sheets    INTEGER DEFAULT 0,
    goals_conceded  INTEGER DEFAULT 0,
    bonus           INTEGER DEFAULT 0,
    bps             INTEGER DEFAULT 0,
    saves           INTEGER DEFAULT 0,
    yellow_cards    INTEGER DEFAULT 0,
    red_cards       INTEGER DEFAULT 0,
    penalties_missed INTEGER DEFAULT 0,
    own_goals       INTEGER DEFAULT 0,
    synced_at       TEXT NOT NULL,
    PRIMARY KEY (event, player_id)
);

CREATE TABLE IF NOT EXISTS signal_sources (
    key             TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    enabled         INTEGER DEFAULT 1,
    meta            TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projection_snapshots (
    source_key          TEXT REFERENCES signal_sources(key),
    snapshot_at         TEXT NOT NULL,
    event               INTEGER NOT NULL,
    horizon             INTEGER DEFAULT 5,
    player_id           INTEGER REFERENCES players(id),
    expected_points     REAL,
    xg                  REAL,
    xa                  REAL,
    xgi                 REAL,
    expected_minutes    REAL,
    selected_pct        REAL,
    anytime_return_prob REAL,
    clean_sheet_prob    REAL,
    raw                 TEXT,
    PRIMARY KEY (source_key, snapshot_at, event, horizon, player_id)
);

CREATE TABLE IF NOT EXISTS intel_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_id      INTEGER NOT NULL,
    event           INTEGER NOT NULL,
    horizon         INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    model_version   TEXT,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS intel_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER REFERENCES intel_runs(id),
    manager_id      INTEGER NOT NULL,
    event           INTEGER NOT NULL,
    horizon         INTEGER NOT NULL,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    title           TEXT NOT NULL,
    detail          TEXT NOT NULL,
    score           REAL DEFAULT 0,
    dedupe_key      TEXT NOT NULL,
    payload         TEXT,
    created_at      TEXT NOT NULL,
    delivery_status TEXT DEFAULT 'pending',
    delivered_at    TEXT,
    UNIQUE(manager_id, event, dedupe_key)
);

CREATE TABLE IF NOT EXISTS alert_delivery_targets (
    name            TEXT PRIMARY KEY,
    target_type     TEXT NOT NULL,
    enabled         INTEGER DEFAULT 1,
    config          TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_availability_snapshots (
    target_event         INTEGER NOT NULL,
    player_id            INTEGER REFERENCES players(id),
    snapshot_at          TEXT NOT NULL,
    team_id              INTEGER REFERENCES teams(id),
    status               TEXT,
    chance_next          INTEGER,
    news                 TEXT,
    news_category        TEXT,
    news_severity        REAL DEFAULT 0,
    news_purity          REAL DEFAULT 0,
    listed_play_prob     REAL,
    listed_start_prob    REAL,
    expected_minutes     REAL,
    model_version        TEXT,
    PRIMARY KEY (target_event, player_id)
);

CREATE TABLE IF NOT EXISTS player_availability_tape (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    target_event         INTEGER NOT NULL,
    player_id            INTEGER REFERENCES players(id),
    snapshot_at          TEXT NOT NULL,
    snapshot_kind        TEXT NOT NULL,
    snapshot_reason      TEXT,
    changed_fields       TEXT,
    team_id              INTEGER REFERENCES teams(id),
    status               TEXT,
    chance_next          INTEGER,
    news                 TEXT,
    news_category        TEXT,
    news_severity        REAL DEFAULT 0,
    news_purity          REAL DEFAULT 0,
    listed_play_prob     REAL,
    listed_start_prob    REAL,
    expected_minutes     REAL,
    model_version        TEXT
);

CREATE TABLE IF NOT EXISTS availability_profiles (
    as_of_event          INTEGER NOT NULL,
    team_id              INTEGER DEFAULT 0,
    status               TEXT NOT NULL,
    chance_bucket        TEXT NOT NULL,
    news_category        TEXT NOT NULL,
    sample_size          INTEGER DEFAULT 0,
    listed_play_rate     REAL DEFAULT 0,
    actual_play_rate     REAL DEFAULT 0,
    listed_start_rate    REAL DEFAULT 0,
    actual_start_rate    REAL DEFAULT 0,
    listed_minutes       REAL DEFAULT 0,
    actual_minutes       REAL DEFAULT 0,
    play_bias            REAL DEFAULT 0,
    start_bias           REAL DEFAULT 0,
    mean_abs_error       REAL DEFAULT 0,
    honesty_score        REAL DEFAULT 0,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (as_of_event, team_id, status, chance_bucket, news_category)
);

CREATE TABLE IF NOT EXISTS background_manager_registry (
    manager_id      INTEGER PRIMARY KEY,
    source          TEXT,
    pinned          INTEGER DEFAULT 0,
    last_seen_at    TEXT NOT NULL,
    last_warmed_at  TEXT,
    meta            TEXT
);

CREATE INDEX IF NOT EXISTS idx_player_gws_player ON player_gws(player_id);
CREATE INDEX IF NOT EXISTS idx_player_gws_event ON player_gws(event);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
CREATE INDEX IF NOT EXISTS idx_fixtures_event ON fixtures(event);
CREATE INDEX IF NOT EXISTS idx_manager_picks_mgr ON manager_picks(manager_id, event);
CREATE INDEX IF NOT EXISTS idx_manager_leagues_mgr ON manager_leagues(manager_id);
CREATE INDEX IF NOT EXISTS idx_league_pages_league ON league_pages(league_id, page);
CREATE INDEX IF NOT EXISTS idx_league_standings_league ON league_standings(league_id, page, rank_sort);
CREATE INDEX IF NOT EXISTS idx_manager_transfers_mgr ON manager_transfers(manager_id, time);
CREATE INDEX IF NOT EXISTS idx_projection_snapshots_lookup ON projection_snapshots(event, horizon, player_id, source_key, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_intel_runs_mgr ON intel_runs(manager_id, event, created_at);
CREATE INDEX IF NOT EXISTS idx_intel_alerts_mgr ON intel_alerts(manager_id, event, delivery_status, created_at);
CREATE INDEX IF NOT EXISTS idx_availability_snapshots_lookup ON player_availability_snapshots(target_event, team_id, status, chance_next);
CREATE INDEX IF NOT EXISTS idx_availability_tape_lookup ON player_availability_tape(target_event, player_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_availability_tape_kind ON player_availability_tape(snapshot_kind, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_availability_profiles_lookup ON availability_profiles(as_of_event, team_id, status, chance_bucket, news_category);
CREATE INDEX IF NOT EXISTS idx_background_manager_registry_seen ON background_manager_registry(pinned, last_seen_at DESC);
"""


async def get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()


# ── Data access ──────────────────────────────────────────────────────

async def upsert_teams(db: aiosqlite.Connection, teams: list[dict]):
    await db.executemany("""
        INSERT OR REPLACE INTO teams
        (id, name, short_name, strength, position, played, win, draw, loss, points,
         str_overall_home, str_overall_away, str_attack_home, str_attack_away,
         str_defence_home, str_defence_away)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(
        t["id"], t["name"], t["short_name"], t.get("strength"),
        t.get("position", 0), t.get("played", 0), t.get("win", 0),
        t.get("draw", 0), t.get("loss", 0), t.get("points", 0),
        t.get("strength_overall_home"), t.get("strength_overall_away"),
        t.get("strength_attack_home"), t.get("strength_attack_away"),
        t.get("strength_defence_home"), t.get("strength_defence_away"),
    ) for t in teams])


async def upsert_players(db: aiosqlite.Connection, players: list[dict]):
    await db.executemany("""
        INSERT OR REPLACE INTO players
        (id, code, web_name, first_name, second_name, team_id, position,
         now_cost, total_points, minutes, goals_scored, assists, clean_sheets,
         goals_conceded, bonus, form, points_per_game, selected_pct,
         xg, xa, xgi, xgc, xg_per90, xa_per90, xgi_per90, xgc_per90,
         status, chance_next, news, penalties_order, corners_order,
         influence, creativity, threat, ict_index, starts, ep_this, ep_next)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(
        p["id"], p.get("code"), p["web_name"], p.get("first_name"), p.get("second_name"),
        p["team"], p["element_type"], p["now_cost"], p.get("total_points", 0),
        p.get("minutes", 0), p.get("goals_scored", 0), p.get("assists", 0),
        p.get("clean_sheets", 0), p.get("goals_conceded", 0), p.get("bonus", 0),
        _float(p.get("form")), _float(p.get("points_per_game")),
        _float(p.get("selected_by_percent")),
        _float(p.get("expected_goals")), _float(p.get("expected_assists")),
        _float(p.get("expected_goal_involvements")), _float(p.get("expected_goals_conceded")),
        _float(p.get("expected_goals_per_90")), _float(p.get("expected_assists_per_90")),
        _float(p.get("expected_goal_involvements_per_90")),
        _float(p.get("expected_goals_conceded_per_90")),
        p.get("status", "a"), p.get("chance_of_playing_next_round"),
        p.get("news"), p.get("penalties_order"), p.get("corners_and_indirect_freekicks_order"),
        _float(p.get("influence")), _float(p.get("creativity")),
        _float(p.get("threat")), _float(p.get("ict_index")),
        p.get("starts", 0), _float(p.get("ep_this")), _float(p.get("ep_next")),
    ) for p in players])


async def upsert_fixtures(db: aiosqlite.Connection, fixtures: list[dict]):
    await db.executemany("""
        INSERT OR REPLACE INTO fixtures
        (id, event, team_h, team_a, team_h_score, team_a_score,
         kickoff_time, finished, team_h_difficulty, team_a_difficulty)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, [(
        f["id"], f.get("event"), f["team_h"], f["team_a"],
        f.get("team_h_score"), f.get("team_a_score"),
        f.get("kickoff_time"), 1 if f.get("finished") else 0,
        f.get("team_h_difficulty"), f.get("team_a_difficulty"),
    ) for f in fixtures])


async def upsert_player_gws(db: aiosqlite.Connection, player_id: int, history: list[dict]):
    await db.executemany("""
        INSERT OR REPLACE INTO player_gws
        (player_id, event, fixture_id, opponent_team, was_home, total_points,
         minutes, goals_scored, assists, clean_sheets, goals_conceded,
         bonus, bps, influence, creativity, threat,
         xg, xa, xgi, xgc, value, starts,
         team_goals_scored, team_goals_conceded)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(
        player_id, h["round"], h["fixture"], h["opponent_team"],
        1 if h.get("was_home") else 0, h.get("total_points", 0),
        h.get("minutes", 0), h.get("goals_scored", 0), h.get("assists", 0),
        h.get("clean_sheets", 0), h.get("goals_conceded", 0),
        h.get("bonus", 0), h.get("bps", 0),
        _float(h.get("influence")), _float(h.get("creativity")), _float(h.get("threat")),
        _float(h.get("expected_goals")), _float(h.get("expected_assists")),
        _float(h.get("expected_goal_involvements")), _float(h.get("expected_goals_conceded")),
        h.get("value"), h.get("starts", 0),
        # match score: derive from was_home + team_h/a_score
        h.get("team_h_score") if h.get("was_home") else h.get("team_a_score"),
        h.get("team_a_score") if h.get("was_home") else h.get("team_h_score"),
    ) for h in history])


async def upsert_manager(db: aiosqlite.Connection, info: dict):
    await db.execute("""
        INSERT OR REPLACE INTO manager_info
        (id, team_name, player_name, overall_points, overall_rank,
         current_event, bank, team_value)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        info["id"], info.get("name"),
        f"{info.get('player_first_name','')} {info.get('player_last_name','')}".strip(),
        info.get("summary_overall_points"), info.get("summary_overall_rank"),
        info.get("current_event"),
        info.get("last_deadline_bank"), info.get("last_deadline_value"),
    ))


async def upsert_manager_picks(db: aiosqlite.Connection, manager_id: int, event: int, picks: list[dict]):
    await db.execute("DELETE FROM manager_picks WHERE manager_id=? AND event=?", (manager_id, event))
    await db.executemany("""
        INSERT INTO manager_picks
        (manager_id, event, player_id, position, multiplier, is_captain, is_vice_captain)
        VALUES (?,?,?,?,?,?,?)
    """, [(
        manager_id, event, p["element"], p["position"],
        p.get("multiplier", 1), 1 if p.get("is_captain") else 0,
        1 if p.get("is_vice_captain") else 0,
    ) for p in picks])


async def replace_manager_leagues(db: aiosqlite.Connection, manager_id: int, leagues: list[dict]):
    await db.execute("DELETE FROM manager_leagues WHERE manager_id=?", (manager_id,))
    await db.executemany("""
        INSERT INTO manager_leagues
        (manager_id, league_id, name, short_name, created, closed, league_type,
         scoring, admin_entry, start_event, has_cup, cup_league, rank_count,
         entry_percentile_rank, entry_rank, entry_last_rank)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(
        manager_id,
        lg["id"],
        lg["name"],
        lg.get("short_name"),
        lg.get("created"),
        1 if lg.get("closed") else 0,
        lg.get("league_type"),
        lg.get("scoring"),
        lg.get("admin_entry"),
        lg.get("start_event"),
        1 if lg.get("has_cup") else 0,
        lg.get("cup_league"),
        lg.get("rank_count"),
        lg.get("entry_percentile_rank"),
        lg.get("entry_rank"),
        lg.get("entry_last_rank"),
    ) for lg in leagues])
    await db.executemany("""
        INSERT INTO league_info
        (id, name, short_name, created, closed, max_entries, league_type, scoring,
         admin_entry, start_event, code_privacy, has_cup, cup_league, rank, last_updated_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            short_name=COALESCE(excluded.short_name, league_info.short_name),
            created=COALESCE(excluded.created, league_info.created),
            closed=excluded.closed,
            max_entries=COALESCE(excluded.max_entries, league_info.max_entries),
            league_type=COALESCE(excluded.league_type, league_info.league_type),
            scoring=COALESCE(excluded.scoring, league_info.scoring),
            admin_entry=COALESCE(excluded.admin_entry, league_info.admin_entry),
            start_event=COALESCE(excluded.start_event, league_info.start_event),
            code_privacy=COALESCE(excluded.code_privacy, league_info.code_privacy),
            has_cup=excluded.has_cup,
            cup_league=COALESCE(excluded.cup_league, league_info.cup_league),
            rank=COALESCE(excluded.rank, league_info.rank)
    """, [(
        lg["id"],
        lg["name"],
        lg.get("short_name"),
        lg.get("created"),
        1 if lg.get("closed") else 0,
        lg.get("max_entries"),
        lg.get("league_type"),
        lg.get("scoring"),
        lg.get("admin_entry"),
        lg.get("start_event"),
        lg.get("code_privacy"),
        1 if lg.get("has_cup") else 0,
        lg.get("cup_league"),
        lg.get("rank"),
    ) for lg in leagues])


async def upsert_league_standings(db: aiosqlite.Connection, data: dict):
    league = data.get("league", {})
    standings = data.get("standings", {})
    league_id = league.get("id")
    page = standings.get("page", 1)
    entries = standings.get("results", [])
    await db.execute("DELETE FROM league_standings WHERE league_id=? AND page=?", (league_id, page))
    await db.executemany("""
        INSERT INTO league_standings
        (league_id, page, rank, last_rank, rank_sort, total, event_total,
         entry_id, entry_name, player_name, has_played, club_badge_src)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(
        league_id,
        page,
        row.get("rank"),
        row.get("last_rank"),
        row.get("rank_sort"),
        row.get("total"),
        row.get("event_total"),
        row.get("entry"),
        row.get("entry_name"),
        row.get("player_name"),
        1 if row.get("has_played") else 0,
        row.get("club_badge_src"),
    ) for row in entries])
    await db.execute("""
        INSERT INTO league_info
        (id, name, short_name, created, closed, max_entries, league_type, scoring,
         admin_entry, start_event, code_privacy, has_cup, cup_league, rank, last_updated_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            short_name=COALESCE(excluded.short_name, league_info.short_name),
            created=COALESCE(excluded.created, league_info.created),
            closed=excluded.closed,
            max_entries=COALESCE(excluded.max_entries, league_info.max_entries),
            league_type=COALESCE(excluded.league_type, league_info.league_type),
            scoring=COALESCE(excluded.scoring, league_info.scoring),
            admin_entry=COALESCE(excluded.admin_entry, league_info.admin_entry),
            start_event=COALESCE(excluded.start_event, league_info.start_event),
            code_privacy=COALESCE(excluded.code_privacy, league_info.code_privacy),
            has_cup=excluded.has_cup,
            cup_league=COALESCE(excluded.cup_league, league_info.cup_league),
            rank=COALESCE(excluded.rank, league_info.rank),
            last_updated_data=COALESCE(excluded.last_updated_data, league_info.last_updated_data)
    """, (
        league_id,
        league.get("name"),
        league.get("short_name"),
        league.get("created"),
        1 if league.get("closed") else 0,
        league.get("max_entries"),
        league.get("league_type"),
        league.get("scoring"),
        league.get("admin_entry"),
        league.get("start_event"),
        league.get("code_privacy"),
        1 if league.get("has_cup") else 0,
        league.get("cup_league"),
        league.get("rank"),
        data.get("last_updated_data"),
    ))
    await db.execute("""
        INSERT INTO league_pages (league_id, page, has_next, results_count)
        VALUES (?,?,?,?)
        ON CONFLICT(league_id, page) DO UPDATE SET
            has_next=excluded.has_next,
            results_count=excluded.results_count
    """, (
        league_id,
        page,
        1 if standings.get("has_next") else 0,
        len(entries),
    ))


async def replace_manager_transfers(db: aiosqlite.Connection, manager_id: int, transfers: list[dict]):
    await db.execute("DELETE FROM manager_transfers WHERE manager_id=?", (manager_id,))
    await db.executemany("""
        INSERT INTO manager_transfers
        (manager_id, event, time, element_in, element_in_cost, element_out, element_out_cost)
        VALUES (?,?,?,?,?,?,?)
    """, [(
        manager_id,
        row.get("event"),
        row.get("time"),
        row.get("element_in"),
        row.get("element_in_cost"),
        row.get("element_out"),
        row.get("element_out_cost"),
    ) for row in transfers])


async def set_sync(db: aiosqlite.Connection, key: str, meta: dict | None = None):
    from datetime import datetime, timezone
    await db.execute("""
        INSERT OR REPLACE INTO sync_log (key, synced_at, meta)
        VALUES (?, ?, ?)
    """, (key, datetime.now(timezone.utc).isoformat(), json.dumps(meta) if meta else None))


async def get_sync(db: aiosqlite.Connection, key: str) -> dict | None:
    row = await db.execute_fetchall("SELECT * FROM sync_log WHERE key=?", (key,))
    if row:
        r = dict(row[0])
        if r.get("meta"):
            r["meta"] = json.loads(r["meta"])
        return r
    return None


# ── Query helpers ────────────────────────────────────────────────────

async def get_current_event(db: aiosqlite.Connection) -> int | None:
    """Get the current gameweek from sync metadata."""
    sync = await get_sync(db, "bootstrap")
    if sync and sync.get("meta"):
        return sync["meta"].get("current_event")
    return None


async def get_next_open_event(db: aiosqlite.Connection, from_event: int | None = None) -> int | None:
    """Get the next event with unfinished fixtures."""
    params: list = []
    where = "WHERE event IS NOT NULL AND finished=0"
    if from_event is not None:
        where += " AND event >= ?"
        params.append(from_event)

    rows = await db.execute_fetchall(
        f"""
        SELECT event
        FROM fixtures
        {where}
        ORDER BY event, kickoff_time, id
        LIMIT 1
        """,
        params,
    )
    if rows:
        return rows[0]["event"]
    return from_event if from_event is not None else await get_current_event(db)


async def get_player(db: aiosqlite.Connection, player_id: int) -> dict | None:
    rows = await db.execute_fetchall("SELECT * FROM players WHERE id=?", (player_id,))
    return dict(rows[0]) if rows else None


async def get_team(db: aiosqlite.Connection, team_id: int) -> dict | None:
    rows = await db.execute_fetchall("SELECT * FROM teams WHERE id=?", (team_id,))
    return dict(rows[0]) if rows else None


async def get_all_teams(db: aiosqlite.Connection) -> list[dict]:
    rows = await db.execute_fetchall("SELECT * FROM teams ORDER BY id")
    return [dict(r) for r in rows]


async def get_player_history(db: aiosqlite.Connection, player_id: int) -> list[dict]:
    rows = await db.execute_fetchall(
        "SELECT * FROM player_gws WHERE player_id=? ORDER BY event",
        (player_id,)
    )
    return [dict(r) for r in rows]


async def get_manager_squad(db: aiosqlite.Connection, manager_id: int, event: int) -> list[dict]:
    rows = await db.execute_fetchall("""
        SELECT mp.manager_id, mp.event, mp.player_id,
               mp.position as squad_position, mp.multiplier,
               mp.is_captain, mp.is_vice_captain,
               p.web_name, p.team_id, p.position as pos_type,
               p.now_cost, p.total_points, p.form, p.ep_next, p.selected_pct,
               p.xg, p.xa, p.xgi, p.xgc, p.minutes, p.goals_scored, p.assists,
               p.clean_sheets, p.goals_conceded, p.bonus, p.status, p.chance_next, p.news,
               p.influence, p.creativity, p.threat, p.ict_index,
               p.xg_per90, p.xa_per90, p.xgi_per90, p.starts,
               p.penalties_order, p.corners_order,
               t.name as team_name, t.short_name as team_short,
               t.strength as team_strength
        FROM manager_picks mp
        JOIN players p ON mp.player_id = p.id
        JOIN teams t ON p.team_id = t.id
        WHERE mp.manager_id=? AND mp.event=?
        ORDER BY mp.position
    """, (manager_id, event))
    return [dict(r) for r in rows]


async def get_manager_leagues(db: aiosqlite.Connection, manager_id: int) -> list[dict]:
    rows = await db.execute_fetchall("""
        SELECT league_id as id, name, short_name, created, closed,
               league_type as type, scoring, admin_entry, start_event,
               has_cup, cup_league, rank_count, entry_percentile_rank,
               entry_rank, entry_last_rank
        FROM manager_leagues
        WHERE manager_id=?
        ORDER BY CASE WHEN league_type='x' THEN 0 ELSE 1 END,
                 CASE WHEN entry_rank IS NULL THEN 1 ELSE 0 END,
                 entry_rank,
                 name
    """, (manager_id,))
    return [dict(r) for r in rows]


async def get_league_page(db: aiosqlite.Connection, league_id: int, page: int) -> dict | None:
    league_rows = await db.execute_fetchall("SELECT * FROM league_info WHERE id=?", (league_id,))
    page_rows = await db.execute_fetchall(
        "SELECT * FROM league_pages WHERE league_id=? AND page=?",
        (league_id, page),
    )
    standing_rows = await db.execute_fetchall("""
        SELECT rank, last_rank, rank_sort, total, event_total,
               entry_id, entry_name, player_name, has_played, club_badge_src
        FROM league_standings
        WHERE league_id=? AND page=?
        ORDER BY rank_sort, entry_id
    """, (league_id, page))
    if not league_rows and not page_rows and not standing_rows:
        return None
    league = dict(league_rows[0]) if league_rows else {"id": league_id}
    page_info = dict(page_rows[0]) if page_rows else {"league_id": league_id, "page": page, "has_next": 0}
    return {
        "league": league,
        "page": page_info["page"],
        "has_next": bool(page_info.get("has_next")),
        "standings": [dict(r) for r in standing_rows],
    }


async def get_manager_transfers(db: aiosqlite.Connection, manager_id: int) -> list[dict]:
    rows = await db.execute_fetchall("""
        SELECT mt.event, mt.time,
               mt.element_in as in_id,
               COALESCE(pin.web_name, '#' || mt.element_in) as in_name,
               mt.element_in_cost / 10.0 as in_cost,
               mt.element_out as out_id,
               COALESCE(pout.web_name, '#' || mt.element_out) as out_name,
               mt.element_out_cost / 10.0 as out_cost
        FROM manager_transfers mt
        LEFT JOIN players pin ON pin.id = mt.element_in
        LEFT JOIN players pout ON pout.id = mt.element_out
        WHERE mt.manager_id=?
        ORDER BY mt.time DESC
    """, (manager_id,))
    return [dict(r) for r in rows]


async def get_upcoming_fixtures(db: aiosqlite.Connection, team_id: int, from_event: int, n: int = 6) -> list[dict]:
    rows = await db.execute_fetchall("""
        SELECT f.*,
               th.short_name as home_short, ta.short_name as away_short,
               th.name as home_name, ta.name as away_name
        FROM fixtures f
        JOIN teams th ON f.team_h = th.id
        JOIN teams ta ON f.team_a = ta.id
        WHERE (f.team_h=? OR f.team_a=?)
          AND f.event >= ?
          AND f.event IS NOT NULL
          AND f.finished=0
        ORDER BY f.event LIMIT ?
    """, (team_id, team_id, from_event, n))
    return [dict(r) for r in rows]


async def get_next_open_fixture(db: aiosqlite.Connection, from_event: int | None = None) -> dict | None:
    params: list = []
    where = "WHERE f.event IS NOT NULL AND f.finished=0"
    if from_event is not None:
        where += " AND f.event >= ?"
        params.append(from_event)

    rows = await db.execute_fetchall(
        f"""
        SELECT f.*,
               th.short_name as home_short, ta.short_name as away_short,
               th.name as home_name, ta.name as away_name
        FROM fixtures f
        JOIN teams th ON f.team_h = th.id
        JOIN teams ta ON f.team_a = ta.id
        {where}
        ORDER BY f.event, f.kickoff_time, f.id
        LIMIT 1
        """,
        params,
    )
    return dict(rows[0]) if rows else None


async def get_team_fixtures_in_window(
    db: aiosqlite.Connection,
    team_id: int,
    from_event: int,
    to_event: int,
) -> list[dict]:
    rows = await db.execute_fetchall("""
        SELECT f.*,
               th.short_name as home_short, ta.short_name as away_short,
               th.name as home_name, ta.name as away_name
        FROM fixtures f
        JOIN teams th ON f.team_h = th.id
        JOIN teams ta ON f.team_a = ta.id
        WHERE (f.team_h=? OR f.team_a=?)
          AND f.event IS NOT NULL
          AND f.finished=0
          AND f.event BETWEEN ? AND ?
        ORDER BY f.event, f.kickoff_time, f.id
    """, (team_id, team_id, from_event, to_event))
    return [dict(r) for r in rows]


async def get_team_match_results(db: aiosqlite.Connection, team_id: int) -> list[dict]:
    """Get all finished match results for a team — used for structural covariance."""
    rows = await db.execute_fetchall("""
        SELECT event, team_h, team_a, team_h_score, team_a_score,
               CASE WHEN team_h=? THEN team_h_score ELSE team_a_score END as goals_scored,
               CASE WHEN team_h=? THEN team_a_score ELSE team_h_score END as goals_conceded,
               CASE WHEN team_h=? THEN 1 ELSE 0 END as was_home
        FROM fixtures
        WHERE (team_h=? OR team_a=?) AND finished=1 AND team_h_score IS NOT NULL
        ORDER BY event
    """, (team_id, team_id, team_id, team_id, team_id))
    return [dict(r) for r in rows]


# ── Live GW + EP snapshots ──────────────────────────────────────────

async def snapshot_ep(conn: aiosqlite.Connection, event: int, player_ids: list[int]):
    """Store pre-GW expected points for players. Only writes if no snapshot exists yet."""
    now = datetime.now(timezone.utc).isoformat()
    existing = await conn.execute_fetchall(
        f"SELECT player_id FROM ep_snapshots WHERE event=? AND player_id IN ({','.join('?' * len(player_ids))})",
        [event] + player_ids,
    )
    already = {r["player_id"] for r in existing}
    new_ids = [pid for pid in player_ids if pid not in already]
    if not new_ids:
        return
    rows = await conn.execute_fetchall(
        f"SELECT id, ep_next FROM players WHERE id IN ({','.join('?' * len(new_ids))})",
        new_ids,
    )
    await conn.executemany(
        "INSERT OR IGNORE INTO ep_snapshots (player_id, event, ep_value, snapped_at) VALUES (?,?,?,?)",
        [(r["id"], event, r["ep_next"], now) for r in rows if r["ep_next"] is not None],
    )
    await conn.commit()


async def get_ep_snapshots(conn: aiosqlite.Connection, event: int, player_ids: list[int]) -> dict[int, float]:
    """Get pre-GW EP snapshots. Returns {player_id: ep_value}."""
    if not player_ids:
        return {}
    rows = await conn.execute_fetchall(
        f"SELECT player_id, ep_value FROM ep_snapshots WHERE event=? AND player_id IN ({','.join('?' * len(player_ids))})",
        [event] + player_ids,
    )
    return {r["player_id"]: r["ep_value"] for r in rows}


async def upsert_live_gw(conn: aiosqlite.Connection, event: int, elements: list[dict]):
    """Upsert live gameweek player data."""
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for el in elements:
        stats = el.get("stats", {})
        rows.append((
            event, el["id"],
            stats.get("minutes", 0), stats.get("total_points", 0),
            stats.get("goals_scored", 0), stats.get("assists", 0),
            stats.get("clean_sheets", 0), stats.get("goals_conceded", 0),
            stats.get("bonus", 0), stats.get("bps", 0),
            stats.get("saves", 0), stats.get("yellow_cards", 0),
            stats.get("red_cards", 0), stats.get("penalties_missed", 0),
            stats.get("own_goals", 0), now,
        ))
    await conn.executemany("""
        INSERT OR REPLACE INTO live_gw_cache
        (event, player_id, minutes, total_points, goals_scored, assists,
         clean_sheets, goals_conceded, bonus, bps, saves, yellow_cards,
         red_cards, penalties_missed, own_goals, synced_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    await conn.commit()


async def get_live_gw(conn: aiosqlite.Connection, event: int, player_ids: list[int]) -> dict[int, dict]:
    """Get live GW data for specific players. Returns {player_id: stats_dict}."""
    if not player_ids:
        return {}
    rows = await conn.execute_fetchall(
        f"""SELECT * FROM live_gw_cache
            WHERE event=? AND player_id IN ({','.join('?' * len(player_ids))})""",
        [event] + player_ids,
    )
    return {r["player_id"]: dict(r) for r in rows}


async def get_event_fixtures(conn: aiosqlite.Connection, event: int) -> list[dict]:
    """Get all fixtures for a specific gameweek with team names."""
    rows = await conn.execute_fetchall("""
        SELECT f.*, th.name as home_name, th.short_name as home_short,
               ta.name as away_name, ta.short_name as away_short
        FROM fixtures f
        JOIN teams th ON f.team_h = th.id
        JOIN teams ta ON f.team_a = ta.id
        WHERE f.event = ?
        ORDER BY f.kickoff_time, f.id
    """, (event,))
    return [dict(r) for r in rows]


# ── Intelligence layer ──────────────────────────────────────────────

async def upsert_signal_source(
    conn: aiosqlite.Connection,
    key: str,
    label: str,
    source_type: str,
    weight: float = 1.0,
    enabled: bool = True,
    meta: dict | None = None,
):
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute("""
        INSERT INTO signal_sources (key, label, source_type, weight, enabled, meta, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            label=excluded.label,
            source_type=excluded.source_type,
            weight=excluded.weight,
            enabled=excluded.enabled,
            meta=excluded.meta,
            updated_at=excluded.updated_at
    """, (key, label, source_type, weight, 1 if enabled else 0, _json_dump(meta), now))


async def get_signal_sources(conn: aiosqlite.Connection, enabled_only: bool = True) -> list[dict]:
    where = "WHERE enabled=1" if enabled_only else ""
    rows = await conn.execute_fetchall(f"""
        SELECT * FROM signal_sources
        {where}
        ORDER BY enabled DESC, weight DESC, key
    """)
    result = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item.get("enabled"))
        if item.get("meta"):
            item["meta"] = json.loads(item["meta"])
        result.append(item)
    return result


async def upsert_projection_snapshot(
    conn: aiosqlite.Connection,
    source_key: str,
    snapshot_at: str,
    event: int,
    horizon: int,
    rows: list[dict],
):
    await conn.executemany("""
        INSERT OR REPLACE INTO projection_snapshots
        (source_key, snapshot_at, event, horizon, player_id, expected_points,
         xg, xa, xgi, expected_minutes, selected_pct, anytime_return_prob,
         clean_sheet_prob, raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        source_key,
        snapshot_at,
        event,
        horizon,
        row["player_id"],
        row.get("expected_points"),
        row.get("xg"),
        row.get("xa"),
        row.get("xgi"),
        row.get("expected_minutes"),
        row.get("selected_pct"),
        row.get("anytime_return_prob"),
        row.get("clean_sheet_prob"),
        _json_dump(row.get("raw")),
    ) for row in rows])


async def get_latest_projection_rows(
    conn: aiosqlite.Connection,
    event: int,
    horizon: int,
    player_ids: list[int] | None = None,
    source_key: str | None = None,
) -> list[dict]:
    params: list = [event, horizon]
    filter_sql = ""
    if player_ids:
        placeholders = ",".join("?" * len(player_ids))
        filter_sql += f" AND player_id IN ({placeholders})"
        params.extend(player_ids)
    if source_key:
        filter_sql += " AND source_key=?"
        params.append(source_key)

    rows = await conn.execute_fetchall(f"""
        SELECT *
        FROM projection_snapshots
        WHERE event=? AND horizon=? {filter_sql}
        ORDER BY source_key, snapshot_at DESC
    """, params)

    latest_cutoff: dict[str, str] = {}
    result = []
    for row in rows:
        item = dict(row)
        source_key = item["source_key"]
        snapshot_at = item["snapshot_at"]
        if source_key not in latest_cutoff:
            latest_cutoff[source_key] = snapshot_at
        if latest_cutoff[source_key] != snapshot_at:
            continue
        if item.get("raw"):
            item["raw"] = json.loads(item["raw"])
        result.append(item)
    return result


async def insert_intel_run(
    conn: aiosqlite.Connection,
    manager_id: int,
    event: int,
    horizon: int,
    summary: dict,
    model_version: str = "transfer-intel-v1",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = await conn.execute("""
        INSERT INTO intel_runs (manager_id, event, horizon, created_at, model_version, summary)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (manager_id, event, horizon, now, model_version, _json_dump(summary)))
    return cur.lastrowid


async def upsert_intel_alerts(conn: aiosqlite.Connection, alerts: list[dict]):
    if not alerts:
        return
    await conn.executemany("""
        INSERT INTO intel_alerts
        (run_id, manager_id, event, horizon, category, severity, title, detail,
         score, dedupe_key, payload, created_at, delivery_status, delivered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL)
        ON CONFLICT(manager_id, event, dedupe_key) DO UPDATE SET
            run_id=excluded.run_id,
            horizon=excluded.horizon,
            category=excluded.category,
            severity=excluded.severity,
            title=excluded.title,
            detail=excluded.detail,
            score=excluded.score,
            payload=excluded.payload,
            created_at=excluded.created_at,
            delivery_status='pending',
            delivered_at=NULL
        WHERE intel_alerts.title <> excluded.title
           OR intel_alerts.detail <> excluded.detail
           OR intel_alerts.severity <> excluded.severity
           OR ABS(COALESCE(intel_alerts.score, 0) - COALESCE(excluded.score, 0)) > 0.01
           OR COALESCE(intel_alerts.payload, '') <> COALESCE(excluded.payload, '')
    """, [(
        alert.get("run_id"),
        alert["manager_id"],
        alert["event"],
        alert["horizon"],
        alert["category"],
        alert["severity"],
        alert["title"],
        alert["detail"],
        alert.get("score", 0),
        alert["dedupe_key"],
        _json_dump(alert.get("payload")),
        alert.get("created_at") or datetime.now(timezone.utc).isoformat(),
    ) for alert in alerts])


async def get_intel_alerts(
    conn: aiosqlite.Connection,
    manager_id: int,
    delivery_status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    params: list = [manager_id]
    where = "WHERE manager_id=?"
    if delivery_status is not None:
        where += " AND delivery_status=?"
        params.append(delivery_status)
    params.append(limit)
    rows = await conn.execute_fetchall(f"""
        SELECT *
        FROM intel_alerts
        {where}
        ORDER BY created_at DESC, score DESC
        LIMIT ?
    """, params)
    result = []
    for row in rows:
        item = dict(row)
        if item.get("payload"):
            item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result


async def mark_intel_alert_delivered(
    conn: aiosqlite.Connection,
    alert_id: int,
    status: str = "delivered",
):
    delivered_at = datetime.now(timezone.utc).isoformat()
    await conn.execute("""
        UPDATE intel_alerts
        SET delivery_status=?, delivered_at=?
        WHERE id=?
    """, (status, delivered_at, alert_id))


async def upsert_alert_delivery_target(
    conn: aiosqlite.Connection,
    name: str,
    target_type: str,
    enabled: bool = True,
    config: dict | None = None,
):
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute("""
        INSERT INTO alert_delivery_targets (name, target_type, enabled, config, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            target_type=excluded.target_type,
            enabled=excluded.enabled,
            config=excluded.config,
            updated_at=excluded.updated_at
    """, (name, target_type, 1 if enabled else 0, _json_dump(config), now))


async def get_alert_delivery_targets(conn: aiosqlite.Connection, enabled_only: bool = True) -> list[dict]:
    where = "WHERE enabled=1" if enabled_only else ""
    rows = await conn.execute_fetchall(f"""
        SELECT *
        FROM alert_delivery_targets
        {where}
        ORDER BY enabled DESC, name
    """)
    result = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item.get("enabled"))
        if item.get("config"):
            item["config"] = json.loads(item["config"])
        result.append(item)
    return result


async def upsert_availability_snapshots(conn: aiosqlite.Connection, rows: list[dict]):
    if not rows:
        return
    await conn.executemany("""
        INSERT OR REPLACE INTO player_availability_snapshots
        (target_event, player_id, snapshot_at, team_id, status, chance_next, news,
         news_category, news_severity, news_purity, listed_play_prob, listed_start_prob,
         expected_minutes, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        row["target_event"],
        row["player_id"],
        row["snapshot_at"],
        row["team_id"],
        row.get("status"),
        row.get("chance_next"),
        row.get("news"),
        row.get("news_category"),
        row.get("news_severity"),
        row.get("news_purity"),
        row.get("listed_play_prob"),
        row.get("listed_start_prob"),
        row.get("expected_minutes"),
        row.get("model_version"),
    ) for row in rows])


async def append_availability_tape(conn: aiosqlite.Connection, rows: list[dict]):
    if not rows:
        return
    await conn.executemany("""
        INSERT INTO player_availability_tape
        (target_event, player_id, snapshot_at, snapshot_kind, snapshot_reason, changed_fields,
         team_id, status, chance_next, news, news_category, news_severity, news_purity,
         listed_play_prob, listed_start_prob, expected_minutes, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        row["target_event"],
        row["player_id"],
        row["snapshot_at"],
        row.get("snapshot_kind") or "poll",
        row.get("snapshot_reason"),
        _json_dump(row.get("changed_fields")),
        row["team_id"],
        row.get("status"),
        row.get("chance_next"),
        row.get("news"),
        row.get("news_category"),
        row.get("news_severity"),
        row.get("news_purity"),
        row.get("listed_play_prob"),
        row.get("listed_start_prob"),
        row.get("expected_minutes"),
        row.get("model_version"),
    ) for row in rows])


async def get_latest_availability_snapshots(
    conn: aiosqlite.Connection,
    target_event: int,
    player_ids: list[int] | None = None,
) -> dict[int, dict]:
    params: list = [target_event]
    filter_sql = ""
    if player_ids:
        placeholders = ",".join("?" * len(player_ids))
        filter_sql = f" AND player_id IN ({placeholders})"
        params.extend(player_ids)
    rows = await conn.execute_fetchall(f"""
        SELECT *
        FROM player_availability_snapshots
        WHERE target_event=? {filter_sql}
    """, params)
    return {row["player_id"]: dict(row) for row in rows}


async def upsert_availability_profiles(
    conn: aiosqlite.Connection,
    as_of_event: int,
    rows: list[dict],
):
    if not rows:
        return
    now = datetime.now(timezone.utc).isoformat()
    await conn.executemany("""
        INSERT OR REPLACE INTO availability_profiles
        (as_of_event, team_id, status, chance_bucket, news_category, sample_size,
         listed_play_rate, actual_play_rate, listed_start_rate, actual_start_rate,
         listed_minutes, actual_minutes, play_bias, start_bias, mean_abs_error,
         honesty_score, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        as_of_event,
        row.get("team_id", 0),
        row["status"],
        row["chance_bucket"],
        row["news_category"],
        row["sample_size"],
        row.get("listed_play_rate"),
        row.get("actual_play_rate"),
        row.get("listed_start_rate"),
        row.get("actual_start_rate"),
        row.get("listed_minutes"),
        row.get("actual_minutes"),
        row.get("play_bias"),
        row.get("start_bias"),
        row.get("mean_abs_error"),
        row.get("honesty_score"),
        now,
    ) for row in rows])


async def get_availability_profiles(conn: aiosqlite.Connection, as_of_event: int) -> list[dict]:
    rows = await conn.execute_fetchall("""
        SELECT MAX(as_of_event) as effective_event
        FROM availability_profiles
        WHERE as_of_event <= ?
    """, (as_of_event,))
    effective_event = rows[0]["effective_event"] if rows else None
    if effective_event is None:
        return []

    profile_rows = await conn.execute_fetchall("""
        SELECT *
        FROM availability_profiles
        WHERE as_of_event = ?
        ORDER BY team_id, status, chance_bucket, news_category
    """, (effective_event,))
    return [dict(row) for row in profile_rows]


async def touch_background_manager(
    conn: aiosqlite.Connection,
    manager_id: int,
    source: str = "api",
    pinned: bool = False,
    meta: dict | None = None,
):
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute("""
        INSERT INTO background_manager_registry
        (manager_id, source, pinned, last_seen_at, last_warmed_at, meta)
        VALUES (?, ?, ?, ?, NULL, ?)
        ON CONFLICT(manager_id) DO UPDATE SET
            source=excluded.source,
            pinned=CASE
                WHEN background_manager_registry.pinned = 1 OR excluded.pinned = 1 THEN 1
                ELSE 0
            END,
            last_seen_at=excluded.last_seen_at,
            meta=CASE
                WHEN excluded.meta IS NOT NULL THEN excluded.meta
                ELSE background_manager_registry.meta
            END
    """, (
        manager_id,
        source,
        1 if pinned else 0,
        now,
        _json_dump(meta),
    ))


async def list_background_managers(
    conn: aiosqlite.Connection,
    max_age_hours: int = 24,
    include_pinned: bool = True,
) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(max_age_hours, 1))).isoformat()
    where = "WHERE last_seen_at >= ?"
    params: list = [cutoff]
    if include_pinned:
        where = "WHERE pinned = 1 OR last_seen_at >= ?"

    rows = await conn.execute_fetchall(f"""
        SELECT *
        FROM background_manager_registry
        {where}
        ORDER BY pinned DESC, last_seen_at DESC, manager_id
    """, params)
    result = []
    for row in rows:
        item = dict(row)
        item["pinned"] = bool(item.get("pinned"))
        if item.get("meta"):
            item["meta"] = json.loads(item["meta"])
        result.append(item)
    return result


async def mark_background_managers_warmed(
    conn: aiosqlite.Connection,
    manager_ids: list[int],
    warmed_at: str | None = None,
):
    if not manager_ids:
        return
    stamp = warmed_at or datetime.now(timezone.utc).isoformat()
    await conn.executemany("""
        UPDATE background_manager_registry
        SET last_warmed_at=?
        WHERE manager_id=?
    """, [(stamp, manager_id) for manager_id in manager_ids])


def _json_dump(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def _float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
