"""
Local FPL session cookie storage + audit.

The user pastes a cookie they already hold in their browser. We store it on
disk with 0o600 perms at ~/.fulcrum/fpl_session.json (atomic writes), attach
it only to fantasy.premierleague.com requests that need auth, and never
include its value in any HTTP response body or log line.

Security invariants (enforced by tests):
  1. Cookie file is created with mode 0o600.
  2. Cookie file is written atomically (temp file + os.replace).
  3. get_status() never returns any cookie value.
  4. audit() records only {ts, endpoint, manager_id, status} — no cookie.
"""

import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULCRUM_DIR = Path(os.environ.get("FULCRUM_HOME", Path.home() / ".fulcrum"))
COOKIE_FILE = FULCRUM_DIR / "fpl_session.json"
AUDIT_LOG = FULCRUM_DIR / "fpl-reads.log"

# Cookie landscape (verified in Chrome April 2026 against a live FPL session):
#   access_token  — PingOne SSO JWT on .premierleague.com. Issued by the new
#                   OAuth/PKCE flow (account.premierleague.com). The current
#                   credential for any account that's logged in via PingOne.
#                   Accepted by the FPL API both as a Cookie and as
#                   Authorization: Bearer.
#   refresh_token — PingOne refresh token on .premierleague.com. Stored so a
#                   future version can refresh access_token without re-paste.
#                   Not used for reads today.
#   pl_profile    — Legacy session JWT on .premierleague.com. Pre-PingOne accounts
#                   may still have one; FPL accepts it for now.
#   sessionid     — Legacy Django session on fantasy.premierleague.com. Pairs
#                   with pl_profile on legacy accounts.
#   datadome      — DataDome anti-bot token. Include when present to avoid
#                   bot-challenge 403s.
#   csrftoken     — Only needed for write endpoints (Phase 2). Accepted now so a
#                   full header paste doesn't lose it.
ALLOWED_COOKIE_KEYS = {
    "access_token", "refresh_token", "global_sso_id",
    "pl_profile", "sessionid",
    "datadome", "csrftoken",
}
# Either of these proves the user is logged in. access_token is the modern flow;
# pl_profile is the legacy flow. At least one must be present to save.
CREDENTIAL_KEYS = ("access_token", "pl_profile")


# ── Storage ──────────────────────────────────────────────────────────

def _ensure_dir() -> None:
    FULCRUM_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_secret(path: Path, content: str) -> None:
    """Write content to path with mode 0o600, atomically."""
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-fpl-")
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_cookie_input(raw: str) -> dict[str, str]:
    """
    Accept either:
      - a full cookie header: "access_token=...; refresh_token=...; datadome=..."
      - the legacy form: "pl_profile=abc; csrftoken=def"
      - just a bare credential value on its own line. Treated as access_token
        (modern flow); use the full-header form to paste a legacy pl_profile.
    Returns {cookie_name: value} filtered to ALLOWED_COOKIE_KEYS.
    """
    if not raw or not raw.strip():
        return {}
    raw = raw.strip()
    if "=" not in raw:
        return {"access_token": raw}
    parts: dict[str, str] = {}
    for chunk in raw.replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        k, _, v = chunk.partition("=")
        k = k.strip()
        v = v.strip().strip('"')
        if k in ALLOWED_COOKIE_KEYS and v:
            parts[k] = v
    return parts


def has_credential(cookies: dict[str, str]) -> bool:
    """True if cookies contain at least one credential we can authenticate with."""
    return any(cookies.get(k) for k in CREDENTIAL_KEYS)


def save_cookies(cookies: dict[str, str], account_id: int | None = None) -> None:
    clean = {k: v for k, v in cookies.items() if k in ALLOWED_COOKIE_KEYS and v}
    if not has_credential(clean):
        raise ValueError(
            f"missing required credential: need one of {CREDENTIAL_KEYS}"
        )
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "cookies": clean,
        "account_id": account_id,
        "stored_at": now,
        "last_validated_at": now if account_id is not None else None,
    }
    _atomic_write_secret(COOKIE_FILE, json.dumps(payload, indent=2, sort_keys=True))


def load_cookies() -> dict[str, Any] | None:
    if not COOKIE_FILE.exists():
        return None
    try:
        data = json.loads(COOKIE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def get_cookie_jar() -> dict[str, str] | None:
    """Return a cookie dict ready to attach to an aiohttp request, or None."""
    data = load_cookies()
    if not data:
        return None
    cookies = (data.get("cookies") or {}) if isinstance(data.get("cookies"), dict) else {}
    if not has_credential(cookies):
        return None
    return {k: v for k, v in cookies.items() if k in ALLOWED_COOKIE_KEYS}


def clear_cookies() -> None:
    try:
        COOKIE_FILE.unlink()
    except FileNotFoundError:
        pass


def mark_validated(account_id: int) -> None:
    """Update validation metadata after a successful authed call."""
    data = load_cookies()
    if not data:
        return
    data["account_id"] = int(account_id)
    data["last_validated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_secret(COOKIE_FILE, json.dumps(data, indent=2, sort_keys=True))


# ── Public status (cookie values never returned) ─────────────────────

def get_status() -> dict[str, Any]:
    data = load_cookies() or {}
    cookies = data.get("cookies") or {}
    if cookies.get("access_token"):
        auth_mode = "pingone"
    elif cookies.get("pl_profile"):
        auth_mode = "legacy"
    else:
        auth_mode = None
    return {
        "connected": has_credential(cookies),
        "auth_mode": auth_mode,
        "has_csrf": bool(cookies.get("csrftoken")),
        "has_datadome": bool(cookies.get("datadome")),
        "account_id": data.get("account_id"),
        "stored_at": data.get("stored_at"),
        "last_validated_at": data.get("last_validated_at"),
    }


# ── Audit log ────────────────────────────────────────────────────────

def audit(endpoint: str, manager_id: int | None, status_code: Any) -> None:
    """Append a one-line JSON audit record. Never logs the cookie value."""
    _ensure_dir()
    try:
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "manager_id": manager_id,
            "status": status_code,
        })
        with open(AUDIT_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        # Audit failure must not break the caller.
        pass


# ── File-mode verification (called from tests) ───────────────────────

def cookie_file_mode() -> int | None:
    """Return the permission bits of the cookie file, or None if missing."""
    if not COOKIE_FILE.exists():
        return None
    return stat.S_IMODE(os.stat(COOKIE_FILE).st_mode)
