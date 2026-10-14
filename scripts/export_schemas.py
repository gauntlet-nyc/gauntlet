"""Owner A: export canonical JSON schemas from Pydantic, not handwritten wire types."""

from pathlib import Path

from gauntlet.contracts.registry import EXPORTED_MODELS, render_schema, schema_filename


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "packages/contracts/jsonschema"
    target.mkdir(parents=True, exist_ok=True)
    for name, model in EXPORTED_MODELS.items():
        (target / schema_filename(name)).write_text(render_schema(model), encoding="utf-8")
    print(f"Exported {len(EXPORTED_MODELS)} schemas to {target}")


if __name__ == "__main__":
    main()
