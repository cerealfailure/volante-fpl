<!--
  Transfer Runway — plain-English capital-plan card.
  Reads like margin notes a portfolio manager would jot:
  how much dry powder, how many moves feasible, which
  is the highest-impact swap.
-->
<script lang="ts">
  import * as Icon from '$lib/components/icons';

  let {
    manager,
    players,
    exposure,
    freeTransfers = 1,
  }: {
    manager: any;
    players: any[];
    exposure: any;
    freeTransfers?: number;
  } = $props();

  // Find the weakest starter by EP
  let weakestStarter = $derived.by(() => {
    const starters = (players ?? []).filter((p: any) => p.is_starter);
    return [...starters].sort((a: any, b: any) => (a.ep_next ?? 0) - (b.ep_next ?? 0))[0];
  });

  // Best-affordable price cap for a replacement: weakest's price + bank
  let priceCap = $derived(
    weakestStarter ? (weakestStarter.price ?? 0) + (manager?.bank ?? 0) : 0
  );

  let hhiLabel = $derived(exposure?.hhi_label ?? '');
</script>

<div class="runway">
  <div class="runway-top">
    <div class="runway-stat">
      <span class="rs-label">Free transfers</span>
      <span class="rs-val mono">{freeTransfers}</span>
    </div>
    <div class="runway-stat">
      <span class="rs-label">In the bank</span>
      <span class="rs-val mono">£{manager?.bank?.toFixed(1) ?? '—'}m</span>
    </div>
    <div class="runway-stat">
      <span class="rs-label">Team value</span>
      <span class="rs-val mono">£{manager?.team_value?.toFixed(1) ?? '—'}m</span>
    </div>
  </div>

  <div class="runway-notes">
    <p>
      <strong>Capital.</strong>
      You can move <span class="accent">{freeTransfers} player{freeTransfers === 1 ? '' : 's'}</span>
      this week without taking a hit.
      {#if weakestStarter}
        The weakest slot is <span class="mono">{weakestStarter.web_name}</span>
        at {weakestStarter.ep_next?.toFixed(1) ?? '—'} EP, giving you a live replacement cap of
        <span class="mono">£{priceCap.toFixed(1)}m</span>.
      {/if}
    </p>

    <p>
      <strong>Shape.</strong>
      {hhiLabel}. Prioritize swaps that reduce the biggest variance bucket, not just marginal EP bumps.
    </p>

    <p class="runway-cta">
      <Icon.Swap size={12} />
      <a href="/transfers">Open the planner</a>
      to see ranked replacements and live portfolio deltas.
    </p>
  </div>
</div>

<style>
  .runway { display: flex; flex-direction: column; gap: 0.85rem; }

  .runway-top {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.6rem;
  }
  .runway-stat {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.7rem 0.85rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .rs-label {
    font-family: var(--mono);
    font-size: 0.58rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .rs-val {
    font-family: var(--heading);
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text-heading);
    letter-spacing: -0.02em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .runway-notes {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    font-size: 0.8rem;
    line-height: 1.5;
    color: var(--text-secondary);
    padding: 0.15rem 0;
  }
  .runway-notes p { margin: 0; }
  .runway-notes strong {
    display: inline-block;
    font-family: var(--heading);
    font-weight: 700;
    color: var(--text-heading);
    margin-right: 0.3rem;
  }
  .runway-notes .accent {
    color: var(--accent-text);
    font-weight: 600;
  }
  .runway-cta {
    padding-top: 0.45rem;
    border-top: 1px dashed var(--border);
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .runway-cta a {
    color: var(--accent-text);
    text-decoration: none;
    font-weight: 600;
    border-bottom: 1px solid currentColor;
  }
  .runway-cta a:hover { color: var(--accent); }

  @media (max-width: 700px) {
    .runway-top { grid-template-columns: 1fr; }
  }

  :global([data-theme="pixel"]) .runway-stat {
    border: 3px solid #1a1a2e;
    background: #fffaf0;
    border-radius: 0 !important;
  }
  :global([data-theme="pixel"]) .rs-label {
    font-family: 'Press Start 2P', monospace;
    font-size: 6px;
  }
  :global([data-theme="pixel"]) .rs-val {
    font-family: 'Press Start 2P', monospace;
    font-size: 12px;
    text-shadow: 2px 2px 0 var(--yellow);
  }
  :global([data-theme="pixel"]) .runway-notes {
    font-family: 'VT323', monospace;
    font-size: 16px;
  }
  :global([data-theme="pixel"]) .runway-notes strong {
    font-family: 'Press Start 2P', monospace;
    font-size: 7px;
    text-transform: uppercase;
  }
</style>
