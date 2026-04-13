<script lang="ts">
  import { getManagerLeagues, getLeagueStandings } from '$lib/api';
  import { managerId } from '$lib/session';
  import { goto } from '$app/navigation';
  import { browser } from '$app/environment';

  // Client-only redirect — goto() throws during SSR
  $effect(() => { if (browser && !$managerId) goto('/'); });

  let leagues: any[] = $state([]);
  let loadingLeagues = $state(true);
  let leaguesStale = $state(false);
  let leaguesSyncedAt = $state('');
  let selectedLeague: any = $state(null);
  let standings: any[] = $state([]);
  let leagueInfo: any = $state(null);
  let loadingStandings = $state(false);
  let standingsPage = $state(1);
  let standingsHasNext = $state(false);
  let standingsStale = $state(false);
  let standingsSyncedAt = $state('');

  async function loadLeagues(refresh = false) {
    if (!$managerId) return;
    loadingLeagues = true;
    try {
      const d = await getManagerLeagues($managerId, refresh);
      leagues = d.leagues;
      leaguesStale = !!d.stale;
      leaguesSyncedAt = d.synced_at ?? '';
    } catch {}
    finally { loadingLeagues = false; }
  }

  $effect(() => { if ($managerId) loadLeagues(); });

  async function openLeague(lg: any, page = 1, refresh = false) {
    selectedLeague = lg;
    standingsPage = page;
    loadingStandings = true;
    try {
      const data = await getLeagueStandings(lg.id, page, refresh);
      leagueInfo = data.league;
      standings = data.standings;
      standingsHasNext = !!data.has_next;
      standingsStale = !!data.stale;
      standingsSyncedAt = data.synced_at ?? '';
    } catch { standings = []; }
    finally { loadingStandings = false; }
  }

  function isMe(entryId: number) { return entryId === $managerId; }
</script>

<div class="container page-stack reveal">
  <header class="page-hero">
    <div>
      <h1>Leagues</h1>
      <p class="dim small">Your mini-leagues and standings, with the active table kept in the main workspace.</p>
    </div>
    <div class="league-summary">
      <div class="summary-chip">
        <span class="dim2 small">Tracked</span>
        <strong>{leagues.length}</strong>
      </div>
      <div class="summary-chip">
        <span class="dim2 small">Selected</span>
        <strong>{selectedLeague ? selectedLeague.name : 'None'}</strong>
      </div>
    </div>
  </header>

  <div class="leagues-layout">
    <section class="league-list card">
      <div class="card-header">
        <h2>My Leagues</h2>
        <button class="btn-ghost small" onclick={() => loadLeagues(true)} disabled={loadingLeagues}>Refresh</button>
      </div>
      {#if loadingLeagues}
        <p class="dim loading small">Loading leagues...</p>
      {:else}
        {#if leaguesStale}<p class="dim2 small" style="padding: 0 0.75rem 0.5rem;">Showing stale cache</p>{/if}
        {#if leaguesSyncedAt}<p class="dim2 small" style="padding: 0 0.75rem 0.5rem;">Synced {new Date(leaguesSyncedAt).toLocaleString()}</p>{/if}
        {#each leagues.filter(l => l.type !== 's' || l.name === 'Overall') as lg}
          <button class="league-row" class:active={selectedLeague?.id === lg.id} onclick={() => openLeague(lg, 1)}>
            <span class="league-name">{lg.name}</span>
            <div class="league-meta">
              <span class="badge badge-accent">#{lg.entry_rank ?? '—'}</span>
              {#if lg.type === 's'}<span class="dim2 small">system</span>{/if}
            </div>
          </button>
        {/each}
      {/if}
    </section>

    <section class="standings-panel card">
      {#if selectedLeague}
        <div class="card-header">
          <h2>{leagueInfo?.name ?? selectedLeague.name}</h2>
          <div class="league-actions">
            <span class="dim2 small">Page {standingsPage}</span>
            <button class="btn-ghost small" onclick={() => openLeague(selectedLeague, standingsPage, true)} disabled={loadingStandings}>Refresh</button>
          </div>
        </div>
        {#if standingsStale}<p class="dim2 small" style="margin-bottom: 0.5rem;">Showing stale cache</p>{/if}
        {#if standingsSyncedAt}<p class="dim2 small" style="margin-bottom: 0.5rem;">Synced {new Date(standingsSyncedAt).toLocaleString()}</p>{/if}
        {#if loadingStandings}
          <p class="dim loading small">Loading standings...</p>
        {:else}
          <table>
            <thead>
              <tr>
                <th>#</th><th>Team</th><th>Manager</th>
                <th class="r">GW</th><th class="r">Total</th>
              </tr>
            </thead>
            <tbody>
              {#each standings as e}
                <tr class:me={isMe(e.entry_id)}>
                  <td class="mono">{e.rank}</td>
                  <td class="team-name">{e.entry_name}</td>
                  <td class="dim2">{e.player_name}</td>
                  <td class="r mono">{e.event_total}</td>
                  <td class="r mono">{e.total}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          <div class="pager">
            <button class="btn-ghost small" onclick={() => openLeague(selectedLeague, standingsPage - 1)} disabled={loadingStandings || standingsPage <= 1}>Prev</button>
            <button class="btn-ghost small" onclick={() => openLeague(selectedLeague, standingsPage + 1)} disabled={loadingStandings || !standingsHasNext}>Next</button>
          </div>
        {/if}
      {:else}
        <div class="surface-note league-empty">Select a league to load its standings table.</div>
      {/if}
    </section>
  </div>
</div>

<style>
  .league-summary {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.55rem;
    min-width: min(100%, 18rem);
  }
  .summary-chip {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.8rem 0.9rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  }
  .summary-chip strong {
    font-size: 0.92rem;
    color: var(--text-heading);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .leagues-layout { display: grid; grid-template-columns: 280px 1fr; gap: 0.85rem; }
  .league-list { padding: 0.55rem; }
  .league-row {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; padding: 0.6rem 0.75rem; background: transparent;
    border: none; border-bottom: 1px solid var(--border);
    color: var(--text); cursor: pointer; text-align: left;
    font-family: var(--font); font-size: 0.8rem;
    transition: background var(--duration) var(--ease);
  }
  .league-row:hover { background: var(--bg-elevated); }
  .league-row.active { background: var(--bg-selected); border-color: var(--accent); }
  .league-name { font-weight: 500; }
  .league-meta { display: flex; align-items: center; gap: 0.4rem; }
  .league-actions { display: flex; align-items: center; gap: 0.5rem; }
  .standings-panel { min-height: 22rem; }
  .league-empty { margin-top: 1rem; }

  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { text-align: left; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }
  td { padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--border); }
  tr:hover { background: var(--bg-card-hover); }
  .r { text-align: right; }
  .team-name { font-weight: 500; }
  .me { background: var(--bg-selected) !important; }
  .me td { font-weight: 600; }
  .pager { display: flex; justify-content: flex-end; gap: 0.5rem; padding-top: 0.75rem; }

  @media (max-width: 820px) {
    .league-summary { grid-template-columns: 1fr; width: 100%; }
    .leagues-layout { grid-template-columns: 1fr; }
  }
</style>
