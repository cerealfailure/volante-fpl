<!-- Referee whistle — for risk callouts -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-whistle {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <!-- body -->
    <path d="M3 6 L11 5 Q13.5 5 13.5 8 Q13.5 11 11 11 L4 11 Q3 11 3 10 Z"
          fill="currentColor" fill-opacity="0.12" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    <!-- pea hole -->
    <circle cx="11" cy="8" r="1.2" fill="none" stroke="currentColor" stroke-width="1.1"/>
    <!-- lanyard -->
    <path d="M4.5 5.5 Q2 3.5 3 2" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linecap="round"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="3" y="2" width="1" height="1" fill="currentColor"/>
    <rect x="2" y="3" width="1" height="2" fill="currentColor"/>
    <rect x="3" y="5" width="1" height="1" fill="currentColor"/>
    <rect x="4" y="5" width="7" height="1" fill="currentColor"/>
    <rect x="3" y="6" width="9" height="1" fill="currentColor"/>
    <rect x="2" y="7" width="11" height="1" fill="currentColor"/>
    <rect x="2" y="8" width="11" height="1" fill="currentColor"/>
    <rect x="2" y="9" width="11" height="1" fill="currentColor"/>
    <rect x="3" y="10" width="10" height="1" fill="currentColor"/>
    <rect x="4" y="11" width="8" height="1" fill="currentColor"/>
    <!-- hole -->
    <rect x="10" y="7" width="2" height="2" fill="var(--bg-card)"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
