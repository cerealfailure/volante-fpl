<!--
  Hoverable stat labels with plain-English explanations.
  Use: <StatExplainer term="xGI" /> anywhere you show a stat.

  Tooltip positioning: we render the popover with `position: fixed`
  and compute coordinates from the trigger's bounding rect on hover.
  This means the tooltip always escapes any ancestor `overflow: hidden`
  or `overflow: auto` — the previous version was getting clipped by
  the player-detail card's scroll container.
-->
<script lang="ts">
  let { term, inline = false }: { term: string, inline?: boolean } = $props();

  const glossary: Record<string, { short: string, long: string }> = {
    'xG':     { short: 'Expected Goals',                long: 'The quality of chances a player has had. xG of 5.0 means their chances were worth ~5 goals on average.' },
    'xA':     { short: 'Expected Assists',              long: 'The quality of chances a player has created for teammates. Higher = better chance creator.' },
    'xGI':    { short: 'Expected Goal Involvement',     long: 'xG + xA combined. The best single stat for measuring attacking output quality. High xGI + low goals/assists = unlucky and likely to improve.' },
    'xGC':    { short: 'Expected Goals Conceded',       long: 'Quality of chances conceded while they were on the pitch. Lower = better defence.' },
    'EP':     { short: 'Expected Points',               long: "FPL's own prediction of points for the next gameweek. Based on form, fixtures, and historical data." },
    'ICT':    { short: 'Influence + Creativity + Threat', long: "FPL's composite index. Influence = impact on outcomes. Creativity = chance creation. Threat = goal threat. Higher = more involved." },
    'HHI':    { short: 'Herfindahl-Hirschman Index',    long: 'Measures team concentration. 0.05 = spread across teams. Above 0.15 = concentrated. Like too much of a portfolio in one stock.' },
    'ENB':    { short: 'Effective Number of Outcomes',  long: "How many independent outcomes your team rides on. ENB of 5 means your 11 players behave like 5 independent picks." },
    'StdDev': { short: 'Standard Deviation',            long: "How volatile your weekly score is. High = amazing AND terrible weeks. Low = more consistent." },
    'DR':     { short: 'Diversification Ratio',         long: 'How well your players hedge each other. Higher = more diversified. 1.0 = acts like one player. 3.0+ = good spread.' },
    'Form':   { short: 'Recent Form',                   long: 'Average points per game over the last 30 days. Best indicator of current performance. Reverts to mean eventually.' },
    'FDR':    { short: 'Fixture Difficulty Rating',     long: '1 (easiest) to 5 (hardest). Based on opponent strength. Stack players with green runs.' },
    'Own%':   { short: 'Ownership Percentage',          long: 'What % of all FPL managers own this player. High = template. Low = differential. Differentials move your rank — both ways.' },
    'BPS':    { short: 'Bonus Points System',           long: 'Hidden scoring awarding 3-2-1 bonus to the best performers each match. Defenders get BPS from tackles/clearances, attackers from goals/assists.' },
    'CS':     { short: 'Clean Sheets',                  long: 'Team concedes 0 goals. Worth 4pts for DEF/GK, 1pt for MID. Same-team defenders share CS fate — perfectly correlated.' },
    'Correlation': { short: 'Return Correlation (ρ)',   long: 'How much two players\' weekly points move together. +1 = always rise together. 0 = independent. -1 = a natural hedge.' },
  };

  let entry = $derived(glossary[term]);
  let showTip = $state(false);
  let tipX = $state(0);
  let tipY = $state(0);
  let tipFlipUp = $state(true);
  let triggerEl = $state<HTMLButtonElement | undefined>();

  function open() {
    if (!triggerEl) return;
    const rect = triggerEl.getBoundingClientRect();
    const tipW = Math.min(300, window.innerWidth - 16);
    const tipH = 110;
    // Horizontal: centre on trigger, clamp to viewport
    let x = rect.left + rect.width / 2;
    const minX = 8 + tipW / 2;
    const maxX = window.innerWidth - 8 - tipW / 2;
    x = Math.max(minX, Math.min(maxX, x));
    // Account for mobile bottom nav (~70px) and sticky header (~56px)
    const headerH = 56;
    const bottomNavH = window.innerWidth < 920 ? 70 : 0;
    const safeTop = headerH + 8;
    const safeBottom = window.innerHeight - bottomNavH - 8;
    const spaceAbove = rect.top - safeTop;
    const spaceBelow = safeBottom - rect.bottom;
    // Prefer above if enough room, otherwise below
    tipFlipUp = spaceAbove >= tipH;
    if (!tipFlipUp && spaceBelow < tipH) {
      // Neither direction has room — pick the bigger one
      tipFlipUp = spaceAbove > spaceBelow;
    }
    let y: number;
    if (tipFlipUp) {
      // tooltip renders upward from y (transform: translate(-50%, -100%))
      y = rect.top - 8;
      if (y - tipH < safeTop) y = safeTop + tipH;
    } else {
      // tooltip renders downward from y (transform: translate(-50%, 0))
      y = rect.bottom + 8;
      if (y + tipH > safeBottom) y = safeBottom - tipH;
    }
    tipX = x;
    tipY = y;
    showTip = true;
    lastOpenTime = Date.now();
  }
  function close() { showTip = false; }
  let lastOpenTime = 0;
  function toggle(e: Event) {
    e.stopPropagation();
    // If mouseenter just opened it (within 200ms), don't close on click
    const now = Date.now();
    if (showTip && now - lastOpenTime > 200) {
      close();
    } else if (!showTip) {
      open();
    }
  }

  // Portal: a sibling .reveal-animated ancestor creates a stacking context
  // (even with fill:both, Chrome keeps a compositing layer) that traps the
  // fixed tooltip behind later page sections. Re-parent to <body> so
  // z-index:9500 applies in the root stacking context.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return {
      destroy() {
        if (node.parentNode) node.parentNode.removeChild(node);
      }
    };
  }
