# Portfolio Theory for FPL — A Quant Research Note

**Audience:** Volante engineers and the manager-as-PM.
**Goal:** Map academic portfolio theory onto a 15-player FPL squad and supply formulas that can be lifted directly into `server/analysis.py` and `server/transfers.py`.
**Existing baseline:** Volante already computes a structural + empirical covariance matrix (`compute_structural_covariance`, `compute_empirical_covariance`, Ledoit-Wolf shrinkage), exposure metrics (HHI, ENB via Meucci PCA, Choueifaty diversification ratio, variance decomposition), and Down/Base/Up scenarios. This note builds on that baseline.

Notation throughout: `w` ∈ R^N is the captain-weighted holdings vector (1 for starters, 2 for captain, 0 elsewhere); `μ` is the EP vector; `Σ` is the covariance matrix of weekly points; `σ_p² = w'Σw` is portfolio variance; `R_p = w'r` is realised portfolio points.

---

## 1. Frameworks to Mine

### 1.1 CAPM and single-factor models (Sharpe 1964)

**Formula.** Decompose each player's weekly returns as `r_i = α_i + β_i·R_M + ε_i`, where `R_M` is the "market" factor and `Cov(ε_i, R_M) = 0`. The standard estimator is `β_i = Cov(r_i, R_M) / Var(R_M)`. Portfolio beta is `β_p = w'β / Σ w_i`.

**FPL mapping.** Three candidate "market" proxies: (a) top-6 EP-weighted premium-attacker basket; (b) **captain-pool basket** (top-30 owned premiums, ownership-weighted) — the "template beta"; (c) the player's own team-points factor, already implemented in Volante via `_load_factor_model` (`beta_atk`, `beta_def`).

For the user's "beta exposure seems high" complaint the key statistic is **portfolio beta to the captain-pool basket**. `β_p > 1.2` means you amplify template moves; if a rival captain hauls you lose ground faster than the median manager.

**Citation.** Sharpe (1964), *Capital asset prices: A theory of market equilibrium under conditions of risk*, Journal of Finance 19(3).

---

### 1.2 APT and multi-factor models (Ross 1976; Fama–French 1993)

**Formula.** `r_i = α_i + Σ_k β_{i,k}·F_k + ε_i`. Factors are exogenous and (ideally) uncorrelated. Portfolio variance decomposes as `σ_p² = β_p'·Σ_F·β_p + w'·D_ε·w` where `D_ε = diag(idio variances)`.

**FPL mapping.** Useful factor zoo for a 15-man squad:

| Factor | Sign convention | Source |
|---|---|---|
| `F_HOME` | +1 home, −1 away each GW | Fixture list |
| `F_FDR` | normalised inverse FDR (easy = +) | Volante FDR table |
| `F_FORM` | rolling 4-GW Z-score of points | Player history |
| `F_TEMPLATE` | EO percentile of player | FPL ownership feed |
| `F_DGW` | +1 in double GW, 0 otherwise | Fixture calendar |
| `F_PRICE_RISE` | xPriceΔ from price-change model | Existing model |

A 5–6 factor model gives interpretable exposures ("60% template-loaded, +1.3 home tilt this GW") and a cleaner Σ than empirical covariance — the noise floor is idio variance, not finite-sample garbage.

**Citation.** Ross (1976), *The arbitrage theory of capital asset pricing*, JET 13. Fama & French (1993), *Common risk factors in the returns on stocks and bonds*, JFE 33.

---

### 1.3 Markowitz mean-variance with concentration penalty (Markowitz 1952)

**Formula.** `max_w  w'μ − ½·λ·w'Σw` s.t. budget, position, club-quota, and integrality constraints. For FPL the constraints are:

- `Σ price_i · x_i ≤ £100m` (budget; `x_i ∈ {0,1}` for squad selection, plus `s_i ∈ {0,1}` for starting XI).
- 2 GK / 5 DEF / 5 MID / 3 FWD in squad; valid formation in XI.
- `Σ_{i ∈ club c} x_i ≤ 3` (club quota).
- Captain `c_i ∈ {0,1}`, `Σ c_i = 1`, `c_i ≤ s_i`.

This becomes a **mixed-integer quadratic program (MIQP)**. Haugh & Singal (2019, Columbia DFS paper) and Matthews et al. (arXiv 2505.02170, 2026) both formalise this for daily fantasy and for FPL specifically.

**Risk-aversion mapping.** `λ` is the only knob. Sensible defaults:
- `λ = 0` → pure EP maximiser, ignores correlations (the dumb baseline).
- `λ = 1/(2·μ_p)` → equal-weighting EP and one-σ swing.
- `λ = 1/μ_p` → conservative, willing to give up 1 EP per `σ²` reduction.

**FPL mapping.** Volante's `transfers.py` greedy-scores candidates. A small MIQP over 1–2 transfers (≤ 600 candidates × 16 slots) is feasible via `cvxpy` + SCIP, runtime < 2s.

**Citation.** Markowitz (1952), *Portfolio Selection*, JoF 7. Haugh & Singal (2019), *How to Play Fantasy Sports Strategically*.

---

### 1.4 Certainty-equivalent utility — CRRA / CARA

**Formula.** Under CARA utility `U(R) = −exp(−γR)` with normal returns: `CE = μ_p − ½·γ·σ_p²`. Under CRRA with log utility: `CE ≈ μ_p − ½·σ_p²/μ_p` (Kelly-flavoured). The half-variance term is a **risk-adjusted EP**.

**FPL mapping.** This is the cheapest single addition to Volante. Compute `risk_adjusted_ep = base_ep − 0.5·γ·portfolio_variance` and surface alongside base EP. **Make γ a function of HHI**, because concentration risk and risk aversion should compound:

```
γ_effective = γ_base · (1 + 4·max(0, HHI − 0.15))
```

Above HHI = 0.15 (Volante's "moderately concentrated" threshold), the risk penalty grows linearly. Default `γ_base = 0.05` (a 25-point variance costs ~0.6 EP).

**Citation.** Pratt (1964), *Risk Aversion in the Small and in the Large*, Econometrica 32. Arrow (1971).

---

### 1.5 Risk parity (Maillard, Roncalli, Teiletche 2010)

**Formula.** Allocate so that each holding contributes equally to portfolio variance: `MCR_i = w_i·(Σw)_i / σ_p`, `RC_i = w_i·MCR_i`, target `RC_i = σ_p / N` for all i.

**FPL mapping.** You can't rebalance integer positions, but you *can* surface **risk-contribution per team**: `RC_t = Σ_{i,j ∈ t} w_i·w_j·Σ_{i,j} / σ_p`. Already half-built in Volante's `team_var_contrib`. Expose the L1 distance from equal team-risk as a **risk-parity gap** — flags a triple-stack contributing 50% of variance even when HHI looks fine.

**Citation.** Maillard, Roncalli & Teiletche (2010), *The Properties of Equally Weighted Risk Contribution Portfolios*, JPM 36(4).

---

### 1.6 Black–Litterman (Black & Litterman 1990)

**Formula.** Posterior mean `μ_BL = [(τΣ)^{-1} + P'Ω^{-1}P]^{-1}·[(τΣ)^{-1}π + P'Ω^{-1}q]`. Here `π` is the prior EP (e.g. xMins × xPts/90 from FPL's own data), `P` is a `K×N` view-pick matrix, `q` are view returns, `Ω` is view covariance, `τ ≈ 0.05` controls prior tightness.

**FPL mapping.** Treat the **statistical projection** (Volante's `projections.py`) as π and treat **odds-derived signals** (devigged anytime-goalscorer, clean-sheet odds, expected-goals supremacy from the betting lab) as views. Each view is one player or one team; `Ω_kk` scales with bookmaker spread. Output: shrunk `μ_BL` that is robust when statistical and market signals disagree.

This is the principled way to fuse Volante's `match_model` outputs with FPL `ep_next`.

**Citation.** Black & Litterman (1990), *Asset Allocation: Combining Investor Views with Market Equilibrium*, Goldman Sachs Fixed Income Research.

---

### 1.7 CVaR / Expected Shortfall (Rockafellar & Uryasev 2000)

**Formula.** `CVaR_α(R) = E[R | R ≤ VaR_α(R)]`. For empirical scenarios `r^(s)`, s=1..S:

```
CVaR_α(w) = min_ζ  ζ + 1/((1−α)·S) · Σ_s max(ζ − w'r^(s), 0)
```

This is **linear in w and ζ**, so CVaR-constrained optimisation is an LP/MILP — much friendlier than VaR.

**FPL mapping.** Use `α = 0.10`: average score in the worst 10% of simulated GWs. More honest than Volante's current point-estimate Downside. Procedure: Monte-Carlo S = 1000 GW outcomes from `(μ, Σ)`, compute `CVaR_0.10`, show alongside Downside / Base / Upside. A transfer raising Base EP by 0.4 but cutting CVaR_0.10 by 3.0 is almost always worth it.

**Citation.** Rockafellar & Uryasev (2000), *Optimization of Conditional Value-at-Risk*, Journal of Risk 2(3).

---

### 1.8 Sortino ratio / lower partial moment

**Formula.** `Sortino = (μ_p − τ) / LPM_2(τ)^{1/2}` where `LPM_2(τ) = E[max(τ − R, 0)²]`. Replace symmetric variance with **downside semi-variance** below a target `τ` (e.g. `τ = average manager EP`).

**FPL mapping.** FPL is a tournament — managers are scored on **rank**, not absolute points. Upside variance is *good* (it's how you climb); downside variance is *bad*. Symmetric Σ overstates the cost of variance. Replace `σ_p²` in §1.4's CE formula with `LPM_2(τ)` for transfer-decision scoring. Target `τ` should be the rolling average overall-manager score for the GW (~50 points).

**Citation.** Sortino & Price (1994), *Performance measurement in a downside risk framework*, J. Investing 3(3). Bawa & Lindenberg (1977) for the LPM family.

---

### 1.9 Kelly criterion / log-optimal (Kelly 1956; Thorp 2006)

**Formula.** For a single bet at decimal odds `b+1` with win prob `p`: `f* = (bp − (1−p))/b`. For multiple **simultaneous correlated bets** with return vector `r` and covariance Σ, the continuous-approximation Kelly fraction is `w* = Σ^{-1}·μ` (same as MV with `λ = 1`). Fractional Kelly (¼ to ½) is universal practice to control estimator error.

**FPL mapping — transfer hits.** A −4 hit is a wager: stake 4 EP for expected gain `ΔEP_horizon` over H GWs. Approximate Kelly: take the hit iff `ΔEP_horizon / 4 > 1 / (½·Kelly_fraction)` — i.e. only when per-£ edge over H weeks exceeds ~2× the candidate's natural variance. Slot into `_score_candidate` in `transfers.py`. For wildcard/free-hit, full Kelly across the rest of the season is too aggressive; quarter Kelly is sane.

**Citation.** Kelly (1956), *A New Interpretation of Information Rate*, BSTJ 35. Thorp (2006), *The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market*, in *Handbook of Asset and Liability Management*.

---

### 1.10 Concentration indices

Three measures, increasing in sophistication:

- **HHI** (Herfindahl): `HHI = Σ s_i²`, where `s_i = w_i / Σw`. Already in Volante. Range `[1/N, 1]`.
- **Gini**: `G = Σ_i Σ_j |s_i − s_j| / (2N·Σ s_i)`. Captures inequality of weights, not just dispersion. Sensitive to outliers (e.g. one triple-stack).
- **Theil entropy**: `T = Σ s_i·log(s_i / s̄)`. Decomposable: total concentration = within-team + between-team. This **decomposability** is the killer feature for FPL — you can attribute concentration risk cleanly to (a) club-quota stacking, (b) position stacking, (c) ownership stacking.

**Recommendation.** Add Theil decomposition next to HHI; it answers *why* you're concentrated, not just *whether*.

**Citation.** Theil (1967), *Economics and Information Theory*. Hannah & Kay (1977) compare HHI/Gini/Theil for industrial concentration.

---

### 1.11 Drawdown-aware optimization (Chekhlov, Uryasev & Zabarankin 2005)

**Formula.** Conditional Drawdown-at-Risk: `CDaR_α = (1/((1−α)T)) · Σ_t max(D_t − ξ, 0) + ξ`, where `D_t = max_{s≤t}(R_s) − R_t` is the running drawdown.

**FPL mapping.** Substitute "wealth" with **negative cumulative overall-rank percentile**. A manager's drawdown is a stretch of red arrows — the largest peak-to-trough rank drop in a rolling window. Optimise transfers to minimise *expected worst-case 5-GW rank drawdown* rather than per-GW EP. Most psychologically aligned objective for a season-long run; addresses the "great September, bombed October" problem. Implementation needs a rank-projection model; hack with `rank_drop ≈ −normalised(R_p − R_median)·scale`.

**Citation.** Chekhlov, Uryasev & Zabarankin (2005), *Drawdown Measure in Portfolio Optimization*, IJTAF 8(1).

---

### Frameworks intentionally rejected

Continuous-time stochastic calculus (GW points are discrete weekly draws), full-season HJB (intractable cardinality; rolling-horizon MIQP suffices), tail-copulas across teams (over-fitting on 38 obs/season; structural Σ already captures the same-team copula), and Goldfarb–Iyengar robust optimisation (Black-Litterman + Ledoit-Wolf shrinkage already does the job).

---

## 2. Concrete Formula → Volante Code Mapping

| # | Framework | File / function | New input | New output stat |
|---|---|---|---|---|
| 1 | CAPM beta | `server/analysis.py` — new `compute_player_betas()` after `_load_factor_model()` | Captain-pool basket weights | `player_beta`, `portfolio_beta_to_template` (one float per squad) |
| 2 | Multi-factor APT | `server/analysis.py` — extend `_load_factor_model()` | Factor table (home, FDR, form, EO, DGW) | `factor_loadings[player_id]` dict and `portfolio_factor_exposure` |
| 3 | CRRA risk-adjusted EP | `server/analysis.py` — new `risk_adjusted_ep()` taking `compute_exposure_metrics()` output | `gamma` config parameter (default 0.05) | `risk_adjusted_ep` (float), surfaced in dashboard alongside base EP |
| 4 | Risk parity gap | `server/analysis.py` — extend `compute_exposure_metrics()` (already computes `team_var_contrib`) | none | `risk_parity_gap` (L1 distance from equal team-risk), `marginal_risk_contribution[player_id]` |
| 5 | Black-Litterman fusion | new `server/projections.py` helper `apply_market_views()` called inside `project_players()` | Devigged odds from `match_odds.py` (project doesn't have this file at `~/volante-fpl/server/`; would need port) | shrunk `μ_BL` overriding `ep_next` when `tau` is low |
| 6 | CVaR | `server/analysis.py` — new `monte_carlo_cvar()` after `compute_exposure_metrics()` | `n_scenarios=1000`, `alpha=0.10` | `cvar_10` (float), replaces single Downside scenario |
| 7 | Sortino / LPM | `server/analysis.py` — replace symmetric σ² in scoring with `LPM_2(τ)`; helper `compute_lpm()` | `tau` (target = average manager EP, default 50) | `sortino_ratio`, `downside_semi_var` |
| 8 | Kelly hit-sizing | `server/transfers.py` — replace `_score_candidate()` weighting with Kelly-edge | `kelly_fraction=0.25`, horizon EP delta with σ | `kelly_edge` per candidate; binary `recommend_take_hit` |
| 9 | Theil decomposition | `server/analysis.py` — extend `compute_exposure_metrics()` | none | `theil_total`, `theil_within_team`, `theil_between_team` |
| 10 | MIQP joint optimisation | `server/transfers.py` — new `optimize_transfer_miqp()` alongside greedy | `cvxpy` + `cylp/scip` dependency | optimal 1-transfer or 2-transfer plan with MV objective |
| 11 | CDaR rank-drawdown | `server/intel.py` (or new `server/drawdown.py`) | Manager rank history table | `expected_5gw_rank_drawdown`, `cdar_10_rank` |

Inputs/outputs assume the existing dict shapes in `compute_exposure_metrics()` (lines 368–504 of `analysis.py`).

---

## 3. Recommended Implementation Order

Ranked by bang-for-buck, prioritising interpretable wins over heavy optimisation:

1. **Player beta to captain-pool basket** (§1.1, row 1). One new column. Directly answers the user's "beta exposure seems high" question. ~80 LOC. Can ship in a day.
2. **Risk-adjusted EP via CRRA with HHI-scaled γ** (§1.4, row 3). Adds one number to every transfer / lineup decision. The single highest-leverage stat for changing day-to-day choices. ~50 LOC, calibration via 2 hyperparameters.
3. **Theil decomposition next to HHI** (§1.10, row 9). HHI tells you *whether* you're concentrated; Theil tells you *why* (club / position / ownership). Cheap and directly improves the existing concentration UI. ~80 LOC.
4. **CVaR_0.10 from Monte Carlo** (§1.7, row 6). Replaces the soft "Downside scenario" with a defensible tail metric. Works off existing Σ. ~150 LOC + a scenario-generator.
5. **Risk-parity-gap and marginal risk contribution per player** (§1.5, row 4). Already 80% built — surface what the code already computes. Each player gets a "marginal variance you'd shed by selling them" number. ~60 LOC.
6. **Kelly-flavoured hit scorer** (§1.9, row 8). Turns the "should I take a −4?" question into a single inequality. Slot into `_score_candidate`. ~100 LOC.
7. **5-factor APT loadings** (§1.2, row 2). Bigger build (need a factor table builder), but produces the richest interpretability layer ("you're long home, short FDR, neutral template"). Defer until 1–6 are shipped.
8. **MIQP joint optimisation for 2-transfer planning** (§1.3, row 10). Highest engineering cost, requires `cvxpy`+SCIP. Do last; greedy `transfers.py` already gets ~95% of the value.

Things I would **not** build until v1.0 of the above is shipped: Black-Litterman fusion, CDaR, full Sortino replacement of all σ² uses. They have real merit but require either new data (odds in the FPL service) or careful calibration that will distract from the easy wins.

---

## 4. References

**Seminal portfolio theory**

- Markowitz, H. (1952). *Portfolio Selection*. The Journal of Finance, 7(1), 77–91.
- Sharpe, W. F. (1964). *Capital Asset Prices: A Theory of Market Equilibrium under Conditions of Risk*. The Journal of Finance, 19(3).
- Ross, S. A. (1976). *The Arbitrage Theory of Capital Asset Pricing*. Journal of Economic Theory, 13.
- Fama, E. F. & French, K. R. (1993). *Common Risk Factors in the Returns on Stocks and Bonds*. Journal of Financial Economics, 33.
- Pratt, J. W. (1964). *Risk Aversion in the Small and in the Large*. Econometrica, 32(1/2).
- Black, F. & Litterman, R. (1990). *Asset Allocation: Combining Investor Views with Market Equilibrium*. Goldman Sachs Fixed Income Research.

**Risk measures**

- Rockafellar, R. T. & Uryasev, S. (2000). *Optimization of Conditional Value-at-Risk*. Journal of Risk, 2(3), 21–41.
- Sortino, F. A. & Price, L. N. (1994). *Performance Measurement in a Downside Risk Framework*. The Journal of Investing, 3(3).
- Chekhlov, A., Uryasev, S. & Zabarankin, M. (2005). *Drawdown Measure in Portfolio Optimization*. International Journal of Theoretical and Applied Finance, 8(1).
- Bawa, V. S. & Lindenberg, E. B. (1977). *Capital Market Equilibrium in a Mean-Lower Partial Moment Framework*. Journal of Financial Economics, 5(2).

**Diversification & concentration**

- Meucci, A. (2009). *Managing Diversification*. Risk, May, 74–79.
- Choueifaty, Y. & Coignard, Y. (2008). *Toward Maximum Diversification*. The Journal of Portfolio Management, 35(1).
- Maillard, S., Roncalli, T. & Teiletche, J. (2010). *The Properties of Equally Weighted Risk Contribution Portfolios*. JPM, 36(4).
- Theil, H. (1967). *Economics and Information Theory*. North-Holland.

**Bet sizing / log-optimal**

- Kelly, J. L. (1956). *A New Interpretation of Information Rate*. Bell System Technical Journal, 35(4).
- Thorp, E. O. (2006). *The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market*. In *Handbook of Asset and Liability Management*, Vol. 1.

**Sports / fantasy specific**

- Haugh, M. B. & Singal, R. (2019). *How to Play Fantasy Sports Strategically (and Win)*. Columbia / Imperial WP.
- Matthews, T. et al. (2026). *A Data-Driven Framework for Team Selection in Fantasy Premier League*. arXiv:2505.02170.
- NTNU (2018). *Developing a Forecast-Based Optimization Model for Fantasy Premier League*. NTNU Open thesis.

**Shrinkage**

- Ledoit, O. & Wolf, M. (2004). *A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices*. JMVA 88(2). [Already used in `analysis.py:ledoit_wolf_shrinkage`.]
