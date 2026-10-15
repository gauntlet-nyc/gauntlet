"""Inventory only. --published reads public PyPI metadata; never calls paid services."""

import argparse
import importlib.metadata
import json
import os
from collections.abc import Mapping

import httpx

PACKAGES = (
    "daytona",
    "anchorbrowser",
    "arize-otel",
    "arize",
    "surrealdb",
    "surrealdb-memory",
    "boto3",
    "playwright",
)


def inventory(*, published: bool) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for package in PACKAGES:
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        row = {
            "package": package,
            "installed_version": installed,
            "live_smoke": "not_run",
            "published_version": None,
        }
        if published:
            try:
                response = httpx.get(f"https://pypi.org/pypi/{package}/json", timeout=15)
                response.raise_for_status()
                row["published_version"] = str(response.json()["info"]["version"])
            except (httpx.HTTPError, ValueError, KeyError):
                row["published_version"] = "environment_error"
        rows.append(row)
    return rows


def ui_preflight(*, environment: Mapping[str, str]) -> dict[str, object]:
    """Check local inputs only; never import provider SDKs, connect, or expose keys."""
    versions: dict[str, str | None] = {}
    for package in ("daytona", "anchorbrowser", "playwright"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    checks = {f"{package}_installed": version is not None for package, version in versions.items()}
    checks["live_opt_in"] = environment.get("RUN_LIVE_INTEGRATIONS") == "1"
    for key in ("DAYTONA_API_KEY", "ANCHOR_API_KEY"):
        value = environment.get(key, "").strip()
        checks[f"{key.lower()}_present"] = bool(value) and not value.upper().startswith("REPLACE_")
    allowed_targets = {
        value.strip() for value in environment.get("GAUNTLET_ALLOWED_TARGET_IDS", "").split(",")
    }
    checks["cartwheel_target_allowed"] = "cartwheel-fixture" in allowed_targets
    return {
        "scope": "local_prerequisites_only",
        "status": "not_tested",
        "local_prerequisites_present": all(checks.values()),
        "checks": checks,
        "package_versions": versions,
        "limitations": [
            "Does not validate credentials, SDK signatures, quotas, connectivity or cleanup.",
            "Does not establish dependency approval, spend authorization or phase acceptance.",
            "Reads process environment only; does not load dotenv files.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--published", action="store_true")
    modes.add_argument("--ui-preflight", action="store_true", help="Check local B-01 prerequisites")
    args = parser.parse_args()
    if args.ui_preflight:
        report = ui_preflight(environment=os.environ)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["local_prerequisites_present"] else 2)
    print(json.dumps(inventory(published=args.published), indent=2))
