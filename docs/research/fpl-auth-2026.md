# FPL Authenticated API — State of the Art (April 2026)

Target endpoint for Volante: `GET https://fantasy.premierleague.com/api/my-team/{entry_id}/`
(returns live pre-deadline team state — free transfers, bank, pending chip, captain, bench order).

All findings below are grounded in community sources; this is a moving target because the
Premier League login service has been hardened repeatedly since 2023. Treat this as a
snapshot, not a spec.

---

## 1. Cookie names that matter

For **read-only GET** on `/api/my-team/{id}/`, the community consensus (multiple guides,
the `amosbastian/fpl` wrapper, Bram Vanherle's auth guide) is that **three cookies** are
returned at login and together form the auth state:

| Cookie | Domain | Role |
|---|---|---|
| `pl_profile` | `.premierleague.com` | Primary identity token (opaque, sent on every authenticated call) |
| `sessionid` | `fantasy.premierleague.com` | FPL-app session; required by `/api/my-team/` and write endpoints |
| `sessionid` | `users.premierleague.com` | Users-service session; needed for the login round-trip, not strictly for `/my-team/` GETs |

**Minimum set for `/api/my-team/{id}/` GETs:** `pl_profile` + `sessionid` (on
`fantasy.premierleague.com`). In practice people send both — some reports of 302
redirects to login when only `pl_profile` is present, so **send both or expect
intermittent failures**.

`csrftoken` is **only required for writes** (POST/PUT). Django CSRF pattern: the server
sets a `csrftoken` cookie, and the client must echo it in the `X-CSRFToken` request
header on any unsafe method. It's irrelevant for the read path we care about.

**`pl_profile` format:** opaque, URL-encoded base64-ish string (not a standard JWT with
three dotted segments). Treat it as a black-box bearer — don't try to parse it.
Community reports put lifetime at roughly the session/"remember-me" window of the
browser — typically **weeks if the user checked "remember me", days otherwise**. No
public doc from FPL confirms this; plan for the token to expire silently and design for
re-prompt.

**DataDome cookie (2024+ addition):** multiple write-ups from 2024 note that some
requests now carry a `datadome` cookie alongside `pl_profile`, and that omitting it
from the `FPL_COOKIE` blob causes intermittent 403s. Capture it if present.

Sources:
[Bram Vanherle — FPL auth guide](https://medium.com/@bram.vanherle1/fantasy-premier-league-api-authentication-guide-2f7aeb2382e4),
[amosbastian/fpl login()](https://github.com/amosbastian/fpl/blob/master/fpl/fpl.py),
[Conor Aspell — Lambda auto-manage](https://conor-aspell.medium.com/updated-automatically-manage-your-fantasy-premier-league-team-with-python-and-aws-lambda-e92eebacd93f).

---

## 2. Response shape of `/api/my-team/{id}/`

Three top-level keys: **`picks`**, **`chips`**, **`transfers`**. Illustrative shape
(reconstructed from `amosbastian/fpl` source and community examples):

```jsonc
{
  "picks": [
    {
      "element": 351,           // player id (bootstrap-static.elements[].id)
      "position": 1,            // 1..15 (1..11 XI, 12..15 bench order)
      "selling_price": 55,      // in tenths of £m (55 = £5.5m)
      "purchase_price": 50,
      "multiplier": 2,          // 0 bench, 1 starter, 2 captain, 3 TC
      "is_captain": false,
      "is_vice_captain": false
    }
    // ...15 entries
  ],
  "chips": [
    { "name": "wildcard",  "status_for_entry": "available", "played_by_entry": [], "number": 1, "start_event": 2, "stop_event": 19, "chip_name": "wildcard" },
    { "name": "freehit",   "status_for_entry": "available", ... },
    { "name": "bboost",    "status_for_entry": "played",    ... },
    { "name": "3xc",       "status_for_entry": "available", ... }
  ],
  "transfers": {
    "cost": 4,       // points cost if confirmed now (hits)
    "status": "cost",// "cost" | "free" | "unlimited" (wildcard/FH active)
    "limit": 5,      // max FTs bankable (currently 5 in 25/26)
    "made": 2,       // transfers already made this GW
    "bank": 13,      // cash in bank, tenths of £m (13 = £1.3m)
    "value": 1012    // squad value (sum of selling_price), tenths of £m
  }
}
```

**Pending-chip detection** (wildcard/free-hit staged but not confirmed): `/api/my-team/`
does **not** expose staged/pending chip activation directly. When the user has clicked
"Play Wildcard" in the UI, the chip is applied to the *next* POST `/api/transfers/`
(payload field `"chip": "wildcard"|"freehit"|"3xc"|"bboost"`). Volante's "pending chip"
indicator must be inferred from `transfers.status == "unlimited"` (wildcard/FH active on
the in-flight transfer session) plus the chip's `status_for_entry`. There's no clean
flag — this is a known gap.

**Difference from `/api/entry/{id}/event/{gw}/picks/`:** the `event/{gw}/picks/`
endpoint is **historical**: it returns the team as it was locked at the deadline for
that specific GW (with `stats`, `automatic_subs`, `active_chip`). `/api/my-team/` is
**live/mutable**: it reflects in-progress transfer decisions, current selling prices,
and current free-transfer count that changes as the user makes moves. For a
pre-deadline live dashboard, `/api/my-team/` is the one you want; `event/.../picks/` is
strictly post-deadline.

Sources: [amosbastian/fpl models/user.py](https://github.com/amosbastian/fpl/blob/master/fpl/models/user.py),
[Frenzel Timothy — Endpoints guide](https://medium.com/@frenzelts/fantasy-premier-league-api-endpoints-a-detailed-guide-acbd5598eb19),
[Oliver Looney — FPL APIs Explained](https://www.oliverlooney.com/blogs/FPL-APIs-Explained).

---

## 3. Error behaviour

| Condition | Status | Body / Notes |
|---|---|---|
| No cookies | `302` -> login, or `403 Forbidden` with HTML body | Not JSON; detect via `Content-Type != application/json` |
| `pl_profile` for wrong entry id | `403 Forbidden`, JSON `{"detail": "You do not have permission..."}` | `amosbastian/fpl` raises "User ID does not match provided email address!" on this |
| Cookie expired | `403` (same as above) or redirect to login | Indistinguishable from "wrong account" — handle both as "re-auth needed" |
| Rate limit | `429 Too Many Requests` | Community reports are rare for authenticated reads; `Retry-After` header usually present |
| Cloudflare / DataDome challenge | `403` with HTML body containing `cf-mitigated` or `datadome` challenge page | Not JSON; detect and stop |
| Deadline window | Intermittent `500`/`503` | API is known to wobble in the 30 min around the deadline and during GW processing |

**Cloudflare / DataDome status (April 2026):** the public read API
(`/api/bootstrap-static/`, `/api/fixtures/`) still works with bare `curl` — no
challenge. The **authenticated path** (`users.premierleague.com/accounts/login/`) is
where bot-protection lives; that endpoint has shown DataDome challenges since 2024,
which is why the community pivoted from "script does the login" to "user extracts
cookies from a real browser session". Once you have `pl_profile` + `sessionid`, the
`/api/my-team/` GET has not been reported as challenge-protected.

---

## 4. Headers and rate limits

**Minimum header set that works consistently:**

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://fantasy.premierleague.com/my-team",
    "Origin":  "https://fantasy.premierleague.com",
}
```

The `amosbastian/fpl` library uses an Android `Dalvik/2.1.0` UA for the login POST
(arguably to dodge web-UA fingerprinting). For reads on `/api/my-team/` a normal
desktop UA is fine. The single most common failure mode in GitHub issues is **sending
no `User-Agent`** — Python `requests` defaults (`python-requests/2.x`) have been 403ed
intermittently.

**Safe request rate:** no published limit. Community-derived safe zone is
**≤ 1 req/sec sustained, bursts up to ~5/sec tolerated**. Keep a local cache and avoid
polling `/api/my-team/` more than once every 30–60s per user.

**Account bans for script access:** no credible public reports of ban-for-script-use
when staying on authenticated endpoints under a single real account. Abuse reports
cluster around aggressive scraping of leagues/standings pages. Volante's per-user
local-tool model is safe.

Example request:

```python
import requests

COOKIES = {
    "pl_profile": "eyJ1IjogeyJpZCI6IDEyMzQ1Njc4LCAiZm4iOiAiSGFycnkiLCJsbiI6ICJMZWUifX0=...",
    "sessionid": "abc123def456...",   # from fantasy.premierleague.com
    # optional but recommended if present:
    # "datadome": "~opaque~",
}
r = requests.get(
    f"https://fantasy.premierleague.com/api/my-team/{entry_id}/",
    cookies=COOKIES, headers=HEADERS, timeout=10,
)
r.raise_for_status()
state = r.json()  # {"picks": [...], "chips": [...], "transfers": {...}}
```

---

## 5. Write endpoints (document only — not in v1)

**`POST https://fantasy.premierleague.com/api/transfers/`** — submit transfers.

```jsonc
// Body
{
  "confirmed": true,                 // false = validate only
  "entry": 1234567,
  "event": 33,                       // next GW
  "chip": null,                      // or "wildcard" | "freehit" | "3xc" | "bboost"
  "wildcard": false,
  "freehit": false,
  "transfers": [
    { "element_in": 351, "element_out": 427,
      "purchase_price": 145, "selling_price": 140 }
  ]
}
```

Required headers on writes: `Content-Type: application/json`,
`Referer: https://fantasy.premierleague.com/transfers`,
`Origin: https://fantasy.premierleague.com`, `X-CSRFToken: <value of csrftoken cookie>`.
Cookies: `pl_profile` + `sessionid` + `csrftoken`. Response `200 {"spent_points": N}`
on success, or `{"non_form_errors": [...]}` on validation failure.

**`POST https://fantasy.premierleague.com/api/my-team/{id}/`** — save captain /
vice / bench order without making transfers. Body: `{"chip": null, "picks": [...same
15-item shape as the GET response...]}`. Same header/cookie requirements.

Source: [Conor Aspell — auto-manage](https://conor-aspell.medium.com/updated-automatically-manage-your-fantasy-premier-league-team-with-python-and-aws-lambda-e92eebacd93f),
[amosbastian/fpl models/user.py](https://github.com/amosbastian/fpl/blob/master/fpl/models/user.py).

---

## 6. Open-source clients worth studying

1. **`amosbastian/fpl`** (Python, async, ~550 stars) — the canonical reference. Its
   `login()` function is where to read the exact payload shape. Gotcha it documents:
   credential-only login fails with 403; the wrapper tells you to set `FPL_COOKIE`
   from a browser session. This is the single best signal about the state of the login
   service. [GitHub](https://github.com/amosbastian/fpl).
2. **`sertalpbilal/FPL-Optimization-Tools`** (Python) — widely used solver. Doesn't
   auth, but its ecosystem (notebooks, colab) is where FPL power-users live; worth
   scanning their issue tracker for recent breakages.
3. **`jeppe-smith/fpl-api`** (TypeScript) — clean types for public endpoints. Notably
   **does not** implement authenticated endpoints ("hopefully soon" — has been unchanged
   for years), which itself is a data point on how brittle the login path is.
4. **`chrisbrownlie/fantasy`** (R) — has a clean `authenticate()` / session-scoped
   cookie model; useful mental model even in Python.
5. **`fpldev/fplserver`** — community endpoint documentation repo; good cross-reference
   for URL patterns.
6. **Conor Aspell's AWS Lambda tutorial** — not a library, but the clearest
   end-to-end example of programmatic login + transfer POST in the wild.

**Common gotcha they all warn about:** login via email/password programmatically is
unreliable. Every serious recent project has pivoted to "user pastes cookie".

---

## 7. Cookie extraction UX (Chrome DevTools, April 2026)

The classic path still works:

1. Log in at `https://fantasy.premierleague.com/` in Chrome (tick "Remember me").
2. Open DevTools → **Application** tab → **Storage** → **Cookies** →
   `https://fantasy.premierleague.com`.
3. Copy the `sessionid` value.
4. Switch Cookies scope to `https://www.premierleague.com` (or any `.premierleague.com`
   row) and copy `pl_profile`.
5. Optional: copy `datadome` from the same domain list if present.

**Cookie flags:** `pl_profile` is set with `Secure`, typically **not** `HttpOnly`
(DevTools can still read it — this is why the UX works). `sessionid` has historically
been `HttpOnly` on some responses — DevTools Application panel **still shows HttpOnly
cookies**, it's only JS `document.cookie` that can't read them. So the extraction path
is unaffected by `HttpOnly`. `SameSite=Lax` on both, which is fine for our use.

No reports in 2025–2026 of FPL tightening cookie attributes in a way that breaks
DevTools extraction.

**UX recommendation for Volante:** a one-time setup modal with screenshots of the
DevTools Cookies panel, two text inputs (`pl_profile`, `sessionid`), an optional third
(`datadome`), and a "Test connection" button that does a `GET /api/me/` — detect 200 vs
302/403 to validate. Store encrypted at rest in `~/.fulcrum/.env`; never write cookies
to git-tracked config files (per global rule).

---

## Executive summary (150 words)

**Minimum cookies for read-only `/api/my-team/{id}/`:** `pl_profile` (domain
`.premierleague.com`) + `sessionid` (domain `fantasy.premierleague.com`). Also capture
`datadome` if present — it's become relevant since 2024 and prevents intermittent 403s.
No `csrftoken` needed for GETs.

**Header set:** desktop Chrome `User-Agent`, `Accept: application/json, text/plain, */*`,
`Accept-Language: en-GB,en;q=0.9`, `Referer: https://fantasy.premierleague.com/my-team`,
`Origin: https://fantasy.premierleague.com`. Never send with Python's default UA.

**Biggest gotcha:** do **not** attempt programmatic email/password login against
`users.premierleague.com/accounts/login/` — it's behind DataDome and fails unpredictably
with 403. Use cookie-paste UX exclusively. The `amosbastian/fpl` maintainer essentially
gave up on credential login and added `FPL_COOKIE` env var as the real path.

**Best client to model:** **`amosbastian/fpl`** — read `login()` and `User.get_team()`
in `models/user.py`; its 403-handling is the correct pattern.

---

**Sources cited:**
[amosbastian/fpl](https://github.com/amosbastian/fpl) ·
[Bram Vanherle auth guide](https://medium.com/@bram.vanherle1/fantasy-premier-league-api-authentication-guide-2f7aeb2382e4) ·
[Oliver Looney — FPL APIs Explained](https://www.oliverlooney.com/blogs/FPL-APIs-Explained) ·
[Frenzel Timothy — Endpoints](https://medium.com/@frenzelts/fantasy-premier-league-api-endpoints-a-detailed-guide-acbd5598eb19) ·
[Conor Aspell — Lambda auto-manage](https://conor-aspell.medium.com/updated-automatically-manage-your-fantasy-premier-league-team-with-python-and-aws-lambda-e92eebacd93f) ·
[sertalpbilal/FPL-Optimization-Tools](https://github.com/sertalpbilal/FPL-Optimization-Tools) ·
[jeppe-smith/fpl-api](https://github.com/jeppe-smith/fpl-api) ·
[chrisbrownlie/fantasy](https://chrisbrownlie.github.io/fantasy/articles/authenticating.html) ·
[fpldev/fplserver](https://github.com/fpldev/fplserver).
