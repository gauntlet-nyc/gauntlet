"""One-command go-live check for every sponsor. Step 1 of the morning checklist.

  python scripts/go_live_check.py            # names of missing variables per sponsor
  RUN_LIVE_INTEGRATIONS=1 python scripts/go_live_check.py --probe
                                             # + ONE cheap live call per configured sponsor

Never prints values. Exit 1 if any probed provider fails, 2 if settings are invalid.
"""

import argparse
import asyncio
import json
import os
import sys

from gauntlet.execution.go_live import exit_code, render, run_environment_check
from gauntlet.execution.go_live_probes import PROBES
from gauntlet.settings import SettingsError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="make one live call per sponsor")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    try:
        results = asyncio.run(run_environment_check(os.environ, probe=args.probe, probes=PROBES))
    except SettingsError as exc:
        print(f"invalid settings: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([vars(item) for item in results], indent=2))
    else:
        print(render(results, probed=args.probe))
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
