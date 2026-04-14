<!--
  Squad player chip — circular team-kit-colored tile with
  shirt number, surname, and expected points.
  Captain gets an armband corner; selected gets a glow.
-->
<script lang="ts">
  import { kitFor } from '$lib/teamColors';
  import * as Icon from '$lib/components/icons';

  let {
    player,
    selected = false,
    onclick,
    flipTip = false,
    averageEp = null,
  }: {
    player: any;
    selected?: boolean;
    onclick?: () => void;
    flipTip?: boolean;
    averageEp?: number | null;
  } = $props();

  let kit = $derived(kitFor(player.team_short));
  let chipEp = $derived(player.projected_ep_next ?? player.projected_ep ?? player.ep_next);

  // Fallback "shirt back" when squad_number isn't provided —
  // use first three chars of web_name, uppercase.
  let shirtText = $derived(
    player.squad_number != null
      ? String(player.squad_number)
      : (player.web_name ?? '').slice(0, 3).toUpperCase()
  );
  let epDelta = $derived(
    averageEp == null || chipEp == null ? null : chipEp - averageEp
  );
</script>

<button
  class="chip"
  class:selected
  class:captain={player.is_captain}
  class:vice={player.is_vice_captain}
  class:flip-tip={flipTip}
  onclick={() => onclick?.()}
  style="--kit-primary: {kit.primary}; --kit-secondary: {kit.secondary};"
  type="button"
