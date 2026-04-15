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

# Cookie landscape (as of April 2026, cross-checked with docs/research/fpl-auth-2026.md):
#   pl_profile   — session JWT on .premierleague.com (parent scope). Required.
#   sessionid    — Django session on fantasy.premierleague.com. Required for
#                  /my-team/ in practice; missing it causes intermittent 403s.
#   datadome     — DataDome anti-bot token, set since 2024. Include when present
#                  to avoid bot-challenge 403s.
#   csrftoken    — Only needed for write endpoints (Phase 2). Accepted now so a
#                  full header paste doesn't lose it.
ALLOWED_COOKIE_KEYS = {"pl_profile", "sessionid", "datadome", "csrftoken"}
REQUIRED_FOR_READS = "pl_profile"


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
      - a full cookie header: "pl_profile=abc; csrftoken=def"
      - just the pl_profile value on its own line
    Returns {cookie_name: value} filtered to ALLOWED_COOKIE_KEYS.
    """
    if not raw or not raw.strip():
        return {}
    raw = raw.strip()
    # Heuristic: if no '=' present, treat as a bare pl_profile value
    if "=" not in raw:
        return {"pl_profile": raw}
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


def save_cookies(cookies: dict[str, str], account_id: int | None = None) -> None:
    clean = {k: v for k, v in cookies.items() if k in ALLOWED_COOKIE_KEYS and v}
    if REQUIRED_FOR_READS not in clean:
        raise ValueError(f"missing required cookie: {REQUIRED_FOR_READS}")
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
    if not cookies.get(REQUIRED_FOR_READS):
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
    return {
        "connected": bool(cookies.get(REQUIRED_FOR_READS)),
        "has_csrf": bool(cookies.get("csrftoken")),
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
