"""Layering rules from master plan Section 4, enforced on source imports."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "gauntlet"

FORBIDDEN: dict[str, set[str]] = {
    "domain": {
        "pydantic",
        "fastapi",
        "httpx",
        "boto3",
        "daytona",
        "anchorbrowser",
        "surrealdb",
        "arize",
        "elevenlabs",
        "gauntlet.contracts",
        "gauntlet.ports",
        "gauntlet.api",
    },
    "contracts": {
        "fastapi",
        "httpx",
        "boto3",
        "daytona",
        "anchorbrowser",
        "surrealdb",
        "arize",
        "elevenlabs",
        "gauntlet.ports",
        "gauntlet.api",
    },
    "ports": {
        "fastapi",
        "httpx",
        "boto3",
        "daytona",
        "anchorbrowser",
        "surrealdb",
        "arize",
        "elevenlabs",
        "gauntlet.api",
    },
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_has_no_forbidden_imports(layer: str) -> None:
    violations = [
        f"{path.name}: {module}"
        for path in (PACKAGE / layer).glob("*.py")
        for module in _imported_modules(path)
        if any(module == banned or module.startswith(banned + ".") for banned in FORBIDDEN[layer])
    ]
    assert not violations
