<!-- Coin — budget / price -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-coin {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <circle cx="8" cy="8" r="6.2" fill="currentColor" fill-opacity="0.1" stroke="currentColor" stroke-width="1.3"/>
    <circle cx="8" cy="8" r="4.4" fill="none" stroke="currentColor" stroke-width="0.8" stroke-dasharray="1.2 1.2"/>
    <text x="8" y="10.3" text-anchor="middle" font-family="system-ui, sans-serif" font-size="6" font-weight="700" fill="currentColor">£</text>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <!-- ring -->
    <rect x="5" y="1" width="6" height="1" fill="currentColor"/>
    <rect x="3" y="2" width="2" height="1" fill="currentColor"/>
    <rect x="11" y="2" width="2" height="1" fill="currentColor"/>
    <rect x="2" y="3" width="1" height="2" fill="currentColor"/>
    <rect x="13" y="3" width="1" height="2" fill="currentColor"/>
    <rect x="1" y="5" width="1" height="6" fill="currentColor"/>
    <rect x="14" y="5" width="1" height="6" fill="currentColor"/>
    <rect x="2" y="11" width="1" height="2" fill="currentColor"/>
    <rect x="13" y="11" width="1" height="2" fill="currentColor"/>
    <rect x="3" y="13" width="2" height="1" fill="currentColor"/>
    <rect x="11" y="13" width="2" height="1" fill="currentColor"/>
    <rect x="5" y="14" width="6" height="1" fill="currentColor"/>
    <!-- £ -->
    <rect x="7" y="4" width="3" height="1" fill="currentColor"/>
    <rect x="6" y="5" width="1" height="2" fill="currentColor"/>
    <rect x="5" y="7" width="4" height="1" fill="currentColor"/>
    <rect x="6" y="8" width="1" height="2" fill="currentColor"/>
    <rect x="5" y="10" width="6" height="1" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
