<!--
  Football pitch SVG background — chalk lines on grass.
  Used as a pure background layer behind the formation.
  Pixel theme gets a blockier, hard-edged variant automatically.
-->
<svg
  class="pitch-field"
  viewBox="0 0 100 140"
  preserveAspectRatio="none"
  aria-hidden="true"
>
  <defs>
    <!-- Horizontal grass stripes, mower-style -->
    <pattern id="grass-stripes" x="0" y="0" width="100" height="14" patternUnits="userSpaceOnUse">
      <rect x="0" y="0"  width="100" height="7" class="grass-a"/>
      <rect x="0" y="7"  width="100" height="7" class="grass-b"/>
    </pattern>
  </defs>

  <!-- Turf -->
  <rect x="0" y="0" width="100" height="140" fill="url(#grass-stripes)"/>

  <!-- Outer touchline -->
  <rect x="2" y="2" width="96" height="136" class="chalk" fill="none"/>

  <!-- Halfway line + center circle + spot -->
  <line x1="2" y1="70" x2="98" y2="70" class="chalk"/>
  <circle cx="50" cy="70" r="10" class="chalk" fill="none"/>
  <circle cx="50" cy="70" r="0.8" class="chalk-fill"/>

  <!-- Top penalty area -->
  <rect x="22" y="2" width="56" height="18" class="chalk" fill="none"/>
  <rect x="34" y="2" width="32" height="7"  class="chalk" fill="none"/>
  <circle cx="50" cy="14" r="0.8" class="chalk-fill"/>
  <!-- top penalty D arc -->
  <path d="M 42 20 A 9 9 0 0 0 58 20" class="chalk" fill="none"/>

  <!-- Bottom penalty area -->
  <rect x="22" y="120" width="56" height="18" class="chalk" fill="none"/>
  <rect x="34" y="131" width="32" height="7"  class="chalk" fill="none"/>
  <circle cx="50" cy="126" r="0.8" class="chalk-fill"/>
  <path d="M 42 120 A 9 9 0 0 1 58 120" class="chalk" fill="none"/>

  <!-- Goals -->
  <rect x="43" y="-0.5" width="14" height="2.5" class="chalk" fill="none"/>
  <rect x="43" y="138" width="14" height="2.5" class="chalk" fill="none"/>

  <!-- Corner arcs -->
  <path d="M 2 4 A 2 2 0 0 1 4 2"   class="chalk" fill="none"/>
  <path d="M 96 2 A 2 2 0 0 1 98 4" class="chalk" fill="none"/>
  <path d="M 2 136 A 2 2 0 0 0 4 138" class="chalk" fill="none"/>
  <path d="M 96 138 A 2 2 0 0 0 98 136" class="chalk" fill="none"/>
</svg>

<style>
  .pitch-field {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 0;
  }

  /* Clean theme: night turf with chalk lines */
  :global([data-theme="clean"]) .grass-a { fill: #0e2a1f; }
  :global([data-theme="clean"]) .grass-b { fill: #10311f; }
  :global([data-theme="clean"]) .chalk {
    stroke: rgba(232, 255, 241, 0.42);
    stroke-width: 0.6;
  }
  :global([data-theme="clean"]) .chalk-fill {
    fill: rgba(232, 255, 241, 0.55);
  }

  /* Pixel theme: blocky grass */
  :global([data-theme="pixel"]) .grass-a { fill: #2a8c2a; }
  :global([data-theme="pixel"]) .grass-b { fill: #1e6b1e; }
  :global([data-theme="pixel"]) .chalk {
    stroke: #f4eede;
    stroke-width: 0.9;
    shape-rendering: crispEdges;
  }
  :global([data-theme="pixel"]) .chalk-fill {
    fill: #f4eede;
  }
</style>
