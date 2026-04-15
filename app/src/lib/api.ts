import { browser } from '$app/environment';

const DEFAULT_API_PROTOCOL = browser ? window.location.protocol : 'http:';
const DEFAULT_API_HOST = browser ? window.location.hostname : '127.0.0.1';
const DEFAULT_API_PORT = browser && window.location.port === '5555' ? '8555' : '8556';
const BASE = import.meta.env.VITE_API_BASE || `${DEFAULT_API_PROTOCOL}//${DEFAULT_API_HOST}:${DEFAULT_API_PORT}`;

function withQuery(path: string, params: Record<string, unknown> = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '' && v !== false) qs.set(k, String(v));
  }
  return `${path}${qs.size ? `?${qs}` : ''}`;
}

async function request(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // Preserve the status + parsed detail on the Error so callers can branch
    // on things like the 428 {reason,message} contract from /api/live/*.
    const msg = typeof body.detail === 'string'
      ? body.detail
      : (body?.detail?.message || `HTTP ${res.status}`);
    const err = new Error(msg) as Error & { status?: number; detail?: unknown };
    err.status = res.status;
    err.detail = body?.detail ?? body;
    throw err;
  }
  return res.json();
}

export const syncAll = () => request('/api/sync', { method: 'POST' });

export const syncManager = (id: number) =>
  request('/api/sync/manager', { method: 'POST', body: JSON.stringify({ manager_id: id }) });

export const getXray = (id: number, lookback?: number, refresh = false) =>
  request(withQuery(`/api/xray/${id}`, { lookback, refresh }));

export const getXrayWithLookback = (id: number, lookback?: number) =>
  request(withQuery(`/api/xray/${id}`, { lookback }));

export const getXrayForecast = (id: number, futureWeeks: number, lookback?: number) =>
  request(withQuery(`/api/xray/${id}`, { lookback, future_weeks: futureWeeks }));

export const getAttribution = (id: number, lookback?: number) =>
  request(withQuery(`/api/xray/${id}/attribution`, { lookback }));

export const getPlayerDetail = (mgr: number, pid: number) =>
  request(`/api/xray/${mgr}/player/${pid}`);

export const simulateTransfer = (mgr: number, out: number, inn: number) =>
  request(`/api/xray/${mgr}/simulate`, {
    method: 'POST', body: JSON.stringify({ player_out: out, player_in: inn }),
  });

export const simulateTransferPlan = (
  mgr: number,
  picks: Array<{ sell_id: number; buy_id: number }>,
  horizon = 5,
  event?: number,
) =>
  request(`/api/xray/${mgr}/simulate-plan`, {
    method: 'POST',
    body: JSON.stringify({ picks, horizon, event }),
  });

export const getPlayers = (params: Record<string, unknown> = {}) =>
  request(withQuery('/api/players', params));

export const getManagerLeagues = (id: number, refresh = false) =>
  request(withQuery(`/api/manager/${id}/leagues`, { refresh }));
export const getLeagueStandings = (id: number, page = 1, refresh = false) =>
  request(withQuery(`/api/leagues/${id}`, { page, refresh }));
export const getManagerTransfers = (id: number, refresh = false) =>
  request(withQuery(`/api/manager/${id}/transfers`, { refresh }));
export const getStatus = (managerId?: number) =>
  request(withQuery('/api/status', { manager_id: managerId }));

// ── Transfer Lab ─────────────────────────────────────────────────────
export const recommendReplacements = (mgr: number, sellIds: number[], n = 5, horizon = 5) =>
  request(`/api/xray/${mgr}/recommend`, {
    method: 'POST', body: JSON.stringify({ sell_ids: sellIds, n, horizon }),
  });
export const getSuggestedTransfers = (mgr: number, n = 5) =>
  request(withQuery(`/api/xray/${mgr}/suggest`, { n }));
export const getTransferAnalysis = (id: number) => request(`/api/manager/${id}/transfer-analysis`);

export const getFixtureExposure = (mgr: number) => request(`/api/xray/${mgr}/fixtures`);

export type CaptainCandidate = {
  player_id: number;
  web_name: string;
  team_short: string;
  squad_position: number;
  ep_next: number;
  expected_minutes_next: number;
  minutes_factor: number;
  captain_score: number;
  is_captain: boolean;
  is_vice_captain: boolean;
};

export type CaptainSuggestion = {
  manager_id: number;
  projection_event: number;
  current_captain: CaptainCandidate | null;
  recommended: CaptainCandidate;
  swing_ep: number;
  should_switch: boolean;
  ranking: CaptainCandidate[];
};

export const getCaptainSuggestion = (mgr: number): Promise<CaptainSuggestion> =>
  request(`/api/xray/${mgr}/suggest-captain`);

// ── Live Gameweek ───────────────────────────────────────────────
export const getLiveData = (mgr: number) => request(`/api/live/${mgr}`);
export const getGameweekStatus = () => request('/api/gameweek-status');
export const getPredictionAccuracy = (mgr: number, weeks = 6) =>
  request(withQuery(`/api/live/${mgr}/accuracy`, { weeks }));

// ── FPL Session (cookie-paste live state) ───────────────────────
export type FplSessionStatus = {
  connected: boolean;
  auth_mode: 'pingone' | 'legacy' | null;
  has_csrf: boolean;
  has_datadome: boolean;
  account_id: number | null;
  stored_at: string | null;
  last_validated_at: string | null;
};

export type LiveSquad = {
  manager_id: number;
  event: number | null;
  picks: Array<{
    element: number; position: number; multiplier: number;
    is_captain: boolean; is_vice_captain: boolean;
    selling_price: number; purchase_price: number;
  }>;
  transfers: {
    made: number | null; limit: number | null; remaining: number | null;
    bank: number | null; value: number | null; cost: number | null;
    status: string | null;
  };
  chips_staged: string[];
};

export type LiveSquadReason = 'no_cookie' | 'expired' | 'account_mismatch';

export const getFplStatus = (): Promise<FplSessionStatus> =>
  request('/api/settings/fpl-status');

export const setFplCookie = (raw: string): Promise<FplSessionStatus> =>
  request('/api/settings/fpl-cookie', {
    method: 'POST',
    body: JSON.stringify({ raw }),
  });

export const clearFplCookie = (): Promise<{ ok: true }> =>
  request('/api/settings/fpl-cookie', { method: 'DELETE' });

export const getLiveSquad = (mgr: number): Promise<LiveSquad> =>
  request(`/api/live/${mgr}/squad`);
