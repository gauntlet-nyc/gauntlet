"""Inventory only. --published reads public PyPI metadata; never calls paid services."""

import argparse
import importlib.metadata
import json

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", action="store_true")
    args = parser.parse_args()
    print(json.dumps(inventory(published=args.published), indent=2))
