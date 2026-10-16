"""Export the control API OpenAPI document that the dashboard types are generated from."""

import json
from pathlib import Path

from gauntlet.api.main import app

OUT = Path(__file__).resolve().parents[1] / "apps/dashboard/openapi.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")
