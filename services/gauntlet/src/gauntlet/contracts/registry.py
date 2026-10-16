"""Single list of wire models exported as JSON Schema. Script and drift test both read this."""

import json
from typing import Final

from .approvals import ApprovalDecision, ApprovalRecord, FixPlan
from .common import StrictDTO
from .events import RunEvent
from .evidence import EvidenceBinding
from .gate import AttackSpec, ChangeImpactMap, ChangeRequest, Finding, Observation, OracleVerdict
from .recall import HistoricalDecision, RecallTrigger, RecallVerdict
from .replay import ReplayResult, ReplaySpec

SCHEMA_VERSION_SUFFIX: Final = "v1"

EXPORTED_MODELS: Final[dict[str, type[StrictDTO]]] = {
    "approval-decision": ApprovalDecision,
    "approval-record": ApprovalRecord,
    "attack-spec": AttackSpec,
    "change-impact-map": ChangeImpactMap,
    "change-request": ChangeRequest,
    "evidence-binding": EvidenceBinding,
    "finding": Finding,
    "fix-plan": FixPlan,
    "historical-decision": HistoricalDecision,
    "observation": Observation,
    "oracle-verdict": OracleVerdict,
    "recall-trigger": RecallTrigger,
    "recall-verdict": RecallVerdict,
    "replay-result": ReplayResult,
    "replay-spec": ReplaySpec,
    "run-event": RunEvent,
}


def schema_filename(name: str) -> str:
    return f"{name}.{SCHEMA_VERSION_SUFFIX}.json"


def render_schema(model: type[StrictDTO]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
