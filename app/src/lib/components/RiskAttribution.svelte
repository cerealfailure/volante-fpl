<!--
  Risk Attribution — shows where your variance actually comes from
  by team. It's the "who really decides my week" chart.

  Reuses data.exposure.team_concentration which already has
  variance_pct (a team's share of total portfolio variance), and
  adds plain-English interpretation.
-->
<script lang="ts">
  import { kitFor } from '$lib/teamColors';

  let {
    concentration,
  }: {
    concentration: Record<string, any>;
  } = $props();

  let entries = $derived(
    Object.entries(concentration)
      .map(([id, c]: any) => ({ id, ...c }))
      .sort((a: any, b: any) => b.variance_pct - a.variance_pct)
      .slice(0, 6)
  );

  let top = $derived(entries[0]);

  let verdict = $derived.by(() => {
    if (!top) return { tone: 'dim2', text: 'No exposure detected.' };
    if (top.variance_pct > 40) {
      return {
        tone: 'negative',
        text: `${top.team_short} drives ${top.variance_pct.toFixed(0)}% of your variance. That club is effectively running the week.`,
      };
    }
    if (top.variance_pct > 25) {
      return {
        tone: 'warning',
        text: `${top.team_short} is the main variance bucket at ${top.variance_pct.toFixed(0)}%. Manage the next fixture run carefully.`,
      };
    }
    return {
      tone: 'positive',
      text: `Variance is spread across ${entries.length} clubs. No single team owns the week.`,
    };
  });
</script>

<div class="ra">
  <div class="ra-stack">
    {#each entries as e}
      {@const kit = kitFor(e.team_short)}
      <div
        class="ra-seg"
        style="flex: {e.variance_pct}; background: {kit.primary};"
        title="{e.team_name}: {e.variance_pct.toFixed(1)}% of variance from {e.player_count} player(s)"
      >
        {#if e.variance_pct > 8}
          <span class="ra-seg-label mono">{e.team_short}</span>
        {/if}
      </div>
    {/each}
  </div>

  <ul class="ra-legend">
    {#each entries as e}
      {@const kit = kitFor(e.team_short)}
      <li>
        <span class="ra-dot" style="background: {kit.primary}"></span>
        <span class="ra-t mono">{e.team_short}</span>
        <span class="ra-players dim2">{e.players.join(', ')}</span>
        <span class="ra-pct mono">{e.variance_pct.toFixed(1)}%</span>
      </li>
    {/each}
  </ul>

  <p class="ra-verdict {verdict.tone}">
    {verdict.text}
  </p>
</div>

<style>
  .ra { display: flex; flex-direction: column; gap: 0.75rem; }

  .ra-stack {
    display: flex;
    height: 26px;
    border: 1px solid var(--border);
    border-radius: 3px;
    overflow: hidden;
  }
  .ra-seg {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 0;
    border-right: 1px solid rgba(0,0,0,0.35);
    position: relative;
  }
  .ra-seg:last-child { border-right: none; }
  .ra-seg-label {
    font-size: 0.6rem;
    font-weight: 700;
    color: rgba(255,255,255,0.95);
    text-shadow: 0 1px 2px rgba(0,0,0,0.7);
  }

  .ra-legend {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.28rem;
  }
  .ra-legend li {
    display: grid;
    grid-template-columns: 0.75rem 2.6rem minmax(0, 1fr) 3.2rem;
    gap: 0.5rem;
    align-items: center;
    font-size: 0.75rem;
  }
  .ra-dot {
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 2px;
    border: 1px solid rgba(0,0,0,0.4);
  }
  .ra-t {
    font-weight: 700;
    color: var(--text);
  }
  .ra-players {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 0.72rem;
  }
  .ra-pct {
    text-align: right;
    font-weight: 700;
    color: var(--text-heading);
    font-variant-numeric: tabular-nums;
  }

  .ra-verdict {
    font-size: 0.76rem;
    line-height: 1.45;
    padding: 0.55rem 0.7rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--bg-elevated) 90%, transparent);
    border-left: 3px solid var(--border);
    margin: 0;
  }
  .ra-verdict.positive { border-left-color: var(--accent); }
  .ra-verdict.warning  { border-left-color: var(--yellow); }
  .ra-verdict.negative { border-left-color: var(--red); }

  :global([data-theme="pixel"]) .ra-stack {
    height: 20px;
    border: 3px solid #1a1a2e;
    border-radius: 0 !important;
  }
  :global([data-theme="pixel"]) .ra-seg {
    border-right: 2px solid #1a1a2e;
  }
  :global([data-theme="pixel"]) .ra-legend li {
    font-family: 'VT323', monospace;
    font-size: 15px;
  }
  :global([data-theme="pixel"]) .ra-t,
  :global([data-theme="pixel"]) .ra-pct {
    font-family: 'Press Start 2P', monospace;
    font-size: 7px;
  }
  :global([data-theme="pixel"]) .ra-dot {
    border-radius: 0 !important;
    border: 2px solid #1a1a2e;
  }
  :global([data-theme="pixel"]) .ra-verdict {
    font-family: 'VT323', monospace;
    font-size: 16px;
    background: #fffaf0;
    border: 3px solid #1a1a2e;
    border-left-width: 6px;
    border-radius: 0 !important;
  }
</style>