</script>

{#if entry}
  <button
    type="button"
    bind:this={triggerEl}
    class="explainer"
    class:inline
    onmouseenter={open}
    onmouseleave={close}
    onclick={toggle}
    onfocusin={open}
    onfocusout={close}
    aria-label={`Explain ${term}`}
  >
    <span class="ex-term">{term}</span>
    <span class="ex-q">?</span>
  </button>
  {#if showTip}
    <div
      class="ex-tip"
      class:flip-down={!tipFlipUp}
      style="left: {tipX}px; top: {tipY}px;"
      role="tooltip"
      use:portal
    >
      <strong>{entry.short}</strong>
      <p>{entry.long}</p>
    </div>
  {/if}
{:else}
  <span>{term}</span>
{/if}

<style>
  .explainer {
    appearance: none;
    background: transparent;
    border: 0;
    padding: 0;
    margin: 0;
    position: relative;
    cursor: help;
    display: inline-flex;
    align-items: center;
    gap: 0.2rem;
    color: inherit;
    font: inherit;
    text-align: inherit;
  }
  .explainer.inline { display: inline; }
  .ex-term { border-bottom: 1px dotted var(--text-muted); }
  .ex-q {
    font-size: 0.5rem;
    font-weight: 700;
    color: var(--accent);
    background: var(--accent-soft);
    width: 0.85rem;
    height: 0.85rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* Tooltip uses position:fixed so it escapes ancestor overflow clipping.
     Coordinates are set inline from $effect of the trigger's bounding rect. */
  .ex-tip {
    position: fixed;
    transform: translate(-50%, -100%);
    background: #132e24;
    border: 1px solid rgba(0, 255, 156, 0.25);
    border-radius: var(--radius-sm);
    padding: 0.65rem 0.8rem;
    width: 300px;
    max-width: calc(100vw - 16px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(0, 255, 156, 0.1);
    z-index: 9500;
    font-size: 0.76rem;
    line-height: 1.5;
    pointer-events: none;
  }
  .ex-tip.flip-down {
    transform: translate(-50%, 0);
  }
  .ex-tip strong {
    display: block;
    color: var(--accent-text);
    font-size: 0.7rem;
    margin-bottom: 0.2rem;
  }
  .ex-tip p {
    color: var(--text-secondary);
    margin: 0;
  }

  /* Pixel theme: bitmap font + chunky frame */
  :global([data-theme="pixel"]) .ex-tip {
    background: #f4eede !important;
    border: 3px solid #1a1a2e !important;
    box-shadow: 4px 4px 0 #1a1a2e !important;
    border-radius: 0 !important;
    font-family: 'VT323', monospace !important;
    font-size: 15px !important;
    color: #1a1a2e !important;
  }
  :global([data-theme="pixel"]) .ex-tip strong {
    font-family: 'Press Start 2P', monospace !important;
    font-size: 7px !important;
    color: var(--accent) !important;
  }
  :global([data-theme="pixel"]) .ex-q {
    background: var(--accent) !important;
    color: #f4eede !important;
    border-radius: 0 !important;
    font-family: 'Press Start 2P', monospace !important;
    font-size: 5px !important;
  }
</style>