>
  <span class="jersey" aria-hidden="true">
    <svg viewBox="0 0 32 32" class="jersey-svg">
      <!-- shoulders + body -->
      <path d="M6 7 L12 4 L13.5 6.5 Q16 8 18.5 6.5 L20 4 L26 7 L28 13 L23 14.5 L23 28 L9 28 L9 14.5 L4 13 Z"
            fill="var(--kit-primary)" stroke="rgba(0,0,0,0.55)" stroke-width="1.2" stroke-linejoin="round"/>
      <!-- stripe -->
      <path d="M13 8 L13 28 M19 8 L19 28" stroke="var(--kit-secondary)" stroke-width="2" opacity="0.9"/>
      <!-- number -->
      <text x="16" y="22" text-anchor="middle"
            font-family="'Bricolage Grotesque', system-ui, sans-serif"
            font-size={shirtText.length > 2 ? 7 : 11} font-weight="800"
            fill="var(--kit-secondary)"
            stroke="rgba(0,0,0,0.7)" stroke-width="0.4"
            paint-order="stroke">
        {shirtText}
      </text>
    </svg>
    {#if player.is_captain}
      <span class="armband" title="Captain">
        <Icon.Armband size={14} />
      </span>
    {/if}
    {#if player.is_vice_captain}
      <span class="armband vice" title="Vice-captain">V</span>
    {/if}
  </span>

  <span class="chip-name">{player.web_name}</span>
  <span class="chip-ep mono">{chipEp?.toFixed(1) ?? '—'} EP</span>
  {#if epDelta != null}
    <span class="chip-delta mono" class:positive={epDelta > 0.05} class:negative={epDelta < -0.05}>
      {epDelta > 0 ? '+' : ''}{epDelta.toFixed(1)} vs avg
    </span>
  {/if}
  <span class="chip-team" style="color: var(--kit-primary)">{player.team_short}</span>

  <div class="tip" role="tooltip">
    <div class="tt"><span>Form</span><span class="mono">{player.form?.toFixed(1) ?? '—'}</span></div>
    <div class="tt"><span>Points</span><span class="mono">{player.total_points}</span></div>
    <div class="tt"><span>xGI</span><span class="mono">{player.xgi?.toFixed(2) ?? '—'}</span></div>
    <div class="tt"><span>Own</span><span class="mono">{player.selected_pct?.toFixed(1)}%</span></div>
    <div class="tt"><span>Price</span><span class="mono">£{player.price?.toFixed(1)}m</span></div>
    <div class="tt"><span>Mins</span><span class="mono">{player.minutes}</span></div>
  </div>
</button>

<style>
  .chip {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
    padding: 0.45rem 0.4rem 0.35rem;
    min-width: 5rem;
    max-width: 6.5rem;
    background: rgba(5, 13, 10, 0.35);
    border: 1px solid rgba(232, 255, 241, 0.08);
    color: var(--text);
    cursor: pointer;
    border-radius: var(--radius-lg);
    backdrop-filter: blur(2px);
    transition: transform var(--duration) var(--ease),
                border-color var(--duration) var(--ease),
                box-shadow var(--duration) var(--ease);
  }
  .chip:hover {
    transform: translateY(-2px);
    border-color: var(--accent);
    box-shadow: 0 10px 30px rgba(0,0,0,0.5), 0 0 0 1px var(--accent);
    z-index: 10;
  }
  .chip.selected {
    border-color: var(--accent);
    background: rgba(0, 255, 156, 0.08);
    box-shadow: 0 0 0 2px var(--accent), 0 12px 40px rgba(0,0,0,0.6);
    z-index: 10;
  }
  .chip.captain { border-top-color: var(--yellow); }

  /* Jersey */
  .jersey {
    position: relative;
    width: 2.4rem;
    height: 2.4rem;
    margin-bottom: 0.1rem;
  }
  .jersey-svg {
    width: 100%;
    height: 100%;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
  }

  .armband {
    position: absolute;
    top: -4px;
    right: -6px;
    width: 1.1rem;
    height: 1.1rem;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--yellow);
    color: #1a1a2e;
    font-size: 0.58rem;
    font-weight: 800;
    border-radius: 50%;
    border: 1.5px solid rgba(0,0,0,0.6);
    box-shadow: 0 2px 4px rgba(0,0,0,0.4);
  }
  .armband.vice {
    background: #a1a1aa;
  }

  .chip-name {
    font-size: 0.72rem;
    font-weight: 700;
    color: #ffffff;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-shadow: 0 1px 2px rgba(0,0,0,0.8);
    letter-spacing: -0.01em;
  }
  .chip-team {
    font-family: var(--mono);
    font-weight: 700;
    font-size: 0.58rem;
    text-shadow: 0 1px 2px rgba(0,0,0,0.9);
  }
  .chip-ep {
    background: var(--accent);
    color: #041a10;
    padding: 0.12rem 0.42rem;
    border-radius: 100px;
    font-size: 0.85rem;
    font-weight: 700;
  }
  .chip-delta {
    font-size: 0.58rem;
    line-height: 1;
  }

  /* Tooltip — sits above, slides out on hover. z-index 1000 to beat any
     ancestor stacking contexts from the pitch SVG or card effects. */
  .tip {
    display: none;
    position: absolute;
    bottom: calc(100% + 10px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--bg-elevated);
    border: 1px solid var(--border-hover);
    padding: 0.6rem 0.75rem;
    z-index: 1000;
    min-width: 9.5rem;
    box-shadow: var(--shadow-lg);
    border-radius: var(--radius);
    pointer-events: none;
  }
  .tip::after {
    /* Little arrow */
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-top-color: var(--border-hover);
  }

  /* Flip the tooltip below the chip for forwards row so it doesn't
     clip off the top of the pitch. */
  .chip.flip-tip .tip {
    bottom: auto;
    top: calc(100% + 10px);
  }
  .chip.flip-tip .tip::after {
    top: auto;
    bottom: 100%;
    border-top-color: transparent;
    border-bottom-color: var(--border-hover);
  }

  .chip:hover .tip { display: block; }
  .chip { z-index: 1; }
  .chip:hover { z-index: 1000; }
  .tt {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    font-size: 0.7rem;
    padding: 0.1rem 0;
  }
  .tt span:first-child { color: var(--text-muted); }

  /* Pixel overrides */
  :global([data-theme="pixel"]) .chip {
    background: #f4eede;
    border: 3px solid #1a1a2e;
    border-radius: 0 !important;
    box-shadow: 3px 3px 0 #1a1a2e;
    padding: 4px 4px 3px;
    backdrop-filter: none;
  }
  :global([data-theme="pixel"]) .chip:hover {
    transform: translate(-1px, -1px);
    box-shadow: 4px 4px 0 #1a1a2e;
  }
  :global([data-theme="pixel"]) .chip.selected {
    background: #fff3b0;
    box-shadow: 3px 3px 0 var(--accent), 5px 5px 0 #1a1a2e;
  }
  :global([data-theme="pixel"]) .chip-name {
    color: #1a1a2e;
    text-shadow: none;
    font-family: 'Press Start 2P', monospace;
    font-size: 6px !important;
  }
  :global([data-theme="pixel"]) .chip-team {
    text-shadow: none;
    font-family: 'Press Start 2P', monospace;
    font-size: 6px !important;
  }
  :global([data-theme="pixel"]) .chip-ep {
    font-family: 'Press Start 2P', monospace;
    font-size: 8px !important;
    background: #1a1a2e;
    color: #f0c020;
    border: 1px solid #1a1a2e;
  }
  :global([data-theme="pixel"]) .chip-delta {
    font-family: 'VT323', monospace;
    font-size: 13px !important;
  }
  :global([data-theme="pixel"]) .jersey {
    width: 2rem;
    height: 2rem;
  }
  :global([data-theme="pixel"]) .armband {
    border-radius: 0 !important;
    border: 2px solid #1a1a2e;
    font-family: 'Press Start 2P', monospace;
    font-size: 5px;
  }
</style>
