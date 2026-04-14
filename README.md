# Volante FPL

Volante FPL is an FPL squad-analysis app with a FastAPI backend and Svelte frontend.

The repo is now split into two modes:

- `fpl_only`: default, safe to clone and run from GitHub, no private intel HTTP surface
- `overall`: opt-in internal mode that enables the private transfer-intelligence stack

This repo is FPL-first. It does not ship sportsbook scraping, bookmaker integrations, parlay tooling, or external betting-feed management.

## Features

- squad x-ray and player detail
- correlation matrix and concentration analysis
- multi-week attribution
- transfer planner with exact joint-plan scoring
- live points, prediction accuracy, leagues, and transfer history
- fixture exposure for the current gameweek
- optional private transfer intelligence overlays in `overall` mode

## Stack

- `server/`: FastAPI + SQLite
- `app/`: SvelteKit
- primary upstream: official FPL API

## Quick Start

```bash
git clone https://github.com/cerealfailure/volante-fpl.git
cd volante-fpl

python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt

cd app
npm install
cd ..

cp .env.example .env
./start.sh
```

Default local URLs:

- frontend: `http://127.0.0.1:5555`
- API: `http://127.0.0.1:8555`

The default `.env.example` keeps the app in `fpl_only` mode and binds locally, which is the recommended GitHub setup.

## Modes

### `fpl_only`

Default mode.

What you get:

- all public FPL analysis pages
- transfer planner
- transfer history and matrix scorecard
- live points and league screens

What stays off:

- `/api/intel/*`
- background intel loop
- private external-projection imports over HTTP

### `overall`

Opt-in internal mode.

What it adds:

- private transfer-intelligence engine
- external projection imports from local CSVs
- stored alerts
- background intel loop

Protection model:

- in `overall` mode, intel HTTP endpoints are local-only by default
- if you set `VOLANTE_INTEL_TOKEN`, those endpoints require `X-Volante-Token` or `Authorization: Bearer ...`

Check the active mode:

```bash
curl http://127.0.0.1:8555/api/status
```

The response includes a `mode` block.

## Environment

Main variables:

- `VOLANTE_MODE=fpl_only|overall`
- `VOLANTE_API_HOST=127.0.0.1`
- `VOLANTE_API_PORT=8555`
- `VOLANTE_WEB_HOST=127.0.0.1`
- `VOLANTE_WEB_PORT=5555`
- `VOLANTE_ALLOW_ORIGIN_REGEX=^https?://[^/]+(?::\\d+)?$`
- `VOLANTE_INTEL_TOKEN=...` optional, recommended for remote internal access
- `VOLANTE_INTEL_MANAGER_ID=123456` optional background loop target
- `VOLANTE_INTEL_HORIZON=5`
- `VOLANTE_INTEL_INTERVAL_MINUTES=60`

See [.env.example](.env.example).

## Sharing With Friends

The repo now starts in local-only mode by default. If you want friends on the same LAN or a deployed box to open it, explicitly opt into network binding:

```bash
export VOLANTE_API_HOST=0.0.0.0
export VOLANTE_WEB_HOST=0.0.0.0
./start.sh
```

Then share:

- `http://<your-host>:5555`

Recommended for friend sharing:

- keep `VOLANTE_MODE=fpl_only`
- only switch to `overall` for your own protected/internal workflows
- if you expose `overall` beyond localhost, set `VOLANTE_INTEL_TOKEN`

## Private Transfer Intelligence

Private intel is available only in `overall` mode.

Enable it:

```bash
export VOLANTE_MODE=overall
export VOLANTE_INTEL_TOKEN=choose-a-long-random-token
./start.sh
```

What it does:

- stores external projection snapshots in SQLite
- blends them with the internal xP engine instead of replacing it
- scores sell pressure using xP, fixtures, uncertainty, minutes risk, and correlation load
- persists alerts and can write them to a local outbox, stdout, or a webhook

### CLI Workflow

CLI is the recommended internal workflow because it avoids exposing private endpoints unnecessarily.

Import a CSV snapshot:

```bash
./scripts/run-transfer-intel.sh \
  --import-csv data/external/your-source.csv \
  --source-key manual_overlay \
  --label "Manual Overlay" \
  --horizon 5
```

Run the analyzer:

```bash
./scripts/run-transfer-intel.sh --manager-id 123456 --horizon 5
```

Read stored alerts:

```bash
./scripts/run-transfer-intel.sh --manager-id 123456 --list-alerts
```

### Background Loop

```bash
export VOLANTE_MODE=overall
export VOLANTE_INTEL_MANAGER_ID=123456
export VOLANTE_INTEL_HORIZON=5
export VOLANTE_INTEL_INTERVAL_MINUTES=60
export VOLANTE_ALERT_STDOUT=1
# optional
export VOLANTE_ALERT_WEBHOOK=https://your-webhook-url
./start.sh
```

### Protected HTTP Intel Endpoints

Only use these if you need HTTP access to the private analyzer.

Run an intel pass:

```bash
curl -X POST "http://127.0.0.1:8555/api/intel/123456/run?horizon=5" \
  -H "X-Volante-Token: $VOLANTE_INTEL_TOKEN"
```

Import a CSV snapshot:

```bash
curl -X POST http://127.0.0.1:8555/api/intel/import-csv \
  -H 'Content-Type: application/json' \
  -H "X-Volante-Token: $VOLANTE_INTEL_TOKEN" \
  -d '{
    "path": "data/external/your-source.csv",
    "source_key": "manual_overlay",
    "label": "Manual Overlay",
    "horizon": 5
  }'
```

Important:

- imported files must live under `data/external/` by default
- prefer `player_id` in CSVs over `web_name`
- HTTP intel endpoints are not available in `fpl_only`

See [data/external/README.md](data/external/README.md) for CSV rules.

## Transfer Planner Notes

The planner is a joint optimizer, not just a set of isolated swaps.

Current behavior:

- never recommends selected outgoing players back into the plan
- supports larger plans, with search tuned most aggressively for up to 6 outs
- scores full plans on projected points, fixture swing, xGI, budget use, and combined covariance deltas
- manual multi-transfer selections now get an exact joint simulation instead of falling back to summed single swaps

## Correlation Tracking

`GET /api/manager/{manager_id}/transfer-analysis`

The transfer-analysis endpoint scores historical transfers against correlation structure, not just realized points.

In the Transfers screen, the history panel shows:

- `Alpha/GW`: realized net points gained or lost per remaining gameweek after allocating that GW's hit cost across its transfers
- `Matrix`: whether the move improved ENB / concentration structure or worsened it

## Data Imports

- SQLite defaults to `~/.fulcrum/fulcrum.db`
- historical correlation scoring may fetch missing historical picks or player histories the first time you request it
- private external CSVs are ignored by git via `.gitignore`

## Verification

Before sharing changes, run:

```bash
python3 -m py_compile server/*.py
cd app && npm run check && npm run build
```
