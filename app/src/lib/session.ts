import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

// ── Current signed-in manager ───────────────────────────
export const managerId = writable<number | null>(
  browser ? (parseInt(localStorage.getItem('volante-mgr') || '') || null) : null
);

managerId.subscribe(v => {
  if (browser) {
    if (v) localStorage.setItem('volante-mgr', String(v));
    else localStorage.removeItem('volante-mgr');
  }
});

// ── Recent-manager list (quick-resume buttons) ──────────
export type RecentManager = {
  id: number;
  team_name: string;
  player_name: string;
  last_used: string;       // ISO timestamp
};

const RECENT_KEY = 'volante-recent-managers';
const MAX_RECENT = 5;

function readRecents(): RecentManager[] {
  if (!browser) return [];
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

export const recentManagers = writable<RecentManager[]>(readRecents());

export function rememberManager(entry: RecentManager) {
  recentManagers.update(list => {
    const without = list.filter(m => m.id !== entry.id);
    const next = [{ ...entry, last_used: new Date().toISOString() }, ...without].slice(0, MAX_RECENT);
    if (browser) {
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch {}
    }
    return next;
  });
}

export function forgetManager(id: number) {
  recentManagers.update(list => {
    const next = list.filter(m => m.id !== id);
    if (browser) {
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch {}
    }
    return next;
  });
}
