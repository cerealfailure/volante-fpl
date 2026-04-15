<!--
  Transfer Planner — multi-drop edition.
  Select any number of players to drop. Volante fetches ranked
  replacements for each slot and lets you earmark picks one slot
  at a time. A combined preview sums EP / StdDev / ENB / HHI
  deltas across all picks, shows the hit cost above your FT
  allowance, and nudges you if a swap actually reduces your
  biggest variance bucket.
-->
<script lang="ts">
  import {
    getXray,
    getManagerTransfers,
    getTransferAnalysis,
    recommendReplacements,
    getSuggestedTransfers,
    simulateTransfer,
    simulateTransferPlan,
    getPlayers,
  } from '$lib/api';
  import { managerId } from '$lib/session';
  import { goto } from '$app/navigation';
  import { browser } from '$app/environment';
  import { gaffer } from '$lib/coach';
  import PitchField from '$lib/components/PitchField.svelte';
  import PlayerChip from '$lib/components/PlayerChip.svelte';
  import RiskCards from '$lib/components/RiskCards.svelte';
  import * as Icon from '$lib/components/icons';

  // Guard: if no session, send home (client-only to dodge SSR goto crash)
  $effect(() => {
    if (browser && !$managerId) goto('/');
  });

  // ── State ────────────────────────────────────────────────
  let xray: any = $state(null);
  let xrayLoading = $state(false);
  let xrayError = $state('');

  // Multi-drop selection — order preserved
  let dropIds: number[] = $state([]);
  // Slot-level recommendations from recommendReplacements(sellIds[])
  let recPayload: any = $state(null);
  let recs: any[] = $state([]);                       // one entry per sell id
  let recsLoading = $state(false);
  let horizon = $state(5);
  const horizonOptions = [3, 5, 8];
  // Which drop slot is currently focused in the right pane
  let activeDropId: number | null = $state(null);
  // Per-slot earmarked candidate {sellId -> candidate}
  let picks: Record<number, any> = $state({});
  // Per-slot single-swap sim {sellId -> sim result}
  let simByPick: Record<number, any> = $state({});
  let simInFlight: Record<number, boolean> = $state({});
  let exactPlanSim: any = $state(null);
  let exactPlanLoading = $state(false);
  let exactPlanRequestKey = $state('');

  // Manual browse mode per slot
  let browseMode = $state(false);
  let browseSearch = $state('');
  let browsePlayers: any[] = $state([]);
  let browseLoading = $state(false);

  // Free transfers from FPL (user can override locally after first sync).
  let freeTransfers = $state(1);
  let freeTransfersTouched = $state(false);
  let refreshing = $state(false);

  // Proactive whole-squad suggestions
  let suggestions: any[] = $state([]);
  let suggestionsLoading = $state(false);
  let suggestionsError = $state('');

  // History
  let history: any[] = $state([]);
  let historyLoading = $state(true);
  let showHistory = $state(false);
  let transferAnalysis: any = $state(null);
  let transferAnalysisLoading = $state(false);

  // ── Load ─────────────────────────────────────────────────
  async function loadXray(refresh = false) {
    if (!$managerId) return;
    if (refresh) refreshing = true; else xrayLoading = true;
    xrayError = '';
    try {
      const d = await getXray($managerId, undefined, refresh);
      xray = d;
      const ft = d?.manager?.free_transfers;
      if (ft != null && !freeTransfersTouched) freeTransfers = ft;
    } catch (e: any) {
      xrayError = e.message;
    } finally {
      xrayLoading = false;
      refreshing = false;
    }
  }

  async function loadSuggestions() {
    if (!$managerId) return;
    suggestionsLoading = true;
    suggestionsError = '';
    try {
      const d = await getSuggestedTransfers($managerId, 5);
      suggestions = d.suggestions ?? [];
    } catch (e: any) {
      suggestionsError = e.message || 'Failed to load suggestions';
      suggestions = [];
    } finally {
      suggestionsLoading = false;
    }
  }

  $effect(() => {
    if (!$managerId) return;
    loadXray(false);
    loadSuggestions();
    getManagerTransfers($managerId, false)
      .then(d => history = d.transfers ?? [])
      .catch(() => {})
      .finally(() => historyLoading = false);
  });
  $effect(() => {
    if (!$managerId || !showHistory || transferAnalysis || transferAnalysisLoading) return;
    transferAnalysisLoading = true;
    getTransferAnalysis($managerId)
      .then((result) => { transferAnalysis = result; })
      .catch(() => {})
      .finally(() => { transferAnalysisLoading = false; });
  });

  // Page-entry gaffer popup — one shot, not reactive
  let greeted = $state(false);
  $effect(() => {
    if (greeted) return;
    greeted = true;
    gaffer.say('SUB BOARD IS OPEN. TAP PLAYERS TO DROP.');
  });

  async function refreshFromFpl() {
    if (refreshing) return;
    await loadXray(true);
    await loadSuggestions();
    gaffer.say('SQUAD REFRESHED FROM FPL.');
  }

  async function applySuggestion(s: any) {
    const sellPlayer = allPlayers.find((p: any) => p.id === s.sell_id);
    if (!sellPlayer) return;
    if (!dropIds.includes(s.sell_id)) {
      dropIds = [...dropIds, s.sell_id];
    }
    activeDropId = s.sell_id;
    browseMode = false;
    await fetchRecs(dropIds);
    await earmark(s.buy);
    if (browser) {
      setTimeout(() => {
        document.querySelector('.plan-summary')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 60);
    }
  }

  // ── Computed ─────────────────────────────────────────────
  let starters = $derived((xray?.players ?? []).filter((p: any) => p.is_starter));
  let bench    = $derived((xray?.players ?? []).filter((p: any) => !p.is_starter));
  let gks  = $derived(starters.filter((p: any) => p.pos_type === 1));
  let defs = $derived(starters.filter((p: any) => p.pos_type === 2));
  let mids = $derived(starters.filter((p: any) => p.pos_type === 3));
  let fwds = $derived(starters.filter((p: any) => p.pos_type === 4));

  let allPlayers = $derived((xray?.players ?? []) as any[]);
  let dropPlayers = $derived(
    dropIds
      .map(id => allPlayers.find((p: any) => p.id === id))
      .filter(Boolean)
  );
  let bank = $derived(xray?.manager?.bank ?? 0);
  // Combined spend budget = bank + sum of prices of everyone we're dropping
  let combinedBudget = $derived(
    bank + dropPlayers.reduce((s: number, p: any) => s + (p?.price ?? 0), 0)
  );
  let enginePlanBudget = $derived(recPayload?.plan_budget ?? combinedBudget);
  let nTransfers = $derived(dropIds.length);
  let nPicks = $derived(dropIds.filter(id => picks[id]).length);
  let hitCost = $derived(Math.max(0, nTransfers - freeTransfers) * 4);
  let transferAlerts = $derived(recPayload?.alerts ?? []);
  let transferPlans = $derived(recPayload?.plans ?? []);
  let planning = $derived(recPayload?.planning ?? null);

  function planSignature(plan: any) {
    return (plan?.slots ?? [])
      .map((slot: any) => `${slot.sell_id}:${slot.candidate?.id}`)
      .sort()
      .join('|');
  }

  function picksSignature() {
    return dropIds
      .filter((id) => picks[id]?.id)
      .map((id) => `${id}:${picks[id].id}`)
      .sort()
      .join('|');
  }

  let activePlan = $derived.by(() => {
    const signature = picksSignature();
    if (!signature || !transferPlans.length) return null;
    return transferPlans.find((plan: any) => planSignature(plan) === signature) ?? null;
  });

  function manualPlanEntries() {
    return dropIds
      .filter((id) => picks[id]?.id)
      .map((id) => ({ sell_id: id, buy_id: picks[id].id }));
  }

  function candidateTakenElsewhere(candidateId: number, slotId: number | null = null) {
    return dropIds.some((id) => id !== slotId && picks[id]?.id === candidateId);
  }

  $effect(() => {
    const mgr = $managerId;
    const allPicked = dropIds.length > 0 && dropIds.every((id) => picks[id]?.id);
    const key = `${mgr ?? 'x'}:${horizon}:${dropIds.join(',')}:${dropIds.map((id) => `${id}:${picks[id]?.id ?? ''}`).join('|')}`;

    if (!mgr || !allPicked || activePlan) {
      exactPlanSim = null;
      exactPlanLoading = false;
      exactPlanRequestKey = '';
      return;
    }

    if (exactPlanRequestKey === key) return;

    exactPlanRequestKey = key;
    exactPlanLoading = true;
    const picksForSim = manualPlanEntries();
    void simulateTransferPlan(mgr, picksForSim, horizon)
      .then((result) => {
        if (exactPlanRequestKey !== key) return;
        exactPlanSim = result;
      })
      .catch(() => {
        if (exactPlanRequestKey !== key) return;
        exactPlanSim = null;
      })
      .finally(() => {
        if (exactPlanRequestKey === key) exactPlanLoading = false;
      });
  });

  // Combined portfolio impact.
  // If the current picks match a suggested full plan, use the exact
  // joint delta from the backend. Otherwise fall back to summed singles.
  let combinedDelta = $derived.by(() => {
    if (activePlan) {
      return {
        exact: true,
        projected: activePlan.projected_ep_gain ?? 0,
        ep: activePlan.delta?.ep_next ?? 0,
        std: activePlan.delta?.portfolio_std ?? 0,
        enb: activePlan.delta?.enb ?? 0,
        hhi: activePlan.delta?.hhi ?? 0,
        netProjected: (activePlan.projected_ep_gain ?? 0) - hitCost,
      };
    }

    if (exactPlanSim?.delta) {
      return {
        exact: true,
        projected: exactPlanSim.projected_ep_gain ?? 0,
        ep: exactPlanSim.delta?.ep_next ?? 0,
        std: exactPlanSim.delta?.portfolio_std ?? 0,
        enb: exactPlanSim.delta?.enb ?? 0,
        hhi: exactPlanSim.delta?.hhi ?? 0,
        netProjected: (exactPlanSim.projected_ep_gain ?? 0) - hitCost,
      };
    }

    let any = false;
    let ep = 0, std = 0, enb = 0, hhi = 0, projected = 0;
    for (const id of dropIds) {
      const pick = picks[id];
      const s = simByPick[id];
      if (pick?.breakdown) {
        any = true;
        projected += pick.breakdown.projected_gain ?? 0;
      }
      if (!s?.delta) continue;
      any = true;
      ep  += s.delta.ep_next ?? 0;
      std += s.delta.portfolio_std ?? 0;
      enb += s.delta.enb ?? 0;
      hhi += s.delta.hhi ?? 0;
    }
    if (!any) return null;
    return { exact: false, projected, ep, std, enb, hhi, netProjected: projected - hitCost };
  });
  let combinedCorrelationChanges = $derived.by(() => {
    if (activePlan?.correlation_changes?.length) {
      return activePlan.correlation_changes.slice(0, 3);
    }
    if (exactPlanSim?.correlation_changes?.length) {
      return exactPlanSim.correlation_changes.slice(0, 3);
    }
    const seen = new Set<string>();
    const rows = [];
    for (const id of dropIds) {
      const sim = simByPick[id];
      if (!sim?.correlation_changes?.length) continue;
      for (const cc of sim.correlation_changes) {
        const key = [cc.player_a, cc.player_b].sort().join('::');
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push(cc);
      }
    }
    rows.sort((a: any, b: any) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0));
    return rows.slice(0, 3);
  });
  let transferAnalysisByKey = $derived.by(() => {
    const rows = transferAnalysis?.transfers ?? [];
    const map = new Map<string, any>();
    for (const row of rows) {
      map.set(historyScoreKey(row), row);
    }
    return map;
  });

  let activeDrop = $derived(
    activeDropId != null
      ? allPlayers.find((p: any) => p.id === activeDropId)
      : null
  );
  let activeRec = $derived(
    activeDropId != null
      ? recs.find((r: any) => r.sell_id === activeDropId)
      : null
  );

  // ── Actions ──────────────────────────────────────────────
  async function fetchRecs(ids: number[]) {
    if (!$managerId || ids.length === 0) {
      recPayload = null;
      recs = [];
      exactPlanSim = null;
      return;
    }
    recsLoading = true;
    try {
      const r = await recommendReplacements($managerId, ids, 8, horizon);
      recPayload = r;
      recs = r.recommendations ?? [];
    } catch (e) {
      recPayload = null;
      recs = [];
    } finally {
      recsLoading = false;
    }
  }

  async function pickDrop(p: any) {
    const idx = dropIds.indexOf(p.id);
    if (idx >= 0) {
      // Un-drop
      const nextDropIds = dropIds.filter(id => id !== p.id);
      dropIds = nextDropIds;
      delete picks[p.id];
      delete simByPick[p.id];
      picks = { ...picks };
      simByPick = { ...simByPick };
      if (activeDropId === p.id) activeDropId = nextDropIds[0] ?? null;
      gaffer.say(`${p.web_name.toUpperCase()} BACK IN THE SQUAD.`);
      await fetchRecs(nextDropIds);
    } else {
      // Add to drop set
      const nextDropIds = [...dropIds, p.id];
      dropIds = nextDropIds;
      activeDropId = p.id;
      browseMode = false;
      gaffer.say(`${p.web_name.toUpperCase()} ON THE SUB BOARD.`);
      await fetchRecs(nextDropIds);
    }
  }

  function focusDrop(id: number) {
    activeDropId = id;
    browseMode = false;
  }

  async function setPlanningHorizon(next: number) {
    if (horizon === next) return;
    horizon = next;
    gaffer.say(`TRANSFER WINDOW SET. NEXT ${next} GAMEWEEKS.`);
    if (dropIds.length) await fetchRecs(dropIds);
  }

  function historyScoreKey(row: any) {
    return `${row?.event ?? '—'}|${row?.out_name ?? ''}|${row?.in_name ?? ''}`;
  }

  function historyAnalysisFor(row: any) {
    return transferAnalysisByKey.get(historyScoreKey(row));
  }

  function alphaPerGwLabel(row: any) {
    const alpha = row?.net_per_gw_alpha ?? row?.per_gw_alpha;
    if (typeof alpha !== 'number' || Number.isNaN(alpha)) return '—';
    return `${alpha >= 0 ? '+' : ''}${alpha.toFixed(2)}`;
  }

  function matrixTradeoffLabel(row: any) {
    const tradeoff = row?.correlation_tradeoff;
    if (!tradeoff?.available) return '—';
    const enb = tradeoff?.delta?.enb;
    const enbText = typeof enb === 'number' ? `${enb >= 0 ? '+' : ''}${enb.toFixed(1)} ENB` : 'flat';
    if (tradeoff.direction === 'improved') return `Up ${enbText}`;
    if (tradeoff.direction === 'worsened') return `Down ${enbText}`;
    return `Flat ${enbText}`;
  }

  async function earmark(candidate: any) {
    if (activeDropId == null) return;
    if (candidateTakenElsewhere(candidate.id, activeDropId)) {
      gaffer.say(`${candidate.web_name.toUpperCase()} IS ALREADY USED IN THIS PLAN.`);
      return;
    }
    picks = { ...picks, [activeDropId]: candidate };
    simInFlight = { ...simInFlight, [activeDropId]: true };
    try {
      const sim = await simulateTransfer($managerId!, activeDropId, candidate.id);
      simByPick = { ...simByPick, [activeDropId]: sim };
      const delta = sim?.delta?.ep_next ?? 0;
      gaffer.say(
        `${candidate.web_name.toUpperCase()} EARMARKED. EP DELTA ${delta >= 0 ? '+' : ''}${delta.toFixed(1)}.`
      );
    } catch {
      simByPick = { ...simByPick, [activeDropId]: null };
    } finally {
      simInFlight = { ...simInFlight, [activeDropId]: false };
    }
    // Auto-advance to the next unpicked slot
    const next = dropIds.find(id => !picks[id] && id !== activeDropId);
    if (next != null) activeDropId = next;
  }

  async function applyPlan(plan: any) {
    const nextPicks = { ...picks };
    for (const slot of plan?.slots ?? []) {
      nextPicks[slot.sell_id] = slot.candidate;
    }
    picks = nextPicks;
    simByPick = {};
    gaffer.say(`PLAN LOADED. ${plan.projected_ep_gain >= 0 ? '+' : ''}${plan.projected_ep_gain?.toFixed(1) ?? '0.0'} PROJECTED.`);
    const next = dropIds.find(id => !nextPicks[id]);
    activeDropId = next ?? dropIds[0] ?? null;
  }

  function clearPlan() {
    dropIds = [];
    recPayload = null;
    picks = {};
    simByPick = {};
    activeDropId = null;
    recs = [];
    gaffer.say('PLAN CLEARED. PICK NEW PLAYERS TO DROP.');
  }

  async function runBrowse() {
    if (!activeDrop) return;
    const posMap: Record<string, number> = { GK: 1, DEF: 2, MID: 3, FWD: 4 };
    browseLoading = true;
    try {
      const r = await getPlayers({
        pos: posMap[activeDrop.position] ?? undefined,
        search: browseSearch || undefined,
        sort: 'ep_next',
        limit: 40,
      });
      const blockedIds = new Set<number>([
        ...allPlayers.map((player: any) => player.id),
        ...dropIds,
        ...dropIds
          .filter((id) => id !== activeDrop.id && picks[id]?.id)
          .map((id) => picks[id].id),
      ]);
      browsePlayers = (r.players ?? []).filter((player: any) => !blockedIds.has(player.id));
    } finally {
      browseLoading = false;
    }
  }

  function toggleBrowse() {
    browseMode = !browseMode;
    if (browseMode) runBrowse();
  }

  function deltaClass(v: number, good: 'pos' | 'neg' = 'pos') {
    if (v == null || v === 0) return 'dim2';
    const isGood = good === 'pos' ? v > 0 : v < 0;
    return isGood ? 'positive' : 'negative';
  }

  function sign(v: number) {
    if (v == null) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(2);
  }

  function scorecardAlpha(group: any) {
    if (group?.avg_alpha == null) return '—';
    return `${group.avg_alpha > 0 ? '+' : ''}${group.avg_alpha.toFixed(1)}`;
  }

  function isDrop(id: number) { return dropIds.includes(id); }

  function planCorrTone(plan: any) {
    const enb = plan?.delta?.enb ?? 0;
    const hhi = plan?.delta?.hhi ?? 0;
    if (enb > 0.2 || hhi < -0.01) return 'positive';
    if (enb < -0.2 || hhi > 0.01) return 'negative';
    return 'dim2';
  }
