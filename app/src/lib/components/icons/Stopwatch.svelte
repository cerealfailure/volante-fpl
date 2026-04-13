<!-- Stopwatch / injury time clock -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-stopwatch {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <rect x="6.2" y="1.4" width="3.6" height="1.4" rx="0.3" fill="currentColor"/>
    <path d="M6.8 2.8 L9.2 2.8" stroke="currentColor" stroke-width="0.8"/>
    <circle cx="8" cy="9" r="5.3" fill="none" stroke="currentColor" stroke-width="1.3"/>
    <line x1="8" y1="5.2" x2="8" y2="3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
    <!-- hand -->
    <line x1="8" y1="9" x2="10.5" y2="6.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
    <circle cx="8" cy="9" r="0.6" fill="currentColor"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="6" y="1" width="4" height="1" fill="currentColor"/>
    <rect x="6" y="2" width="4" height="1" fill="currentColor"/>
    <rect x="7" y="3" width="2" height="1" fill="currentColor"/>
    <!-- case -->
    <rect x="5" y="4" width="6" height="1" fill="currentColor"/>
    <rect x="3" y="5" width="2" height="1" fill="currentColor"/>
    <rect x="11" y="5" width="2" height="1" fill="currentColor"/>
    <rect x="2" y="6" width="1" height="2" fill="currentColor"/>
    <rect x="13" y="6" width="1" height="2" fill="currentColor"/>
    <rect x="1" y="8" width="1" height="3" fill="currentColor"/>
    <rect x="14" y="8" width="1" height="3" fill="currentColor"/>
    <rect x="2" y="11" width="1" height="2" fill="currentColor"/>
    <rect x="13" y="11" width="1" height="2" fill="currentColor"/>
    <rect x="3" y="13" width="2" height="1" fill="currentColor"/>
    <rect x="11" y="13" width="2" height="1" fill="currentColor"/>
    <rect x="5" y="14" width="6" height="1" fill="currentColor"/>
    <!-- hand -->
    <rect x="8" y="6" width="1" height="3" fill="currentColor"/>
    <rect x="9" y="9" width="2" height="1" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
