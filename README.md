# Volante FPL

Volante FPL is the stripped FPL engine from the wider Volante project.

This version keeps the parts that matter for squad analysis:

- squad x-ray and player detail
- correlation matrix and concentration analysis
- multi-week attribution
- transfer planner with covariance deltas
- live points, prediction accuracy, leagues, and transfer history
- fixture exposure for the current gameweek
- correlation scorecard on past transfers

This repo does not include sportsbook scraping, bookmaker odds, parlay analysis, prediction-market integrations, or API-key management for external betting feeds.

## Stack

- `server/`: FastAPI + SQLite
- `app/`: SvelteKit
- shared data source: official FPL API

## Setup

```bash
git clone <your-repo-url>
cd volante-fpl

python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt

cd app
npm install
cd ..
```

## Run

```bash
./start.sh
```

Backend runs on `http://localhost:8555`.
Frontend runs on `http://localhost:5555`.

## Correlation Tracking

The transfer-analysis endpoint now scores historical transfers against correlation structure, not just realized points.

`GET /api/manager/{manager_id}/transfer-analysis`

It will:

- score each past transfer by points gained or lost after the move
- reconstruct starter snapshots for the transfer gameweek
- estimate whether the move improved or worsened diversification
- summarize whether ENB-improving moves actually outperformed concentration-increasing ones

In the Transfers screen, the history panel now shows two checks for each move:

- `Alpha/GW`: realized points gained or lost per remaining gameweek, which makes early and late-season transfers comparable
- `Matrix`: whether the move lifted ENB / reduced concentration (`Up`) or pushed the squad into a tighter stack (`Down`)

That gives you a concrete way to test whether using the matrix is helping rather than relying on feel:

- compare the `ENB Up` bucket vs the `ENB Down` bucket in the scorecard
- inspect individual moves where the matrix said `Up` but the realized alpha was negative, or vice versa
- keep using `Alpha/GW` rather than raw points when judging the process, because old transfers had more time to accumulate returns

## Notes

- SQLite still defaults to `~/.fulcrum/fulcrum.db` for continuity with the existing local data cache.
- Historical correlation scoring may fetch missing historical picks or player histories from the FPL API the first time you request it.
