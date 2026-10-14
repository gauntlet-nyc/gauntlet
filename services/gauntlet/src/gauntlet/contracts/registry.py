"""Single list of wire models exported as JSON Schema. Script and drift test both read this."""

import json
from typing import Final

from .approvals import ApprovalDecision, ApprovalRecord, FixPlan
from .common import StrictDTO
from .events import RunEvent
from .gate import AttackSpec, ChangeImpactMap, ChangeRequest, Finding, Observation, OracleVerdict
from .lineage import ExposureRecord, LineageEdge, ToolEvent
from .memory import TemporalMemoryFact
from .recall import HistoricalDecision, RecallTrigger, RecallVerdict
from .remediation import AuditSummary, RemediationProposal
from .replay import ReplayResult, ReplaySpec
from .voice import VoiceBriefing, VoiceReplayRequest, VoiceToolCall

SCHEMA_VERSION_SUFFIX: Final = "v1"

EXPORTED_MODELS: Final[dict[str, type[StrictDTO]]] = {
    "approval-decision": ApprovalDecision,
    "approval-record": ApprovalRecord,
    "attack-spec": AttackSpec,
    "audit-summary": AuditSummary,
    "change-impact-map": ChangeImpactMap,
    "change-request": ChangeRequest,
    "exposure-record": ExposureRecord,
    "finding": Finding,
    "fix-plan": FixPlan,
    "historical-decision": HistoricalDecision,
    "lineage-edge": LineageEdge,
    "observation": Observation,
    "oracle-verdict": OracleVerdict,
    "recall-trigger": RecallTrigger,
    "recall-verdict": RecallVerdict,
    "remediation-proposal": RemediationProposal,
    "replay-result": ReplayResult,
    "replay-spec": ReplaySpec,
    "run-event": RunEvent,
    "temporal-memory-fact": TemporalMemoryFact,
    "tool-event": ToolEvent,
    "voice-briefing": VoiceBriefing,
    "voice-replay-request": VoiceReplayRequest,
    "voice-tool-call": VoiceToolCall,
}


def schema_filename(name: str) -> str:
    return f"{name}.{SCHEMA_VERSION_SUFFIX}.json"


def render_schema(model: type[StrictDTO]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
