<script lang="ts">
  import '../styles/base.css';
  import '../styles/themes/clean.css';
  import '../styles/themes/pixel.css';
  import { managerId } from '$lib/session';
  import { page } from '$app/stores';
  import { onNavigate } from '$app/navigation';
  import { gaffer } from '$lib/coach';
  import ThemeSwitcher from '$lib/components/ThemeSwitcher.svelte';
  import CoachPopup from '$lib/components/CoachPopup.svelte';
  import * as Icon from '$lib/components/icons';
  let { children } = $props();

  // View Transitions API — wire SvelteKit route changes to
  // document.startViewTransition when the browser supports it.
  // Graceful fallback: pages swap instantly as before.
  onNavigate((navigation) => {
    const doc = document as Document & { startViewTransition?: (cb: () => void | Promise<void>) => unknown };
    if (!doc.startViewTransition) return;
    return new Promise<void>((resolve) => {
      doc.startViewTransition!(async () => {
        resolve();
        await navigation.complete;
      });
    });
  });

  function logout() {
    managerId.set(null);
    window.location.href = '/';
  }

  type NavItem = {
    href: string;
    label: string;
    icon: 'pitch' | 'swap' | 'trophy' | 'ball';
    coach: string;
  };
  const navItems: NavItem[] = [
    { href: '/points',    label: 'Points',    icon: 'ball',      coach: 'LIVE POINTS. YOUR WEEK AS IT STANDS.' },
    { href: '/',          label: 'Squad',     icon: 'pitch',     coach: 'DRESSING ROOM. TAP A KIT FOR THE READ.' },
    { href: '/transfers', label: 'Transfers', icon: 'swap',      coach: 'SUB BOARD IS UP. PICK SOMEONE TO DROP.' },
    { href: '/leagues',   label: 'Leagues',   icon: 'trophy',    coach: "LEAGUE TABLE. LET'S SEE WHO'S TOP." },
  ];
  const navIcons = {
    pitch: Icon.Pitch,
    swap: Icon.Swap,
    trophy: Icon.Trophy,
    ball: Icon.Ball,
  } as const;

  function isActive(href: string, path: string) {
    if (href === '/') return path === '/';
    return path.startsWith(href);
  }

  function onNav(item: NavItem) {
    gaffer.say(item.coach);
  }
</script>

