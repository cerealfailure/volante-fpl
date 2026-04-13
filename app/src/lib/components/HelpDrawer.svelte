<!--
  Team-as-portfolio primer.
  Slide-in drawer from the right that explains what Volante is doing
  in plain football language. Triggered from the sign-in screen and
  the meta-footer "what do these numbers mean?" link.
-->
<script lang="ts">
  import * as Icon from '$lib/components/icons';

  let {
    open = false,
    onClose,
  }: {
    open?: boolean;
    onClose?: () => void;
  } = $props();

  function closeOnEsc(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose?.();
  }
</script>

<svelte:window onkeydown={closeOnEsc} />

{#if open}
  <!-- Scrim -->
  <button type="button" class="scrim" onclick={onClose} aria-label="Close portfolio primer"></button>

  <aside class="drawer" aria-label="Portfolio primer">
    <header class="drawer-head">
      <div class="row-tight">
        <Icon.Whistle size={16} />
        <h2>Portfolio primer</h2>
      </div>
      <button class="drawer-close" onclick={onClose} aria-label="Close">×</button>
    </header>

    <div class="drawer-body">
      <section class="lesson">
        <span class="eyebrow">1 · Frame</span>
        <h3>Your squad is a portfolio of picks.</h3>
        <p>
          Every pick is a position on one footballer's next ninety minutes. When
          you stack two Arsenal attackers or double up at the back with
          Liverpool defenders, those picks move together — if Arsenal blank,
          both slots miss at once. Volante reads your XI as a portfolio and
          shows you where those hidden overlaps live.
        </p>
      </section>

      <section class="lesson">
        <span class="eyebrow">2 · The four numbers</span>
        <h3>What the health bar is telling you.</h3>

        <dl class="term-list">
          <dt><Icon.Jersey size={14} /> ENB · Effective number of outcomes</dt>
          <dd>
            Out of 11 players, how many <em>independent</em> outcomes you
            actually have after correlation kicks in. 11 means fully
            diversified. 4 means your week is really only riding on four
            outcomes.
          </dd>

          <dt><Icon.Stopwatch size={14} /> StdDev · Points swing per GW</dt>
          <dd>
            Your expected points <em>error bar</em>. A StdDev of 12 means a
            normal week can land ±12 points above or below your mean,
            before you even touch a captain.
          </dd>

          <dt><Icon.Trophy size={14} /> HHI · Concentration index</dt>
          <dd>
            Herfindahl-Hirschman Index borrowed from antitrust. Close to 0
            means spread across many clubs; above 0.15 means one or two
            teams drive most of your variance.
          </dd>

          <dt><Icon.Pitch size={14} /> DR · Diversification ratio</dt>
          <dd>
            How much of your portfolio's "natural" risk you've actually
            reduced by hedging. Higher = better hedged squad.
          </dd>
        </dl>
      </section>

      <section class="lesson">
        <span class="eyebrow">3 · Correlation</span>
        <h3>Stacks vs hedges.</h3>
        <p>
          A <span class="accent">positive</span> correlation (two Arsenal
          attackers, a GK and his own centre-back) means the pair boom and
          bust together — big weeks get bigger, bad weeks get worse.
          A <span class="warning">negative</span> correlation is a natural
          hedge — one wins when the other loses. Volante's matrix shows you
          every pair in your XI and colour-codes the hotspots.
        </p>
      </section>

      <section class="lesson">
        <span class="eyebrow">4 · Captain</span>
        <h3>Why captaincy amplifies everything.</h3>
        <p>
          Captaining a player doubles their weight, so captain correlation
          goes double too. The Issues tab flags when your skipper is
          driving an outsized share of your weekly variance — even if
          their points forecast looks healthy.
        </p>
      </section>

      <section class="lesson">
        <span class="eyebrow">5 · How to use this</span>
        <h3>A weekly routine.</h3>
        <ol class="steps">
          <li><strong>Check the health bar.</strong> ENB under 5 or HHI above 0.15 = you're stacked.</li>
          <li><strong>Read the Issues tab.</strong> Each callout is a plain-English diagnosis.</li>
          <li><strong>Open Transfers.</strong> Drop the riskiest name, browse replacements, and watch the deltas.</li>
          <li><strong>Look at This Week.</strong> See which matches drive most of your EP, and which fixtures can swing the week hardest.</li>
        </ol>
      </section>

      <p class="caveat">
        <Icon.Card variant="yellow" size={12} />
        Not financial advice. Ledoit–Wolf shrinkage makes the covariance
        matrix stable on small samples but can't fix a bad lineup —
        football knowledge still matters.
      </p>
    </div>
  </aside>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 9000;
    backdrop-filter: blur(3px);
    animation: scrimFade 0.25s var(--ease);
  }
  @keyframes scrimFade { from { opacity: 0; } to { opacity: 1; } }

  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(560px, 94vw);
    background:
      linear-gradient(180deg, var(--bg-card) 0%, var(--bg-warm) 100%);
    border-left: 1px solid var(--border);
    box-shadow: -20px 0 60px rgba(0, 0, 0, 0.6);
    z-index: 9001;
    display: flex;
    flex-direction: column;
    animation: drawerSlide 0.35s var(--ease);
  }
  @keyframes drawerSlide {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }

  .drawer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.1rem 1.5rem 1rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .drawer-close {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-secondary);
    width: 2rem;
    height: 2rem;
    font-size: 1.3rem;
    line-height: 1;
    cursor: pointer;
    border-radius: var(--radius);
  }
  .drawer-close:hover { color: var(--text); border-color: var(--border-hover); }

  .drawer-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }

  .lesson {
    margin-bottom: 1.8rem;
    padding-bottom: 1.4rem;
    border-bottom: 1px dashed var(--border);
  }
  .lesson:last-of-type { border-bottom: none; }
  .lesson .eyebrow {
    display: inline-block;
    margin-bottom: 0.4rem;
  }
  .lesson h3 {
    font-family: var(--heading);
    font-size: 1.3rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text-heading);
    margin-bottom: 0.55rem;
    line-height: 1.15;
    text-transform: none;
  }
  .lesson p {
    font-size: 0.92rem;
    line-height: 1.65;
    color: var(--text-secondary);
    margin-bottom: 0.4rem;
  }
  .term-list {
    margin-top: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }
  .term-list dt {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--mono);
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--accent-text);
  }
  .term-list dd {
    margin-left: 1.5rem;
    margin-top: 0.25rem;
    font-size: 0.88rem;
    color: var(--text-secondary);
    line-height: 1.55;
  }
  .term-list dd em {
    color: var(--text);
    font-weight: 600;
    font-style: italic;
  }

  .steps {
    margin: 0.6rem 0 0;
    padding-left: 1.3rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .steps li {
    font-size: 0.88rem;
    line-height: 1.55;
    color: var(--text-secondary);
  }
  .steps li strong {
    color: var(--text-heading);
    font-weight: 600;
  }

  .caveat {
    display: flex;
    align-items: flex-start;
    gap: 0.55rem;
    padding: 0.75rem 0.9rem;
    background: var(--yellow-soft);
    border: 1px solid var(--yellow);
    border-left-width: 3px;
    border-radius: var(--radius);
    color: var(--text-secondary);
    font-size: 0.8rem;
    line-height: 1.55;
    margin-top: 1rem;
  }

  /* Pixel theme overrides — scoreboard feel */
  :global([data-theme="pixel"]) .drawer {
    background: #f4eede;
    border-left: 3px solid #1a1a2e;
    box-shadow: -4px 0 0 #1a1a2e;
  }
  :global([data-theme="pixel"]) .lesson h3 {
    font-family: 'Press Start 2P', monospace;
    font-size: 10px;
    line-height: 1.6;
    text-shadow: 2px 2px 0 var(--accent);
  }
  :global([data-theme="pixel"]) .lesson p,
  :global([data-theme="pixel"]) .term-list dd,
  :global([data-theme="pixel"]) .steps li {
    font-family: var(--font);
    font-size: 15px;
  }
</style>
