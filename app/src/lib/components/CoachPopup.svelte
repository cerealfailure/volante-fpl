<!--
  CoachPopup — "The Gaffer" toast.
  Slides in from bottom-right only when there's a message to deliver.
  Phases: hidden → thinking ("..." pulse) → speaking (types out) → hidden.
  Works in both clean and pixel themes.

  The sprite does a tiny two-frame walk-cycle while visible, like he
  just jogged over from the dugout.
-->
<script lang="ts">
  import { gaffer, GAFFER_NAME, type GafferState } from '$lib/coach';
  import { theme } from '$lib/theme';
  import { onDestroy } from 'svelte';

  let snapshot: GafferState = $state({ phase: 'hidden', text: '', id: 0 });
  const unsub = gaffer.subscribe(s => { snapshot = s; });
  onDestroy(unsub);

  // Typed-out message state (speaking phase only)
  let shown = $state('');
  let typeTimer: ReturnType<typeof setInterval> | null = null;
  function clearType() {
    if (typeTimer) { clearInterval(typeTimer); typeTimer = null; }
  }

  $effect(() => {
    // Retype on every new speaking phase
    clearType();
    if (snapshot.phase !== 'speaking') {
      shown = '';
      return;
    }
    const fullText = snapshot.text;
    shown = '';
    let i = 0;
    typeTimer = setInterval(() => {
      if (i >= fullText.length) { clearType(); return; }
      shown += fullText[i] ?? '';
      i += 1;
    }, 14);
    return clearType;
  });

  onDestroy(() => clearType());

  function dismiss() { gaffer.hide(); }

  // Svelte-style "entering" state — we want a one-off slide-in whenever
  // the popup goes from hidden → visible. We mount/unmount the root div
  // based on `visible`, letting the keyframe fire each time.
  let visible = $derived(snapshot.phase !== 'hidden');
</script>

