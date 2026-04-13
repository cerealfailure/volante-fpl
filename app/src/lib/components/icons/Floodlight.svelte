<!-- Stadium floodlight — theme switcher "night" state -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-floodlight {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <!-- pole -->
    <path d="M8 6 L8 15" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
    <!-- bank housing -->
    <rect x="4.5" y="2.5" width="7" height="3.2" rx="0.3" fill="currentColor" fill-opacity="0.12" stroke="currentColor" stroke-width="1.2"/>
    <!-- bulbs -->
    <circle cx="6" cy="4.1" r="0.55" fill="currentColor"/>
    <circle cx="8" cy="4.1" r="0.55" fill="currentColor"/>
    <circle cx="10" cy="4.1" r="0.55" fill="currentColor"/>
    <!-- beam -->
    <path d="M5 5.5 L2 10 M8 5.5 L8 10 M11 5.5 L14 10" stroke="currentColor" stroke-width="0.8" opacity="0.4" stroke-linecap="round"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="4" y="2" width="8" height="1" fill="currentColor"/>
    <rect x="4" y="5" width="8" height="1" fill="currentColor"/>
    <rect x="3" y="3" width="1" height="2" fill="currentColor"/>
    <rect x="12" y="3" width="1" height="2" fill="currentColor"/>
    <rect x="5" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="7" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="9" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="11" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="7" y="6" width="2" height="9" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
