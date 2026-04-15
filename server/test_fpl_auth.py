"""
Tests for fpl_auth: cookie storage, file perms, redaction, parsing.

Security-critical invariants are under /* security */ blocks — those must not
regress.
"""
import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

import fpl
import fpl_auth


@pytest.fixture(autouse=True)
def _isolated_fulcrum(monkeypatch, tmp_path):
    """Redirect FULCRUM_DIR to a tmp dir so tests don't clobber real cookies."""
    monkeypatch.setattr(fpl_auth, "FULCRUM_DIR", tmp_path)
    monkeypatch.setattr(fpl_auth, "COOKIE_FILE", tmp_path / "fpl_session.json")
    monkeypatch.setattr(fpl_auth, "AUDIT_LOG", tmp_path / "fpl-reads.log")
    yield


# ── parse_cookie_input ───────────────────────────────────────────────

def test_parse_bare_value_treated_as_access_token():
    out = fpl_auth.parse_cookie_input("eyJhbGciOi.deadbeef.signature")
    assert out == {"access_token": "eyJhbGciOi.deadbeef.signature"}


def test_parse_full_cookie_header_pingone():
    raw = (
        "access_token=eyJ-modern; refresh_token=rf-xyz; "
        "datadome=dd-token; _ga=evil"
    )
    out = fpl_auth.parse_cookie_input(raw)
    assert out == {
        "access_token": "eyJ-modern",
        "refresh_token": "rf-xyz",
        "datadome": "dd-token",
    }


def test_parse_full_cookie_header_legacy():
    raw = "pl_profile=abc123; csrftoken=xyz789; sessionid=dj-session; datadome=dd-token"
    out = fpl_auth.parse_cookie_input(raw)
    assert out == {
        "pl_profile": "abc123",
        "csrftoken": "xyz789",
        "sessionid": "dj-session",
        "datadome": "dd-token",
    }


def test_parse_ignores_unknown_keys():
    out = fpl_auth.parse_cookie_input("access_token=a; _ga=evil; __cfduid=tracker")
    assert out == {"access_token": "a"}


def test_parse_strips_quotes_and_whitespace():
    out = fpl_auth.parse_cookie_input('  pl_profile="quoted-value"  ; csrftoken = trimmed ')
    assert out == {"pl_profile": "quoted-value", "csrftoken": "trimmed"}


def test_parse_empty_returns_empty():
    assert fpl_auth.parse_cookie_input("") == {}
    assert fpl_auth.parse_cookie_input("   \n  ") == {}


def test_parse_multiline_accepts_newlines_as_separators():
    raw = "pl_profile=a\ncsrftoken=b"
    assert fpl_auth.parse_cookie_input(raw) == {"pl_profile": "a", "csrftoken": "b"}


# ── save / load roundtrip ────────────────────────────────────────────

def test_save_and_load_roundtrip():
    fpl_auth.save_cookies({"pl_profile": "token-abc", "csrftoken": "csrf-def"}, account_id=3174196)
    data = fpl_auth.load_cookies()
    assert data["cookies"] == {"pl_profile": "token-abc", "csrftoken": "csrf-def"}
    assert data["account_id"] == 3174196
    assert data["stored_at"]
    assert data["last_validated_at"]


def test_save_rejects_missing_credential():
    with pytest.raises(ValueError, match="credential"):
        fpl_auth.save_cookies({"csrftoken": "only-csrf", "datadome": "dd"})


def test_save_accepts_access_token_alone():
    fpl_auth.save_cookies({"access_token": "eyJ-modern"}, account_id=3174196)
    data = fpl_auth.load_cookies()
    assert data["cookies"] == {"access_token": "eyJ-modern"}
    assert data["account_id"] == 3174196


def test_get_status_reports_pingone_mode():
    fpl_auth.save_cookies({"access_token": "eyJ-modern", "datadome": "dd"}, account_id=42)
    s = fpl_auth.get_status()
    assert s["connected"] is True
    assert s["auth_mode"] == "pingone"
    assert s["has_datadome"] is True


def test_get_status_reports_legacy_mode():
    fpl_auth.save_cookies({"pl_profile": "old-jwt"}, account_id=42)
    s = fpl_auth.get_status()
    assert s["connected"] is True
    assert s["auth_mode"] == "legacy"


def test_save_strips_disallowed_keys():
    fpl_auth.save_cookies({"pl_profile": "a", "_ga": "leak"})
    data = fpl_auth.load_cookies()
    assert "pl_profile" in data["cookies"]
    assert "_ga" not in data["cookies"]


def test_get_cookie_jar_returns_none_when_absent():
    assert fpl_auth.get_cookie_jar() is None


def test_get_cookie_jar_returns_dict_when_present():
    fpl_auth.save_cookies({"pl_profile": "a", "csrftoken": "b"})
    jar = fpl_auth.get_cookie_jar()
    assert jar == {"pl_profile": "a", "csrftoken": "b"}


def test_clear_cookies_removes_file():
    fpl_auth.save_cookies({"pl_profile": "x"})
    assert fpl_auth.COOKIE_FILE.exists()
    fpl_auth.clear_cookies()
    assert not fpl_auth.COOKIE_FILE.exists()


def test_clear_cookies_idempotent():
    fpl_auth.clear_cookies()  # no file
    fpl_auth.clear_cookies()  # still no file — must not raise


