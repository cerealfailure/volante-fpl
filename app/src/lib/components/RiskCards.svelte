<!--
  Risk callout cards — plain-English insights
  with football iconography (yellow/red card + ball info).
-->
<script lang="ts">
  import * as Icon from '$lib/components/icons';
  let { callouts }: { callouts: any[] } = $props();
</script>

<div class="risk-cards">
  {#each callouts as callout}
    <div class="risk-card severity-{callout.severity}">
      <div class="risk-header">
        <span class="risk-icon">
          {#if callout.severity === 'high'}
            <Icon.Card variant="red" size={14} />
          {:else if callout.severity === 'medium'}
            <Icon.Card variant="yellow" size={14} />
          {:else}
            <Icon.Whistle size={14} />
          {/if}
        </span>
        <span class="risk-title">{callout.title}</span>
      </div>
      <p class="risk-detail">{callout.detail}</p>
    </div>
  {/each}
</div>

<style>
  .risk-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 0.55rem;
  }
  .risk-card {
    background: color-mix(in srgb, var(--bg-card) 94%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.8rem 0.9rem;
    border-left: 3px solid;
  }
  .severity-high   { border-left-color: var(--red); }
  .severity-medium { border-left-color: var(--yellow); }
  .severity-info   { border-left-color: var(--accent); }

  .risk-header {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    margin-bottom: 0.3rem;
  }
  .risk-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.4rem;
    height: 1.4rem;
    flex-shrink: 0;
  }
  .severity-high   .risk-icon { color: var(--red); }
  .severity-medium .risk-icon { color: var(--yellow); }
  .severity-info   .risk-icon { color: var(--accent); }

  .risk-title {
    font-family: var(--heading);
    font-weight: 700;
    font-size: 0.85rem;
    letter-spacing: -0.01em;
    color: var(--text-heading);
  }
  .risk-detail {
    font-size: 0.77rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }
</style>
