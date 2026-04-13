<script lang="ts">
  import { getLiveData, getPredictionAccuracy } from '$lib/api';
  import { managerId } from '$lib/session';
  import PitchField from '$lib/components/PitchField.svelte';
  import * as Icon from '$lib/components/icons';
  import { onDestroy } from 'svelte';
  import { goto } from '$app/navigation';

  let data: any = $state(null);
  let accuracy: any = $state(null);
  let loading = $state(true);
  let timer: ReturnType<typeof setInterval> | null = null;

  // Redirect to home if not logged in
  $effect(() => {
    if (!$managerId) { goto('/'); return; }
    load();
  });

  async function load() {
    if (!$managerId) return;
    loading = !data;
    try {
      const [live, acc] = await Promise.all([
        getLiveData($managerId),
        getPredictionAccuracy($managerId).catch(() => null),
      ]);
      data = live;
      accuracy = acc;
      if (!timer && (live?.is_live || live?.has_started)) {
        timer = setInterval(refresh, 120_000);
      }
    } catch {}
    finally { loading = false; }
  }

  async function refresh() {
    if (!$managerId) return;
    try { data = await getLiveData($managerId); } catch {}
  }

  onDestroy(() => { if (timer) clearInterval(timer); });

  // Derived
  let starters = $derived(
    (data?.players ?? []).filter((p: any) => p.is_starter)
  );
  let bench = $derived(
    (data?.players ?? []).filter((p: any) => !p.is_starter)
  );
  let gks  = $derived(starters.filter((p: any) => p.pos_type === 1));
  let defs = $derived(starters.filter((p: any) => p.pos_type === 2));
  let mids = $derived(starters.filter((p: any) => p.pos_type === 3));
  let fwds = $derived(starters.filter((p: any) => p.pos_type === 4));
  let fixtures = $derived(data?.fixtures ?? []);
  let isLive = $derived(data?.is_live === true);
  let hasStarted = $derived(data?.has_started === true);
</script>

