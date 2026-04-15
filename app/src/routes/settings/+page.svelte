<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getFplStatus,
    setFplCookie,
    clearFplCookie,
    type FplSessionStatus,
  } from '$lib/api';

  let status = $state<FplSessionStatus | null>(null);
  let loading = $state(true);
  let cookieInput = $state('');
  let saving = $state(false);
  let error = $state('');
  let success = $state('');

  async function refresh() {
    loading = true;
    try {
      status = await getFplStatus();
    } catch (e: any) {
      error = e?.message || 'Could not reach Volante backend';
    } finally {
      loading = false;
    }
  }

  onMount(refresh);

  async function onSave() {
    error = '';
    success = '';
    if (!cookieInput.trim()) {
      error = 'Paste your FPL cookie before saving.';
      return;
    }
    saving = true;
    try {
      status = await setFplCookie(cookieInput);
      cookieInput = '';
      success = `Connected to FPL as manager #${status.account_id}.`;
    } catch (e: any) {
      error = e?.message || 'Could not save cookie.';
    } finally {
      saving = false;
    }
  }

  async function onDisconnect() {
    error = '';
    success = '';
    if (!confirm('Disconnect FPL session? You can re-paste anytime.')) return;
    try {
      await clearFplCookie();
      success = 'Disconnected.';
      await refresh();
    } catch (e: any) {
      error = e?.message || 'Could not disconnect.';
    }
  }

  function fmtTime(iso: string | null): string {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  }
</script>

<svelte:head><title>Volante — Settings</title></svelte:head>

