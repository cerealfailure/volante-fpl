<!--
  Position Sizing — shows each starter as a horizontal bar sized
  by their share of total expected points, coloured by team kit.
  Captain weight is doubled (as it is in FPL scoring). Gives an
  at-a-glance answer to "how concentrated is my lineup?"
-->
<script lang="ts">
  import { kitFor } from '$lib/teamColors';
  import * as Icon from '$lib/components/icons';

  let {
    players,
    onPlayerClick,
  }: {
    players: any[];
    onPlayerClick?: (p: any) => void;
  } = $props();

  // Effective weight = ep_next, doubled for captain
  let rows = $derived.by(() => {
    const withWeight = players.map((p: any) => ({
      ...p,
      _w: (p.ep_next ?? 0) * (p.is_captain ? 2 : 1),
    }));
    const total = withWeight.reduce((s: number, p: any) => s + p._w, 0) || 1;
    return withWeight
      .map((p: any) => ({ ...p, _pct: (p._w / total) * 100 }))
      .sort((a: any, b: any) => b._pct - a._pct);
  });

  // Max value used for bar width
  let maxPct = $derived(rows.length > 0 ? rows[0]._pct : 0);
</script>

<div class="sizing">
  {#each rows as p (p.id)}
    {@const kit = kitFor(p.team_short)}
    <button type="button" class="ps-row" onclick={() => onPlayerClick?.(p)}>
      <div class="ps-meta">
        <span class="ps-name">
          {p.web_name}
          {#if p.is_captain}
            <span class="ps-cap" title="Captain — weight doubled">C</span>
          {:else if p.is_vice_captain}
            <span class="ps-cap vc" title="Vice-captain">V</span>
          {/if}
        </span>
        <span class="ps-sub">
          <span class="mono" style="color: {kit.primary}">{p.team_short}</span>
          <span class="dim2">·</span>
          <span class="dim2">{p.position}</span>
        </span>
      </div>
      <div class="ps-bar-wrap">
        <div
          class="ps-bar"
          style="width: {(p._pct / maxPct) * 100}%; background: linear-gradient(90deg, {kit.primary}, {kit.primary}cc);"
        ></div>
      </div>
      <span class="ps-val mono">{p._pct.toFixed(1)}%</span>
    </button>
  {/each}
</div>

<style>
  .sizing {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
  }
  .ps-row {
    display: grid;
    grid-template-columns: 8rem minmax(0, 1fr) 3rem;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.28rem 0.35rem;
    border-radius: var(--radius-sm);
    background: transparent;
    cursor: pointer;
    text-align: left;
    transition: background var(--duration) var(--ease);
  }
  .ps-row:hover { background: var(--bg-elevated); }

  .ps-meta {
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
    min-width: 0;
    overflow: hidden;
  }
  .ps-name {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .ps-cap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 0.95rem;
    height: 0.95rem;
    background: var(--yellow);
    color: #1a1a2e;
    font-size: 0.58rem;
    font-weight: 800;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .ps-cap.vc { background: var(--text-muted); }
  .ps-sub {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.62rem;
  }

  .ps-bar-wrap {
    height: 12px;
    background: var(--bg-elevated);
    border-radius: 2px;
    overflow: hidden;
    border: 1px solid var(--border);
  }
  .ps-bar {
    height: 100%;
    border-radius: 1px;
    transition: width var(--duration) var(--ease);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.15);
  }

  .ps-val {
    font-size: 0.82rem;
    font-weight: 800;
    color: var(--text-heading);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  :global([data-theme="pixel"]) .ps-row {
    padding: 4px;
    border: 2px solid #1a1a2e;
    background: #f4eede;
    margin-bottom: 2px;
    border-radius: 0 !important;
  }
  :global([data-theme="pixel"]) .ps-bar-wrap {
    border: 2px solid #1a1a2e;
    border-radius: 0 !important;
    height: 14px;
  }
  :global([data-theme="pixel"]) .ps-name {
    font-family: 'Press Start 2P', monospace;
    font-size: 7px;
  }
  :global([data-theme="pixel"]) .ps-sub,
  :global([data-theme="pixel"]) .ps-val {
    font-family: 'Press Start 2P', monospace;
    font-size: 6px;
  }
</style>
