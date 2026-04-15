"""
Unit tests for the correlation-aware EP penalty in transfers._correlation_penalty.

These don't need a database — they exercise the pure numpy logic by feeding a
hand-built cov matrix and confirming the penalty has the expected sign and
ordering: a swap that increases concentration should produce a positive penalty;
a swap that diversifies should produce a negative one.
"""
import numpy as np

import transfers


def _ctx(cov, ids, current_xv, lam=1.0):
    return {
        "cov": np.array(cov, dtype=float),
        "idx": {pid: i for i, pid in enumerate(ids)},
        "current_xv_ids": current_xv,
        "lambda": lam,
    }


def test_no_context_returns_zero():
    p, br = transfers._correlation_penalty(1, 2, None)
    assert p == 0.0
    assert br is None


def test_concentrating_swap_raises_penalty():
    # Three players. 1 and 2 are highly correlated (same team factor).
    # 3 is independent. Current XV = [3, 1]. Swap 3 → 2 concentrates risk.
    ids = [1, 2, 3]
    cov = [
        [4.0, 3.5, 0.0],
        [3.5, 4.0, 0.0],
        [0.0, 0.0, 4.0],
    ]
    ctx = _ctx(cov, ids, current_xv=[3, 1])
    penalty, br = transfers._correlation_penalty(candidate_id=2, sell_id=3, risk_context=ctx)
    assert penalty > 0
    assert br["marginal_var"] > 0


def test_diversifying_swap_produces_negative_penalty():
    # Inverse of the above: current XV = [1, 2] (concentrated). Swap 2 → 3
    # diversifies, so penalty should be negative.
    ids = [1, 2, 3]
    cov = [
        [4.0, 3.5, 0.0],
        [3.5, 4.0, 0.0],
        [0.0, 0.0, 4.0],
    ]
    ctx = _ctx(cov, ids, current_xv=[1, 2])
    penalty, br = transfers._correlation_penalty(candidate_id=3, sell_id=2, risk_context=ctx)
    assert penalty < 0
    assert br["marginal_var"] < 0


def test_neutral_swap_zero_marginal():
    # Swap two players that have identical loadings → no portfolio var change.
    ids = [1, 2, 3]
    cov = [
        [4.0, 0.0, 0.0],
        [0.0, 4.0, 0.0],
        [0.0, 0.0, 4.0],
    ]
    ctx = _ctx(cov, ids, current_xv=[1, 3])
    penalty, br = transfers._correlation_penalty(candidate_id=2, sell_id=1, risk_context=ctx)
    assert abs(penalty) < 1e-9
    assert abs(br["marginal_var"]) < 1e-9


def test_unknown_id_falls_back_to_zero():
    ids = [1, 2]
    cov = [[1.0, 0.0], [0.0, 1.0]]
    ctx = _ctx(cov, ids, current_xv=[1, 2])
    p, br = transfers._correlation_penalty(candidate_id=999, sell_id=1, risk_context=ctx)
    assert p == 0.0
    assert br is None
