<!--
  Correlation heatmap — readable at any squad size.
  Names truncated to fit, cells sized dynamically.
  Bottom tooltip bar instead of floating overlay.
-->
<script lang="ts">
  let { matrix, names, players, selectedPair = null }: {
    matrix: number[][],
    names: string[],
    players: any[],
    selectedPair?: { playerA: string; playerB: string } | null
  } = $props();

  let hovered: { i: number, j: number } | null = $state(null);
  let selectedIndices = $derived.by(() => {
    if (!selectedPair) return [];
    return names
      .map((name, index) => ({ name, index }))
      .filter(({ name }) => name === selectedPair.playerA || name === selectedPair.playerB)
      .map(({ index }) => index);
  });

  function isSelectedCell(i: number, j: number) {
    if (selectedIndices.length !== 2) return false;
    return (
      (i === selectedIndices[0] && j === selectedIndices[1]) ||
      (i === selectedIndices[1] && j === selectedIndices[0])
    );
  }

  function corrColor(v: number): string {
    const c = Math.max(-1, Math.min(1, v));
    if (c >= 0) {
      const t = c;
      return `rgb(${Math.round(30 + 194 * t)},${Math.round(30 + 50 * (1 - t))},${Math.round(50 + 30 * (1 - t))})`;
    } else {
      const t = -c;
      return `rgb(${Math.round(30 + 34 * (1 - t))},${Math.round(30 + 98 * t)},${Math.round(50 + 190 * t)})`;
    }
  }

  function shortName(name: string): string {
    if (name.length <= 8) return name;
    return name.slice(0, 7) + '.';
  }

  function corrLabel(v: number): string {
    if (v > 0.4) return 'Strong +';
    if (v > 0.2) return 'Moderate +';
    if (v > 0.05) return 'Weak +';
    if (v > -0.05) return 'Near zero';
    if (v > -0.2) return 'Weak -';
    if (v > -0.4) return 'Moderate -';
    return 'Strong -';
  }
</script>

<div class="corr-wrap">
  <!-- Grid table approach — much more readable than SVG -->
  <div class="corr-grid" style="grid-template-columns: 5rem repeat({names.length}, 1fr);">
    <!-- Header row -->
    <div class="corr-corner"></div>
    {#each names as name, j}
      <div
        class="corr-col-label"
        class:hovered-col={hovered?.j === j}
        class:selected-axis={selectedIndices.includes(j)}
      >
        <span>{shortName(name)}</span>
      </div>
    {/each}

    <!-- Data rows -->
    {#each names as rowName, i}
      <div
        class="corr-row-label"
        class:hovered-row={hovered?.i === i}
        class:selected-axis={selectedIndices.includes(i)}
      >
        {shortName(rowName)}
      </div>
      {#each matrix[i] as val, j}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          class="corr-cell"
          class:diagonal={i === j}
          class:hovered={hovered?.i === i && hovered?.j === j}
          class:selected={isSelectedCell(i, j)}
          style="background: {i === j ? 'var(--bg-elevated)' : corrColor(val)};"
          onmouseenter={() => hovered = { i, j }}
          onmouseleave={() => hovered = null}
        >
          {#if i === j}
            <span class="cell-val dim2">—</span>
          {:else}
            <span class="cell-val" style="color: {Math.abs(val) > 0.25 ? '#eaeaf2' : '#888'};">
              {val > 0 ? '+' : ''}{val.toFixed(2)}
            </span>
          {/if}
        </div>
      {/each}
    {/each}
  </div>

  <!-- Info bar -->
  <div class="corr-info">
    {#if hovered && hovered.i !== hovered.j}
      <span class="mono">{names[hovered.i]}</span>
      <span class="dim2">&harr;</span>
      <span class="mono">{names[hovered.j]}</span>
      <span class="badge {matrix[hovered.i][hovered.j] > 0.3 ? 'badge-red' : matrix[hovered.i][hovered.j] < -0.1 ? 'badge-blue' : 'badge-accent'}">
        &rho; = {matrix[hovered.i][hovered.j] > 0 ? '+' : ''}{matrix[hovered.i][hovered.j].toFixed(3)}
      </span>
      <span class="dim2 small">{corrLabel(matrix[hovered.i][hovered.j])}</span>
      {#if players[hovered.i]?.team_short === players[hovered.j]?.team_short}
        <span class="badge badge-yellow">Same team</span>
      {/if}
    {:else}
      <span class="dim2 small">Hover a cell to see correlation detail. Positive = boom/bust together. Negative = natural hedge.</span>
    {/if}
  </div>

  <!-- Legend -->
  <div class="corr-legend">
    <span class="small" style="color: {corrColor(-0.6)};">-1 (hedge)</span>
    <div class="legend-bar">
      <div class="lb" style="background: {corrColor(-0.6)};"></div>
      <div class="lb" style="background: {corrColor(-0.3)};"></div>
      <div class="lb" style="background: {corrColor(0)};"></div>
      <div class="lb" style="background: {corrColor(0.3)};"></div>
      <div class="lb" style="background: {corrColor(0.6)};"></div>
    </div>
    <span class="small" style="color: {corrColor(0.6)};">+1 (correlated)</span>
  </div>
</div>

<style>
  .corr-wrap { overflow-x: auto; }
  .corr-grid {
    display: grid;
    gap: 1px;
    font-size: 0.7rem;
  }
  .corr-corner { background: transparent; }
  .corr-col-label {
    display: flex; align-items: flex-end; justify-content: center;
    padding: 0.2rem 0.1rem;
    font-family: var(--mono); font-size: 0.58rem; font-weight: 500;
    color: var(--text-secondary);
    text-align: center; word-break: break-all;
    transition: color var(--duration);
  }
  .corr-col-label.hovered-col { color: var(--accent-text); }
  .corr-col-label.selected-axis { color: var(--text-heading); }
  .corr-row-label {
    display: flex; align-items: center;
    padding: 0.2rem 0.3rem;
    font-family: var(--mono); font-size: 0.62rem; font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: color var(--duration);
  }
  .corr-row-label.hovered-row { color: var(--accent-text); }
  .corr-row-label.selected-axis { color: var(--text-heading); }

  .corr-cell {
    display: flex; align-items: center; justify-content: center;
    aspect-ratio: 1;
    border-radius: 3px;
    cursor: crosshair;
    transition: transform var(--duration), box-shadow var(--duration);
    min-height: 2rem;
  }
  .corr-cell.hovered { transform: scale(1.1); box-shadow: var(--shadow-glow); z-index: 2; }
  .corr-cell.selected {
    transform: scale(1.06);
    box-shadow: 0 0 0 2px var(--accent), var(--shadow-glow);
    z-index: 3;
  }
  .corr-cell.diagonal { cursor: default; }
  .cell-val { font-family: var(--mono); font-size: 0.6rem; font-weight: 500; }

  .corr-info {
    display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
    padding: 0.5rem 0.25rem;
    min-height: 2rem;
    font-size: 0.78rem;
  }

  .corr-legend {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.25rem 0;
  }
  .legend-bar { display: flex; gap: 1px; }
  .lb { width: 2rem; height: 6px; border-radius: 2px; }
</style>
