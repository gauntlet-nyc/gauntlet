"""Validate every Gauntlet environment variable and print names-only readiness.

Never prints values. Exit 2 on invalid configuration (the error names the variables).
"""

import json

from gauntlet.settings import SettingsError, load_settings


def main() -> None:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, indent=2))
        raise SystemExit(2) from None
    print(json.dumps({"status": "valid", "integrations": settings.readiness()}, indent=2))


if __name__ == "__main__":
    main()