def test_mark_validated_updates_metadata():
    fpl_auth.save_cookies({"pl_profile": "x"})
    fpl_auth.mark_validated(3174196)
    data = fpl_auth.load_cookies()
    assert data["account_id"] == 3174196
    assert data["last_validated_at"]


# ── /* security */ File permissions ──────────────────────────────────

def test_cookie_file_is_0600_on_first_write():
    fpl_auth.save_cookies({"pl_profile": "secret"})
    mode = fpl_auth.cookie_file_mode()
    assert mode == 0o600, f"expected 0o600, got {oct(mode) if mode else None}"


def test_cookie_file_is_0600_after_overwrite():
    fpl_auth.save_cookies({"pl_profile": "first"})
    fpl_auth.save_cookies({"pl_profile": "second"})
    assert fpl_auth.cookie_file_mode() == 0o600


def test_mark_validated_preserves_0600():
    fpl_auth.save_cookies({"pl_profile": "x"})
    fpl_auth.mark_validated(42)
    assert fpl_auth.cookie_file_mode() == 0o600


# ── /* security */ Redaction: status() must never leak cookie values ─

SECRET = "this-is-the-cookie-value-that-should-never-leak"


def test_status_does_not_contain_cookie_value():
    fpl_auth.save_cookies({"pl_profile": SECRET}, account_id=3174196)
    s = fpl_auth.get_status()
    # Serialize and scan — any representation of the secret is a leak.
    dump = json.dumps(s)
    assert SECRET not in dump
    # But status must still signal connection.
    assert s["connected"] is True
    assert s["account_id"] == 3174196


def test_audit_log_does_not_contain_cookie_value():
    fpl_auth.save_cookies({"pl_profile": SECRET})
    fpl_auth.audit("/my-team/123/", 123, 200)
    log_text = fpl_auth.AUDIT_LOG.read_text()
    assert SECRET not in log_text
    # And the audit line parses as JSON.
    record = json.loads(log_text.strip().split("\n")[-1])
    assert record["endpoint"] == "/my-team/123/"
    assert record["manager_id"] == 123
    assert record["status"] == 200


# ── /* security */ Atomic write: a crash mid-write must leave either
#    the old contents or nothing — never a truncated file. ───────────

def test_atomic_write_leaves_no_temp_files_on_success(tmp_path):
    fpl_auth.save_cookies({"pl_profile": "a"})
    fpl_auth.save_cookies({"pl_profile": "b"})
    fpl_auth.save_cookies({"pl_profile": "c"})
    temp_files = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-fpl-")]
    assert not temp_files, f"temp files not cleaned up: {temp_files}"


def test_atomic_write_cleans_up_temp_on_failure(monkeypatch, tmp_path):
    # Force os.replace to fail, verify no orphaned temp file remains.
    original_replace = os.replace
    calls = {"n": 0}

    def boom(src, dst):
        calls["n"] += 1
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        fpl_auth.save_cookies({"pl_profile": "victim"})
    monkeypatch.setattr(os, "replace", original_replace)

    temp_files = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-fpl-")]
    assert not temp_files, f"temp files leaked: {temp_files}"
    assert not fpl_auth.COOKIE_FILE.exists()


# ── Load robustness ──────────────────────────────────────────────────

def test_load_tolerates_corrupted_json(tmp_path):
    fpl_auth.COOKIE_FILE.write_text("not json {{{")
    assert fpl_auth.load_cookies() is None
    assert fpl_auth.get_cookie_jar() is None


def test_load_tolerates_wrong_shape(tmp_path):
    fpl_auth.COOKIE_FILE.write_text(json.dumps(["a", "list", "not", "dict"]))
    assert fpl_auth.load_cookies() is None


def test_get_cookie_jar_rejects_missing_credential(tmp_path):
    fpl_auth.COOKIE_FILE.write_text(json.dumps({"cookies": {"csrftoken": "only"}}))
    assert fpl_auth.get_cookie_jar() is None


def test_authed_headers_send_bearer_for_pingone():
    # Empirically (Apr 2026): FPL's /api/me/ validates Authorization: Bearer for
    # PingOne accounts. The access_token cookie alone returns 200 with
    # {"player": null} — the cookie is recognized but treated as anonymous.
    h = fpl._build_authed_headers({"access_token": "eyJ-modern", "datadome": "dd"})
    assert h["Authorization"] == "Bearer eyJ-modern"
    assert "access_token=eyJ-modern" in h["Cookie"]
    assert "datadome=dd" in h["Cookie"]


def test_authed_headers_legacy_pl_profile_cookie_only():
    # Legacy accounts authenticate via the pl_profile cookie; no Bearer needed.
    h = fpl._build_authed_headers({"pl_profile": "old-jwt", "sessionid": "dj"})
    assert "Authorization" not in h
    assert "pl_profile=old-jwt" in h["Cookie"]
    assert "sessionid=dj" in h["Cookie"]


def test_get_cookie_jar_accepts_access_token(tmp_path):
    fpl_auth.COOKIE_FILE.write_text(json.dumps({
        "cookies": {"access_token": "eyJ-modern", "datadome": "dd"},
    }))
    jar = fpl_auth.get_cookie_jar()
    assert jar == {"access_token": "eyJ-modern", "datadome": "dd"}
