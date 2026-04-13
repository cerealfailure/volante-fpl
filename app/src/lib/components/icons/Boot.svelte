<!-- Football boot with studs -->
<script lang="ts">
  let { size = 16, class: klass = '' }: { size?: number | string; class?: string } = $props();
</script>

<svg class="icon icon-boot {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <!-- ankle + upper -->
    <path d="M3 5 L6.5 4 L9 4 L10.5 6 Q14 6.5 14 9 L14 11 L3.2 11 L2.6 8 Z"
          fill="currentColor" fill-opacity="0.12" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    <!-- laces -->
    <path d="M6 5.4 L8.8 6.3 M6 6.6 L9 7.4 M6.2 7.8 L9.4 8.5" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
    <!-- sole studs -->
    <circle cx="5" cy="11.8" r="0.6" fill="currentColor"/>
    <circle cx="8" cy="11.8" r="0.6" fill="currentColor"/>
    <circle cx="11" cy="11.8" r="0.6" fill="currentColor"/>
    <circle cx="13" cy="11.8" r="0.6" fill="currentColor"/>
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <rect x="4" y="4" width="4" height="1" fill="currentColor"/>
    <rect x="3" y="5" width="6" height="1" fill="currentColor"/>
    <rect x="3" y="6" width="7" height="1" fill="currentColor"/>
    <rect x="3" y="7" width="9" height="1" fill="currentColor"/>
    <rect x="3" y="8" width="11" height="1" fill="currentColor"/>
    <rect x="2" y="9" width="13" height="1" fill="currentColor"/>
    <rect x="2" y="10" width="13" height="1" fill="currentColor"/>
    <!-- studs -->
    <rect x="3" y="12" width="1" height="1" fill="currentColor"/>
    <rect x="6" y="12" width="1" height="1" fill="currentColor"/>
    <rect x="9" y="12" width="1" height="1" fill="currentColor"/>
    <rect x="12" y="12" width="1" height="1" fill="currentColor"/>
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
