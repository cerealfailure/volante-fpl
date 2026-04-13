<!--
  Scenario Cards — three what-ifs computed client-side from the
  existing xray data. Not a forecast; a stress test.

   - Base case: sum of ep_next (with captain doubled)
   - Downside: -1.5 × portfolio_std (a bad 2-sigma week)
   - Upside:   +1.5 × portfolio_std plus the captain's upside
-->
<script lang="ts">
  import { kitFor } from '$lib/teamColors';
  import * as Icon from '$lib/components/icons';

  let {
    players,
    exposure,
  }: {
    players: any[];
    exposure: any;
  } = $props();

  let captain = $derived(players.find((p: any) => p.is_captain));
  let topVarTeam = $derived.by(() => {
    const tc = exposure?.team_concentration ?? {};
    const entries: any[] = Object.values(tc);
    return entries.sort((a: any, b: any) => b.variance_pct - a.variance_pct)[0];
  });

  let baseEp = $derived.by(() => {
    return players.reduce((s: number, p: any) => {
      const w = p.is_captain ? 2 : 1;
      return s + w * (p.ep_next ?? 0);
    }, 0);
  });

  let std = $derived(exposure?.portfolio_std ?? 0);

  let downside = $derived(Math.max(0, baseEp - 1.5 * std));
  let upside   = $derived(baseEp + 1.5 * std);

  let downsideNarrative = $derived.by(() => {
    if (!topVarTeam) return 'A tough week breaks in the wrong direction.';
    return `${topVarTeam.team_short} is the swing bucket at ${topVarTeam.variance_pct.toFixed(0)}% of variance. If that stack blanks, the week drags fast.`;
  });

  let upsideNarrative = $derived.by(() => {
    if (!captain) return 'Everything clicks — clean sheets hold, attackers connect.';
    return `${captain.web_name} turns the armband into a haul and the main attacking stack lands together.`;
  });
</script>

<div class="sc-grid">
  <div class="sc-card sc-down">
    <header>
      <Icon.Card variant="red" size={14} />
      <span class="sc-eyebrow">Downside</span>
    </header>
    <span class="sc-num mono">{downside.toFixed(1)}</span>
    <span class="sc-delta negative mono">−{(baseEp - downside).toFixed(1)} vs base</span>
    <p class="sc-narr">{downsideNarrative}</p>
  </div>

  <div class="sc-card sc-base">
    <header>
      <Icon.Ball size={14} />
      <span class="sc-eyebrow">Base</span>
    </header>
    <span class="sc-num mono">{baseEp.toFixed(1)}</span>
    <span class="sc-delta dim2 mono">± {std.toFixed(1)} std dev</span>
    <p class="sc-narr">Current XI expectation with captain weight included. Treat it as a midpoint, not a promise.</p>
  </div>

  <div class="sc-card sc-up">
    <header>
      <Icon.Trophy size={14} />
      <span class="sc-eyebrow">Upside</span>
    </header>
    <span class="sc-num mono">{upside.toFixed(1)}</span>
    <span class="sc-delta positive mono">+{(upside - baseEp).toFixed(1)} vs base</span>
    <p class="sc-narr">{upsideNarrative}</p>
  </div>
</div>

<style>
  .sc-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.6rem;
  }
  .sc-card {
    background: color-mix(in srgb, var(--bg-card) 94%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 0.8rem 0.9rem 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.28rem;
    position: relative;
    overflow: hidden;
  }
  .sc-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
  }
  .sc-down::before { background: var(--red); }
  .sc-base::before { background: var(--accent); }
  .sc-up::before   { background: var(--yellow); }

  header {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text-muted);
  }
  .sc-eyebrow {
    font-family: var(--mono);
    font-size: 0.6rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .sc-num {
    font-family: var(--heading);
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: var(--text-heading);
    line-height: 1;
    font-variant-numeric: tabular-nums;
    margin-top: 0.2rem;
  }
  .sc-delta {
    font-size: 0.72rem;
    font-weight: 700;
  }
  .sc-narr {
    font-size: 0.76rem;
    line-height: 1.45;
    color: var(--text-secondary);
    margin-top: 0.2rem;
    padding-top: 0.45rem;
    border-top: 1px dashed var(--border);
  }

  @media (max-width: 900px) {
    .sc-grid { grid-template-columns: 1fr; }
  }

  :global([data-theme="pixel"]) .sc-card {
    border: 3px solid #1a1a2e;
    box-shadow: 3px 3px 0 #1a1a2e;
    background: #f4eede;
    border-radius: 0 !important;
  }
  :global([data-theme="pixel"]) .sc-card::before { height: 4px; }
  :global([data-theme="pixel"]) .sc-num {
    font-family: 'Press Start 2P', monospace;
    font-size: 14px;
    text-shadow: 2px 2px 0 var(--yellow);
  }
  :global([data-theme="pixel"]) .sc-eyebrow,
  :global([data-theme="pixel"]) .sc-delta {
    font-family: 'Press Start 2P', monospace;
    font-size: 6px;
  }
  :global([data-theme="pixel"]) .sc-narr {
    font-family: 'VT323', monospace;
    font-size: 15px;
    line-height: 1.3;
  }
</style>