<div class="shell">
  <header>
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="Volante home">
        <span class="brand-crest">
          <img src="/logo.svg" alt="" class="brand-mark-img clean-only" />
          <img src="/logo-pixel.svg" alt="" class="brand-mark-img pixel-only" />
        </span>
        <span class="brand-wordmark">
          <span class="brand-name">VOLANTE</span>
          <span class="brand-tag">FPL · PORTFOLIO · DESK</span>
        </span>
      </a>

      {#if $managerId}
        <nav class="header-nav" aria-label="Primary">
          {#each navItems as item}
            {@const NavIcon = navIcons[item.icon]}
            <a href={item.href}
               class="nav-link"
               class:active={isActive(item.href, $page.url.pathname)}
               onclick={() => onNav(item)}>
              <span class="nav-ico">
                <NavIcon size={16} />
              </span>
              <span class="nav-label">{item.label}</span>
            </a>
          {/each}
        </nav>
      {/if}

      <div class="header-right">
        {#if $managerId}
          <button class="id-chip" onclick={logout} title="Log out">
            <Icon.Jersey size={14} />
            <span class="mono">#{$managerId}</span>
          </button>
        {:else}
          <span class="dim2 small tagline">
            <Icon.Ball size={14} />
            Portfolio analytics for FPL managers
          </span>
        {/if}
        <ThemeSwitcher />
      </div>
    </div>
    <div class="header-pitch-line" aria-hidden="true"></div>
  </header>

  <main>
    {@render children()}
  </main>

  {#if $managerId}
    <nav class="mobile-nav" aria-label="Primary mobile">
      {#each navItems as item}
        {@const NavIcon = navIcons[item.icon]}
        <a
          href={item.href}
          class="mobile-link"
          class:active={isActive(item.href, $page.url.pathname)}
          onclick={() => onNav(item)}
        >
          <span class="nav-ico"><NavIcon size={17} /></span>
          <span class="mobile-label">{item.label}</span>
        </a>
      {/each}
    </nav>
  {/if}

  <!-- The Gaffer — toast popup that only appears when a page pushes a message.
       Lives here so every route can trigger it without its own mount. -->
  <CoachPopup />
</div>

<style>
  .shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    --shell-header-offset: 3.6rem;
  }

  header {
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--bg) 72%, transparent);
    position: sticky;
    top: 0;
    z-index: 50;
    backdrop-filter: blur(12px) saturate(140%);
    -webkit-backdrop-filter: blur(12px) saturate(140%);
  }
  .header-inner {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.65rem var(--gutter);
    max-width: var(--shell-max);
    margin: 0 auto;
  }
  .header-pitch-line {
    height: 1px;
    background: linear-gradient(90deg,
      transparent 0%,
      var(--accent) 18%,
      var(--accent) 82%,
      transparent 100%);
    opacity: 0.55;
    transform-origin: left center;
    animation: drawLine 680ms var(--ease) 80ms both;
  }

  /* Brand — view-transition-name keeps the crest anchored through route changes */
  .brand {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    flex-shrink: 0;
    text-decoration: none;
    color: inherit;
    view-transition-name: brand;
  }
  .brand-crest {
    position: relative;
    display: inline-flex;
  }
  .brand-mark-img {
    width: 2rem;
    height: 2rem;
    border-radius: var(--radius-sm);
    display: block;
  }

  .brand-wordmark {
    display: flex;
    flex-direction: column;
    line-height: 1;
    gap: 0.15rem;
  }
  .brand-name {
    font-family: var(--heading);
    font-weight: 800;
    font-size: 1.02rem;
    letter-spacing: -0.01em;
    color: var(--text-heading);
  }
  .brand-tag {
    font-family: var(--mono);
    font-size: 0.58rem;
    letter-spacing: 0.22em;
    color: var(--text-muted);
    text-transform: uppercase;
  }

  /* Nav pill — :has() dimming when one link is hovered */
  .header-nav {
    display: flex;
    gap: 0.1rem;
    margin-left: 0.75rem;
    padding: 0.2rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--bg-elevated);
  }
  .nav-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.42rem 0.78rem;
    color: var(--text-secondary);
    text-decoration: none;
    border-radius: 999px;
    font-family: var(--font);
    font-size: var(--fs-13);
    font-weight: 600;
    letter-spacing: 0.005em;
    position: relative;
    transition: color var(--duration-fast) var(--ease),
                opacity var(--duration-fast) var(--ease);
  }
  .nav-link:hover { color: var(--text); }
  .header-nav:has(.nav-link:hover) .nav-link:not(:hover) {
    opacity: 0.55;
  }
  .nav-link.active {
    color: var(--accent-text);
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 1px var(--border-accent);
  }
  .header-nav:has(.nav-link:hover) .nav-link.active:not(:hover) {
    opacity: 0.75;
  }
  .nav-ico {
    display: inline-flex;
    color: currentColor;
  }

  .header-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.55rem;
  }
  .id-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.45rem 0.75rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    font-size: 0.78rem;
    border-radius: var(--radius);
    cursor: pointer;
  }
  .id-chip:hover {
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .tagline {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text-muted);
  }

  main {
    flex: 1;
    padding: 1.75rem 0 4rem;
    view-transition-name: page-main;
  }

  .mobile-nav {
    position: sticky;
    bottom: 0;
    z-index: 45;
    display: none;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0.25rem;
    padding: 0.55rem 0.75rem calc(0.55rem + env(safe-area-inset-bottom));
    border-top: 1px solid var(--border);
    background: color-mix(in srgb, var(--bg) 78%, transparent);
    backdrop-filter: blur(12px) saturate(140%);
    -webkit-backdrop-filter: blur(12px) saturate(140%);
  }
  .mobile-link {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.15rem;
    min-height: 2.8rem;
    border-radius: var(--radius);
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.58rem;
    font-weight: 600;
    padding: 0.2rem 0;
  }
  .mobile-link.active {
    color: var(--accent-text);
    background: var(--accent-soft);
  }
  .mobile-label {
    line-height: 1;
  }

  @media (max-width: 920px) {
    .shell { --shell-header-offset: 3.5rem; }
    .header-nav { display: none; }
    .brand-tag { display: none; }
    .tagline { display: none; }
    .mobile-nav { display: grid; }
    main { padding-bottom: 5.75rem; }
  }
</style>
