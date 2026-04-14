import argparse
import asyncio
import json

import intel


async def _main():
    parser = argparse.ArgumentParser(description="Volante transfer intelligence CLI")
    parser.add_argument("--manager-id", type=int, help="FPL manager ID to analyze")
    parser.add_argument("--event", type=int, help="Override current event")
    parser.add_argument("--horizon", type=int, default=5, help="Planning horizon in gameweeks")
    parser.add_argument("--import-csv", dest="import_csv", help="Import a local CSV projection snapshot")
    parser.add_argument("--source-key", help="Source key for CSV imports")
    parser.add_argument("--label", help="Optional label for CSV source")
    parser.add_argument("--list-alerts", action="store_true", help="List stored alerts for the manager")
    parser.add_argument("--limit", type=int, default=20, help="Alert listing limit")
    parser.add_argument("--no-deliver", action="store_true", help="Do not deliver pending alerts after a run")

    args = parser.parse_args()

    if args.import_csv:
        if not args.source_key:
            raise SystemExit("--source-key is required with --import-csv")
        result = await intel.import_projection_csv(
            args.import_csv,
            args.source_key,
            label=args.label,
            event=args.event,
            horizon=args.horizon,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    if args.list_alerts:
        if not args.manager_id:
            raise SystemExit("--manager-id is required with --list-alerts")
        alerts = await intel.list_alerts(args.manager_id, limit=args.limit)
        print(json.dumps(alerts, indent=2, sort_keys=True))
        return

    if not args.manager_id:
        raise SystemExit("--manager-id is required")

    result = await intel.run_transfer_intelligence(
        args.manager_id,
        event=args.event,
        horizon=args.horizon,
        persist=True,
        deliver=not args.no_deliver,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
