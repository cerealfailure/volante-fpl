import pytest
from fastapi import HTTPException

import fpl
import main


@pytest.fixture(autouse=True)
def _clear_live_cache():
    main._LIVE_CACHE.clear()
    yield
    main._LIVE_CACHE.clear()


def test_compute_free_transfers_resets_after_chip():
    history = [
        {"event": 1, "event_transfers": 0},
        {"event": 2, "event_transfers": 0},
        {"event": 3, "event_transfers": 0},
    ]

    assert fpl._compute_free_transfers(history) == 4
    assert fpl._compute_free_transfers(history, [{"event": 2, "name": "wildcard"}]) == 2
    assert fpl._compute_free_transfers(history, [{"event": 2, "name": "freehit"}]) == 2


def test_shape_my_team_filters_and_computes_remaining():
    shaped = main._shape_my_team(
        3174196,
        {
            "entry_history": {"event": 33},
            "picks": [
                {
                    "element": 10,
                    "position": 1,
                    "multiplier": 2,
                    "is_captain": True,
                    "is_vice_captain": False,
                    "selling_price": 110,
                    "purchase_price": 100,
                    "ignore_me": "secret",
                }
            ],
            "transfers": {
                "made": 2,
                "limit": 5,
                "bank": 17,
                "value": 1015,
                "cost": 4,
                "status": "cost",
                "debug": "leave-out",
            },
            "chips": [
                {"name": "wildcard", "status_for_entry": "active"},
                {"name": "bboost", "status_for_entry": "played"},
                {"name": "3xc", "status_for_entry": "selected"},
            ],
            "account": {"email": "should-not-leak@example.com"},
        },
    )

    assert shaped == {
        "manager_id": 3174196,
        "event": 33,
        "picks": [
            {
                "element": 10,
                "position": 1,
                "multiplier": 2,
                "is_captain": True,
                "is_vice_captain": False,
                "selling_price": 110,
                "purchase_price": 100,
            }
        ],
        "transfers": {
            "made": 2,
            "limit": 5,
            "remaining": 3,
            "bank": 17,
            "value": 1015,
            "cost": 4,
            "status": "cost",
        },
        "chips_staged": ["wildcard", "3xc"],
    }


@pytest.mark.asyncio
async def test_live_squad_requires_cookie(monkeypatch):
    monkeypatch.setattr(main, "_live_cache_get", lambda manager_id: None)
    monkeypatch.setattr(main.fpl_auth, "get_cookie_jar", lambda: None)

    with pytest.raises(HTTPException) as exc:
        await main.live_squad(3174196)

    assert exc.value.status_code == 428
    assert exc.value.detail["reason"] == "no_cookie"


@pytest.mark.asyncio
async def test_live_squad_rejects_cookie_for_different_account(monkeypatch):
    monkeypatch.setattr(main, "_live_cache_get", lambda manager_id: None)
    monkeypatch.setattr(main.fpl_auth, "get_cookie_jar", lambda: {"pl_profile": "cookie"})
    monkeypatch.setattr(main.fpl_auth, "load_cookies", lambda: {"account_id": 123456})

    with pytest.raises(HTTPException) as exc:
        await main.live_squad(3174196)

    assert exc.value.status_code == 428
    assert exc.value.detail["reason"] == "account_mismatch"
    assert exc.value.detail["stored_account_id"] == 123456
