<!-- Goal net — for players page icon -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-goal {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <!-- net -->
    <path d="M3 4 L13 4 L13 12 L3 12 Z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    <path d="M3 6 L13 6 M3 8 L13 8 M3 10 L13 10" stroke="currentColor" stroke-width="0.6" opacity="0.55"/>
    <path d="M5 4 L5 12 M7 4 L7 12 M9 4 L9 12 M11 4 L11 12" stroke="currentColor" stroke-width="0.6" opacity="0.55"/>
    <!-- posts -->
    <path d="M2.4 4 L2.4 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M13.6 4 L13.6 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M2.4 4 L13.6 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    <!-- ball in net -->
    <circle cx="8" cy="9" r="1.3" fill="currentColor"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <!-- crossbar + posts -->
    <rect x="2" y="3" width="12" height="1" fill="currentColor"/>
    <rect x="2" y="4" width="1" height="10" fill="currentColor"/>
    <rect x="13" y="4" width="1" height="10" fill="currentColor"/>
    <!-- net grid -->
    <rect x="4" y="5" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="6" y="5" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="8" y="5" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="10" y="5" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="12" y="5" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="3" y="7" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="5" y="7" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="11" y="7" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="12" y="7" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="4" y="11" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <rect x="11" y="11" width="1" height="1" fill="currentColor" opacity="0.6"/>
    <!-- ball -->
    <rect x="7" y="8" width="2" height="1" fill="currentColor"/>
    <rect x="6" y="9" width="4" height="1" fill="currentColor"/>
    <rect x="7" y="10" width="2" height="1" fill="currentColor"/>
    <!-- ground -->
    <rect x="1" y="14" width="14" height="1" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
