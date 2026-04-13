<!--
  Football — classic 12-panel. Clean variant is a clean line drawing.
  Pixel variant uses blocky rects for Tecmo-era scoreboard look.
  Switches automatically via [data-theme="pixel"] on <html>.
-->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-ball {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <!-- Clean variant: classic football panels -->
  <g class="clean-only">
    <circle cx="8" cy="8" r="6.5" fill="currentColor" fill-opacity="0.08" stroke="currentColor" stroke-width="1.2"/>
    <!-- center pentagon -->
    <path d="M8 4.8 L10.2 6.3 L9.4 8.8 L6.6 8.8 L5.8 6.3 Z" fill="currentColor" stroke="currentColor" stroke-width="0.8" stroke-linejoin="round"/>
    <!-- lines radiating to rim -->
    <path d="M8 4.8 L8 2" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
    <path d="M10.2 6.3 L12.8 5.4" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
    <path d="M9.4 8.8 L11.4 11.6" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
    <path d="M6.6 8.8 L4.6 11.6" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
    <path d="M5.8 6.3 L3.2 5.4" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
  </g>
  <!-- Pixel variant: blocky grid ball -->
  <g class="pixel-only" shape-rendering="crispEdges">
    <!-- outline ring -->
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
    <!-- panels -->
    <rect x="7" y="4" width="2" height="2" fill="currentColor"/>
    <rect x="4" y="6" width="2" height="2" fill="currentColor"/>
    <rect x="10" y="6" width="2" height="2" fill="currentColor"/>
    <rect x="7" y="8" width="2" height="2" fill="currentColor"/>
    <rect x="5" y="10" width="2" height="2" fill="currentColor"/>
    <rect x="9" y="10" width="2" height="2" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
