<!-- Captain armband -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-armband {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <path d="M2 5 Q8 2.5 14 5 L14 11 Q8 13.5 2 11 Z"
          fill="var(--yellow)" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    <text x="8" y="10.5" text-anchor="middle" font-family="system-ui, sans-serif" font-size="6.5" font-weight="800" fill="currentColor">C</text>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="2" y="5" width="12" height="1" fill="currentColor"/>
    <rect x="2" y="10" width="12" height="1" fill="currentColor"/>
    <rect x="2" y="6" width="12" height="4" fill="var(--yellow)"/>
    <rect x="1" y="6" width="1" height="4" fill="currentColor"/>
    <rect x="14" y="6" width="1" height="4" fill="currentColor"/>
    <rect x="6" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="5" y="7" width="1" height="2" fill="currentColor"/>
    <rect x="6" y="9" width="1" height="1" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
