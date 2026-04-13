<!-- Corner flag — good for position/transfer iconography -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-flag {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <path d="M4 2 L4 14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M4 2.5 L13 4.5 L4 6.8 Z" fill="currentColor" fill-opacity="0.25" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    <circle cx="4" cy="14" r="1.2" fill="currentColor"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="4" y="2" width="1" height="12" fill="currentColor"/>
    <rect x="5" y="2" width="2" height="1" fill="currentColor"/>
    <rect x="5" y="3" width="4" height="1" fill="currentColor"/>
    <rect x="5" y="4" width="6" height="1" fill="currentColor"/>
    <rect x="5" y="5" width="4" height="1" fill="currentColor"/>
    <rect x="5" y="6" width="2" height="1" fill="currentColor"/>
    <rect x="3" y="13" width="3" height="1" fill="currentColor"/>
    <rect x="2" y="14" width="5" height="1" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