<div class="container page-stack reveal">

  <section class="intro reveal" style="--i:0">
    <span class="eyebrow">FPL · SESSION · DESK</span>
    <h1>Plug in your live FPL session.</h1>
    <p class="sub">
      Volante only sees your past-deadline team through the public API.
      Paste a cookie from your browser to unlock live squad state,
      accurate free-transfer count, and live bank. Cookie stays on this
      machine — nothing leaves it, nothing goes to GitHub.
    </p>
  </section>

  <section class="card status-card reveal" style="--i:1">
    <header class="card-head">
      <h2>Connection</h2>
      {#if loading}
        <span class="chip chip-muted">checking…</span>
      {:else if status?.connected}
        <span class="chip chip-ok">connected</span>
      {:else}
        <span class="chip chip-off">not connected</span>
      {/if}
    </header>
    {#if status?.connected}
      <dl class="kv">
        <dt>Account</dt>
        <dd>#{status.account_id ?? '—'}</dd>
        <dt>Stored</dt>
        <dd>{fmtTime(status.stored_at)}</dd>
        <dt>Last validated</dt>
        <dd>{fmtTime(status.last_validated_at)}</dd>
        <dt>CSRF present</dt>
        <dd>{status.has_csrf ? 'yes (for Phase 2 writes)' : 'no (reads still work)'}</dd>
      </dl>
      <div class="row">
        <button class="btn-ghost danger" onclick={onDisconnect}>Disconnect</button>
        <p class="hint">
          Disconnecting wipes <code>~/.fulcrum/fpl_session.json</code>.
        </p>
      </div>
    {/if}
  </section>

  <section class="card paste-card reveal" style="--i:2">
    <header class="card-head">
      <h2>{status?.connected ? 'Re-paste cookie' : 'Paste cookie'}</h2>
    </header>

    <ol class="steps">
      <li>Log in at <code>fantasy.premierleague.com</code> in Chrome.</li>
      <li>Open DevTools (<kbd>⌥⌘I</kbd>) → <b>Application</b> tab → <b>Cookies</b> → <b>https://fantasy.premierleague.com</b>.</li>
      <li>Find these and copy their values:
        <ul class="cookie-list">
          <li><code>pl_profile</code> <span class="dim2">(required — scope <code>.premierleague.com</code>)</span></li>
          <li><code>sessionid</code> <span class="dim2">(strongly recommended — scope <code>fantasy.premierleague.com</code>)</span></li>
          <li><code>datadome</code> <span class="dim2">(include if present — avoids bot challenges)</span></li>
        </ul>
      </li>
      <li>Paste below. You can paste a full <code>pl_profile=...; sessionid=...</code> string or just the <code>pl_profile</code> value on its own.</li>
      <li>Click <b>Test & Save</b>. Volante will ping FPL's <code>/me/</code> once to confirm the cookie works and to capture which account it belongs to.</li>
    </ol>

    <label class="field">
      <span class="label-text">Cookie</span>
      <textarea
        bind:value={cookieInput}
        placeholder={'pl_profile=eyJ...; sessionid=dj-... '}
        autocomplete="off"
        spellcheck="false"
        rows="4"
      ></textarea>
    </label>

    {#if error}<p class="msg err">⚠ {error}</p>{/if}
    {#if success}<p class="msg ok">✓ {success}</p>{/if}

    <div class="row">
      <button class="btn-primary" onclick={onSave} disabled={saving || !cookieInput.trim()}>
        {saving ? 'Validating…' : 'Test & Save'}
      </button>
      <p class="hint">
        Cookie is stored at <code>~/.fulcrum/fpl_session.json</code> with <code>0600</code> perms.
        Never echoed back, never logged, never in the repo.
      </p>
    </div>
  </section>

  <section class="card safety reveal" style="--i:3">
    <header class="card-head"><h2>Safety gates</h2></header>
    <ul class="bullets">
      <li><b>Read-only by default.</b> No write endpoints are registered. Volante cannot submit transfers, change your captain, or activate chips.</li>
      <li><b>Scope-isolated.</b> The cookie is attached only to <code>fantasy.premierleague.com</code> authenticated calls. Public endpoints (bootstrap, fixtures, public entry) use a separate unauthenticated session.</li>
      <li><b>Loopback-only writes.</b> The settings endpoints reject non-localhost callers, so if you ever expose Volante on your LAN, attackers can't touch your cookie.</li>
      <li><b>Audit log.</b> Every authenticated call is recorded at <code>~/.fulcrum/fpl-reads.log</code> with timestamp, endpoint and status — never the cookie.</li>
      <li><b>Rate-limited.</b> Live squad is cached 30s in memory, so refreshes don't hammer FPL.</li>
    </ul>
  </section>

</div>

<style>
  .container.page-stack { padding: 2rem 1rem 4rem; max-width: 860px; }
  .eyebrow { font-size: 0.7rem; letter-spacing: 0.15em; color: var(--accent); font-weight: 700; }
  h1 {
    font-family: var(--font-display);
    font-size: clamp(2rem, 4vw, 2.7rem);
    line-height: 1.05;
    margin: 0.35rem 0 0.5rem;
  }
  .sub { color: var(--text-secondary); max-width: 640px; line-height: 1.55; }

  .card {
    background: var(--bg-card);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    padding: 1.1rem 1.25rem;
    margin-top: 1rem;
  }
  .card-head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; margin-bottom: 0.7rem;
  }
  .card-head h2 { margin: 0; font-size: 1.05rem; letter-spacing: 0.02em; }

  .chip {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
    padding: 0.2rem 0.55rem; border-radius: 999px; text-transform: uppercase;
  }
  .chip-ok { background: var(--accent-soft); color: var(--accent-text); }
  .chip-off { background: rgba(255,120,120,0.1); color: #ff8a8a; }
  .chip-muted { background: rgba(255,255,255,0.06); color: var(--text-muted); }

  .kv { display: grid; grid-template-columns: max-content 1fr; gap: 0.3rem 1.1rem; margin: 0 0 0.8rem; font-size: 0.88rem; }
  .kv dt { color: var(--text-muted); }
  .kv dd { margin: 0; color: var(--text); font-variant-numeric: tabular-nums; }

  .steps { padding-left: 1.2rem; line-height: 1.6; color: var(--text-secondary); }
  .steps li { margin-bottom: 0.35rem; }
  .steps code { background: var(--bg-elevated); padding: 1px 5px; border-radius: 3px; }
  kbd { background: var(--bg-elevated); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; font-family: inherit; font-size: 0.82em; }
  .cookie-list { margin: 0.3rem 0 0.4rem 0; padding-left: 1.2rem; }
  .cookie-list li { margin-bottom: 0.15rem; }

  .field { display: block; margin-top: 0.6rem; }
  .label-text { display: block; font-size: 0.7rem; letter-spacing: 0.12em; color: var(--text-muted); margin-bottom: 0.3rem; text-transform: uppercase; }
  textarea {
    width: 100%; box-sizing: border-box; background: var(--bg-elevated);
    border: 1px solid var(--line); border-radius: var(--radius-sm);
    color: var(--text); padding: 0.65rem 0.8rem; font-family: var(--font-mono);
    font-size: 0.82rem; resize: vertical; min-height: 88px;
  }
  textarea:focus { outline: 2px solid var(--accent-soft); }

  .row { display: flex; align-items: center; gap: 0.8rem; margin-top: 0.7rem; flex-wrap: wrap; }
  .hint { color: var(--text-muted); font-size: 0.78rem; margin: 0; line-height: 1.5; }
  .hint code { background: var(--bg-elevated); padding: 1px 4px; border-radius: 3px; }

  .msg { margin: 0.7rem 0 0; padding: 0.55rem 0.75rem; border-radius: var(--radius-sm); font-size: 0.86rem; }
  .msg.err { background: rgba(255,120,120,0.1); color: #ff8a8a; border: 1px solid rgba(255,120,120,0.2); }
  .msg.ok { background: var(--accent-soft); color: var(--accent-text); border: 1px solid rgba(0,255,156,0.2); }

  .bullets { padding-left: 1.1rem; line-height: 1.6; color: var(--text-secondary); margin: 0; }
  .bullets li { margin-bottom: 0.4rem; }
  .bullets code { background: var(--bg-elevated); padding: 1px 5px; border-radius: 3px; }

  .btn-ghost.danger { color: #ff8a8a; border-color: rgba(255,120,120,0.3); }
  .btn-ghost.danger:hover { background: rgba(255,120,120,0.08); }
</style>
