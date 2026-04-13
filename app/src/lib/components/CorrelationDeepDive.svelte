<script lang="ts">
  type Attribution = {
    lookback: number;
    concentration_context?: Array<{
      severity: 'high' | 'medium' | 'info';
      title: string;
      detail: string;
      recommendation?: string;
    }>;
    weeks?: Array<{
      event: number;
      total_points: number;
      captain_name: string;
      captain_pts: number;
      team_stacks?: Array<{
        team_short: string;
        count: number;
        total_pts: number;
        verdict: 'boom' | 'bust' | 'neutral';
        explanation: string;
      }>;
      position_breakdown: {
        GK: { total: number };
        DEF: { total: number };
        MID: { total: number };
        FWD: { total: number };
      };
    }>;
    patterns?: Array<{
      type: 'positive' | 'negative' | 'info';
      title: string;
      detail: string;
    }>;
    explanations?: Array<{
      player_a: string;
      player_b: string;
      rho: number;
      explanation: string;
      same_team: boolean;
    }>;
  };

  let {
    attribution = null,
    lookback = 10,
    onLookbackChange,
    onPairSelect,
    selectedPair = null,
  }: {
    attribution: Attribution | null;
    lookback?: number | null;
    onLookbackChange?: (value: number | null) => void;
    onPairSelect?: (pair: { playerA: string; playerB: string }) => void;
    selectedPair?: { playerA: string; playerB: string } | null;
  } = $props();

  const lookbackOptions = [
    { label: 'Last 5', value: 5 },
    { label: 'Last 10', value: 10 },
    { label: 'Last 15', value: 15 },
    { label: 'Season', value: null },
  ] as const;
  const positionLabels = ['GK', 'DEF', 'MID', 'FWD'] as const;

  function pairKey(playerA: string, playerB: string) {
    return [playerA, playerB].sort().join('::');
  }

  let selectedPairKey = $derived(
    selectedPair ? pairKey(selectedPair.playerA, selectedPair.playerB) : ''
  );

  function verdictClass(verdict: string) {
    if (verdict === 'boom') return 'positive';
    if (verdict === 'bust') return 'negative';
    return 'dim2';
  }

  function patternClass(type: string) {
    if (type === 'positive') return 'positive';
    if (type === 'negative') return 'negative';
    return 'accent';
  }

  function signedRho(rho: number) {
    return `${rho > 0 ? '+' : ''}${rho.toFixed(2)}`;
  }
</script>

