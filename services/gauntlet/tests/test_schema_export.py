"""Committed JSON Schemas must equal what the Pydantic models generate today."""

from pathlib import Path

import pytest
from gauntlet.contracts.common import StrictDTO
from gauntlet.contracts.registry import EXPORTED_MODELS, render_schema, schema_filename

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "jsonschema"


def test_no_orphan_schema_files() -> None:
    expected = {schema_filename(name) for name in EXPORTED_MODELS}
    assert {p.name for p in SCHEMA_DIR.glob("*.json")} == expected


@pytest.mark.parametrize(("name", "model"), sorted(EXPORTED_MODELS.items()))
def test_committed_schema_is_current(name: str, model: type[StrictDTO]) -> None:
    committed = (SCHEMA_DIR / schema_filename(name)).read_text(encoding="utf-8")
    assert committed == render_schema(model), "run scripts/export_schemas.py and commit"
