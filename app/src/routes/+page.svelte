<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getAttribution,
    getFixtureExposure,
    getFplStatus,
    getPlayerDetail,
    getXray,
    getXrayForecast,
    getXrayWithLookback,
    type FplSessionStatus,
  } from '$lib/api';
  import { managerId, recentManagers, rememberManager, forgetManager } from '$lib/session';
  import { gaffer } from '$lib/coach';
  import CorrelationDeepDive from '$lib/components/CorrelationDeepDive.svelte';
  import CorrelationMatrix from '$lib/components/CorrelationMatrix.svelte';
  import ExposureChart from '$lib/components/ExposureChart.svelte';
  import FixtureStrip from '$lib/components/FixtureStrip.svelte';
  import RiskCards from '$lib/components/RiskCards.svelte';
  import StatExplainer from '$lib/components/StatExplainer.svelte';
  import PitchField from '$lib/components/PitchField.svelte';
  import PlayerChip from '$lib/components/PlayerChip.svelte';
  import HelpDrawer from '$lib/components/HelpDrawer.svelte';
  import PositionSizing from '$lib/components/PositionSizing.svelte';
  import RiskAttribution from '$lib/components/RiskAttribution.svelte';
  import ScenarioCards from '$lib/components/ScenarioCards.svelte';
  import TransferRunway from '$lib/components/TransferRunway.svelte';
  import * as Icon from '$lib/components/icons';

  let idInput = $state('');
  let loading = $state(false);
  let error = $state('');
  let data: any = $state(null);
  let selectedPlayer: any = $state(null);
  let playerDetail: any = $state(null);
  let loadingPlayer = $state(false);

  // Help/info drawer (team-as-portfolio explainer)
  let showHelp = $state(false);

  // Deep-link: /?help=1 opens the primer drawer on load
  import { browser } from '$app/environment';
  $effect(() => {
    if (browser && window.location.search.includes('help=1')) {
      showHelp = true;
    }
  });

  // fixture exposure
  let exposure: any = $state(null);
  let expLoading = $state(false);
  let fplStatus = $state<FplSessionStatus | null>(null);
  let fplStatusLoading = $state(true);
  let authBootstrapping = $state(true);
  let livePromptedManagerId = $state<number | null>(null);
  let showPublicFallback = $state(false);

  // section tabs for analysis area
  let analysisTab: 'week' | 'portfolio' | 'issues' | 'deep' = $state('portfolio');
  let deepXray: any = $state(null);
  let portfolioXray: any = $state(null);
  let portfolioLoading = $state(false);
  let portfolioError = $state('');
  let portfolioFutureWeeks: number | null = $state(5);
  let portfolioLoadedKey: string | null = $state(null);
  let portfolioRequestKey = $state('');
  let attribution: any = $state(null);
  let attributionLoading = $state(false);
  let attributionError = $state('');
  let deepLookback: number | null = $state(10);
  let deepLoadedKey: string | null = $state(null);
  let deepRequestKey = $state('');
  let selectedPair: { playerA: string; playerB: string } | null = $state(null);
  let activeManagerScopeId: number | null = $state(null);
  let urlStateApplied = $state(false);

  // collapsible issues
  let showIssues = $state(false);

  onMount(() => {
    void bootstrapAuth();
  });

  async function refreshFplStatus() {
    fplStatusLoading = true;
    try {
      fplStatus = await getFplStatus();
    } catch {
      fplStatus = null;
    } finally {
      fplStatusLoading = false;
    }
  }

  async function bootstrapAuth() {
    authBootstrapping = true;
    await refreshFplStatus();
    const connectedId = fplStatus?.connected ? fplStatus.account_id : null;
    if (connectedId) {
      await loadManager(connectedId);
    } else {
      managerId.set(null);
      data = null;
      exposure = null;
      error = '';
    }
    authBootstrapping = false;
  }

  async function loadFixtureExposure(managerIdOverride?: number) {
    const activeId = managerIdOverride ?? $managerId;
    if (!activeId) return;
    expLoading = true;
    try { exposure = await getFixtureExposure(activeId); } catch {}
    finally { expLoading = false; }
  }

  function rememberLoadedManager(id: number, snapshot: any) {
    rememberManager({
      id,
      team_name: snapshot?.manager?.name ?? 'My Team',
      player_name: snapshot?.manager?.player_name ?? '',
      last_used: new Date().toISOString(),
    });
  }

  async function loadManager(id: number) {
    if (!id || id < 1) {
      error = 'Enter a valid FPL manager ID';
      return;
    }
    loading = true;
    error = '';
    data = null;
    exposure = null;
    selectedPlayer = null;
    playerDetail = null;
    try {
      const snapshot = await getXray(id);
      data = snapshot;
      managerId.set(id);
      rememberLoadedManager(id, snapshot);
      await loadFixtureExposure(id);
    } catch (e: any) {
      error = e.message || 'Failed to sign in';
      data = null;
      exposure = null;
      managerId.set(null);
    } finally { loading = false; }
  }

  async function login(idOverride?: number) {
    const id = idOverride ?? parseInt(idInput);
    await loadManager(id);
  }

  function loginConnectedManager() {
    if (fplStatus?.account_id) login(fplStatus.account_id);
  }

  let liveSessionState = $derived.by(() => {
    const activeManagerId = data?.manager?.id ?? $managerId;
    if (!fplStatus?.connected) return 'missing';
    if (activeManagerId && fplStatus.account_id && fplStatus.account_id !== activeManagerId) return 'mismatch';
    return 'connected';
  });

  $effect(() => {
    const activeManagerId = data?.manager?.id ?? $managerId;
    if (!activeManagerId || fplStatusLoading || livePromptedManagerId === activeManagerId) return;
    livePromptedManagerId = activeManagerId;
    if (!fplStatus?.connected) {
      gaffer.say('LIVE FPL OFF. OPEN SETTINGS AND PASTE pl_profile + sessionid FOR LIVE BANK AND FT.');
      return;
    }
    if (fplStatus.account_id && fplStatus.account_id !== activeManagerId) {
      gaffer.say(`LIVE COOKIE BELONGS TO #${fplStatus.account_id}. RE-PASTE IT OR SWITCH MANAGERS.`);
    }
  });

  async function selectPlayer(p: any) {
    if (selectedPlayer?.id === p.id) { selectedPlayer = null; playerDetail = null; return; }
    selectedPlayer = p; loadingPlayer = true;
    gaffer.say(
      `${p.web_name.toUpperCase()} · ${p.team_short} ${p.position} · ${displayEp(p)?.toFixed(1) ?? '—'} XP · ${p.form?.toFixed(1) ?? '—'} FORM.`
    );
    try {
      playerDetail = await getPlayerDetail($managerId!, p.id);
    } catch { playerDetail = null; }
    finally { loadingPlayer = false; }
  }

  function handleKey(e: KeyboardEvent) { if (e.key === 'Enter') login(); }

  let starters: any[] = $derived(data?.players?.filter((p: any) => p.is_starter) ?? []);
  let bench: any[] = $derived(data?.players?.filter((p: any) => !p.is_starter) ?? []);
  let starterNames: string[] = $derived(starters.map((p: any) => p.web_name));
  let gks  = $derived(starters.filter((p: any) => p.pos_type === 1));
  let defs = $derived(starters.filter((p: any) => p.pos_type === 2));
  let mids = $derived(starters.filter((p: any) => p.pos_type === 3));
  let fwds = $derived(starters.filter((p: any) => p.pos_type === 4));
  const displayEp = (player: any) => player?.projected_ep_next ?? player?.projected_ep_window ?? player?.ep_next ?? player?.form ?? 2;
  let projectionEvent = $derived(data?.projection_event ?? data?.meta?.projection_event ?? data?.event);

  // formation string, e.g. "3-4-3"
  let formation = $derived(`${defs.length}-${mids.length}-${fwds.length}`);
  let analysisData = $derived.by(() => {
    if (analysisTab === 'portfolio') return portfolioXray ?? data;
    if (analysisTab === 'deep') return deepXray ?? data;
    return data;
  });
  const portfolioWindowOptions = [
    { label: 'History', value: null },
    { label: 'Next 1', value: 1 },
    { label: 'Next 3', value: 3 },
    { label: 'Next 5', value: 5 },
    { label: 'Next 8', value: 8 },
  ] as const;

  // ── Expected points calculations ──
  let squadEP = $derived.by(() => {
    if (!starters.length) return 0;
    return starters.reduce((sum: number, p: any) => {
      const ep = displayEp(p);
      return sum + ep * (p.is_captain ? 2 : 1);
    }, 0);
  });
  let squadAvgEP = $derived(starters.length ? squadEP / 11 : 0);
  let benchWaste = $derived.by(() => {
    if (!starters.length || !bench.length) return [];
    const worst = starters.reduce((w: any, p: any) =>
      (displayEp(p) < displayEp(w)) ? p : w, starters[0]);
    const wEP = displayEp(worst);
    return bench.filter((b: any) => displayEp(b) > wEP + 0.3)
      .map((b: any) => ({ bench: b, benchEP: displayEp(b), starter: worst, starterEP: wEP, diff: displayEp(b) - wEP }));
  });
  let flaggedStarters = $derived(starters.filter((p: any) => p.status && p.status !== 'a'));
  let squadTrend = $derived.by(() => {
    const weeks = [...(attribution?.weeks ?? [])].slice(0, 5).reverse();
    if (!weeks.length) return [];
    const peak = Math.max(squadEP, ...weeks.map((week: any) => week.total_points), 1);
    return weeks.map((week: any) => ({
      event: week.event,
      actual: week.total_points,
      actualPct: week.total_points / peak * 100,
      expectedPct: squadEP / peak * 100,
    }));
  });

  // ── Gaffer: single quiet greeting, no bombardment ──
  let greetedForId: number | null = $state(null);
  $effect(() => {
    if (!data) return;
    const id = data.manager?.id ?? $managerId;
    if (greetedForId === id) return;
    greetedForId = id;
    gaffer.say(`GW${projectionEvent} PROJECTIONS LOADED.`);
  });

  function lookbackKey(value: number | null) {
    return value == null ? 'season' : String(value);
  }

  function portfolioKey(value: number | null) {
    return value == null ? 'history' : `future:${value}`;
  }

  function lookbackQuery(value: number | null) {
    return value == null ? undefined : value;
  }

  function portfolioCoachLine(value: number | null) {
    return value == null
      ? 'CORRELATION MATRIX RESET TO HISTORY.'
      : `CORRELATION FORECAST LOADED. NEXT ${value} WEEKS.`;
  }

  function lookbackCoachLine(value: number | null) {
    return value == null
      ? 'CORRELATION ATTRIBUTION LOADED. FULL SEASON.'
      : `CORRELATION ATTRIBUTION LOADED. LAST ${value} WEEKS.`;
  }

  async function loadPortfolioWindow(futureWeeks = portfolioFutureWeeks, announce = false) {
    if (!$managerId) return;
    const key = `${$managerId}:${portfolioKey(futureWeeks)}`;
    if (portfolioLoadedKey === key && portfolioXray) {
      if (announce) gaffer.say(portfolioCoachLine(futureWeeks));
      return;
    }

    portfolioRequestKey = key;
    portfolioLoading = true;
    portfolioError = '';
    try {
      const nextXray = futureWeeks == null
        ? await getXray($managerId)
        : await getXrayForecast($managerId, futureWeeks);
      if (portfolioRequestKey !== key) return;
      portfolioXray = nextXray;
      portfolioLoadedKey = key;
      if (announce) gaffer.say(portfolioCoachLine(futureWeeks));
    } catch (e: any) {
      if (portfolioRequestKey !== key) return;
      portfolioError = e.message || 'Failed to load forecast';
    } finally {
      if (portfolioRequestKey === key) {
        portfolioLoading = false;
      }
    }
  }

  async function loadDeepDive(lookback = deepLookback, announce = false) {
    if (!$managerId) return;
    const key = `${$managerId}:${lookbackKey(lookback)}`;
    if (deepLoadedKey === key && attribution && deepXray) {
      if (announce) gaffer.say(lookbackCoachLine(lookback));
      return;
    }

    deepRequestKey = key;
    attributionLoading = true;
    attributionError = '';
    try {
      const [nextAttribution, nextXray] = await Promise.all([
        getAttribution($managerId, lookbackQuery(lookback)),
        getXrayWithLookback($managerId, lookbackQuery(lookback)),
      ]);
      if (deepRequestKey !== key) return;
      attribution = nextAttribution;
      deepXray = nextXray;
      deepLoadedKey = key;
      if (announce) gaffer.say(lookbackCoachLine(lookback));
    } catch (e: any) {
      if (deepRequestKey !== key) return;
      attributionError = e.message || 'Failed to load correlation attribution';
    } finally {
      if (deepRequestKey === key) {
        attributionLoading = false;
      }
    }
  }

  function setAnalysisTab(next: 'week' | 'portfolio' | 'issues' | 'deep') {
    analysisTab = next;
    if (next === 'portfolio') {
      loadPortfolioWindow();
    } else if (next === 'deep') {
      loadDeepDive();
    }
  }

  async function changePortfolioWindow(next: number | null) {
    if (portfolioFutureWeeks === next) return;
    portfolioFutureWeeks = next;
    selectedPair = null;
    await loadPortfolioWindow(next, true);
  }

  async function changeLookback(next: number | null) {
    if (deepLookback === next) return;
    deepLookback = next;
    selectedPair = null;
    await loadDeepDive(next, true);
  }

  function handlePairSelect(pair: { playerA: string; playerB: string }) {
    selectedPair = pair;
  }

  $effect(() => {
    if (!browser || urlStateApplied) return;
    urlStateApplied = true;
    const params = new URLSearchParams(window.location.search);
    if (params.get('help') === '1') {
      showHelp = true;
    }
    if (params.get('tab') === 'portfolio') {
      const requestedFuture = parseInt(params.get('future') || '', 10);
      if (Number.isFinite(requestedFuture) && requestedFuture > 0) {
        portfolioFutureWeeks = requestedFuture;
      }
      analysisTab = 'portfolio';
    } else if (params.get('tab') === 'deep') {
      const requestedLookback = parseInt(params.get('lookback') || '', 10);
      if (Number.isFinite(requestedLookback) && requestedLookback > 0) {
        deepLookback = requestedLookback;
      }
      analysisTab = 'deep';
    }
  });

  $effect(() => {
    if (analysisTab !== 'deep' || !data || attributionLoading) return;
    loadDeepDive();
  });

  $effect(() => {
    if (analysisTab !== 'portfolio' || !data || portfolioLoading) return;
    loadPortfolioWindow();
  });

  $effect(() => {
    const activeManagerId = data?.manager?.id ?? $managerId;
    if (!activeManagerId || activeManagerScopeId === activeManagerId) return;
    activeManagerScopeId = activeManagerId;
    deepXray = null;
    portfolioXray = null;
    portfolioLoading = false;
    portfolioError = '';
    portfolioFutureWeeks = 5;
    portfolioLoadedKey = null;
    portfolioRequestKey = '';
    attribution = null;
    attributionError = '';
    attributionLoading = false;
    deepLookback = 10;
    deepLoadedKey = null;
    deepRequestKey = '';
    selectedPair = null;
  });
