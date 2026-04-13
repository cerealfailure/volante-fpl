<!--
  Jersey / shirt. Stripes prop lets it act as a mini kit badge.
-->
<script lang="ts">
  let {
    size = 16,
    class: klass = '',
    primary = 'currentColor',
    secondary = 'transparent',
    stripe = false,
  }: {
    size?: number | string;
    class?: string;
    primary?: string;
    secondary?: string;
    stripe?: boolean;
  } = $props();
</script>

<svg class="icon icon-jersey {klass}" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
  <g class="clean-only">
    <!-- shoulder yoke + body -->
    <path d="M3 3.5 L6 2 L6.8 3.4 Q8 4 9.2 3.4 L10 2 L13 3.5 L13.8 6.2 L11.4 7 L11.4 14 L4.6 14 L4.6 7 L2.2 6.2 Z"
          fill={primary} stroke="currentColor" stroke-width="1" stroke-linejoin="round"/>
    {#if stripe}
      <path d="M7.2 4 L7.2 14 M8.8 4 L8.8 14" stroke={secondary} stroke-width="1.1"/>
    {/if}
  </g>
  <g class="pixel-only" shape-rendering="crispEdges">
    <!-- pixel jersey -->
    <rect x="5" y="2" width="2" height="1" fill="currentColor"/>
    <rect x="9" y="2" width="2" height="1" fill="currentColor"/>
    <rect x="4" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="7" y="3" width="2" height="1" fill="currentColor"/>
    <rect x="11" y="3" width="1" height="1" fill="currentColor"/>
    <rect x="3" y="4" width="2" height="1" fill="currentColor"/>
    <rect x="6" y="4" width="4" height="1" fill={primary}/>
    <rect x="11" y="4" width="2" height="1" fill="currentColor"/>
    <rect x="2" y="5" width="2" height="1" fill="currentColor"/>
    <rect x="4" y="5" width="8" height="1" fill={primary}/>
    <rect x="12" y="5" width="2" height="1" fill="currentColor"/>
    <rect x="2" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="3" y="6" width="10" height="1" fill={primary}/>
    <rect x="13" y="6" width="1" height="1" fill="currentColor"/>
    <rect x="4" y="7" width="8" height="1" fill={primary}/>
    <rect x="4" y="8" width="8" height="1" fill={primary}/>
    <rect x="4" y="9" width="8" height="1" fill={primary}/>
    <rect x="4" y="10" width="8" height="1" fill={primary}/>
    <rect x="4" y="11" width="8" height="1" fill={primary}/>
    <rect x="4" y="12" width="8" height="1" fill={primary}/>
    <rect x="4" y="13" width="8" height="1" fill={primary}/>
    <!-- outline -->
    <rect x="4" y="14" width="8" height="1" fill="currentColor"/>
    <rect x="3" y="7" width="1" height="7" fill="currentColor"/>
    <rect x="12" y="7" width="1" height="7" fill="currentColor"/>
    {#if stripe}
      <rect x="6" y="6" width="1" height="8" fill={secondary}/>
      <rect x="9" y="6" width="1" height="8" fill={secondary}/>
    {/if}
  </g>
</svg>

<style>
  .icon { display: inline-block; vertical-align: -0.15em; flex-shrink: 0; }
  :global([data-theme="clean"]) .pixel-only { display: none; }
  :global([data-theme="pixel"]) .clean-only { display: none; }
</style>