{#if visible}
  <aside
    class="gaffer"
    class:pixel={$theme === 'pixel'}
    role="status"
    aria-live="polite"
  >
    <div class="gaffer-inner">
      <div class="gaffer-sprite">
        {#if $theme === 'pixel'}
          <!-- Pixel coach with 2-frame walk cycle -->
          <svg class="g-pix walking" viewBox="0 0 18 24" shape-rendering="crispEdges" aria-hidden="true">
            <!-- hair/cap -->
            <rect x="6" y="2" width="6" height="1" fill="#1a1a2e"/>
            <rect x="5" y="3" width="8" height="1" fill="#1a1a2e"/>
            <!-- face -->
            <rect x="6" y="4" width="6" height="3" fill="#f4c090"/>
            <rect x="7" y="5" width="1" height="1" fill="#1a1a2e"/>
            <rect x="10" y="5" width="1" height="1" fill="#1a1a2e"/>
            <!-- frown-of-concentration / mouth -->
            <rect x="8" y="6" width="2" height="1" fill="#8a1020"/>
            <!-- collar -->
            <rect x="5" y="7" width="8" height="1" fill="#e63946"/>
            <rect x="8" y="8" width="2" height="1" fill="#f0c020"/>
            <!-- tracksuit body -->
            <rect x="4" y="8" width="10" height="6" fill="#1a1a2e"/>
            <rect x="6" y="9" width="6" height="4" fill="#e63946"/>
            <rect x="4" y="14" width="10" height="1" fill="#1a1a2e"/>
            <!-- arms (walk cycle) -->
            <rect class="g-arm-l" x="2" y="9"  width="2" height="5" fill="#1a1a2e"/>
            <rect class="g-arm-r" x="14" y="9" width="2" height="5" fill="#1a1a2e"/>
            <!-- legs (walk cycle) -->
            <rect class="g-leg-l" x="6" y="15" width="2" height="4" fill="#1a1a2e"/>
            <rect class="g-leg-r" x="10" y="15" width="2" height="4" fill="#1a1a2e"/>
            <!-- boots -->
            <rect x="5" y="19" width="3" height="1" fill="#3a3a4e"/>
            <rect x="10" y="19" width="3" height="1" fill="#3a3a4e"/>
          </svg>
        {:else}
          <!-- Clean theme: confident minimal gaffer portrait -->
          <svg class="g-clean" viewBox="0 0 40 40" aria-hidden="true">
            <defs>
              <linearGradient id="g-bg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#0f2920"/>
                <stop offset="100%" stop-color="#071512"/>
              </linearGradient>
            </defs>
            <rect width="40" height="40" rx="8" fill="url(#g-bg)" stroke="rgba(0,255,156,0.35)" stroke-width="1"/>
            <!-- head -->
            <circle cx="20" cy="15" r="5" fill="#e8d2a8" stroke="#1a1a2e" stroke-width="0.8"/>
            <!-- hair -->
            <path d="M15 13 Q20 6 25 13" fill="#1a1a2e"/>
            <!-- body / tracksuit collar -->
            <path d="M10 32 Q10 22 20 22 Q30 22 30 32 L30 38 L10 38 Z"
                  fill="#0a1a10" stroke="rgba(0,255,156,0.55)" stroke-width="1"/>
            <!-- zip -->
            <line x1="20" y1="23" x2="20" y2="35" stroke="#00ff9c" stroke-width="0.8" stroke-dasharray="1 1"/>
            <!-- whistle -->
            <circle cx="24" cy="28" r="1.2" fill="#ffd166"/>
          </svg>
        {/if}
      </div>

      <div class="gaffer-body">
        <div class="gaffer-head">
          <span class="gaffer-name">{GAFFER_NAME}</span>
          <button class="gaffer-x" onclick={(e) => { e.stopPropagation(); dismiss(); }} aria-label="Dismiss">×</button>
        </div>
        {#if snapshot.phase === 'thinking'}
          <p class="gaffer-text"><span class="dots"><span>·</span><span>·</span><span>·</span></span></p>
        {:else}
          <p class="gaffer-text">{shown}</p>
        {/if}
      </div>
    </div>
  </aside>
{/if}

<style>
  .gaffer {
    position: fixed;
    right: 1rem;
    bottom: 1rem;
    z-index: 900;
    max-width: 360px;
    width: calc(100vw - 2rem);
    cursor: pointer;
    animation: gaffer-in 320ms cubic-bezier(0.22, 0.9, 0.35, 1);
  }
  @keyframes gaffer-in {
    0%   { transform: translateX(calc(100% + 24px)); opacity: 0; }
    65%  { transform: translateX(-6px);               opacity: 1; }
    100% { transform: translateX(0);                  opacity: 1; }
  }

  .gaffer-inner {
    display: flex;
    gap: 0.85rem;
    align-items: flex-start;
    padding: 0.85rem 0.95rem 0.85rem 0.85rem;
    background: linear-gradient(180deg, var(--bg-card) 0%, var(--bg-warm) 100%);
    border: 1px solid var(--border-hover);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius-lg);
    box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55),
                0 0 0 1px rgba(0, 255, 156, 0.1);
  }

  .gaffer-sprite {
    flex-shrink: 0;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .g-clean {
    width: 40px;
    height: 40px;
    border-radius: var(--radius);
  }

  .gaffer-body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .gaffer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .gaffer-name {
    font-family: var(--mono);
    font-size: 0.58rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent-text);
    font-weight: 700;
  }
  .gaffer-x {
    background: transparent;
    border: none;
    color: var(--text-muted);
    width: 1.1rem;
    height: 1.1rem;
    font-size: 0.95rem;
    line-height: 1;
    cursor: pointer;
    border-radius: 50%;
    padding: 0;
  }
  .gaffer-x:hover { color: var(--text); background: var(--bg-elevated); }

  .gaffer-text {
    margin: 0.1rem 0 0;
    font-family: var(--font);
    font-size: 0.86rem;
    line-height: 1.4;
    color: var(--text);
    min-height: 1.2em;
  }

  /* Thinking dots: three bouncing ellipsis characters */
  .dots { display: inline-flex; gap: 0.15rem; }
  .dots span {
    display: inline-block;
    font-size: 1.4rem;
    line-height: 0.4;
    color: var(--accent);
    animation: dot-pulse 900ms infinite ease-in-out;
  }
  .dots span:nth-child(2) { animation-delay: 120ms; }
  .dots span:nth-child(3) { animation-delay: 240ms; }
  @keyframes dot-pulse {
    0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
    30%           { opacity: 1;   transform: translateY(-2px); }
  }

  /* ─── PIXEL THEME ─── */
  .gaffer.pixel .gaffer-inner {
    background: #f4eede;
    border: 3px solid #1a1a2e;
    border-left: 3px solid #1a1a2e;
    box-shadow: 4px 4px 0 #1a1a2e;
    border-radius: 0;
    padding: 10px 14px 10px 10px;
    gap: 12px;
  }
  .gaffer.pixel .gaffer-sprite {
    width: 36px;
    height: 48px;
  }
  .g-pix {
    width: 36px;
    height: 48px;
    image-rendering: pixelated;
  }
  /* Walk cycle — swap arm/leg positions in steps */
  .g-pix.walking .g-arm-l { animation: g-arm-l 0.55s steps(2) infinite; }
  .g-pix.walking .g-arm-r { animation: g-arm-r 0.55s steps(2) infinite; }
  .g-pix.walking .g-leg-l { animation: g-leg-l 0.55s steps(2) infinite; }
  .g-pix.walking .g-leg-r { animation: g-leg-r 0.55s steps(2) infinite; }
  @keyframes g-arm-l {
    0%, 50%  { transform: translateY(0); }
    50.01%, 100% { transform: translateY(-1px); }
  }
  @keyframes g-arm-r {
    0%, 50%  { transform: translateY(-1px); }
    50.01%, 100% { transform: translateY(0); }
  }
  @keyframes g-leg-l {
    0%, 50%  { transform: translateX(0) scaleY(1); }
    50.01%, 100% { transform: translateX(-1px) scaleY(0.85); }
  }
  @keyframes g-leg-r {
    0%, 50%  { transform: translateX(1px) scaleY(0.85); }
    50.01%, 100% { transform: translateX(0) scaleY(1); }
  }

  .gaffer.pixel .gaffer-name {
    font-family: 'Press Start 2P', monospace;
    font-size: 6px;
    color: #e63946;
    letter-spacing: 0;
  }
  .gaffer.pixel .gaffer-text {
    font-family: 'VT323', monospace;
    font-size: 18px;
    line-height: 1.2;
    color: #1a1a2e;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }
  .gaffer.pixel .gaffer-x {
    font-family: 'Press Start 2P', monospace;
    font-size: 9px;
    color: #1a1a2e;
    border: 2px solid #1a1a2e;
    border-radius: 0;
    width: 1.2rem;
    height: 1.2rem;
  }
  .gaffer.pixel .gaffer-x:hover { background: var(--accent); color: #f4eede; }
  .gaffer.pixel .dots span { color: var(--accent); }

  /* Mobile */
  @media (max-width: 640px) {
    .gaffer { right: 0.75rem; bottom: 0.75rem; max-width: calc(100vw - 1.5rem); }
  }

  @media (prefers-reduced-motion: reduce) {
    .gaffer { animation: none; }
    .g-pix.walking .g-arm-l,
    .g-pix.walking .g-arm-r,
    .g-pix.walking .g-leg-l,
    .g-pix.walking .g-leg-r,
    .dots span { animation: none; }
  }
</style>