</script>

<div class="container page-stack reveal">
  <header class="planner-head">
    <div>
      <span class="eyebrow"><Icon.Swap size={12} /> Transfer Planner</span>
      <h1>Drop as many as you need. See the joint ripple.</h1>
      <p class="dim">
        Add players to the sub board, let the engine rank the full move set, and work off transfer alerts before softer matrix tweaks.
      </p>
    </div>
    <div class="planner-tools">
      <div class="bank-card">
        <Icon.Coin size={16} />
        <div>
          <span class="stat-label">Combined budget</span>
          <span class="bank-val mono">£{enginePlanBudget.toFixed(1)}m</span>
          <span class="dim2 small">£{bank.toFixed(1)}m bank + {nTransfers} sell price{nTransfers === 1 ? '' : 's'}</span>
        </div>
      </div>
      <div class="ft-card">
        <Icon.Swap size={14} />
        <div>
          <span class="stat-label">Free transfers</span>
          <span class="bank-val mono">{xray?.manager?.free_transfers ?? '—'}</span>
          <span class="dim2 small">
            {#if xray?.manager?.event_transfers != null}
              {xray.manager.event_transfers} made GW{xray.event}
            {:else}
              from FPL
            {/if}
          </span>
        </div>
      </div>
      <button class="btn-ghost refresh-btn" onclick={refreshFromFpl} disabled={refreshing} title="Pull latest squad and transfer data from FPL">
        <Icon.Stopwatch size={12} />
        {refreshing ? 'Syncing…' : 'Refresh from FPL'}
      </button>
      <div class="horizon-card">
        <span class="stat-label">Planning window</span>
        <div class="horizon-pills">
          {#each horizonOptions as option}
            <button
              class="horizon-pill"
              class:active={horizon === option}
              onclick={() => setPlanningHorizon(option)}
            >
              Next {option}
            </button>
          {/each}
        </div>
        {#if planning}
          <span class="dim2 small">
            Engine leans {planning.recommended_horizon} GWs. GW{planning.window_start_event} to GW{planning.window_end_event}.
          </span>
        {/if}
      </div>
    </div>
  </header>

  {#if xrayLoading}
    <div class="loading-state"><div class="spinner"></div><p class="dim">Loading squad…</p></div>
  {:else if xrayError}
    <p class="error-msg">{xrayError}</p>
  {:else if xray}
    <section class="suggest-card card">
      <div class="suggest-head">
        <div>
          <span class="eyebrow"><Icon.Goal size={12} /> Suggested moves</span>
          <h2>Biggest upgrades available right now</h2>
          <p class="dim small">
            Ranked by expected points, fixture run, form, and diversification impact.
            Load one to drop it straight into the planner.
          </p>
        </div>
        <button class="btn-ghost small" onclick={loadSuggestions} disabled={suggestionsLoading}>
          {suggestionsLoading ? 'Scanning…' : 'Rescan'}
        </button>
      </div>
      {#if suggestionsLoading && !suggestions.length}
        <p class="dim small">Scanning the squad for clean upgrades…</p>
      {:else if suggestionsError}
        <p class="error-msg small">{suggestionsError}</p>
      {:else if suggestions.length === 0}
        <p class="dim small">No clear one-move upgrades found right now.</p>
      {:else}
        <ul class="suggest-list">
          {#each suggestions as s, i}
            <li>
              <button class="suggest-row" onclick={() => applySuggestion(s)} title="Load into planner">
                <span class="suggest-rank mono">#{i + 1}</span>
                <div class="suggest-swap">
                  <div class="sg-side out">
                    <span class="sg-label dim2">Out</span>
                    <span class="sg-name">{s.sell_name}</span>
                    <span class="sg-sub dim2 small">{s.sell_team} · {s.position} · £{s.sell_price.toFixed(1)}m</span>
                  </div>
                  <span class="sg-arrow" aria-hidden="true">→</span>
                  <div class="sg-side in">
                    <span class="sg-label dim2">In</span>
                    <span class="sg-name">{s.buy.web_name}</span>
                    <span class="sg-sub dim2 small">{s.buy.team_short} · £{s.buy.price.toFixed(1)}m · {s.buy.ep_next?.toFixed(1) ?? '—'} EP</span>
                  </div>
                </div>
                <div class="suggest-deltas">
                  <span class="mono {deltaClass(s.ep_delta, 'pos')}">{sign(s.ep_delta)} EP</span>
                  <span class="mono dim2">{s.corr_delta >= 0 ? '+' : ''}{s.corr_delta.toFixed(2)} corr</span>
                  <span class="mono accent">{s.score.toFixed(2)}</span>
                </div>
                {#if s.buy.fixture_strip?.length}
                  <div class="suggest-fixtures">
                    {#each s.buy.fixture_strip.slice(0, 5) as f}
                      <span class="fx fdr-{f.difficulty}">
                        {f.is_home ? '' : '@'}{f.opponent} GW{f.event}
                      </span>
                    {/each}
                  </div>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    {#if dropIds.length > 0 && transferAlerts.length}
      <section class="planner-alerts fade-in">
        <div class="section-head">
          <div>
            <span class="eyebrow"><Icon.Whistle size={12} /> Transfer alerts</span>
            <h2>Move the squad here first</h2>
          </div>
          {#if planning}
            <span class="dim2 small">{planning.recommended_reason}</span>
          {/if}
        </div>
        <RiskCards callouts={transferAlerts} />
      </section>
    {/if}

    <div class="planner-grid">
      <!-- ═════ LEFT: Squad with multi-drop selection ═════ -->
      <div class="card squad-pane">
        <div class="card-header">
          <h2>Your XI</h2>
          <span class="dim2 small">tap any player to add to the sub board</span>
        </div>
        <div class="pitch-wrap">
          <PitchField />
          <div class="formation">
            {#each [fwds, mids, defs, gks] as row, rowIdx}
              <div class="formation-row">
                {#each row as p (p.id)}
                  <PlayerChip
                    player={p}
                    selected={isDrop(p.id)}
                    flipTip={rowIdx === 0}
                    onclick={() => pickDrop(p)}
                  />
                {/each}
              </div>
            {/each}
          </div>
        </div>

        <div class="bench-strip">
          <span class="eyebrow"><Icon.Swap size={12} /> Bench</span>
          <div class="bench-pills">
            {#each bench as p (p.id)}
              <button
                class="bench-pill"
                class:selected={isDrop(p.id)}
                onclick={() => pickDrop(p)}
              >
                <span class="bp-name">{p.web_name}</span>
                <span class="bp-team dim2">{p.team_short}</span>
                <span class="bp-ep mono">{p.ep_next?.toFixed(1) ?? '—'}</span>
              </button>
            {/each}
          </div>
        </div>
      </div>

      <!-- ═════ RIGHT: Multi-drop candidates + combined preview ═════ -->
      <div class="card replace-pane">
        {#if dropIds.length === 0}
          <div class="empty-state">
            <Icon.Boot size={32} />
            <h3>Pick one or more players</h3>
            <p class="dim">
              Tap a kit on the pitch to open a drop slot. Add more than one and the joint plan updates as you earmark each replacement.
            </p>
          </div>
        {:else}
          <!-- Sub-board pill row: one pill per drop, click to focus -->
          <div class="drop-pills">
            {#each dropPlayers as p (p.id)}
              {@const isActive = activeDropId === p.id}
              {@const pick = picks[p.id]}
              <button
                class="drop-pill"
                class:active={isActive}
                class:has-pick={!!pick}
                onclick={() => focusDrop(p.id)}
                title={pick ? `${p.web_name} → ${pick.web_name}` : `Focus ${p.web_name}`}
              >
                <div class="dp-copy">
                  <span class="dp-name">{p.web_name}</span>
                  <span class="dp-sub">
                    {p.team_short} · {p.position} · £{p.price?.toFixed(1)}m
                  </span>
                  {#if pick}
                    <span class="dp-pick mono"><span class="dp-arrow">→</span>{pick.web_name}</span>
                  {/if}
                </div>
                <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions a11y_no_noninteractive_element_interactions -->
                <span
                  class="dp-x"
                  title="Un-drop"
                  role="button"
                  tabindex="0"
                  onclick={(e) => { e.stopPropagation(); pickDrop(p); }}
                >×</span>
              </button>
            {/each}
            <button class="drop-clear" onclick={clearPlan} title="Clear all drops">
              Clear
            </button>
          </div>

          {#if transferPlans.length}
            <section class="plan-ideas">
              <div class="section-head compact">
                <div>
                  <span class="eyebrow"><Icon.Stopwatch size={12} /> Full-plan ideas</span>
                  <h3>Joint moves, scored as one plan</h3>
                </div>
                <span class="dim2 small">Best search range: up to 6 outs</span>
              </div>
              <div class="plan-cards">
                {#each transferPlans as plan, i}
                  <button
                    type="button"
                    class="plan-card"
                    class:active={activePlan && planSignature(activePlan) === planSignature(plan)}
                    onclick={() => applyPlan(plan)}
                  >
                    <div class="plan-card-top">
                      <span class="plan-rank">#{i + 1}</span>
                      <span class="mono {plan.projected_ep_gain >= 0 ? 'positive' : 'negative'}">
                        {sign(plan.projected_ep_gain)}
                      </span>
                    </div>
                    <div class="plan-lines">
                      {#each plan.slots as slot}
                        <span>{slot.sell_name} → {slot.candidate.web_name}</span>
                      {/each}
                    </div>
                    <div class="plan-metrics">
                      <span class="mono">£{plan.spent?.toFixed(1)}m / £{plan.budget?.toFixed(1)}m</span>
                      <span class="mono {planCorrTone(plan)}">ENB {sign(plan.delta?.enb ?? 0)}</span>
                      <span class="mono {deltaClass(plan.delta?.hhi ?? 0, 'neg')}">HHI {sign(plan.delta?.hhi ?? 0)}</span>
                    </div>
                    <p class="dim small">{plan.summary}</p>
                  </button>
                {/each}
              </div>
            </section>
          {/if}

          {#if activeDrop}
            <div class="replace-head">
              <div>
                <span class="eyebrow"><Icon.Card variant="red" size={12} /> Dropping now</span>
                <h2>{activeDrop.web_name}</h2>
                <span class="dim2 small">
                  {activeDrop.team_short} · {activeDrop.position} · £{activeDrop.price?.toFixed(1)}m
                  · Slot budget £{((activeDrop.price ?? 0) + bank).toFixed(1)}m
                </span>
              </div>
              <button class="btn-ghost" onclick={toggleBrowse}>
                <Icon.Goal size={12} />
                {browseMode ? 'Recommended' : 'Browse pool'}
              </button>
            </div>

            {#if browseMode}
              <div class="browse-controls">
                <input
                  type="search"
                  bind:value={browseSearch}
                  onkeydown={(e) => { if (e.key === 'Enter') runBrowse(); }}
                  placeholder="Search {activeDrop.position}s…"
                />
                <button class="btn-ghost small" onclick={runBrowse}>Search</button>
              </div>
              <div class="cand-list scroll">
                {#if browseLoading}
                  <p class="dim small">Loading…</p>
                {:else}
                  {#each browsePlayers as c}
                    {@const taken = candidateTakenElsewhere(c.id, activeDropId)}
                    <button
                      type="button"
                      class="cand-row"
                      class:active={picks[activeDropId!]?.id === c.id}
                      class:blocked={taken}
                      disabled={taken}
                      onclick={() => earmark(c)}
                    >
                      <div class="cand-top">
                        <span class="cand-name">{c.web_name}</span>
                        <span class="badge badge-accent">{c.team_short}</span>
                        {#if taken}
                          <span class="cand-flag">Used elsewhere</span>
                        {/if}
                      </div>
                      <div class="cand-meta">
                        <span class="mono">£{c.price?.toFixed(1)}m</span>
                        <span class="dim2">·</span>
                        <span class="mono">{c.total_points} pts</span>
                        <span class="dim2">·</span>
                        <span class="mono accent">{c.ep_next?.toFixed(1) ?? '—'} EP</span>
                      </div>
                    </button>
                  {/each}
                {/if}
              </div>
            {:else}
              {#if recsLoading}
                <p class="dim small loading">Scoring replacements…</p>
              {:else if !activeRec || activeRec.error || !(activeRec.candidates?.length)}
                <p class="dim small">No affordable replacements found.</p>
              {:else}
                <div class="cand-list scroll">
                  {#each activeRec.candidates as c, i}
                    {@const taken = candidateTakenElsewhere(c.id, activeDropId)}
                    <button
                      type="button"
                      class="cand-row"
                      class:active={picks[activeDropId!]?.id === c.id}
                      class:blocked={taken}
                      disabled={taken}
                      onclick={() => earmark(c)}
                    >
                      <div class="cand-rank">#{i + 1}</div>
                      <div class="cand-body">
                        <div class="cand-top">
                          <span class="cand-name">{c.web_name}</span>
                          <span class="badge badge-accent">{c.team_short}</span>
                          {#if c.requires_plan_budget}
                            <span class="cand-flag">Needs funding</span>
                          {/if}
                          {#if taken}
                            <span class="cand-flag">Used elsewhere</span>
                          {/if}
                          {#if c.score != null}<span class="cand-score mono">{c.score?.toFixed(2)}</span>{/if}
                        </div>
                        <div class="cand-meta">
                          <span class="mono">£{c.price?.toFixed(1)}m</span>
                          <span class="dim2">·</span>
                          <span class="mono">{c.total_points} pts</span>
                          <span class="dim2">·</span>
                          <span class="mono accent">{c.ep_next?.toFixed(1) ?? '—'} EP</span>
                          <span class="dim2">·</span>
                          <span class="mono {c.breakdown?.projected_gain > 0 ? 'positive' : c.breakdown?.projected_gain < 0 ? 'negative' : ''}">
                            {sign(c.breakdown?.projected_gain ?? 0)} proj
                          </span>
                          <span class="dim2">·</span>
                          <span class="mono">{c.form?.toFixed(1)} form</span>
                        </div>
                        {#if c.fixture_strip?.length}
                          <div class="cand-fixtures">
                            {#each c.fixture_strip.slice(0, 5) as f}
                              <span class="fx fdr-{f.difficulty}">
                                {f.is_home ? '' : '@'}{f.opponent} GW{f.event}
                              </span>
                            {/each}
                          </div>
                        {/if}
                      </div>
                    </button>
                  {/each}
                </div>
              {/if}
            {/if}
          {/if}
        {/if}
      </div>
    </div>

    <!-- ═════ COMBINED PLAN SUMMARY ═════ -->
    {#if dropIds.length > 0}
      <section class="plan-summary fade-in">
        <header class="ps-head">
          <div>
            <span class="eyebrow"><Icon.Stopwatch size={12} /> Combined plan</span>
            <h2>
              {nPicks} of {nTransfers} slot{nTransfers === 1 ? '' : 's'} earmarked
            </h2>
            {#if activePlan}
              <span class="dim2 small">Exact joint delta from the loaded suggestion.</span>
            {:else if exactPlanSim}
              <span class="dim2 small">Exact joint delta from your current manual plan.</span>
            {:else if exactPlanLoading}
              <span class="dim2 small">Calculating exact joint delta…</span>
            {/if}
          </div>
          <div class="ps-ft">
            <label class="ps-ft-label">
              Free transfers
              <input
                type="number"
                min="0"
                max="5"
                bind:value={freeTransfers}
                oninput={() => freeTransfersTouched = true}
                class="ps-ft-input mono"
              />
              {#if xray?.manager?.free_transfers != null && !freeTransfersTouched}
                <span class="dim2 small">(FPL: {xray.manager.free_transfers})</span>
              {/if}
            </label>
            <span class="ps-hit {hitCost > 0 ? 'negative' : 'dim2'}">
              Hit cost: {hitCost > 0 ? `-${hitCost}` : '0'} pts
            </span>
          </div>
        </header>

        {#if combinedDelta}
          <div class="ps-body">
            <div class="ps-deltas">
              <div class="ps-cell">
                <span class="stat-label">Projected gain</span>
                <span class="mono {deltaClass(combinedDelta.projected, 'pos')}">
                  {sign(combinedDelta.projected)}
                </span>
              </div>
              <div class="ps-cell">
                <span class="stat-label">ΔNext GW EP</span>
                <span class="mono {deltaClass(combinedDelta.ep, 'pos')}">
                  {sign(combinedDelta.ep)}
                </span>
              </div>
              <div class="ps-cell">
                <span class="stat-label">ΔStd Dev</span>
                <span class="mono {deltaClass(combinedDelta.std, 'neg')}">
                  {sign(combinedDelta.std)}
                </span>
              </div>
              <div class="ps-cell">
                <span class="stat-label">ΔENB</span>
                <span class="mono {deltaClass(combinedDelta.enb, 'pos')}">
                  {sign(combinedDelta.enb)}
                </span>
              </div>
              <div class="ps-cell">
                <span class="stat-label">ΔHHI</span>
                <span class="mono {deltaClass(combinedDelta.hhi, 'neg')}">
                  {sign(combinedDelta.hhi)}
                </span>
              </div>
              <div class="ps-cell ps-net">
                <span class="stat-label">Net projected (after hits)</span>
                <span class="mono {deltaClass(combinedDelta.netProjected, 'pos')}">
                  {sign(combinedDelta.netProjected)}
                </span>
              </div>
            </div>

            {#if combinedCorrelationChanges.length}
              <div class="sim-corrs">
                <span class="eyebrow">Correlation ripple</span>
                {#each combinedCorrelationChanges as cc}
                  <div class="corr-shift">
                    <span>{cc.player_a} ↔ {cc.player_b}</span>
                    <span class="mono {cc.delta > 0 ? 'negative' : 'positive'}">
                      {cc.delta > 0 ? '+' : ''}{cc.delta.toFixed(3)}
                    </span>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <p class="ps-note dim">
            {#if combinedDelta.exact}
              This is the exact joint read for the full move set. Use it to judge the whole plan, not one slot at a time.
            {:else}
              Projected gain is summed from slot-level reads. Load one of the suggested plans above for the exact joint delta.
            {/if}
          </p>
        {:else}
          <p class="dim small">
            Earmark a candidate or load a suggested plan and the combined deltas will appear here.
          </p>
        {/if}
      </section>
    {/if}

    <!-- ═════ HISTORY (collapsed) ═════ -->
    <section class="history card">
      <button class="history-toggle" onclick={() => showHistory = !showHistory}>
        <Icon.Flag size={14} />
        <span>Transfer log</span>
        <span class="dim2 small">({history.length})</span>
        <span class="caret">{showHistory ? '−' : '+'}</span>
      </button>

      {#if showHistory}
        <div class="history-body">
          {#if historyLoading}
            <p class="dim small">Loading…</p>
          {:else if history.length === 0}
            <p class="dim small">No transfers recorded this season.</p>
          {:else}
            {#if transferAnalysisLoading}
              <p class="dim small">Scoring matrix impact…</p>
            {:else if transferAnalysis?.correlation_scorecard}
              <div class="history-scorecard">
                <div class="history-score history-score-wide">
                  <span class="eyebrow"><Icon.Goal size={11} /> Matrix scorecard</span>
                  <strong>{transferAnalysis.correlation_scorecard.headline}</strong>
                  <span class="dim2 small">{transferAnalysis.correlation_scorecard.tracked_transfers} starter-level transfers scored</span>
                </div>
                <div class="history-score">
                  <span class="stat-label">ENB Up</span>
                  <span class="mono positive">{scorecardAlpha(transferAnalysis.correlation_scorecard.improved)}</span>
                  <span class="dim2 small">{transferAnalysis.correlation_scorecard.improved?.win_rate ?? '—'}% hit rate</span>
                </div>
                <div class="history-score">
                  <span class="stat-label">ENB Down</span>
                  <span class="mono negative">{scorecardAlpha(transferAnalysis.correlation_scorecard.worsened)}</span>
                  <span class="dim2 small">{transferAnalysis.correlation_scorecard.worsened?.win_rate ?? '—'}% hit rate</span>
                </div>
              </div>
            {/if}
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>GW</th>
                  <th>Out</th>
                  <th class="r">Sell</th>
                  <th>In</th>
                  <th class="r">Buy</th>
                  <th class="r">Alpha/GW</th>
                  <th>Matrix</th>
                </tr>
              </thead>
              <tbody>
                {#each history as t}
                  {@const scored = historyAnalysisFor(t)}
                  <tr>
                    <td class="dim2 small">{new Date(t.time).toLocaleDateString()}</td>
                    <td class="mono">{t.event ?? '—'}</td>
                    <td>{t.out_name}</td>
                    <td class="r mono">£{t.out_cost?.toFixed(1) ?? '—'}</td>
                    <td>{t.in_name}</td>
                    <td class="r mono">£{t.in_cost?.toFixed(1) ?? '—'}</td>
                    <td class="r mono {scored?.net_per_gw_alpha > 0 ? 'positive' : scored?.net_per_gw_alpha < 0 ? 'negative' : ''}">
                      {alphaPerGwLabel(scored)}
                    </td>
                    <td>
                      {#if scored?.correlation_tradeoff?.available}
                        <span class="matrix-pill matrix-{scored.correlation_tradeoff.direction}">
                          {matrixTradeoffLabel(scored)}
                        </span>
                      {:else}
                        <span class="dim2 small">—</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .planner-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .planner-head h1 {
    font-size: 2.4rem;
    line-height: 0.98;
    margin: 0.3rem 0 0.4rem;
  }
  .planner-head p {
    max-width: 48ch;
    font-size: 0.86rem;
    line-height: 1.5;
  }
  .planner-tools {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 0.75rem;
  }
  .bank-card,
  .ft-card {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.8rem 1rem;
    background: color-mix(in srgb, var(--bg-card) 90%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    min-width: 180px;
    color: var(--accent-text);
  }
  .bank-card > div,
  .ft-card > div {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .refresh-btn {
    align-self: center;
    white-space: nowrap;
  }
  .refresh-btn:disabled {
    opacity: 0.55;
    cursor: wait;
  }
  .bank-val {
    font-family: var(--heading);
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: var(--text-heading);
    line-height: 1;
  }
  .horizon-card {
    min-width: 220px;
    padding: 0.8rem 1rem;
    background: color-mix(in srgb, var(--bg-card) 90%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .horizon-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  .horizon-pill {
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    border-radius: 999px;
    padding: 0.28rem 0.6rem;
    font-family: var(--mono);
    font-size: 0.68rem;
    cursor: pointer;
  }
  .horizon-pill.active {
    color: var(--accent-text);
    border-color: var(--border-accent);
    background: var(--accent-soft);
  }
  .planner-alerts {
    margin-bottom: 0.9rem;
  }
  .suggest-card {
    padding: 1rem 1.1rem;
    margin-bottom: 0.9rem;
  }
  .suggest-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.85rem;
    margin-bottom: 0.75rem;
    flex-wrap: wrap;
  }
  .suggest-head h2 {
    margin: 0.18rem 0 0.25rem;
    line-height: 1.05;
  }
  .suggest-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .suggest-row {
    width: 100%;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-rows: auto auto;
    gap: 0.4rem 0.75rem;
    align-items: center;
    padding: 0.65rem 0.8rem;
    background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    text-align: left;
    transition: all var(--duration) var(--ease);
  }
  .suggest-row:hover {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .suggest-rank {
    grid-row: 1 / span 2;
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--accent-text);
    align-self: center;
  }
  .suggest-swap {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    min-width: 0;
  }
  .sg-side {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }
  .sg-label {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .sg-name {
    font-weight: 700;
    font-size: 0.92rem;
    color: var(--text-heading);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sg-sub {
    white-space: nowrap;
  }
  .sg-arrow {
    color: var(--accent);
    font-size: 1.2rem;
    font-weight: 700;
  }
  .suggest-deltas {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.14rem;
    white-space: nowrap;
  }
  .suggest-fixtures {
    grid-column: 2 / span 2;
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }
  .section-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.7rem;
    flex-wrap: wrap;
  }
  .section-head h2,
  .section-head h3 {
    margin: 0.18rem 0 0;
    line-height: 1.05;
  }
  .section-head.compact {
    margin-bottom: 0.55rem;
  }

  .loading-state { display: flex; align-items: center; gap: 1rem; padding: 3rem 0; justify-content: center; }
  .spinner {
    width: 20px; height: 20px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error-msg { color: var(--red); padding: 1rem; }

  /* ═════ PLANNER GRID ═════ */
  .planner-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
    gap: 0.85rem;
    align-items: start;
    margin-bottom: 1rem;
  }

  .squad-pane {
    padding: 1rem;
    overflow: visible;
  }

  .pitch-wrap {
    position: relative;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: visible;
    min-height: 440px;
    background: #081810;
  }
  .pitch-wrap :global(svg.pitch-field) {
    border-radius: var(--radius);
    overflow: hidden;
  }
  .formation {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-around;
    gap: 0.6rem;
    padding: 1.25rem 0.75rem;
    min-height: 440px;
  }
  .formation-row {
    display: flex;
    justify-content: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .bench-strip {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 0.25rem 0;
    margin-top: 0.75rem;
    border-top: 1px dashed var(--border);
    flex-wrap: wrap;
  }
  .bench-pills { display: flex; flex-wrap: wrap; gap: 0.35rem; flex: 1; }
  .bench-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.6rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    font-size: 0.72rem;
    cursor: pointer;
    border-radius: var(--radius);
  }
  .bench-pill:hover, .bench-pill.selected {
    border-color: var(--accent);
    color: var(--text);
  }
  .bp-name { font-weight: 600; }
  .bp-team { font-family: var(--mono); font-size: 0.6rem; }
  .bp-ep { font-size: 0.7rem; font-weight: 700; color: var(--accent-text); }

  /* ═════ REPLACE PANE ═════ */
  .replace-pane {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-height: 540px;
  }
  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    text-align: center;
    color: var(--text-muted);
    padding: 3rem 1rem;
  }
  .empty-state h3 {
    font-family: var(--heading);
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text-heading);
    letter-spacing: -0.02em;
    text-transform: none;
  }
  .empty-state p { max-width: 30ch; font-size: 0.85rem; line-height: 1.5; }

  .replace-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .replace-head h2 {
    font-size: 1.4rem;
    letter-spacing: -0.02em;
    margin: 0.2rem 0 0.15rem;
  }
  .plan-ideas {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px dashed var(--border);
  }
  .plan-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.5rem;
  }
  .plan-card {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
    text-align: left;
    padding: 0.75rem 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
    cursor: pointer;
  }
  .plan-card:hover,
  .plan-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .plan-card-top {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: center;
  }
  .plan-rank {
    font-family: var(--heading);
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--accent-text);
  }
  .plan-lines {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    color: var(--text-heading);
    font-size: 0.82rem;
    font-weight: 600;
  }
  .plan-metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    font-size: 0.68rem;
  }

  .browse-controls {
    display: flex;
    gap: 0.5rem;
  }
  .browse-controls input { flex: 1; }

  .cand-list {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .cand-list.scroll {
    max-height: 420px;
    overflow-y: auto;
    padding-right: 0.25rem;
  }

  .cand-row {
    display: flex;
    gap: 0.75rem;
    width: 100%;
    padding: 0.58rem 0.72rem;
    background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    text-align: left;
    transition: all var(--duration) var(--ease);
  }
  .cand-row:hover,
  .cand-row.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .cand-row:disabled,
  .cand-row.blocked {
    cursor: not-allowed;
    opacity: 0.62;
  }
  .cand-row:disabled:hover,
  .cand-row.blocked:hover {
    border-color: var(--border);
    background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
  }
  .cand-rank {
    font-family: var(--heading);
    font-size: 1.3rem;
    font-weight: 800;
    color: var(--accent-text);
    letter-spacing: -0.02em;
    line-height: 1;
    min-width: 1.6rem;
    flex-shrink: 0;
  }
  .cand-body { flex: 1; min-width: 0; }
  .cand-top {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 0.25rem;
  }
  .cand-name {
    font-weight: 700;
    font-size: 0.92rem;
    color: var(--text-heading);
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .cand-score {
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--accent-text);
    background: var(--bg);
    padding: 0.1rem 0.4rem;
    border-radius: 100px;
    border: 1px solid var(--border-accent);
  }
  .cand-flag {
    display: inline-flex;
    align-items: center;
    padding: 0.12rem 0.42rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--yellow) 15%, transparent);
    border: 1px solid color-mix(in srgb, var(--yellow) 30%, var(--border));
    color: var(--yellow);
    font-size: 0.58rem;
    font-family: var(--mono);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .cand-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    font-size: 0.72rem;
    color: var(--text-secondary);
  }
  .cand-fixtures {
    display: flex;
    gap: 0.25rem;
    margin-top: 0.3rem;
  }
  .fx {
    font-family: var(--mono);
    font-size: 0.58rem;
    padding: 0.12rem 0.35rem;
    border-radius: var(--radius-sm);
  }
  .fdr-1 { background: rgba(0,255,156,0.15); color: var(--fdr-1); }
  .fdr-2 { background: rgba(106,255,157,0.12); color: var(--fdr-2); }
  .fdr-3 { background: rgba(148,179,166,0.12); color: var(--text-secondary); }
  .fdr-4 { background: rgba(255,209,102,0.16); color: var(--fdr-4); }
  .fdr-5 { background: rgba(255,61,90,0.16); color: var(--fdr-5); }

  /* ═════ DROP PILLS (sub board) ═════ */
  .drop-pills {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.4rem;
    margin-bottom: 0.85rem;
    padding-bottom: 0.85rem;
    border-bottom: 1px dashed var(--border);
  }
  .drop-pill {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.45rem;
    padding: 0.5rem 0.65rem;
    background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.75rem;
    position: relative;
    text-align: left;
  }
  .drop-pill:hover {
    border-color: var(--accent);
    color: var(--text);
  }
  .drop-pill.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent-text);
    box-shadow: 0 0 0 2px var(--accent-soft);
  }
  .drop-pill.has-pick { align-items: start; }
  .dp-copy {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }
  .dp-name { font-weight: 700; color: var(--text-heading); }
  .dp-sub { font-size: 0.62rem; color: var(--text-muted); font-family: var(--mono); }
  .dp-arrow { color: var(--accent); font-weight: 700; margin-right: 0.22rem; }
  .dp-pick { color: var(--accent-text); font-size: 0.68rem; font-weight: 600; }
  .dp-x {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1rem;
    height: 1rem;
    border-radius: 50%;
    background: transparent;
    color: var(--text-muted);
    font-size: 0.85rem;
    line-height: 1;
    cursor: pointer;
    margin-left: 0.2rem;
  }
  .dp-x:hover {
    background: var(--red);
    color: #fff;
  }
  .drop-clear {
    align-self: stretch;
    background: transparent;
    border: 1px dashed var(--border);
    color: var(--text-muted);
    font-size: 0.68rem;
    padding: 0.4rem 0.7rem;
    border-radius: var(--radius);
    cursor: pointer;
  }
  .drop-clear:hover { border-color: var(--red); color: var(--red); border-style: solid; }

  /* ═════ COMBINED PLAN SUMMARY ═════ */
  .plan-summary {
    margin-top: 0.5rem;
    padding: 0.95rem 1rem;
    background: linear-gradient(180deg, color-mix(in srgb, var(--bg-card) 94%, transparent) 0%, color-mix(in srgb, var(--bg-warm) 92%, transparent) 100%);
    border: 1px solid var(--border-accent);
    border-radius: var(--radius-lg);
  }
  .ps-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.85rem;
    flex-wrap: wrap;
  }
  .ps-head h2 {
    font-size: 1.3rem;
    line-height: 1.05;
    margin: 0.25rem 0 0;
  }
  .ps-ft { display: flex; align-items: center; gap: 0.75rem; }
  .ps-ft-label {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-family: var(--mono);
    font-size: 0.6rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .ps-ft-input {
    width: 3rem;
    font-size: 0.9rem;
    text-align: center;
    padding: 0.3rem;
  }
  .ps-hit {
    font-family: var(--mono);
    font-size: 0.78rem;
    font-weight: 700;
  }

  .ps-deltas {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 0.55rem;
  }
  .ps-body {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(16rem, 18rem);
    gap: 0.8rem;
    align-items: start;
  }
  .ps-cell {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.25rem;
    padding: 0.75rem 0.85rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .ps-cell .mono {
    font-family: var(--heading);
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: -0.025em;
    line-height: 1;
  }
  .ps-cell.ps-net {
    background: var(--accent-soft);
    border-color: var(--border-accent);
  }
  .sim-corrs {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
    padding: 0.8rem 0.9rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .corr-shift {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    align-items: center;
    font-size: 0.82rem;
    color: var(--text-secondary);
  }
  .corr-shift .mono {
    font-size: 0.88rem;
    font-weight: 700;
    color: var(--text-heading);
  }
  .ps-note {
    margin: 0.65rem 0 0;
    padding-top: 0.55rem;
    border-top: 1px dashed var(--border);
    font-size: 0.74rem;
    line-height: 1.45;
  }

  /* ═════ HISTORY ═════ */
  .history { padding: 0.2rem 0.8rem; }
  .history-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 0.85rem 0.25rem;
    font-family: var(--heading);
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    cursor: pointer;
    justify-content: flex-start;
  }
  .history-toggle:hover { color: var(--text); }
  .history-toggle .caret {
    margin-left: auto;
    font-family: var(--mono);
    font-size: 1.2rem;
    color: var(--accent-text);
  }
  .history-body {
    padding: 0 0.25rem 0.85rem;
    max-height: 360px;
    overflow-y: auto;
  }
  .history-scorecard {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) repeat(2, minmax(0, 1fr));
    gap: 0.55rem;
    margin-bottom: 0.85rem;
  }
  .history-score {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    padding: 0.8rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--bg-elevated) 90%, transparent);
  }
  .history-score strong {
    font-size: 0.9rem;
    line-height: 1.35;
    color: var(--text-heading);
  }
  .history-body table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  .history-body th {
    text-align: left;
    font-family: var(--mono);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--border);
  }
  .history-body td { padding: 0.45rem 0.6rem; border-bottom: 1px dashed var(--border); white-space: nowrap; }
  .history-body tr:hover td { background: var(--bg-card-hover); }
  .history-body .r { text-align: right; }
  .matrix-pill {
    display: inline-flex;
    align-items: center;
    padding: 0.18rem 0.45rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    font-size: 0.68rem;
    font-family: var(--mono);
    letter-spacing: 0.01em;
  }
  .matrix-pill.matrix-improved {
    color: var(--accent-text);
    border-color: var(--border-accent);
    background: var(--accent-soft);
  }
  .matrix-pill.matrix-worsened {
    color: var(--red);
    border-color: color-mix(in srgb, var(--red) 40%, var(--border));
    background: color-mix(in srgb, var(--red) 12%, transparent);
  }
  .matrix-pill.matrix-flat {
    color: var(--text-secondary);
  }

  @media (max-width: 980px) {
    .planner-grid { grid-template-columns: 1fr; }
    .planner-head h1 { font-size: 1.8rem; }
    .planner-tools { width: 100%; }
    .bank-card, .ft-card, .horizon-card { width: 100%; }
    .ps-body { grid-template-columns: 1fr; }
    .ps-deltas { grid-template-columns: repeat(2, 1fr); }
    .history-scorecard { grid-template-columns: 1fr; }
  }
</style>
