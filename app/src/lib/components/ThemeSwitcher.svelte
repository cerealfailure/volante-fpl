<script lang="ts">
  import { theme } from '$lib/theme';
  import * as Icon from '$lib/components/icons';

  function toggle() {
    theme.update(t => t === 'clean' ? 'pixel' : 'clean');
  }
</script>

<button
  class="theme-toggle"
  onclick={toggle}
  title="Switch to {$theme === 'clean' ? 'pixel (Tecmo scoreboard)' : 'clean (floodlit)'} theme"
  aria-label="Switch theme"
>
  {#if $theme === 'clean'}
    <Icon.Ball size={16} />
    <span class="tt-label">8-BIT</span>
  {:else}
    <Icon.Floodlight size={16} />
    <span class="tt-label">FLOODLIT</span>
  {/if}
</button>

<style>
  .theme-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    height: 2.1rem;
    padding: 0 0.65rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: var(--radius);
    font-family: var(--mono);
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    transition: all var(--duration) var(--ease);
  }
  .theme-toggle:hover {
    border-color: var(--accent);
    color: var(--accent-text);
    background: var(--accent-soft);
  }
  .tt-label { display: inline-block; }

  :global([data-theme="pixel"]) .theme-toggle {
    height: auto;
    font-size: 7px;
    padding: 8px 10px;
  }
  :global([data-theme="pixel"]) .tt-label {
    font-family: 'Press Start 2P', monospace;
  }
</style>
