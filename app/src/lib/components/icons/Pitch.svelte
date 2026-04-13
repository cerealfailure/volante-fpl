<!-- Mini pitch — for Squad nav icon -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-pitch {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <rect x="1.5" y="3" width="13" height="10" rx="0.8" fill="currentColor" fill-opacity="0.08" stroke="currentColor" stroke-width="1.2"/>
    <!-- halfway line -->
    <line x1="8" y1="3" x2="8" y2="13" stroke="currentColor" stroke-width="1"/>
    <!-- center circle -->
    <circle cx="8" cy="8" r="2" fill="none" stroke="currentColor" stroke-width="1"/>
    <circle cx="8" cy="8" r="0.5" fill="currentColor"/>
    <!-- penalty boxes -->
    <rect x="1.5" y="5" width="2.2" height="6" fill="none" stroke="currentColor" stroke-width="0.9"/>
    <rect x="12.3" y="5" width="2.2" height="6" fill="none" stroke="currentColor" stroke-width="0.9"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <!-- outline -->
    <rect x="1" y="3" width="14" height="1" fill="currentColor"/>
    <rect x="1" y="12" width="14" height="1" fill="currentColor"/>
    <rect x="1" y="3" width="1" height="10" fill="currentColor"/>
    <rect x="14" y="3" width="1" height="10" fill="currentColor"/>
    <!-- half line -->
    <rect x="8" y="4" width="1" height="8" fill="currentColor"/>
    <!-- center circle-ish -->
    <rect x="7" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="9" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="6" y="7" width="1" height="2" fill="currentColor"/>
    <rect x="10" y="7" width="1" height="2" fill="currentColor"/>
    <rect x="7" y="9" width="1" height="1" fill="currentColor"/>
    <rect x="9" y="9" width="1" height="1" fill="currentColor"/>
    <!-- penalty areas -->
    <rect x="2" y="5" width="2" height="1" fill="currentColor"/>
    <rect x="2" y="10" width="2" height="1" fill="currentColor"/>
    <rect x="4" y="6" width="1" height="4" fill="currentColor"/>
    <rect x="12" y="5" width="2" height="1" fill="currentColor"/>
    <rect x="12" y="10" width="2" height="1" fill="currentColor"/>
    <rect x="11" y="6" width="1" height="4" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
