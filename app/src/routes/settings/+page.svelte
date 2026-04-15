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
        <dt>Auth mode</dt>
        <dd>{status.auth_mode === 'pingone' ? 'PingOne (access_token)' : status.auth_mode === 'legacy' ? 'Legacy (pl_profile)' : '—'}</dd>
        <dt>Stored</dt>
        <dd>{fmtTime(status.stored_at)}</dd>
        <dt>Last validated</dt>
        <dd>{fmtTime(status.last_validated_at)}</dd>
        <dt>DataDome token</dt>
        <dd>{status.has_datadome ? 'present (helps avoid bot challenges)' : 'absent'}</dd>
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
      <h2>{status?.connected ? 'Re-connect (token expired)' : 'Connect your live FPL session — 5 steps'}</h2>
    </header>

    <p class="caveat">
      The cookie panel in DevTools <b>does not work</b> for FPL accounts
      created since 2025. The real session token lives in
      <code>localStorage</code>. Follow the steps below exactly — copy the
      whole one-liner including the leading <code>copy(</code>.
    </p>

    <ol class="steps big-steps">
      <li>
        <div class="step-title">Open FPL and log in</div>
        <div class="step-body">
          Go to <a href="https://fantasy.premierleague.com/my-team" target="_blank" rel="noopener">https://fantasy.premierleague.com/my-team</a>
          in Chrome (or any Chromium browser) and make sure your team page
          loads. If it asks for a password, log in.
        </div>
      </li>

      <li>
        <div class="step-title">Open DevTools — on the FPL tab, not on Volante</div>
        <div class="step-body">
          Press <kbd>⌥</kbd>+<kbd>⌘</kbd>+<kbd>I</kbd> (macOS) or
          <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>I</kbd> (Windows / Linux).
          A panel will open at the bottom or side of the FPL page.
        </div>
      </li>

      <li>
        <div class="step-title">Click the <b>Console</b> tab inside DevTools</div>
        <div class="step-body">
          Across the top of the DevTools panel you'll see tabs:
          <code>Elements</code> · <code>Console</code> · <code>Sources</code> ·
          <code>Network</code> · <code>Application</code> · …
          Click <b>Console</b>. You'll see a blinking <code>&gt;</code> prompt.
        </div>
      </li>

      <li>
        <div class="step-title">Paste this <i>entire line</i> into the Console and press Enter</div>
        <div class="step-body">
          <pre class="snippet">copy('access_token=' + JSON.parse(localStorage[Object.keys(localStorage).find(k=&gt;k.startsWith('oidc.user:'))]).access_token)</pre>
          <button class="btn-ghost small copy-btn" onclick={() => navigator.clipboard.writeText("copy('access_token=' + JSON.parse(localStorage[Object.keys(localStorage).find(k=>k.startsWith('oidc.user:'))]).access_token)")}>
            Copy snippet to clipboard
          </button>
          <p class="step-note">
            The Console will print <code>undefined</code> — that's normal.
            What matters is that your clipboard now holds
            <code>access_token=eyJhbG…</code> (a long string starting with
            <code>access_token=eyJ</code>).
            <br>
            <b>If you see <code>SyntaxError</code> or <code>TypeError</code>:</b>
            you're not actually logged in to FPL — go back to step 1.
          </p>
        </div>
      </li>

      <li>
        <div class="step-title">Paste into the box below and click <b>Test & Save</b></div>
        <div class="step-body">
          Volante will ping FPL once with the token, confirm it belongs to
          you, and unlock the live squad / bank / free-transfer count.
          You should see the <b>Connection</b> chip above flip to
          <span class="chip chip-ok inline-chip">connected</span>.
        </div>
      </li>
    </ol>

    <details class="legacy">
      <summary>I have an old FPL account (pre-2025) — show the legacy <code>pl_profile</code> path</summary>
      <ol class="steps">
        <li>DevTools → <b>Application</b> tab → <b>Cookies</b> → click
          <code>https://fantasy.premierleague.com</code>.</li>
        <li>Find the rows <code>pl_profile</code> and <code>sessionid</code>.
          Copy each <b>Value</b>.</li>
        <li>Build one line:
          <pre class="snippet">pl_profile=&lt;value&gt;; sessionid=&lt;value&gt;</pre>
          and paste it below.</li>
        <li>Click <b>Test & Save</b>.</li>
      </ol>
    </details>

    <label class="field">
      <span class="label-text">Paste your token here</span>
      <textarea
        bind:value={cookieInput}
        placeholder="access_token=eyJhbG..."
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
        Stored at <code>~/.fulcrum/fpl_session.json</code> with <code>0600</code>
        perms. Never echoed, never logged, never in the repo.
        <b>Token expires every few hours</b> — when it does, just rerun the
        same one-liner and re-paste.
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
  .caveat {
    margin: 0 0 0.8rem 0;
    padding: 0.6rem 0.75rem;
    border-radius: var(--radius-sm);
    background: rgba(255, 200, 60, 0.08);
    border: 1px solid rgba(255, 200, 60, 0.25);
    color: var(--text-secondary);
    font-size: 0.82rem;
    line-height: 1.5;
  }
  .caveat code { background: var(--bg-elevated); padding: 1px 5px; border-radius: 3px; }
  .snippet {
    margin: 0.4rem 0;
    padding: 0.55rem 0.7rem;
    background: var(--bg-elevated);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.45;
  }
  .copy-btn { margin: 0.2rem 0 0.4rem; }
  .big-steps { padding-left: 1.4rem; line-height: 1.5; counter-reset: step; }
  .big-steps > li {
    margin-bottom: 1rem;
    padding-left: 0.4rem;
  }
  .big-steps > li::marker { font-weight: 700; color: var(--accent-text); }
  .step-title { font-weight: 600; color: var(--text); margin-bottom: 0.25rem; font-size: 0.95rem; }
  .step-body { color: var(--text-secondary); font-size: 0.86rem; line-height: 1.55; }
  .step-body code { background: var(--bg-elevated); padding: 1px 5px; border-radius: 3px; font-size: 0.92em; }
  .step-body a { color: var(--accent-text); }
  .step-note { margin: 0.5rem 0 0; font-size: 0.8rem; color: var(--text-muted); line-height: 1.5; }
  .inline-chip { display: inline-block; vertical-align: middle; margin: 0 0.15rem; }
  .legacy {
    margin: 0.6rem 0 1rem;
    padding: 0.65rem 0.85rem;
    border: 1px dashed var(--line);
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--bg-elevated) 50%, transparent);
  }
  .legacy summary { cursor: pointer; font-size: 0.84rem; color: var(--text-secondary); }
  .legacy summary code { background: var(--bg-elevated); padding: 1px 5px; border-radius: 3px; }
  .legacy[open] summary { margin-bottom: 0.5rem; }

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
