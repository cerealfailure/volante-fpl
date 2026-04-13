<script lang="ts">
  import { getXray, recommendReplacements, getTransferAnalysis } from '$lib/api';
  import { managerId } from '$lib/session';
  import { goto } from '$app/navigation';
  import { browser } from '$app/environment';
  import StatExplainer from '$lib/components/StatExplainer.svelte';

  // Client-only redirect — goto() throws during SSR
  $effect(() => { if (browser && !$managerId) goto('/'); });

  let data: any = $state(null);
  let loading = $state(true);
  let sellIds: Set<number> = $state(new Set());
  let recs: any = $state(null);
  let recsLoading = $state(false);
  let analysis: any = $state(null);
  let analysisLoading = $state(false);
  let tab: 'lab' | 'history' = $state('lab');

  // load squad
  $effect(() => {
    if ($managerId) {
      getXray($managerId).then(d => { data = d; }).catch(() => {}).finally(() => { loading = false; });
    }
  });

  let squad = $derived(data?.players ?? []);
  let starters = $derived(squad.filter((p: any) => p.is_starter));
  let bench = $derived(squad.filter((p: any) => !p.is_starter));

  function toggleSell(id: number) {
    const next = new Set(sellIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    sellIds = next;
    recs = null;
  }

  async function getRecs() {
    if (!$managerId || sellIds.size === 0) return;
    recsLoading = true;
    try {
      recs = await recommendReplacements($managerId, [...sellIds]);
    } catch { recs = null; }
    finally { recsLoading = false; }
  }

  async function loadAnalysis() {
    if (!$managerId) return;
    analysisLoading = true;
    try { analysis = await getTransferAnalysis($managerId); } catch {}
    finally { analysisLoading = false; }
  }

  function verdictClass(v: string) { return v === 'good' ? 'positive' : v === 'bad' ? 'negative' : 'dim2'; }

  const posName: Record<number, string> = {1:'GK',2:'DEF',3:'MID',4:'FWD'};
</script>

<div class="container page-stack reveal">
  <header class="page-hero">
    <div>
      <span class="eyebrow">Transfer Lab</span>
      <h1>Drop the weak spots. Pull the ranks.</h1>
      <p class="dim">Single-screen scanning for replacement candidates and full transfer history review.</p>
    </div>
    <div class="tab-row">
      <button class="tab-btn" class:active={tab === 'lab'} onclick={() => tab = 'lab'}>Find Replacements</button>
      <button class="tab-btn" class:active={tab === 'history'} onclick={() => { tab = 'history'; if (!analysis) loadAnalysis(); }}>Transfer History</button>
    </div>
  </header>

  {#if tab === 'lab'}
    {#if loading}
      <p class="dim">Loading squad...</p>
    {:else if !data}
      <p class="dim">No squad data. Go to Squad tab first.</p>
    {:else}
      <div class="surface-note">Mark players for sale, then pull replacement candidates ranked by EP, fixtures, form and diversification.</div>

      <!-- Squad grid -->
      <div class="squad-grid">
        {#each starters as p}
          <div class="sq-card" class:selling={sellIds.has(p.id)}>
            <button class="sq-sell" onclick={() => toggleSell(p.id)} title={sellIds.has(p.id) ? 'Cancel sell' : 'Mark for sale'}>
              {sellIds.has(p.id) ? '↩' : '×'}
            </button>
            <div class="sq-info">
              <span class="sq-name">{p.web_name}</span>
              <span class="sq-meta">{p.team_short} · {p.position}</span>
            </div>
            <div class="sq-stats">
              <span class="mono">{p.total_points}<span class="dim2 small"> pts</span></span>
              <span class="mono accent">{p.ep_next?.toFixed(1) ?? '—'}<span class="dim2 small"> EP</span></span>
              <span class="mono">{p.form?.toFixed(1)}<span class="dim2 small"> form</span></span>
              <span class="mono dim2">£{p.price?.toFixed(1)}m</span>
            </div>
            {#if sellIds.has(p.id)}
              <div class="sq-selling-tag">SELLING</div>
            {/if}
          </div>
        {/each}
      </div>

      <!-- Bench -->
      <div class="bench-row">
        <span class="dim2 small">BENCH</span>
        {#each bench as p}
          <div class="bench-card" class:selling={sellIds.has(p.id)}>
            <button class="sq-sell small" onclick={() => toggleSell(p.id)}>{sellIds.has(p.id) ? '↩' : '×'}</button>
            <span class="small">{p.web_name}</span>
            <span class="mono dim2 small">£{p.price?.toFixed(1)}m</span>
          </div>
        {/each}
      </div>

      {#if sellIds.size > 0}
        <div class="rec-bar">
          <span class="mono accent">{sellIds.size} player{sellIds.size > 1 ? 's' : ''} selected</span>
          <button class="btn-primary" onclick={getRecs} disabled={recsLoading}>
            {recsLoading ? 'Finding replacements...' : 'Get Recommendations'}
          </button>
        </div>
      {/if}

      <!-- Recommendations -->
      {#if recs?.recommendations}
        {#each recs.recommendations as slot}
          {#if !slot.error}
            <div class="rec-section card fade-in">
              <div class="card-header">
                <h2>Replace {slot.sell_name} <span class="dim2">({slot.position}, £{slot.sell_price.toFixed(1)}m → budget £{slot.budget.toFixed(1)}m)</span></h2>
                <span class="dim2 small">{slot.total_candidates} candidates</span>
              </div>
              <table class="rec-table">
                <thead>
                  <tr>
                    <th>#</th><th>Player</th><th>Team</th><th class="r">Price</th>
                    <th class="r"><StatExplainer term="EP" /></th>
                    <th class="r"><StatExplainer term="Form" /></th>
                    <th class="r"><StatExplainer term="xGI" /></th>
                    <th class="r">Score</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {#each slot.candidates as c, i}
                    <tr>
                      <td class="mono dim2">{i + 1}</td>
                      <td class="player-name">{c.web_name}</td>
                      <td><span class="badge badge-accent">{c.team_short}</span></td>
                      <td class="r mono">£{c.price.toFixed(1)}m</td>
                      <td class="r mono accent">{c.ep_next?.toFixed(1) ?? '—'}</td>
                      <td class="r mono">{c.form?.toFixed(1) ?? '—'}</td>
                      <td class="r mono">{c.xgi?.toFixed(2) ?? '—'}</td>
                      <td class="r mono"><strong>{c.score > 0 ? '+' : ''}{c.score}</strong></td>
                      <td class="breakdown">
                        {#if c.breakdown.ep_delta > 0}<span class="positive small">EP+{c.breakdown.ep_delta.toFixed(1)}</span>{/if}
                        {#if c.breakdown.fixture_run > 0.5}<span class="positive small">Fix+</span>{/if}
                        {#if c.breakdown.fixture_run < -0.5}<span class="negative small">Fix-</span>{/if}
                        {#if c.breakdown.form_trend > 0.5}<span class="positive small">Form↑</span>{/if}
                        {#if c.breakdown.set_pieces > 0}<span class="accent small">SP</span>{/if}
                        {#if c.breakdown.diversification > 0.5}<span class="positive small">Div+</span>{/if}
                        {#if c.breakdown.diversification < -0.3}<span class="negative small">Stack</span>{/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        {/each}
      {/if}
    {/if}

  {:else if tab === 'history'}
    <!-- Transfer History Analysis -->
    {#if analysisLoading}
      <p class="dim">Analyzing transfer history...</p>
    {:else if !analysis}
      <p class="dim">No transfer data yet.</p>
    {:else}
      <!-- Summary stats -->
      <div class="th-summary">
        <div class="card metric-card">
          <span class="stat-value mono {analysis.summary.avg_alpha > 0 ? 'positive' : 'negative'}">{analysis.summary.avg_alpha > 0 ? '+' : ''}{analysis.summary.avg_alpha}</span>
          <span class="stat-label">Avg Alpha / Transfer</span>
        </div>
        <div class="card metric-card">
          <span class="stat-value mono">{analysis.summary.total_transfers}</span>
          <span class="stat-label">Total Transfers</span>
        </div>
        <div class="card metric-card">
          <span class="stat-value mono negative">{analysis.summary.hit_cost}</span>
          <span class="stat-label">Points Lost to Hits</span>
        </div>
        <div class="card metric-card">
          <span class="stat-value mono {analysis.summary.total_alpha > 0 ? 'positive' : 'negative'}">{analysis.summary.total_alpha > 0 ? '+' : ''}{analysis.summary.total_alpha}</span>
          <span class="stat-label">Total Alpha</span>
        </div>
      </div>

      <!-- Habit warnings -->
      {#if analysis.habits?.length}
        <div class="habits fade-in">
          {#each analysis.habits as h}
            <div class="habit-card {h.severity}">
              <strong>{h.type.replace('_', ' ')}</strong>
              <p>{h.detail}</p>
            </div>
          {/each}
        </div>
      {/if}

      <!-- Transfer table -->
      <div class="card" style="margin-top: 1rem;">
        <div class="card-header"><h2>Every Transfer Scored</h2></div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>GW</th><th>Sold</th><th>Bought</th><th class="r">Sold Pts After</th><th class="r">Bought Pts After</th><th class="r">Delta</th><th>Verdict</th></tr>
            </thead>
            <tbody>
              {#each analysis.transfers as t}
                <tr>
                  <td class="mono">{t.event}</td>
                  <td>{t.out_name}</td>
                  <td>{t.in_name}</td>
                  <td class="r mono">{t.out_pts_after}</td>
                  <td class="r mono">{t.in_pts_after}</td>
                  <td class="r mono {verdictClass(t.verdict)}">{t.pts_delta > 0 ? '+' : ''}{t.pts_delta}</td>
                  <td>
                    <span class="badge {t.verdict === 'good' ? 'badge-green' : t.verdict === 'bad' ? 'badge-red' : 'badge-accent'}">
                      {t.verdict}
                    </span>
                    {#if t.is_knee_jerk}<span class="badge badge-yellow small">knee-jerk</span>{/if}
                    {#if t.was_hit}<span class="badge badge-red small">hit</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  /* page-hero inherited from base.css; only tab-row is local */
  .tab-row { display: flex; gap: 0.35rem; flex-wrap: wrap; }
  .tab-btn { font-family: var(--font); font-size: 0.78rem; font-weight: 600; padding: 0.46rem 0.8rem; background: color-mix(in srgb, var(--bg-elevated) 90%, transparent); border: 1px solid var(--border); color: var(--text-secondary); cursor: pointer; border-radius: 999px; transition: all var(--duration); }
  .tab-btn:hover { border-color: var(--accent); color: var(--text); }
  .tab-btn.active { background: color-mix(in srgb, var(--accent) 12%, var(--bg-elevated)); color: var(--accent-text); border-color: var(--border-accent); }

  /* Squad grid */
  .squad-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.5rem; margin-bottom: 0.5rem; }
  .sq-card {
    position: relative; padding: 0.6rem 0.7rem;
    background: color-mix(in srgb, var(--bg-card) 92%, transparent); border: 1px solid var(--border); border-radius: var(--radius-sm);
    transition: all var(--duration) var(--ease);
  }
  .sq-card.selling { border-color: var(--red); background: var(--red-soft); }
  .sq-sell {
    position: absolute; top: 0.3rem; right: 0.3rem;
    background: var(--bg-elevated); border: 1px solid var(--border);
    color: var(--text-muted); width: 1.3rem; height: 1.3rem;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.65rem; cursor: pointer; border-radius: var(--radius-sm);
    transition: all var(--duration);
  }
  .sq-sell:hover { border-color: var(--red); color: var(--red); }
  .sq-card.selling .sq-sell { background: var(--red); color: white; border-color: var(--red); }
  .sq-info { margin-bottom: 0.3rem; }
  .sq-name { font-weight: 600; font-size: 0.85rem; display: block; }
  .sq-meta { font-size: 0.68rem; color: var(--text-muted); }
  .sq-stats { display: flex; gap: 0.5rem; font-size: 0.75rem; flex-wrap: wrap; }
  .sq-selling-tag { position: absolute; bottom: 0; left: 0; right: 0; text-align: center; background: var(--red); color: white; font-size: 0.55rem; font-weight: 700; letter-spacing: 0.1em; padding: 0.1rem; border-radius: 0 0 var(--radius-sm) var(--radius-sm); }

  .bench-row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 1rem; padding: 0.5rem 0; border-top: 1px solid var(--border); }
  .bench-card { display: flex; align-items: center; gap: 0.3rem; padding: 0.25rem 0.5rem; background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-sm); position: relative; }
  .bench-card.selling { border-color: var(--red); background: var(--red-soft); }

  .rec-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.75rem 0; margin-bottom: 0.5rem; flex-wrap: wrap; }

  /* Recommendation table */
  .rec-section { margin-bottom: 0.85rem; }
  .rec-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  .rec-table th { text-align: left; font-size: 0.65rem; text-transform: uppercase; color: var(--text-muted); padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--border); }
  .rec-table td { padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); }
  .rec-table .r { text-align: right; }
  .rec-table tr:hover { background: var(--bg-card-hover); }
  .player-name { font-weight: 500; }
  .breakdown { display: flex; gap: 0.25rem; flex-wrap: wrap; }
  .breakdown span { padding: 0.05rem 0.3rem; border-radius: 3px; font-size: 0.6rem; font-weight: 600; }

  /* Transfer history */
  .th-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.65rem; margin-bottom: 1rem; }
  .metric-card { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 0.8rem; }

  .habits { display: flex; flex-direction: column; gap: 0.5rem; }
  .habit-card { padding: 0.75rem 1rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); border-left: 3px solid; }
  .habit-card.high { border-left-color: var(--red); }
  .habit-card.medium { border-left-color: var(--yellow); }
  .habit-card.info { border-left-color: var(--accent); }
  .habit-card strong { font-size: 0.82rem; text-transform: capitalize; }
  .habit-card p { font-size: 0.78rem; color: var(--text-secondary); margin-top: 0.2rem; }

  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  th { text-align: left; font-size: 0.65rem; text-transform: uppercase; color: var(--text-muted); padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--border); }
  td { padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
  tr:hover { background: var(--bg-card-hover); }
  .r { text-align: right; }

  @media (max-width: 860px) {
    .th-summary { grid-template-columns: repeat(2, 1fr); }
  }
</style>
