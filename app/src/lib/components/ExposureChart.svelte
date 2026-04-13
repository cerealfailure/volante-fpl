<!--
  Team exposure breakdown — horizontal bars showing
  weight % and variance % per team.
  Sorted by variance contribution (what actually matters).
-->
<script lang="ts">
  let { concentration }: { concentration: Record<string, any> } = $props();

  let entries = $derived(
    Object.entries(concentration)
      .map(([id, c]) => ({ id, ...c }))
      .sort((a, b) => b.variance_pct - a.variance_pct)
  );

  let maxVar = $derived(Math.max(...entries.map(e => e.variance_pct), 1));

  // team kit color approximations
  const teamColors: Record<string, string> = {
    ARS: '#ef0107', CHE: '#034694', LIV: '#c8102e', MCI: '#6cabdd',
    MUN: '#da291c', TOT: '#132257', NEW: '#241f20', AVL: '#670e36',
    BHA: '#0057b8', WHU: '#7a263a', BOU: '#da291c', FUL: '#000000',
    WOL: '#fdb913', BRE: '#e30613', EVE: '#003399', NFO: '#dd0000',
    CRY: '#1b458f', IPS: '#0033a0', LEI: '#003090', SOU: '#d71920',
    BUR: '#6c1d45', LEE: '#1d428a', LUT: '#f78f1e',
  };

  function barColor(short: string): string {
    return teamColors[short] || 'var(--gold)';
  }
</script>

<div class="exposure-chart">
  {#each entries as entry}
    <div class="exposure-row">
      <div class="team-label">
        <span class="team-short mono" style="color: {barColor(entry.team_short)}">{entry.team_short}</span>
        <span class="player-count dim2">{entry.player_count}p</span>
      </div>
      <div class="bars">
        <div class="bar-track">
          <div class="bar-fill var-bar" style="width: {(entry.variance_pct / maxVar) * 100}%; background: {barColor(entry.team_short)}">
          </div>
        </div>
        <div class="bar-labels">
          <span class="mono">{entry.variance_pct.toFixed(1)}%</span>
          <span class="dim2 small">var</span>
          <span class="dim2">·</span>
          <span class="dim2 mono small">{entry.weight_pct.toFixed(0)}% wt</span>
        </div>
      </div>
      <div class="players-list dim2 small">{entry.players.join(', ')}</div>
    </div>
  {/each}
</div>

<style>
  .exposure-chart {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .exposure-row {
    display: grid;
    grid-template-columns: 4.5rem 1fr;
    grid-template-rows: auto auto;
    gap: 0.15rem 0.5rem;
    align-items: center;
  }
  .team-label {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .team-short {
    font-weight: 600;
    font-size: 0.8rem;
  }
  .player-count {
    font-size: 0.65rem;
  }
  .bars {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .bar-track {
    flex: 1;
    height: 16px;
    background: var(--bg-elevated);
    border-radius: 3px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.4s ease;
    min-width: 2px;
    opacity: 0.7;
  }
  .bar-labels {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    min-width: 7rem;
    flex-shrink: 0;
  }
  .players-list {
    grid-column: 2;
    line-height: 1.3;
  }
</style>
