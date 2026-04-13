<!-- Sub board — transfers / swaps -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-swap {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <!-- board -->
    <rect x="1.5" y="3" width="13" height="10" rx="1.2" fill="currentColor" fill-opacity="0.08" stroke="currentColor" stroke-width="1.2"/>
    <!-- arrows -->
    <path d="M4 6.5 L10 6.5 M4 6.5 L5.8 5 M4 6.5 L5.8 8" stroke="var(--green)" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    <path d="M12 9.5 L6 9.5 M12 9.5 L10.2 8 M12 9.5 L10.2 11" stroke="var(--red)" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <!-- board outline -->
    <rect x="1" y="3" width="14" height="1" fill="currentColor"/>
    <rect x="1" y="12" width="14" height="1" fill="currentColor"/>
    <rect x="1" y="3" width="1" height="10" fill="currentColor"/>
    <rect x="14" y="3" width="1" height="10" fill="currentColor"/>
    <!-- up arrow (in) -->
    <rect x="3" y="6" width="8" height="1" fill="var(--green)"/>
    <rect x="9" y="5" width="1" height="1" fill="var(--green)"/>
    <rect x="10" y="5" width="1" height="1" fill="var(--green)"/>
    <rect x="9" y="7" width="1" height="1" fill="var(--green)"/>
    <rect x="10" y="7" width="1" height="1" fill="var(--green)"/>
    <!-- down arrow (out) -->
    <rect x="5" y="9" width="8" height="1" fill="var(--red)"/>
    <rect x="5" y="8" width="1" height="1" fill="var(--red)"/>
    <rect x="6" y="8" width="1" height="1" fill="var(--red)"/>
    <rect x="5" y="10" width="1" height="1" fill="var(--red)"/>
    <rect x="6" y="10" width="1" height="1" fill="var(--red)"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
