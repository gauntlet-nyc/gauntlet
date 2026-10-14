"""Layering rules from master plan Section 4, enforced on source imports."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "gauntlet"

PROVIDER_SDKS = frozenset(
    {"httpx", "boto3", "daytona", "anchorbrowser", "surrealdb", "arize", "elevenlabs", "playwright"}
)
WEB = frozenset({"fastapi", "starlette", "gauntlet.api"})

FORBIDDEN: dict[str, frozenset[str]] = {
    "domain": PROVIDER_SDKS | WEB | {"pydantic", "gauntlet.contracts", "gauntlet.ports"},
    "contracts": PROVIDER_SDKS | WEB | {"gauntlet.ports"},
    "ports": PROVIDER_SDKS | WEB | {"gauntlet.intake", "gauntlet.analysis", "gauntlet.planning"},
    "analysis": PROVIDER_SDKS | WEB | {"gauntlet.planning", "gauntlet.application"},
    "planning": PROVIDER_SDKS | WEB | {"gauntlet.analysis", "gauntlet.application", "subprocess"},
    "application": PROVIDER_SDKS | WEB | {"gauntlet.analysis", "subprocess"},
    "intake": PROVIDER_SDKS | WEB | {"gauntlet.analysis", "gauntlet.application", "subprocess"},
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
    files = sorted((PACKAGE / layer).rglob("*.py"))
    assert files, f"layer {layer} has no modules"
    violations = [
        f"{path.relative_to(PACKAGE)}: {module}"
        for path in files
        for module in _imported_modules(path)
        if any(module == banned or module.startswith(banned + ".") for banned in FORBIDDEN[layer])
    ]
    assert not violations