<div class="container page-stack">
  {#if loading && !data}
    <div class="pts-loading"><div class="spinner"></div><p class="dim">Loading points…</p></div>

  {:else if !data || !hasStarted}
    <div class="pts-empty">
      <Icon.Ball size={32} />
      <h2>No live gameweek</h2>
      <p class="dim">Points will appear here once the gameweek kicks off.</p>
    </div>

  {:else}
    <!-- ═════ GW HEADER ═════ -->
    <header class="pts-header">
      <div class="pts-gw-label">
        <span class="eyebrow"><Icon.Ball size={12} /> Gameweek {data.event}</span>
        {#if isLive}
          <span class="pts-live-pill"><span class="pts-live-dot"></span>LIVE</span>
        {:else}
          <span class="pts-final-pill">Final</span>
        {/if}
      </div>
      <div class="pts-total">
        <span class="pts-total-num mono">{data.live_points.total}</span>
        <span class="pts-total-label">pts</span>
      </div>
      <div class="pts-meta-row">
        <div class="pts-meta-cell">
          <span class="dim2">Predicted</span>
          <span class="mono">{data.live_points.pre_gw_ep}</span>
        </div>
        <div class="pts-meta-cell">
          <span class="dim2">Delta</span>
          <span class="mono {(data.live_points.total - data.live_points.pre_gw_ep) >= 0 ? 'accent' : 'negative'}">{(data.live_points.total - data.live_points.pre_gw_ep) >= 0 ? '+' : ''}{(data.live_points.total - data.live_points.pre_gw_ep).toFixed(1)}</span>
        </div>
        <div class="pts-meta-cell">
          <span class="dim2">Fixtures</span>
          <span class="mono">{data.gw_status.finished}/{data.gw_status.total_fixtures}</span>
        </div>
        {#if data.manager}
          <div class="pts-meta-cell">
            <span class="dim2">Overall</span>
            <span class="mono">{data.manager.overall_points?.toLocaleString()}</span>
          </div>
        {/if}
      </div>
    </header>

    <!-- ═════ PITCH ═════ -->
    <section class="pts-pitch-section">
      <div class="pts-pitch-wrap">
        <PitchField />
        <div class="pts-formation">
          {#each [fwds, mids, defs, gks] as row}
            <div class="pts-row">
              {#each row as p (p.id)}
                {@const playing = p.fixture_status === 'in_progress'}
                {@const done = p.fixture_status === 'finished'}
                {@const upcoming = p.fixture_status === 'upcoming'}
                <div class="pts-chip" class:pts-playing={playing} class:pts-done={done} class:pts-upcoming={upcoming}>
                  <div class="pts-chip-pts mono">{p.effective_points}</div>
                  <div class="pts-chip-name">{p.web_name}</div>
                  <div class="pts-chip-info">
                    <span class="pts-chip-team">{p.team_short}</span>
                    {#if p.is_captain}<span class="pts-chip-cap">C</span>{/if}
                  </div>
                  {#if p.minutes > 0 || done}
                    <div class="pts-chip-stats">
                      {#if p.goals > 0}<span>G{p.goals}</span>{/if}
                      {#if p.assists > 0}<span>A{p.assists}</span>{/if}
                      {#if p.clean_sheets > 0}<span>CS</span>{/if}
                      {#if p.bonus > 0}<span class="accent">+{p.bonus}</span>{/if}
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          {/each}
        </div>
      </div>

      <!-- Bench -->
      <div class="pts-bench">
        <span class="eyebrow"><Icon.Swap size={11} /> Bench</span>
        <div class="pts-bench-row">
          {#each bench as p (p.id)}
            <div class="pts-bench-chip" class:pts-done={p.fixture_status === 'finished'}>
              <span class="pts-bench-pts mono">{p.live_points}</span>
              <span class="pts-bench-name">{p.web_name}</span>
              <span class="pts-bench-team dim2">{p.team_short}</span>
            </div>
          {/each}
        </div>
      </div>
    </section>

    <!-- ═════ FIXTURES ═════ -->
    <section class="pts-fixtures">
      <span class="eyebrow"><Icon.Stopwatch size={11} /> Fixtures</span>
      <div class="pts-fix-grid">
        {#each fixtures as fix}
          {@const yours = fix.squad_players?.length > 0}
          <div class="pts-fix" class:pts-fix-yours={yours} class:pts-fix-live={fix.status === 'in_progress'}>
            <div class="pts-fix-match">
              <span class="pts-fix-team">{fix.home}</span>
              <span class="pts-fix-score mono">{fix.home_score ?? '-'}</span>
              <span class="pts-fix-vs">-</span>
              <span class="pts-fix-score mono">{fix.away_score ?? '-'}</span>
              <span class="pts-fix-team">{fix.away}</span>
            </div>
            <div class="pts-fix-status">
              {#if fix.status === 'in_progress'}
                <span class="pts-fix-min accent mono">{fix.minutes_est}'</span>
              {:else if fix.status === 'finished'}
                <span class="dim2">FT</span>
              {:else}
                <span class="dim2">-</span>
              {/if}
            </div>
            {#if yours}
              <div class="pts-fix-players">
                {#each fix.squad_players as sp}
                  <span class="pts-fix-player" class:pts-fix-cap={sp.captain}>
                    {sp.name} <span class="mono accent">{sp.pts}</span>
                  </span>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    </section>

    <!-- ═════ PREDICTION ACCURACY ═════ -->
    {#if accuracy?.weeks?.length}
      <section class="pts-accuracy">
        <div class="pts-acc-head">
          <span class="eyebrow"><Icon.Trophy size={11} /> Prediction Accuracy</span>
          {#if accuracy.summary}
            <span class="dim2 small">Avg error {accuracy.summary.mean_abs_error}pts over {accuracy.summary.weeks_tracked} GWs</span>
          {/if}
        </div>
        <div class="pts-acc-chart">
          {#each accuracy.weeks as week}
            {@const peak = Math.max(...accuracy.weeks.map((w: any) => Math.max(w.predicted, w.actual)), 1)}
            <div class="pts-acc-col" title="GW{week.event}: EP {week.predicted} → Actual {week.actual}">
              <div class="pts-acc-bars">
                <div class="pts-acc-bar pts-acc-ep" style="height: {(week.predicted / peak) * 100}%"></div>
                <div class="pts-acc-bar pts-acc-act" style="height: {(week.actual / peak) * 100}%"></div>
              </div>
              <span class="pts-acc-lbl dim2">{week.event}</span>
            </div>
          {/each}
        </div>
        <div class="pts-acc-legend">
          <span><span class="pts-acc-sw pts-acc-ep-sw"></span> Predicted EP</span>
          <span><span class="pts-acc-sw pts-acc-act-sw"></span> Actual</span>
        </div>
      </section>
    {/if}
  {/if}
</div>

<style>
  /* ═════ LOADING / EMPTY ═════ */
  .pts-loading { display: flex; align-items: center; gap: 1rem; padding: 4rem 0; justify-content: center; }
  .spinner { width: 22px; height: 22px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .pts-empty { text-align: center; padding: 5rem 0; display: flex; flex-direction: column; align-items: center; gap: 0.75rem; color: var(--text-secondary); }
  .pts-empty h2 { margin: 0; }

  /* ═════ HEADER ═════ */
  .pts-header {
    text-align: center;
    padding-bottom: 1.2rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }
  .pts-gw-label {
    display: flex; align-items: center; justify-content: center; gap: 0.6rem;
    margin-bottom: 0.5rem;
  }
  .pts-live-pill {
    display: inline-flex; align-items: center; gap: 0.25rem;
    padding: 0.2rem 0.5rem;
    background: rgba(255,61,90,0.1); border: 1px solid var(--red);
    border-radius: 999px; color: var(--red);
    font-family: var(--mono); font-size: 0.58rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
  }
  .pts-live-dot {
    width: 5px; height: 5px; background: var(--red); border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(0.7)} }
  .pts-final-pill {
    padding: 0.2rem 0.5rem; background: var(--accent-soft);
    border: 1px solid var(--accent); border-radius: 999px;
    color: var(--accent-text); font-family: var(--mono);
    font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  }
  .pts-total { margin: 0.3rem 0 0.6rem; }
  .pts-total-num {
    font-family: var(--heading); font-size: 4rem; font-weight: 800;
    letter-spacing: -0.04em; color: var(--text-heading); line-height: 1;
  }
  .pts-total-label {
    font-family: var(--mono); font-size: 1rem; color: var(--text-secondary);
    letter-spacing: 0.08em; margin-left: 0.3rem;
  }
  .pts-meta-row {
    display: flex; justify-content: center; gap: 1.5rem; flex-wrap: wrap;
  }
  .pts-meta-cell {
    display: flex; flex-direction: column; align-items: center; gap: 0.1rem;
  }
  .pts-meta-cell .dim2 { font-size: 0.6rem; }
  .pts-meta-cell .mono { font-size: 0.95rem; font-weight: 700; }

  /* ═════ PITCH ═════ */
  .pts-pitch-section { margin-bottom: 1.25rem; }
  .pts-pitch-wrap {
    position: relative;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: visible;
    min-height: 420px;
    background: #081810;
  }
  .pts-pitch-wrap :global(svg.pitch-field) {
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .pts-formation {
    position: relative; z-index: 1;
    display: flex; flex-direction: column;
    justify-content: space-around; gap: 0.4rem;
    padding: 1.2rem 0.5rem;
    min-height: 420px;
  }
  .pts-row {
    display: flex; justify-content: center;
    gap: 0.35rem; flex-wrap: wrap;
  }

  /* Player chip — FPL-style: points on top, name below, team + captain badge */
  .pts-chip {
    width: 72px;
    display: flex; flex-direction: column; align-items: center;
    gap: 1px; cursor: default;
    transition: transform var(--duration) var(--ease);
  }
  .pts-chip:hover { transform: translateY(-2px); }
  .pts-chip-pts {
    width: 100%;
    text-align: center;
    padding: 0.25rem 0;
    font-size: 1.15rem; font-weight: 800;
    color: var(--text-heading);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius) var(--radius) 0 0;
    line-height: 1;
  }
  .pts-playing .pts-chip-pts {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, var(--bg-card));
    color: var(--accent);
  }
  .pts-upcoming .pts-chip-pts {
    color: var(--text-muted); opacity: 0.6;
  }
  .pts-chip-name {
    width: 100%;
    text-align: center;
    padding: 0.18rem 0.15rem;
    font-size: 0.6rem; font-weight: 700;
    color: var(--bg);
    background: var(--accent);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    line-height: 1.2;
  }
  .pts-done .pts-chip-name { background: var(--text-secondary); }
  .pts-upcoming .pts-chip-name { background: var(--text-muted); opacity: 0.6; }
  .pts-chip-info {
    width: 100%;
    display: flex; justify-content: center; align-items: center; gap: 0.2rem;
    padding: 0.12rem 0;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 var(--radius) var(--radius);
    font-size: 0.52rem;
  }
  .pts-chip-team {
    font-family: var(--mono); color: var(--text-muted);
    font-size: 0.5rem; letter-spacing: 0.04em;
  }
  .pts-chip-cap {
    display: inline-flex; align-items: center; justify-content: center;
    width: 12px; height: 12px;
    background: var(--yellow); color: var(--bg);
    border-radius: 50%; font-size: 0.42rem; font-weight: 800;
  }
  .pts-chip-stats {
    display: flex; gap: 0.2rem; margin-top: 0.15rem;
    font-size: 0.5rem; font-family: var(--mono); color: var(--text-secondary);
  }

  /* Bench */
  .pts-bench {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.65rem 0.5rem 0;
    flex-wrap: wrap;
  }
  .pts-bench-row { display: flex; gap: 0.35rem; flex-wrap: wrap; }
  .pts-bench-chip {
    display: flex; align-items: center; gap: 0.35rem;
    padding: 0.32rem 0.55rem;
    background: var(--bg-elevated); border: 1px solid var(--border);
    border-radius: var(--radius); font-size: 0.72rem;
  }
  .pts-bench-chip.pts-done { opacity: 0.7; }
  .pts-bench-pts { font-weight: 800; color: var(--text-heading); }
  .pts-bench-name { font-weight: 600; }
  .pts-bench-team { font-size: 0.58rem; }

  /* ═════ FIXTURES ═════ */
  .pts-fixtures {
    margin-bottom: 1.25rem;
    padding: 0.85rem;
    background: rgba(12, 30, 24, 0.95);
    border: 1px solid rgba(0, 255, 156, 0.12);
    border-radius: var(--radius-lg);
  }
  .pts-fixtures > .eyebrow { margin-bottom: 0.55rem; display: block; }
  .pts-fix-grid { display: flex; flex-direction: column; gap: 0.3rem; }
  .pts-fix {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.5rem 0.7rem;
    background: rgba(15, 37, 30, 0.9); border: 1px solid rgba(148, 179, 166, 0.15);
    border-radius: var(--radius);
    flex-wrap: wrap;
  }
  .pts-fix-yours { border-color: rgba(0, 255, 156, 0.3); }
  .pts-fix-live { border-color: var(--accent); background: rgba(0, 255, 156, 0.06); }
  .pts-fix-match {
    display: flex; align-items: center; gap: 0.3rem;
    font-size: 0.82rem; font-weight: 600; min-width: 10rem;
    color: var(--text);
  }
  .pts-fix-score { font-size: 0.92rem; font-weight: 800; color: var(--text-heading); }
  .pts-fix-vs { color: var(--text-muted); font-size: 0.72rem; }
  .pts-fix-status { min-width: 2rem; text-align: center; font-size: 0.72rem; }
  .pts-fix-min { font-weight: 700; }
  .pts-fix-players {
    display: flex; gap: 0.25rem; flex-wrap: wrap; margin-left: auto;
  }
  .pts-fix-player {
    font-size: 0.68rem; padding: 0.12rem 0.35rem;
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 2px; white-space: nowrap; color: var(--text);
  }
  .pts-fix-cap { border-color: var(--yellow); background: var(--yellow-soft); font-weight: 600; }

  /* ═════ ACCURACY ═════ */
  .pts-accuracy {
    margin-bottom: 1.25rem;
    padding: 0.85rem;
    background: rgba(12, 30, 24, 0.95);
    border: 1px solid rgba(0, 255, 156, 0.12);
    border-radius: var(--radius-lg);
  }
  .pts-acc-head {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.5rem;
  }
  .pts-acc-chart {
    display: flex; gap: 0.25rem; align-items: flex-end;
    height: 100px; padding: 0.5rem 0;
  }
  .pts-acc-col {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; gap: 0.1rem;
  }
  .pts-acc-bars {
    display: flex; gap: 2px; align-items: flex-end;
    height: 80px; width: 100%;
  }
  .pts-acc-bar {
    flex: 1; border-radius: 2px 2px 0 0; min-height: 2px;
  }
  .pts-acc-ep { background: var(--yellow); opacity: 0.65; }
  .pts-acc-act { background: var(--accent); opacity: 0.8; }
  .pts-acc-lbl { font-size: 0.55rem; font-family: var(--mono); }
  .pts-acc-legend {
    display: flex; gap: 1rem; justify-content: center;
    font-size: 0.62rem; color: var(--text-muted);
  }
  .pts-acc-sw {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 2px; margin-right: 0.2rem; vertical-align: middle;
  }
  .pts-acc-ep-sw { background: var(--yellow); opacity: 0.65; }
  .pts-acc-act-sw { background: var(--accent); opacity: 0.8; }

  @media (max-width: 960px) {
    .pts-total-num { font-size: 3rem; }
    .pts-chip { width: 60px; }
    .pts-chip-pts { font-size: 0.95rem; }
    .pts-chip-name { font-size: 0.52rem; }
    .pts-fix-match { min-width: auto; }
  }
  @media (max-width: 480px) {
    .pts-total-num { font-size: 2.4rem; }
    .pts-meta-row { gap: 0.8rem; }
    .pts-meta-cell .mono { font-size: 0.82rem; }
    .pts-chip { width: 52px; }
    .pts-chip-pts { font-size: 0.82rem; padding: 0.2rem 0; }
    .pts-chip-name { font-size: 0.48rem; padding: 0.12rem 0.1rem; }
    .pts-chip-info { font-size: 0.44rem; }
    .pts-chip-cap { width: 10px; height: 10px; font-size: 0.38rem; }
    .pts-chip-stats { font-size: 0.44rem; }
    .pts-formation { padding: 0.8rem 0.25rem; min-height: 340px; }
    .pts-pitch-wrap { min-height: 340px; }
    .pts-bench-chip { font-size: 0.62rem; padding: 0.25rem 0.4rem; }
    .pts-fix { padding: 0.4rem 0.5rem; }
    .pts-fix-match { font-size: 0.72rem; }
    .pts-fix-score { font-size: 0.82rem; }
    .pts-fix-players { margin-left: 0; width: 100%; }
    .pts-fixtures, .pts-accuracy { padding: 0.6rem; }
  }
</style>
