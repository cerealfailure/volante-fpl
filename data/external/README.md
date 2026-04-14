# External Projection Imports

Volante's private intelligence layer can run without paid APIs.

Put external projection exports in this folder and import them through the CLI or the protected intel HTTP endpoints.

Important rules:

- imports must live under `data/external/` unless you explicitly extend `VOLANTE_INTEL_IMPORT_ROOTS`
- `player_id` is strongly recommended
- `web_name` works, but ambiguous names are skipped
- if you use HTTP imports in `overall` mode, send `X-Volante-Token` when `VOLANTE_INTEL_TOKEN` is set

## Supported CSV columns

Only one of `player_id` or `web_name` is required.

```text
player_id,web_name,team_short,expected_points,xg,xa,xgi,expected_minutes,selected_pct,anytime_return_prob,clean_sheet_prob
```

Accepted aliases:

- `expected_points`, `xp`, `xP`
- `expected_minutes`, `minutes`
- `selected_pct`, `ownership`
- `anytime_return_prob`, `return_prob`
- `clean_sheet_prob`, `cs_prob`

`team_short` is optional, but helps disambiguate name-based imports.

## CLI examples

```bash
./scripts/run-transfer-intel.sh \
  --import-csv data/external/your-source.csv \
  --source-key manual_overlay \
  --label "Manual Overlay" \
  --horizon 5
```

```bash
./scripts/run-transfer-intel.sh --manager-id YOUR_MANAGER_ID --horizon 5
```

## Protected HTTP examples

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

```bash
curl -X POST "http://127.0.0.1:8555/api/intel/YOUR_MANAGER_ID/run?horizon=5" \
  -H "X-Volante-Token: $VOLANTE_INTEL_TOKEN"
```