</script>

<div class="container page-stack" class:reveal={!!data}>
  {#if authBootstrapping && !data}
    <div class="loading-state">
      <div class="spinner"></div>
      <p class="dim">Checking live FPL session…</p>
    </div>
  {:else if !$managerId && !data}
    <section class="signin reveal">
      <div class="signin-crest" style="--i:0">
        <img src="/logo.svg" alt="Volante" class="crest clean-only" width="80" height="80" />
        <img src="/logo-pixel.svg" alt="Volante" class="crest pixel-only" width="80" height="80" />
      </div>

      <span class="eyebrow" style="--i:1"><Icon.Ball size={12} /> FPL · PORTFOLIO · DESK</span>
      <h1 class="display" style="--i:2">
        {#if fplStatus?.connected && fplStatus.account_id}
          Your live desk is ready.<br/>Open the connected squad.
        {:else}
          Connect your live FPL session.<br/>Then let Volante pull the squad.
        {/if}
      </h1>
      <span class="signin-rule" aria-hidden="true" style="--i:3"></span>
      <p class="signin-sub" style="--i:4">
        {#if fplStatus?.connected && fplStatus.account_id}
          Volante found a saved FPL session for manager <span class="mono">#{fplStatus.account_id}</span>.
          Open that account to keep bank, free transfers and live pre-deadline state in sync.
        {:else}
          Cookie-first is the clean path here. Paste <span class="mono">pl_profile</span> and <span class="mono">sessionid</span> once,
          and the app will use your real FPL account instead of making you hunt for manager IDs.
        {/if}
      </p>

      <section class="live-cookie-card" style="--i:5">
        <div class="live-cookie-head">
          <div>
            <span class="label-text">Live FPL Session</span>
            <h2>
              {#if fplStatus?.connected}
                Cookie connected. Use it as the primary sign-in.
              {:else}
                Use the cookie system for live bank, FT and staged-chip state.
              {/if}
            </h2>
          </div>
          {#if fplStatusLoading}
            <span class="live-chip">checking…</span>
          {:else if fplStatus?.connected}
            <span class="live-chip connected">connected</span>
          {:else}
            <span class="live-chip">not connected</span>
          {/if}
        </div>

        <p class="live-cookie-copy">
          Manager ID gets you the public squad view. The live cookie path upgrades that with in-progress transfer count,
          live bank and current pre-deadline squad state.
        </p>

        {#if fplStatus?.connected && fplStatus.account_id}
          <p class="live-cookie-note">
            Connected as manager <span class="mono">#{fplStatus.account_id}</span>. Use that manager for live reads.
          </p>
        {:else}
          <ol class="live-cookie-steps">
            <li>Log in at <code>fantasy.premierleague.com</code> in Chrome.</li>
            <li>Open Chrome DevTools on the official FPL site, not inside Volante: <b>Application</b> → <b>Cookies</b> → <b>https://fantasy.premierleague.com</b>.</li>
            <li>Copy <code>pl_profile</code> and <code>sessionid</code>, then open <a href="/settings">Settings</a> and paste <code>pl_profile=&lt;value&gt;; sessionid=&lt;value&gt;</code>.</li>
          </ol>
        {/if}

        <div class="live-cookie-actions">
          {#if fplStatus?.connected && fplStatus.account_id}
            <button class="btn-primary cookie-open-live" onclick={loginConnectedManager} disabled={loading}>
              <Icon.Jersey size={12} />
              Open my live team
            </button>
          {/if}
          <a class="cookie-settings-link" href="/settings">
            <Icon.Whistle size={12} />
            {fplStatus?.connected ? 'Review live session' : 'Open live session setup'}
          </a>
        </div>
      </section>

      <div class="public-fallback" style="--i:6">
        <button
          class="public-toggle"
          type="button"
          aria-expanded={showPublicFallback}
          onclick={() => showPublicFallback = !showPublicFallback}
        >
          <Icon.Flag size={12} />
          {showPublicFallback ? 'Hide public manager fallback' : 'Use public manager ID instead'}
        </button>

        {#if showPublicFallback}
          <div class="public-panel">
            {#if $recentManagers.length > 0}
              <div class="recent-managers">
                <div class="recent-head">
                  <Icon.Jersey size={12} />
                  <span>Recent public managers</span>
                </div>
                <div class="recent-list">
                  {#each $recentManagers as mgr}
                    <div class="recent-row">
                      <button class="recent-chip" onclick={() => login(mgr.id)} disabled={loading}>
                        <span class="rc-name">{mgr.team_name}</span>
                        <span class="rc-sub mono">#{mgr.id} · {mgr.player_name}</span>
                      </button>
                      <button class="recent-forget" title="Remove" onclick={() => forgetManager(mgr.id)}>×</button>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            <form class="signin-form public-form" onsubmit={(e) => { e.preventDefault(); login(); }}>
              <label class="signin-field">
                <span class="label-text">Public Manager ID</span>
                <div class="field-row">
                  <input
                    type="text"
                    inputmode="numeric"
                    bind:value={idInput}
                    onkeydown={handleKey}
                    placeholder="e.g. 12345"
                    disabled={loading}
                    autocomplete="off"
                  />
                  <button class="btn-ghost" type="submit" disabled={loading}>
                    {loading ? 'Syncing…' : 'Open public team'}
                  </button>
                </div>
              </label>
              <p class="signin-hint">
                <Icon.Flag size={12} />
                <span>Find the ID at <span class="mono">fantasy.premierleague.com → Points</span> — it’s in the URL.</span>
              </p>
            </form>
          </div>
        {/if}
      </div>

      {#if error}<p class="error-msg">{error}</p>{/if}

      <button class="help-link" style="--i:7" onclick={() => showHelp = true}>
        <Icon.Whistle size={12} />
        <span>Read the one-minute primer</span>
      </button>

      <div class="signin-feats" style="--i:8">
        <div class="feat">
          <Icon.Pitch size={18} />
          <div>
            <strong>Squad as portfolio</strong>
            <span>Correlation, exposure and concentration in one view.</span>
          </div>
        </div>
        <div class="feat">
          <Icon.Whistle size={18} />
          <div>
            <strong>Risk callouts</strong>
            <span>Short warnings when the week is leaning too hard on one outcome.</span>
          </div>
        </div>
        <div class="feat">
          <Icon.Coin size={18} />
          <div>
            <strong>Transfer runway</strong>
            <span>Use capital, EP and variance together instead of chasing isolated form.</span>
          </div>
        </div>
      </div>
    </section>
  {:else if loading && !data}
    <div class="loading-state"><div class="spinner"></div><p class="dim">Syncing squad data…</p></div>
  {:else if data}
    {#if liveSessionState !== 'connected'}
      <section class="live-banner fade-in" style="--i:0">
        <div class="live-banner-copy">
          <strong>
            {#if liveSessionState === 'mismatch'}
              Live cookie is connected to a different manager.
            {:else}
              Live cookie is not connected yet.
            {/if}
          </strong>
          <span>
            {#if liveSessionState === 'mismatch'}
              The stored session belongs to <span class="mono">#{fplStatus?.account_id}</span>, so this manager stays on public LAST GW data until you re-paste the correct cookie.
            {:else}
              This manager is running on public LAST GW data. Add your FPL cookie to unlock live bank and true free-transfer count.
            {/if}
          </span>
        </div>
        <a class="live-banner-link" href="/settings">
          <Icon.Whistle size={12} />
          Open Settings
        </a>
      </section>
    {/if}

    <!-- ═════ MANAGER HEADER ═════ -->
    <section class="mgr-header" style="--i:0">
      <div class="mgr-identity">
        <span class="eyebrow">
          <Icon.Jersey size={12} />
          MANAGER #{data.manager.id ?? $managerId} · Squad GW{data.event} · Proj GW{projectionEvent}
        </span>
        <h1 class="display">{data.manager.name || 'My Team'}</h1>
        <p class="dim mgr-name">{data.manager.player_name}</p>
      </div>
      <div class="scoreboard">
        <div class="sb-cell">
          <span class="sb-val mono">{data.manager.overall_points?.toLocaleString() ?? '—'}</span>
          <span class="sb-label">Points</span>
        </div>
        <div class="sb-cell">
          <span class="sb-val mono">{data.manager.overall_rank?.toLocaleString() ?? '—'}</span>
          <span class="sb-label">Overall rank</span>
        </div>
        <div class="sb-cell">
          <span class="sb-val mono">£{data.manager.team_value?.toFixed(1) ?? '—'}m</span>
          <span class="sb-label">Team value</span>
        </div>
        <div class="sb-cell">
          <span class="sb-val mono">£{data.manager.bank?.toFixed(1) ?? '—'}m</span>
          <span class="sb-label">Bank</span>
        </div>
      </div>
    </section>

    <!-- ═════ QUICK HEALTH BAR ═════ -->
    <div class="health-bar" style="--i:1">
      <div class="hb-stat hb-ep">
        <span class="mono accent" style="font-size: 1.1rem;">{squadEP.toFixed(1)}</span>
        <StatExplainer term="EP" />
      </div>
      <div class="hb-sep"></div>
      <div class="hb-stat"><span class="mono accent">{analysisData.exposure.enb}</span> <StatExplainer term="ENB" /></div>
      <div class="hb-sep"></div>
      <div class="hb-stat"><span class="mono">{analysisData.exposure.portfolio_std}</span> <StatExplainer term="StdDev" /></div>
      <div class="hb-sep"></div>
      <div class="hb-stat"><span class="mono {analysisData.exposure.hhi > 0.15 ? 'negative' : ''}">{analysisData.exposure.hhi}</span> <StatExplainer term="HHI" /></div>
      <div class="hb-sep"></div>
      <div class="hb-stat"><span class="mono">{analysisData.exposure.diversification_ratio}</span> <StatExplainer term="DR" /></div>
      {#if analysisData.callouts?.length}
        <div class="hb-sep"></div>
        <button class="hb-issues" onclick={() => showIssues = !showIssues}>
          <Icon.Card variant="yellow" size={14} />
          <span>{analysisData.callouts.length} issue{analysisData.callouts.length > 1 ? 's' : ''}</span>
        </button>
      {/if}
    </div>

    <!-- Issues drawer (collapsible) -->
    {#if showIssues && analysisData.callouts?.length}
      <section class="fade-in" style="--i:2"><RiskCards callouts={analysisData.callouts} /></section>
    {/if}

    <!-- ═════ DESK NOTES ═════ -->
    <section class="desk-notes" style="--i:3">
      <header class="desk-head">
        <span class="eyebrow"><Icon.Whistle size={12} /> Desk notes</span>
        <button class="desk-help" onclick={() => showHelp = true}>
          <Icon.Whistle size={12} />
          Primer
        </button>
      </header>

      <ScenarioCards players={starters} exposure={analysisData.exposure} />

      <div class="desk-grid">
        <div class="card desk-card">
          <div class="card-header">
            <div class="row-tight">
              <Icon.Jersey size={14} />
              <h2>Position sizing</h2>
            </div>
            <span class="dim2 small">Expected points share · captain counted 2x</span>
          </div>
          <PositionSizing
            players={starters}
            onPlayerClick={(p) => selectPlayer(p)}
          />
        </div>

        <div class="card desk-card">
          <div class="card-header">
            <div class="row-tight">
              <Icon.Trophy size={14} />
              <h2>Risk attribution</h2>
            </div>
            <span class="dim2 small">which team decides your week</span>
          </div>
          <RiskAttribution concentration={analysisData.exposure.team_concentration} />
        </div>
      </div>

      <div class="card desk-card">
        <div class="card-header">
          <div class="row-tight">
            <Icon.Coin size={14} />
            <h2>Transfer runway</h2>
          </div>
          <span class="dim2 small">capital &amp; weakest slot</span>
        </div>
        <TransferRunway
          manager={data.manager}
          players={data.players}
          exposure={analysisData.exposure}
        />
      </div>
    </section>

    <!-- ═════ SQUAD PITCH + DETAIL ═════ -->
    <section class="squad-section" style="--i:5" class:with-detail={!!selectedPlayer}>
      <div class="pitch-card card">
        <div class="card-header">
          <div class="pitch-head">
            <div class="row-tight">
              <h2>Starting XI</h2>
              <span class="formation-badge badge badge-accent">{formation}</span>
            </div>
            <div class="xi-hero">
              <div class="xi-hero-copy">
                <span class="stat-value">{squadEP.toFixed(1)}</span>
                <span class="eyebrow">Expected points · GW{projectionEvent}</span>
              </div>
              {#if squadTrend.length}
                <div class="xi-sparkline" aria-label="Last 5 gameweeks actual points vs expected points">
                  {#each squadTrend as point}
                    <div class="xi-spark-col" title="GW{point.event}: {point.actual} pts vs {squadEP.toFixed(1)} EP">
                      <span class="xi-spark-exp" style="bottom: calc({point.expectedPct}% - 1px);"></span>
                      <span class="xi-spark-act" style="height: {Math.max(point.actualPct, 6)}%;"></span>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          </div>
          <span class="dim2 small">click a kit for details</span>
        </div>

        <div class="pitch-wrap">
          <PitchField />
          <div class="formation">
            {#each [fwds, mids, defs, gks] as row, rowIdx}
              <div class="formation-row">
                {#each row as p (p.id)}
                  <PlayerChip
                    player={p}
                    selected={selectedPlayer?.id === p.id}
                    averageEp={squadAvgEP}
                    flipTip={rowIdx === 0}
                    onclick={() => selectPlayer(p)}
                  />
                {/each}
              </div>
            {/each}
          </div>
        </div>

        <div class="bench-strip">
          <span class="eyebrow">
            <Icon.Swap size={12} /> Bench
          </span>
          <div class="bench-pills">
            {#each bench as p (p.id)}
              <button
                class="bench-pill"
                class:selected={selectedPlayer?.id === p.id}
                onclick={() => selectPlayer(p)}
              >
                <span class="bp-name">{p.web_name}</span>
                <span class="bp-team dim2">{p.team_short}</span>
                <span class="bp-ep mono">{displayEp(p)?.toFixed(1) ?? '—'}</span>
              </button>
            {/each}
          </div>
        </div>
      </div>

      {#if selectedPlayer}
        <div class="detail-card card kickoff">
          <div class="card-header">
            <div class="row-tight">
              <Icon.Jersey size={18} />
              <h2>{selectedPlayer.web_name}</h2>
            </div>
            <span class="badge badge-accent">{selectedPlayer.team_short} · {selectedPlayer.position}</span>
          </div>
          <div class="detail-stats">
            <div class="ds ep"><span class="mono accent">{displayEp(selectedPlayer)?.toFixed(1) ?? '—'}</span><StatExplainer term="EP" /></div>
            <div class="ds"><span class="mono">{selectedPlayer.total_points}</span><span class="stat-label">Pts</span></div>
            <div class="ds"><span class="mono">{selectedPlayer.form?.toFixed(1)}</span><StatExplainer term="Form" /></div>
            <div class="ds"><span class="mono">£{selectedPlayer.price?.toFixed(1)}m</span><span class="stat-label">Price</span></div>
            <div class="ds"><span class="mono accent">{selectedPlayer.xgi?.toFixed(2) ?? '—'}</span><StatExplainer term="xGI" /></div>
            <div class="ds"><span class="mono">{selectedPlayer.goals}</span><span class="stat-label">Goals</span></div>
            <div class="ds"><span class="mono">{selectedPlayer.assists}</span><span class="stat-label">Assists</span></div>
            <div class="ds"><span class="mono">{selectedPlayer.clean_sheets}</span><StatExplainer term="CS" /></div>
            <div class="ds"><span class="mono">{selectedPlayer.bonus}</span><StatExplainer term="BPS" /></div>
            <div class="ds"><span class="mono">{selectedPlayer.selected_pct?.toFixed(1)}%</span><StatExplainer term="Own%" /></div>
            <div class="ds"><span class="mono">{selectedPlayer.minutes}</span><span class="stat-label">Mins</span></div>
            <div class="ds"><span class="mono">{selectedPlayer.ict_index?.toFixed(1) ?? '—'}</span><StatExplainer term="ICT" /></div>
          </div>

          {#if selectedPlayer.projection_availability}
            <div class="detail-note dim2 small">
              Modelled for GW{projectionEvent}. Expected minutes {selectedPlayer.expected_minutes_next?.toFixed(0) ?? '—'},
              availability reliability {(selectedPlayer.projection_availability.reliability_score * 100).toFixed(0)}%,
              official FPL EP {selectedPlayer.ep_next?.toFixed(1) ?? '—'}.
            </div>
          {/if}

          {#if loadingPlayer}<p class="dim small loading">Loading…</p>{/if}

          {#if playerDetail?.gw_history?.length}
            <div class="detail-section">
              <h3>Gameweek points</h3>
              <div class="sparkline">
                {#each playerDetail.gw_history.slice(-15) as gw}
                  <div class="spark-bar" style="height: {Math.max(gw.points * 4, 2)}px" title="GW{gw.event}: {gw.points}pts">
                    <span class="spark-lbl">{gw.points}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          {#if playerDetail?.correlations?.length}
            <div class="detail-section">
              <h3>Squad correlations</h3>
              <div class="corr-list">
                {#each playerDetail.correlations.slice(0, 8) as c}
                  <div class="corr-row">
                    <span>{c.web_name}</span>
                    <span class="badge {c.correlation > 0.3 ? 'badge-red' : c.correlation < -0.1 ? 'badge-blue' : 'badge-accent'}">{c.team_short}</span>
                    <span class="mono {c.correlation > 0.3 ? 'negative' : ''}">{c.correlation > 0 ? '+' : ''}{c.correlation.toFixed(3)}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          {#if playerDetail?.fixtures?.length}
            <div class="detail-section">
              <h3>Next fixtures</h3>
              <div class="fix-row">
                {#each playerDetail.fixtures.slice(0, 6) as f}
                  <span class="fix-cell fdr-{f.difficulty}">{f.is_home ? '' : '@'}{f.opponent}</span>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </section>

    <!-- ═════ ANALYSIS TABS ═════ -->
    <div class="analysis-tabs" style="--i:6">
      <button class="atab" class:active={analysisTab === 'week'} onclick={() => setAnalysisTab('week')}>
        <Icon.Stopwatch size={14} /> Open Fixtures
      </button>
      <button class="atab" class:active={analysisTab === 'portfolio'} onclick={() => setAnalysisTab('portfolio')}>
        <Icon.Goal size={14} /> GW{projectionEvent} Outlook
      </button>
      <button class="atab" class:active={analysisTab === 'deep'} onclick={() => setAnalysisTab('deep')}>
        <Icon.Jersey size={14} /> What Landed
      </button>
      <button class="atab" class:active={analysisTab === 'issues'} onclick={() => setAnalysisTab('issues')}>
        <Icon.Whistle size={14} /> Issues ({analysisData.callouts?.length ?? 0})
      </button>
    </div>

    {#if analysisTab === 'week'}
      <!-- OPEN FIXTURES: only what can still move the current gameweek -->
      <div class="card fade-in" style="margin-bottom: 0.75rem;">
        <div class="card-header">
          <div>
            <h2>What can still move this week</h2>
            <span class="dim2 small">Remaining fixtures only. Use What Landed for points already banked and correlation attribution.</span>
          </div>
          {#if exposure}<span class="dim2 small">GW{exposure.event}</span>{/if}
        </div>

        {#if expLoading}
          <p class="dim" style="padding: 0.5rem;">Loading...</p>
        {:else if !exposure?.fixtures?.length}
          <p class="dim" style="padding: 0.5rem;">No remaining open fixtures this week.</p>
        {:else}
          <!-- Scannable risk bars — answer "which matches matter?" in 2 seconds -->
          <div class="risk-bars">
            {#each exposure.fixtures as fix}
              {@const swing = fix.angle?.swing ?? fix.ep_range ?? 0}
              {@const sev = fix.angle?.severity ?? 'low'}
              {@const nPlayers = (fix.home_players?.length ?? 0) + (fix.away_players?.length ?? 0)}
              <div class="rb-row">
                <span class="rb-match">{fix.home} v {fix.away}</span>
                <div class="rb-track">
                  <div class="rb-fill sev-{sev}" style="width: {Math.min(swing / 18 * 100, 100)}%"></div>
                </div>
                <span class="mono rb-swing">{swing}pt</span>
                <span class="dim2 small">{nPlayers}p</span>
              </div>
            {/each}
          </div>

          <!-- Detail cards — only for fixtures that actually matter -->
          {#each exposure.fixtures as fix}
            {@const a = fix.angle ?? {}}
            {@const swing = a.swing ?? fix.ep_range ?? 0}
            {@const allP = [...(fix.home_players ?? []), ...(fix.away_players ?? [])]}
            {#if swing >= 3}
              <div class="fd sev-{a.severity ?? 'low'}">
                <div class="fd-top">
                  <div>
                    <strong class="fd-match">{fix.home} v {fix.away}</strong>
                    <span class="fd-chips">{#each allP as p}<span class="fd-chip" class:cap={p.captain}>{p.name}</span>{/each}</span>
                  </div>
                  <span class="fd-swing mono">{swing}pt swing</span>
                </div>
                {#if a.headline}<p class="fd-hl">{a.headline}</p>{/if}
                {#if a.detail}<p class="fd-body">{a.detail}</p>{/if}
                {#if a.insurance_hint}<p class="fd-hint">{a.insurance_hint}</p>{/if}
              </div>
            {/if}
          {/each}
        {/if}
      </div>

      <!-- Fixture outlook strip -->
      <section class="card fade-in" style="margin-top: 0.75rem;">
        <div class="card-header">
          <h2>Fixture Outlook</h2>
          <span class="dim2 small">Next 6 GWs</span>
        </div>
        <FixtureStrip outlook={data.fixture_outlook} currentEvent={projectionEvent} />
      </section>

    {:else if analysisTab === 'portfolio'}
      <!-- COMING: forward-looking correlation matrix + team exposure -->
      <section class="grid-main fade-in">
        <div class="card">
          <div class="card-header">
            <div>
              <div class="row-tight">
                <h2><StatExplainer term="Correlation" /> Matrix</h2>
                {#if portfolioLoading}
                  <span class="badge badge-yellow">Refreshing…</span>
                {/if}
              </div>
              <span class="dim2 small">{analysisData.meta.window_summary}</span>
            </div>
            <span class="badge badge-accent">{analysisData.meta.window_label}</span>
          </div>
          <div class="portfolio-window-rail" aria-label="Correlation window">
            {#each portfolioWindowOptions as option}
              <button
                type="button"
                class="window-chip"
                class:active={portfolioFutureWeeks === option.value}
                onclick={() => changePortfolioWindow(option.value)}
              >
                {option.label}
              </button>
            {/each}
          </div>
          {#if portfolioError}
            <p class="error-msg" style="margin-bottom: 0.75rem;">{portfolioError}</p>
          {/if}
          <CorrelationMatrix
            matrix={analysisData.exposure.correlation_matrix}
            names={starterNames}
            players={starters}
            selectedPair={selectedPair}
          />
          <div class="corr-explainer">
            {#if analysisData.meta.window_type === 'future'}
              <p class="dim small">
                This is the current XI projected through <strong>{analysisData.meta.window_label}</strong>.
                Red pairs move together, blue pairs naturally hedge.
              </p>
            {:else}
              <p class="dim small">
                Historical view of how strongly two players have moved together.
                High red pockets cut your effective number of independent outcomes; use the rail to compare that with the next fixture windows.
              </p>
            {/if}
          </div>
        </div>
        <div class="card">
          <div class="card-header">
            <h2>Team Exposure</h2>
            <span class="dim2 small">Variance decomposition</span>
          </div>
          <ExposureChart concentration={analysisData.exposure.team_concentration} />
          <div class="corr-explainer">
            <p class="dim small">
              Variance % shows which club can swing the week the most. Once one team gets above roughly 40%, the squad is carrying a concentrated club stack.
            </p>
          </div>
        </div>
      </section>

    {:else if analysisTab === 'deep'}
      <section class="card fade-in">
        <div class="card-header">
          <div>
            <h2>Correlation Deep Dive</h2>
            <span class="dim2 small">How the stack paid, week by week, after the matches actually landed</span>
          </div>
          <span class="badge badge-accent">{attribution?.lookback ?? deepLookback ?? 'Season'} GWs</span>
        </div>

        {#if attributionLoading}
          <p class="dim" style="padding: 0.5rem 0;">Loading correlation attribution…</p>
        {:else if attributionError}
          <p class="error-msg">{attributionError}</p>
        {:else if attribution}
          <CorrelationDeepDive
            attribution={attribution}
            lookback={deepLookback}
            onLookbackChange={changeLookback}
            onPairSelect={handlePairSelect}
            selectedPair={selectedPair}
          />
        {/if}
      </section>

    {:else if analysisTab === 'issues'}
      <!-- ISSUES: risk callouts -->
      {#if analysisData.callouts?.length}
        <section class="fade-in"><RiskCards callouts={analysisData.callouts} /></section>
      {:else}
        <div class="surface-note fade-in">No material issues detected. The current squad shape is fairly balanced.</div>
      {/if}
    {/if}

    <p class="meta-footer fade-in">
      <Icon.Whistle size={12} />
      <span>
        {#if analysisData.meta.window_type === 'future'}
          Forecast window: GW{analysisData.meta.window_start_event}–GW{analysisData.meta.window_end_event},
          blended with {analysisData.meta.history_gameweeks_used} historical gameweeks,
          α={analysisData.meta.shrinkage_alpha}/{analysisData.meta.forecast_alpha}.
        {:else}
          Historical covariance from {analysisData.meta.gameweeks_used} gameweeks,
          α={analysisData.meta.shrinkage_alpha}, Ledoit–Wolf regularised.
        {/if}
        Maths in a kit.
      </span>
      <button class="footer-help-link" onclick={() => showHelp = true}>
        Primer
      </button>
    </p>
  {/if}
</div>

<!-- Team-as-portfolio explainer drawer — rendered once, toggled from anywhere -->
<HelpDrawer open={showHelp} onClose={() => showHelp = false} />

<style>
  /* ═════ SIGN-IN ═════ */
  .signin {
    max-width: 560px;
    margin: 3.5rem auto 2rem;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.85rem;
    position: relative;
  }
  .signin-crest {
    margin-bottom: 0.25rem;
    position: relative;
  }
  .signin-crest .crest {
    width: 84px;
    height: 84px;
    border-radius: var(--radius-lg);
    box-shadow:
      0 0 0 1px rgba(0, 255, 156, 0.14),
      0 24px 70px rgba(0, 255, 156, 0.18),
      0 6px 24px rgba(0, 0, 0, 0.55);
    display: inline-block;
    transition: transform 500ms var(--ease);
  }
  .signin-crest:hover .crest { transform: translateY(-2px) rotate(-1.5deg); }
  .signin h1 {
    margin: 0.3rem 0 0;
    max-width: 14ch;
  }
  .signin-rule {
    display: block;
    width: 64px;
    height: 2px;
    background: var(--accent);
    transform-origin: left center;
    animation: drawLine 600ms var(--ease) 400ms both;
    margin: 0.2rem 0 0.25rem;
    opacity: 0.85;
  }
  .signin-sub {
    color: var(--text-secondary);
    max-width: 44ch;
    line-height: 1.55;
    margin-bottom: 0.4rem;
    font-size: 0.92rem;
  }

  /* Quick-resume recent-managers */
  .recent-managers {
    width: 100%;
    max-width: 420px;
    margin-top: 0.85rem;
    padding: 0.85rem 0.95rem 0.95rem;
    background: color-mix(in srgb, var(--bg-card) 92%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    text-align: left;
  }
  .recent-head {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding-bottom: 0.55rem;
    margin-bottom: 0.4rem;
    border-bottom: 1px dashed var(--border);
  }
  .recent-list { display: flex; flex-direction: column; gap: 0.3rem; }
  .recent-row { display: flex; gap: 0.3rem; align-items: stretch; }
  .recent-chip {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 0.6rem 0.85rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    cursor: pointer;
    text-align: left;
    gap: 0.15rem;
  }
  .recent-chip:hover {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .rc-name {
    font-family: var(--heading);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text-heading);
  }
  .rc-sub {
    font-size: 0.66rem;
    color: var(--text-muted);
    letter-spacing: 0.04em;
  }
  .recent-forget {
    width: 1.8rem;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 1rem;
    line-height: 1;
    border-radius: var(--radius);
    cursor: pointer;
  }
  .recent-forget:hover {
    color: var(--red);
    border-color: var(--red);
  }

  .or-divider {
    width: 100%;
    max-width: 420px;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: var(--text-muted);
    font-size: 0.68rem;
    font-family: var(--mono);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin: 0.8rem 0 0.3rem;
  }
  .or-divider::before,
  .or-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .signin-form {
    width: 100%;
    max-width: 420px;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    text-align: left;
  }
  .signin-field { display: flex; flex-direction: column; gap: 0.35rem; }
  .label-text {
    font-family: var(--mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .field-row {
    display: flex;
    gap: 0.45rem;
  }
  .field-row input {
    flex: 1;
    font-size: 1rem;
    padding: 0.7rem 0.85rem;
  }
  .field-row button { padding: 0.7rem 1.1rem; }

  .signin-hint {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text-muted);
    font-size: 0.72rem;
    margin-top: 0.2rem;
  }
  .error-msg { color: var(--red); font-size: 0.85rem; margin-top: 0.3rem; }

  .live-cookie-card {
    width: 100%;
    max-width: 520px;
    margin-top: 0.35rem;
    padding: 1rem 1.05rem;
    border: 1px solid rgba(0, 255, 156, 0.18);
    border-radius: var(--radius-lg);
    background:
      linear-gradient(180deg, rgba(0, 255, 156, 0.05), transparent 65%),
      color-mix(in srgb, var(--bg-card) 94%, transparent);
    text-align: left;
  }
  .live-cookie-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  .live-cookie-head h2 {
    margin: 0.25rem 0 0;
    max-width: 22ch;
    font-size: 1.05rem;
    line-height: 1.15;
  }
  .live-chip {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    padding: 0.28rem 0.6rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    font-family: var(--mono);
    font-size: 0.64rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.04);
  }
  .live-chip.connected {
    color: var(--accent-text);
    border-color: rgba(0, 255, 156, 0.24);
    background: var(--accent-soft);
  }
  .live-cookie-copy,
  .live-cookie-note {
    margin: 0.7rem 0 0;
    color: var(--text-secondary);
    line-height: 1.55;
    font-size: 0.88rem;
  }
  .live-cookie-note {
    color: var(--text);
  }
  .live-cookie-steps {
    margin: 0.75rem 0 0;
    padding-left: 1.15rem;
    color: var(--text-secondary);
    line-height: 1.6;
    font-size: 0.86rem;
  }
  .live-cookie-steps li { margin-bottom: 0.2rem; }
  .live-cookie-steps code,
  .live-cookie-note .mono {
    background: var(--bg-elevated);
    padding: 1px 5px;
    border-radius: 3px;
  }
  .live-cookie-steps a {
    color: var(--accent);
    text-decoration: none;
  }
  .live-cookie-steps a:hover { text-decoration: underline; }
  .live-cookie-actions {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    flex-wrap: wrap;
    margin-top: 0.9rem;
  }
  .cookie-open-live {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }
  .cookie-signin,
  .cookie-settings-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }
  .cookie-settings-link {
    color: var(--text);
    text-decoration: none;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.5rem 0.9rem;
    background: var(--bg-elevated);
    font-size: 0.8rem;
  }
  .cookie-settings-link:hover {
    border-color: var(--accent);
    color: var(--accent-text);
  }

  .public-fallback {
    width: 100%;
    max-width: 520px;
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
  }
  .public-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    align-self: center;
    background: transparent;
    border: 1px dashed var(--border);
    color: var(--text-secondary);
    padding: 0.5rem 0.9rem;
    border-radius: 999px;
    cursor: pointer;
    font-size: 0.76rem;
  }
  .public-toggle:hover {
    border-style: solid;
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .public-panel {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 0.95rem 1rem;
    background: color-mix(in srgb, var(--bg-card) 92%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
  }
  .public-form {
    max-width: none;
  }

  .help-link {
    background: transparent;
    border: 1px dashed var(--border);
    color: var(--text-secondary);
    font-size: 0.74rem;
    padding: 0.45rem 0.9rem;
    border-radius: 100px;
    cursor: pointer;
    margin-top: 0.4rem;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
  }
  .help-link:hover {
    color: var(--accent-text);
    border-color: var(--accent);
    border-style: solid;
  }

  .signin-feats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.85rem;
    width: 100%;
    margin-top: 1.4rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }
  .feat {
    display: flex;
    gap: 0.6rem;
    align-items: flex-start;
    padding: 0;
    text-align: left;
  }
  .feat strong {
    display: block;
    font-family: var(--heading);
    font-size: 0.82rem;
    margin-bottom: 0.15rem;
    color: var(--text-heading);
  }
  .feat span {
    display: block;
    font-size: 0.7rem;
    color: var(--text-muted);
    line-height: 1.45;
  }

  .footer-help-link {
    margin-left: 0.4rem;
    background: transparent;
    border: none;
    color: var(--accent-text);
    cursor: pointer;
    text-decoration: underline;
    font-size: inherit;
    padding: 0;
  }
  .footer-help-link:hover { color: var(--accent); }

  .live-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.9rem;
    padding: 0.95rem 1rem;
    border: 1px solid rgba(0, 255, 156, 0.16);
    border-radius: var(--radius-lg);
    background:
      linear-gradient(90deg, rgba(0, 255, 156, 0.06), transparent 45%),
      var(--bg-card);
  }
  .live-banner-copy {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .live-banner-copy strong {
    font-family: var(--heading);
    font-size: 0.98rem;
    color: var(--text-heading);
  }
  .live-banner-copy span {
    color: var(--text-secondary);
    line-height: 1.5;
    font-size: 0.85rem;
  }
  .live-banner-link {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text);
    text-decoration: none;
    padding: 0.55rem 0.9rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
  }
  .live-banner-link:hover {
    border-color: var(--accent);
    color: var(--accent-text);
  }

  .loading-state {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 4rem 0;
    justify-content: center;
  }
  .spinner {
    width: 22px;
    height: 22px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ═════ MANAGER HEADER ═════ */
  .mgr-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 0.25rem;
    padding-bottom: 1.1rem;
    border-bottom: 1px solid var(--border);
    gap: 1.5rem;
    flex-wrap: wrap;
  }
  .mgr-identity h1 {
    margin: 0.35rem 0 0.25rem;
  }
  .mgr-name {
    font-family: var(--mono);
    font-size: 0.76rem;
    color: var(--text-secondary);
    letter-spacing: 0.02em;
  }

  /* (live styles moved to /points page) */

  .scoreboard {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 1.1rem 1.4rem;
    padding: 0.95rem 1.15rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    min-width: min(100%, 32rem);
    position: relative;
  }
  .scoreboard::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    pointer-events: none;
    background: linear-gradient(180deg, rgba(255,255,255,0.025), transparent 38%);
  }
  .sb-cell {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    position: relative;
  }
  .sb-cell + .sb-cell::before {
    content: '';
    position: absolute;
    left: -0.7rem;
    top: 10%;
    bottom: 10%;
    width: 1px;
    background: var(--border);
  }
  .sb-val {
    font-family: var(--heading);
    font-size: 1.55rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: var(--text-heading);
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .sb-label {
    font-family: var(--mono);
    font-size: 0.58rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .sb-sep {
    display: none;
  }

  /* ═════ METRICS ═════ */
  .metrics-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .metric-card {
    display: flex;
    gap: 0.85rem;
    align-items: center;
    padding: 1rem 1.1rem;
  }
  .metric-ico {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.2rem;
    height: 2.2rem;
    border-radius: var(--radius);
    background: var(--accent-soft);
    color: var(--accent-text);
    flex-shrink: 0;
  }
  .metric-body {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }

  /* ═════ DESK NOTES — tight, breathable stack ═════ */
  .desk-notes {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .desk-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.1rem;
  }
  .desk-help {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.4rem 0.7rem;
    background: transparent;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    color: var(--text-secondary);
    font-size: 0.72rem;
    cursor: pointer;
  }
  .desk-help:hover {
    border-style: solid;
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .desk-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
    gap: 0.75rem;
  }
  .desk-card .card-header { margin-bottom: 0.65rem; }

  @media (max-width: 960px) {
    .desk-grid { grid-template-columns: 1fr; }
  }

  /* ═════ SQUAD PITCH ═════ */
  .squad-section {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 1rem;
    margin-bottom: 1rem;
  }
  .squad-section.with-detail {
    grid-template-columns: minmax(0, 1fr) 340px;
  }
  .pitch-card { overflow: visible; padding: 1.1rem; }
  .pitch-head {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }
  .formation-badge {
    font-size: 0.68rem !important;
  }
  .xi-hero {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .xi-hero-copy {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .xi-hero-copy .stat-value {
    font-size: 2.5rem;
  }
  .xi-sparkline {
    display: flex;
    align-items: flex-end;
    gap: 0.22rem;
    height: 2.8rem;
    min-width: 7rem;
    padding: 0.15rem 0;
  }
  .xi-spark-col {
    position: relative;
    width: 1.1rem;
    height: 100%;
    display: flex;
    align-items: flex-end;
  }
  .xi-spark-act {
    width: 100%;
    background: linear-gradient(180deg, var(--accent) 0%, var(--accent-deep) 100%);
    border-radius: 2px 2px 0 0;
    opacity: 0.85;
  }
  .xi-spark-exp {
    position: absolute;
    left: 0;
    right: 0;
    border-top: 2px solid var(--yellow);
    opacity: 0.9;
  }

  .pitch-wrap {
    position: relative;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    /* visible so player tooltips escape the pitch bounds */
    overflow: visible;
    min-height: 460px;
    background: #081810;
  }
  /* Keep the rounded-corner feel on the grass SVG itself */
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
    padding: 1.4rem 0.75rem;
    min-height: 460px;
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
  }
  .bench-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    flex: 1;
  }
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
  .bp-ep {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--accent-text);
  }

  /* ═════ DETAIL CARD ═════ */
  .detail-card {
    /* Let the page scroll, not the card — otherwise tooltips (StatExplainer)
       get clipped by the card's scroll container. */
    overflow: visible;
    padding: 1.1rem;
  }
  .detail-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.4rem;
    margin-bottom: 0.75rem;
  }
  .ds {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.4rem 0.25rem;
    background: var(--bg-elevated);
    border-radius: var(--radius);
    border: 1px solid var(--border);
  }
  .ds .mono { font-size: 0.88rem; font-weight: 700; }
  .ds .stat-label { font-size: 0.54rem; }
  .ds.ep .mono {
    font-size: 1.2rem;
    letter-spacing: -0.02em;
  }
  .detail-note {
    margin-top: -0.2rem;
    margin-bottom: 0.6rem;
    line-height: 1.45;
  }

  .detail-section {
    margin-top: 0.85rem;
    padding-top: 0.7rem;
    border-top: 1px dashed var(--border);
  }
  .detail-section h3 { margin-bottom: 0.4rem; }
  .sparkline { display: flex; align-items: flex-end; gap: 3px; height: 64px; }
  .spark-bar {
    flex: 1;
    min-width: 0;
    background: var(--accent);
    opacity: 0.65;
    border-radius: 2px 2px 0 0;
    position: relative;
  }
  .spark-bar:hover { opacity: 1; }
  .spark-lbl {
    position: absolute;
    bottom: calc(100% + 2px);
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.58rem;
    font-family: var(--mono);
    color: var(--text-muted);
    display: none;
  }
  .spark-bar:hover .spark-lbl { display: block; color: var(--text); }

  .corr-list { display: flex; flex-direction: column; gap: 0.22rem; }
  .corr-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    padding: 0.22rem 0;
  }
  .corr-row span:first-child { flex: 1; }

  .fix-row { display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .fix-cell {
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-sm);
    font-family: var(--mono);
    font-size: 0.7rem;
    font-weight: 600;
  }
  .fdr-1 { background: rgba(0,255,156,0.15); color: var(--fdr-1); }
  .fdr-2 { background: rgba(106,255,157,0.12); color: var(--fdr-2); }
  .fdr-3 { background: rgba(148,179,166,0.12); color: var(--text-secondary); }
  .fdr-4 { background: rgba(255,209,102,0.16); color: var(--fdr-4); }
  .fdr-5 { background: rgba(255,61,90,0.16); color: var(--fdr-5); }

  /* ═════ MAIN GRID ═════ */
  .grid-main {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 0.85rem;
    margin-top: 0.85rem;
  }
  .meta-footer {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    margin-top: 1rem;
    padding-top: 0.85rem;
    border-top: 1px dashed var(--border);
    color: var(--text-muted);
    font-size: 0.72rem;
    line-height: 1.5;
  }

  /* ═════ HEALTH BAR ═════ */
  .health-bar {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
    gap: 0.4rem;
    padding: 0;
    margin-bottom: 0.25rem;
  }
  .hb-stat {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.8rem;
    padding: 0.7rem 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg-card);
    transition: border-color var(--duration) var(--ease), transform var(--duration) var(--ease);
  }
  .hb-stat:hover {
    border-color: var(--border-hover);
    transform: translateY(-1px);
  }
  .hb-stat .mono { font-weight: 700; font-size: 0.92rem; }
  .hb-sep { display: none; }
  .hb-issues {
    display: inline-flex; align-items: center; justify-content: center; gap: 0.35rem;
    background: var(--yellow-soft); border: 1px solid var(--yellow);
    color: var(--yellow); padding: 0.25rem 0.6rem;
    border-radius: var(--radius); cursor: pointer;
    font-size: 0.75rem; font-weight: 600;
    font-family: var(--mono); transition: all var(--duration);
    min-height: 100%;
  }
  .hb-issues:hover { background: var(--yellow); color: var(--bg); }
  .hb-ep { align-items: baseline; }

  .squad-warnings {
    display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 1rem;
  }
  .sw-row {
    display: flex; align-items: flex-start; gap: 0.5rem;
    padding: 0.5rem 0.75rem; border-radius: var(--radius-sm);
    font-size: 0.82rem; line-height: 1.4; color: var(--text-secondary);
  }
  .sw-injury { background: var(--red-soft); border: 1px solid var(--red); }
  .sw-bench { background: var(--yellow-soft); border: 1px solid var(--yellow); }

  .corr-explainer {
    margin-top: 0.65rem; padding-top: 0.55rem; border-top: 1px dashed var(--border);
    display: flex; flex-direction: column; gap: 0.3rem;
  }
  .corr-explainer p { line-height: 1.5; }
  .portfolio-window-rail {
    display: flex;
    gap: 0.45rem;
    overflow-x: auto;
    padding: 0.15rem 0 0.8rem;
    scrollbar-width: none;
  }
  .portfolio-window-rail::-webkit-scrollbar { display: none; }
  .window-chip {
    flex: 0 0 auto;
    padding: 0.52rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    transition: all var(--duration);
  }
  .window-chip:hover {
    color: var(--text);
    border-color: var(--accent);
  }
  .window-chip.active {
    color: var(--accent-text);
    border-color: color-mix(in srgb, var(--accent) 70%, var(--border));
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
    background: color-mix(in srgb, var(--accent) 12%, var(--bg-elevated));
  }

  /* ═════ ANALYSIS TABS ═════ */
  .analysis-tabs {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.75rem;
    overflow-x: auto;
    padding-bottom: 0.15rem;
    scrollbar-width: none;
  }
  .analysis-tabs::-webkit-scrollbar { display: none; }
  .atab {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.52rem 0.86rem; background: color-mix(in srgb, var(--bg-elevated) 88%, transparent);
    border: 1px solid var(--border); color: var(--text-secondary);
    font-family: var(--font); font-size: 0.82rem; font-weight: 600;
    cursor: pointer; border-radius: 999px;
    transition: all var(--duration);
    position: relative;
    white-space: nowrap;
    flex: 0 0 auto;
  }
  .atab:hover { color: var(--text); border-color: var(--accent); }
  .atab.active { color: var(--accent-text); border-color: var(--border-accent); background: color-mix(in srgb, var(--accent) 12%, var(--bg-elevated)); }

  /* ═════ FIXTURE EXPOSURE (This Week tab) ═════ */
  .exp-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .exp-card { padding: 0.85rem 1rem; }
  .exp-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
  .exp-match { font-size: 0.95rem; }
  .exp-badges { display: flex; align-items: center; gap: 0.4rem; }

  .exp-body { display: flex; flex-direction: column; gap: 0.5rem; }
  .exp-players-row { display: flex; gap: 0.25rem; flex-wrap: wrap; }
  .exp-chip { font-size: 0.72rem; padding: 0.15rem 0.4rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .exp-chip.cap { border-color: var(--yellow); background: var(--yellow-soft); }

  .exp-outcomes-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.3rem; }
  .exp-oc { display: flex; flex-direction: column; align-items: center; padding: 0.3rem; background: var(--bg-elevated); border-radius: var(--radius-sm); border: 1px solid var(--border); }
  .exp-oc.best { border-color: var(--accent); background: var(--accent-soft); }
  .exp-oc .mono { font-size: 0.88rem; font-weight: 600; }

  .exp-insight { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.5; padding: 0.4rem 0.5rem; background: var(--bg-elevated); border-radius: var(--radius-sm); border-left: 3px solid var(--border); }

  /* ═════ RISK BARS (this week scannable view) ═════ */
  .risk-bars { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 1rem; }
  .rb-row { display: flex; align-items: center; gap: 0.5rem; }
  .rb-match { font-size: 0.8rem; font-weight: 600; min-width: 7rem; }
  .rb-track { flex: 1; height: 8px; background: var(--bg-elevated); border-radius: 4px; overflow: hidden; }
  .rb-fill { height: 100%; border-radius: 4px; min-width: 2px; }
  .rb-fill.sev-high { background: var(--red); }
  .rb-fill.sev-medium { background: var(--yellow); }
  .rb-fill.sev-low { background: var(--text-muted); }
  .rb-swing { font-size: 0.78rem; min-width: 3rem; }

  /* ═════ FIXTURE DETAIL CARDS ═════ */
  .fd { padding: 0.75rem 0.85rem; border-left: 3px solid var(--border); margin-bottom: 0.5rem; background: var(--bg-elevated); border-radius: var(--radius-sm); }
  .fd.sev-high { border-left-color: var(--red); }
  .fd.sev-medium { border-left-color: var(--yellow); }
  .fd.sev-low { border-left-color: var(--text-muted); }
  .fd-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.3rem; }
  .fd-match { font-size: 0.9rem; }
  .fd-chips { display: flex; gap: 0.2rem; flex-wrap: wrap; margin-top: 0.2rem; }
  .fd-chip { font-size: 0.68rem; padding: 0.1rem 0.35rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .fd-chip.cap { border-color: var(--yellow); background: var(--yellow-soft); font-weight: 600; }
  .fd-swing { font-size: 0.85rem; font-weight: 700; white-space: nowrap; }
  .fd-hl { font-size: 0.85rem; font-weight: 600; color: var(--text-heading); margin-bottom: 0.15rem; }
  .fd-body { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.5; }
  .fd-hint { font-size: 0.75rem; color: var(--accent-text); margin-top: 0.3rem; padding: 0.3rem 0.5rem; background: var(--accent-soft); border-radius: var(--radius-sm); line-height: 1.4; }

  @media (max-width: 960px) {
    .squad-section { grid-template-columns: 1fr; }
    .grid-main { grid-template-columns: 1fr; }
    .scoreboard { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .signin-feats { grid-template-columns: 1fr; }
    .live-cookie-head,
    .live-banner {
      flex-direction: column;
      align-items: stretch;
    }
    .signin h1 { font-size: 2rem; }
    .mgr-identity h1 { font-size: 2rem; }
    .xi-sparkline { min-width: 0; }
  }
</style>
