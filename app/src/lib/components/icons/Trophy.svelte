<!-- League trophy -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-trophy {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <path d="M5 2 L11 2 L11 6 Q11 9 8 9 Q5 9 5 6 Z" fill="currentColor" fill-opacity="0.12" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    <!-- handles -->
    <path d="M5 3 Q2 3.5 2.5 5.5 Q3 6.5 5 6.2" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linecap="round"/>
    <path d="M11 3 Q14 3.5 13.5 5.5 Q13 6.5 11 6.2" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linecap="round"/>
    <!-- stem + base -->
    <path d="M8 9 L8 11.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
    <rect x="5.5" y="11.5" width="5" height="1.8" rx="0.3" fill="currentColor"/>
    <rect x="4.5" y="13" width="7" height="1.2" rx="0.2" fill="currentColor"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="4" y="2" width="8" height="1" fill="currentColor"/>
    <rect x="4" y="3" width="1" height="5" fill="currentColor"/>
    <rect x="11" y="3" width="1" height="5" fill="currentColor"/>
    <rect x="5" y="4" width="6" height="4" fill="currentColor" opacity="0.25"/>
    <rect x="2" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="1" y="4" width="1" height="2" fill="currentColor"/>
    <rect x="2" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="3" y="7" width="1" height="1" fill="currentColor"/>
    <rect x="13" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="14" y="4" width="1" height="2" fill="currentColor"/>
    <rect x="13" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="12" y="7" width="1" height="1" fill="currentColor"/>
    <rect x="5" y="8" width="6" height="1" fill="currentColor"/>
    <rect x="7" y="9" width="2" height="2" fill="currentColor"/>
    <rect x="5" y="11" width="6" height="1" fill="currentColor"/>
    <rect x="3" y="12" width="10" height="2" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
