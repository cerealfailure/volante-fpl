<!-- Yellow/red card — variant via `color` prop (or currentColor) -->
<script lang="ts">
  let {
    size = 16,
    class: klass = '',
    variant = 'yellow',
  }: {
    size?: number | string;
    class?: string;
    variant?: 'yellow' | 'red';
  } = $props();
</script>

<svg class="icon icon-card {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <rect x="4" y="2" width="8" height="12" rx="0.6"
          fill={variant === 'yellow' ? 'var(--yellow)' : 'var(--red)'}
          stroke="currentColor" stroke-width="1.2"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="4" y="2" width="8" height="12" fill={variant === 'yellow' ? 'var(--yellow)' : 'var(--red)'}/>
    <rect x="4" y="2" width="8" height="1" fill="currentColor"/>
    <rect x="4" y="13" width="8" height="1" fill="currentColor"/>
    <rect x="4" y="2" width="1" height="12" fill="currentColor"/>
    <rect x="11" y="2" width="1" height="12" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
