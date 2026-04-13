<!--
  Fixture outlook — horizontal strip per player showing
  next 6 GWs color-coded by difficulty.
  Green (easy) → grey (medium) → red (hard).
-->
<script lang="ts">
  let { outlook, currentEvent }: { outlook: any[], currentEvent: number } = $props();

  // collect all unique upcoming GW numbers across all players
  let gwNumbers = $derived.by(() => {
    const gws = new Set<number>();
    for (const p of outlook) {
      for (const f of p.fixtures) gws.add(f.event);
    }
    return [...gws].sort((a, b) => a - b).slice(0, 6);
  });

  function fdrClass(difficulty: number | null): string {
    if (difficulty == null) return '';
    if (difficulty <= 1) return 'fdr-1';
    if (difficulty <= 2) return 'fdr-2';
    if (difficulty <= 3) return 'fdr-3';
    if (difficulty <= 4) return 'fdr-4';
    return 'fdr-5';
  }
</script>

<div class="fixture-strip">
  <table>
    <thead>
      <tr>
        <th class="player-col">Player</th>
        <th class="pos-col">Pos</th>
        {#each gwNumbers as gw}
          <th class="gw-col">GW{gw}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each outlook as player}
        <tr>
          <td class="player-col">
            <span class="player-name">{player.web_name}</span>
          </td>
          <td class="pos-col dim2">{player.pos}</td>
          {#each gwNumbers as gw}
            {@const fix = player.fixtures.find((f: any) => f.event === gw)}
            <td class="gw-col">
              {#if fix}
                <span class="fixture-cell {fdrClass(fix.difficulty)}">
                  <span class="opp">{fix.is_home ? '' : '@'}{fix.opponent}</span>
                </span>
              {:else}
                <span class="fixture-cell blank">—</span>
              {/if}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .fixture-strip {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
  }
  th {
    text-align: center;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    padding: 0.4rem 0.35rem;
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 0.35rem;
    border-bottom: 1px solid var(--border);
  }
  .player-col { text-align: left; min-width: 5.5rem; padding-left: 0.5rem; }
  .pos-col { text-align: center; width: 2.5rem; }
  .gw-col { text-align: center; width: 4.5rem; }

  .fixture-cell {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.22rem 0.42rem;
    border-radius: 4px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 600;
    min-width: 3.2rem;
  }
  .fixture-cell.blank { color: var(--text-muted); }

  .fdr-1 { background: rgba(64, 192, 128, 0.2); color: var(--fdr-1); }
  .fdr-2 { background: rgba(96, 208, 144, 0.15); color: var(--fdr-2); }
  .fdr-3 { background: rgba(148, 179, 166, 0.12); color: var(--text-secondary); }
  .fdr-4 { background: rgba(224, 160, 48, 0.15); color: var(--fdr-4); }
  .fdr-5 { background: rgba(224, 80, 80, 0.2); color: var(--fdr-5); }

  .player-name { font-weight: 500; }
  tr:hover { background: color-mix(in srgb, var(--bg-card-hover) 92%, transparent); }
</style>
