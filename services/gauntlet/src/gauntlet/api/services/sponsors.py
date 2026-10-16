"""Sponsor-proof status. Reports configuration presence only; never values, never live claims.

A sponsor moves to "live verified" only by editing this table after a real recorded run that is
logged in docs/SDK_VALIDATION.md. Setting env vars alone never changes the status.
"""

from importlib.util import find_spec

from ..schemas import SponsorStatus
from ..settings import ApiSettings

_ROWS: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    (
        "Daytona",
        "daytona",
        "gauntlet.integrations.daytona",
        "RUN_LIVE_INTEGRATIONS=1 .venv/bin/python scripts/probe_b01_provider_smoke.py "
        "--execute --authorize-spend --registration <file>",
        ("base/head sandboxes", "fixture checksum receipt", "replay worlds"),
        "An earlier Daytona cold-restore receipt is recorded in docs/SDK_VALIDATION.md; "
        "the Gate demo path has not run on Daytona.",
    ),
    (
        "Anchor",
        "anchor",
        "gauntlet.integrations.anchor",
        "RUN_LIVE_INTEGRATIONS=1 .venv/bin/python scripts/probe_b01_provider_smoke.py "
        "--execute --authorize-spend --registration <file>",
        ("cloud browser session", "viewport hit-test", "screenshots/recording"),
        "Runs with GAUNTLET_ANCHOR_REQUIRE_PROXY=0 for the demo (weaker isolation: no egress "
        "proxy). Proxy support stays in code.",
    ),
    (
        "Arize AX",
        "arize",
        "gauntlet.integrations.arize",
        "See docs/SDK_VALIDATION.md (Arize row) for the live span/experiment command",
        ("planner/worker/oracle spans", "counterfactual experiment"),
        "Evaluation visibility only; never the trusted oracle.",
    ),
    (
        "SurrealDB core",
        "surrealdb",
        "gauntlet.integrations.surrealdb",
        "See docs/SDK_VALIDATION.md (SurrealDB core row) for the live command",
        ("run events", "decision history", "lineage graph"),
        "Recall pages currently read the seeded fixture (offline).",
    ),
    (
        "SurrealDB Agent Memory",
        "surrealdb_agent_memory",
        "gauntlet.integrations.surrealdb",
        "See docs/SDK_VALIDATION.md (Agent Memory row) for the live command",
        ("temporal memory facts", "as_of recall", "supersession"),
        "Separate service from SurrealDB core.",
    ),
    (
        "ElevenLabs",
        "elevenlabs",
        "gauntlet.integrations.elevenlabs",
        "See docs/SDK_VALIDATION.md (ElevenLabs row) for the live command",
        ("spoken run briefing",),
        "Read-only briefing; voice can never approve.",
    ),
    (
        "Azure OpenAI (planner)",
        "azure_openai",
        "gauntlet.integrations.azure_openai",
        "See docs/SDK_VALIDATION.md (Azure OpenAI planner stand-in) for the live command",
        ("attack plan proposals",),
        "Model only proposes; validators, oracles and humans decide.",
    ),
    (
        "AWS Bedrock (planner, alternate)",
        "bedrock",
        "gauntlet.integrations.bedrock",
        "GAUNTLET_MODEL_PROVIDER=bedrock; no AWS account exists, so never run live",
        ("attack plan proposals",),
        "Built and selectable; never claimed live.",
    ),
)


def _module_exists(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def sponsor_statuses(settings: ApiSettings) -> list[SponsorStatus]:
    statuses: list[SponsorStatus] = []
    for sponsor, key, module, command, produces, notes in _ROWS:
        adapter = module if _module_exists(module) else f"{module} (not on this branch yet)"
        statuses.append(
            SponsorStatus(
                sponsor=sponsor,
                adapter=adapter,
                configured=settings.provider_configured(key),
                missing_env=list(settings.missing_env(key)),
                status="offline-tested, live NOT RUN",
                live_command=command,
                produces=list(produces),
                notes=notes,
            )
        )
    return statuses