<div class="cdd-root">
  <div class="cdd-lookback-picker">
    {#each lookbackOptions as option}
      <button
        type="button"
        class="cdd-lookback"
        class:active={lookback === option.value}
        onclick={() => onLookbackChange?.(option.value)}
      >
        {option.label}
      </button>
    {/each}
  </div>

  {#if attribution?.concentration_context?.length}
    <div class="cdd-context">
      {#each attribution.concentration_context as item}
        <div class="cdd-context-row sev-{item.severity}">
          <div class="cdd-context-title">{item.title}</div>
          <div class="cdd-context-body">
            <span>{item.detail}</span>
            {#if item.recommendation}
              <em>{item.recommendation}</em>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  {#if attribution?.weeks?.length}
    <div class="cdd-weeks">
      {#each attribution.weeks as week}
        <article class="cdd-week">
          <header class="cdd-week-head">
            <div class="cdd-week-title">
              <span class="eyebrow">GW{week.event}</span>
              <span class="stat-value">{week.total_points}</span>
            </div>
            <div class="cdd-week-cap">
              <span class="stat-label">Captain</span>
              <span class="mono">{week.captain_name} · {week.captain_pts} pts</span>
            </div>
          </header>

          {#if week.team_stacks?.length}
            <div class="cdd-team-strip">
              {#each week.team_stacks as stack}
                <div class="cdd-team-chip verdict-{stack.verdict}">
                  <div class="cdd-team-top">
                    <span>{stack.team_short}</span>
                    <span class={verdictClass(stack.verdict)}>{stack.verdict}</span>
                  </div>
                  <div class="cdd-team-meta mono">{stack.count} picks · {stack.total_pts} pts</div>
                  <div class="cdd-team-note">{stack.explanation}</div>
                </div>
              {/each}
            </div>
          {/if}

          <div class="cdd-pos-row">
            {#each positionLabels as pos}
              <div class="cdd-pos-cell">
                <span class="stat-label">{pos}</span>
                <span class="mono">{week.position_breakdown[pos].total}</span>
              </div>
            {/each}
          </div>
        </article>
      {/each}
    </div>
  {/if}

  {#if attribution?.patterns?.length}
    <div class="cdd-patterns">
      {#each attribution.patterns as pattern}
        <div class="cdd-pattern {patternClass(pattern.type)}" title={pattern.detail}>
          {pattern.title}
        </div>
      {/each}
    </div>
  {/if}

  {#if attribution?.explanations?.length}
    <div class="cdd-pairs">
      <div class="cdd-pairs-head">
        <span class="eyebrow">Top pair links</span>
        <span class="dim2 small">Tap a row to hold the pair.</span>
      </div>
      {#each attribution.explanations as pair}
        <button
          type="button"
          class="cdd-pair-row"
          class:selected={selectedPairKey === pairKey(pair.player_a, pair.player_b)}
          onclick={() => onPairSelect?.({ playerA: pair.player_a, playerB: pair.player_b })}
        >
          <span class="cdd-pair-names">{pair.player_a} ↔ {pair.player_b}</span>
          <span class="cdd-pair-rho mono {pair.rho >= 0 ? 'negative' : 'positive'}">ρ={signedRho(pair.rho)}</span>
          <span class="cdd-pair-text">{pair.explanation}</span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .cdd-root {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }

  .cdd-lookback-picker {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid var(--border);
  }
  .cdd-lookback {
    padding: 0.45rem 0.8rem;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-family: var(--font);
    font-size: 0.82rem;
    font-weight: 600;
    position: relative;
  }
  .cdd-lookback:hover {
    background: var(--bg-elevated);
    color: var(--text);
  }
  .cdd-lookback.active {
    color: var(--accent-text);
  }
  .cdd-lookback.active::after {
    content: '';
    position: absolute;
    left: 0.55rem;
    right: 0.55rem;
    bottom: -0.32rem;
    height: 2px;
    background: var(--accent);
  }

  .cdd-context {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .cdd-context-row {
    display: grid;
    grid-template-columns: minmax(0, 12rem) minmax(0, 1fr);
    gap: 0.9rem;
    padding: 0.65rem 0.8rem;
    border-left: 3px solid var(--border);
    background: var(--bg-elevated);
    border-radius: var(--radius-sm);
  }
  .cdd-context-row.sev-high { border-left-color: var(--red); }
  .cdd-context-row.sev-medium { border-left-color: var(--yellow); }
  .cdd-context-row.sev-info { border-left-color: var(--accent); }
  .cdd-context-title {
    font-family: var(--heading);
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text-heading);
  }
  .cdd-context-body {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    color: var(--text-secondary);
    font-size: 0.84rem;
    line-height: 1.45;
  }
  .cdd-context-body em {
    color: var(--text);
    font-style: italic;
  }

  .cdd-weeks {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }
  .cdd-week {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.9rem;
  }
  .cdd-week-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 0.65rem;
  }
  .cdd-week-title {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .cdd-week-title .stat-value {
    font-size: 1.8rem;
  }
  .cdd-week-cap {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.15rem;
  }

  .cdd-team-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: 0.55rem;
    margin-bottom: 0.65rem;
  }
  .cdd-team-chip {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    padding: 0.65rem 0.7rem;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-elevated);
  }
  .cdd-team-chip.verdict-boom { border-color: rgba(0, 255, 156, 0.28); }
  .cdd-team-chip.verdict-bust { border-color: rgba(255, 61, 90, 0.28); }
  .cdd-team-top {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    font-family: var(--mono);
    font-size: 0.6rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .cdd-team-meta {
    font-size: 0.76rem;
    color: var(--text-heading);
  }
  .cdd-team-note {
    font-size: 0.78rem;
    line-height: 1.45;
    color: var(--text-secondary);
  }

  .cdd-pos-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.4rem;
  }
  .cdd-pos-cell {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    padding: 0.45rem 0.55rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }
  .cdd-pos-cell .mono {
    font-size: 0.88rem;
    font-weight: 700;
    color: var(--text-heading);
  }

  .cdd-patterns {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }
  .cdd-pattern {
    display: inline-flex;
    align-items: center;
    padding: 0.4rem 0.65rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    font-size: 0.76rem;
    line-height: 1.3;
  }

  .cdd-pairs {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .cdd-pairs-head {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: center;
  }
  .cdd-pair-row {
    display: grid;
    grid-template-columns: minmax(0, 12rem) 5.5rem minmax(0, 1fr);
    gap: 0.75rem;
    align-items: start;
    text-align: left;
    padding: 0.65rem 0.8rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: inherit;
  }
  .cdd-pair-row:hover {
    border-color: var(--border-hover);
    background: var(--bg-card-hover);
  }
  .cdd-pair-row.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .cdd-pair-names {
    font-family: var(--heading);
    font-weight: 700;
    letter-spacing: -0.015em;
    color: var(--text-heading);
  }
  .cdd-pair-rho {
    font-size: 0.78rem;
    font-weight: 700;
  }
  .cdd-pair-text {
    color: var(--text-secondary);
    font-size: 0.8rem;
    line-height: 1.45;
  }

  @media (max-width: 900px) {
    .cdd-context-row,
    .cdd-pair-row {
      grid-template-columns: 1fr;
    }
    .cdd-week-head,
    .cdd-pairs-head {
      flex-direction: column;
      align-items: flex-start;
    }
    .cdd-week-cap {
      align-items: flex-start;
    }
  }
</style>
