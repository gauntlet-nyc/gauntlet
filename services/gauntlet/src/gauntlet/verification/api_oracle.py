"""Hard API contract oracle for Cartwheel's synthetic orders endpoint (P9).

`api.order_contract`: every POST /api/orders whose recorded request body is not exactly the
valid synthetic item must be refused (4xx) and create nothing; every valid one must return 201
with the fixed synthetic order invariants. Judged from the trusted client's stored exchanges.
"""

import hashlib
import json
from typing import Final
from uuid import uuid4

from gauntlet.application.evidence import check_evidence
from gauntlet.contracts import AttackSpec, EvidenceSubject, Observation, OracleVerdict
from gauntlet.domain import OracleKind, OracleOutcome
from gauntlet.ports.artifacts import ArtifactStore
from gauntlet.ports.errors import UnknownOracleError
from gauntlet.ports.oracle import OracleDescriptor

API_ORACLE_ID: Final = "api.order_contract"
_SCHEMA: Final = "gauntlet-api-exchange-1"
_INVARIANTS: Final = {
    "item_id": "demo-wheel",
    "quantity": 1,
    "amount_minor": 4900,
    "currency": "USD",
    "status": "placed",
    "synthetic": True,
}

DESCRIPTOR: Final = OracleDescriptor(
    oracle_id=API_ORACLE_ID,
    kind=OracleKind.HARD,
    criterion_version="1.0",
    worker_kinds=frozenset({"api"}),
    description=(
        "POST /api/orders must refuse anything but the exact synthetic item with 4xx, and "
        "accept the valid item with 201 and fixed order invariants"
    ),
)


def _valid_request(body: object) -> bool:
    try:
        parsed = json.loads(body) if isinstance(body, str) else None
    except ValueError:
        return False
    return parsed == {"item_id": "demo-wheel", "quantity": 1}


class ApiContractOracle:
    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def _verdict(
        self, obs: Observation, outcome: OracleOutcome, observed: str, evidence: tuple[str, ...]
    ) -> OracleVerdict:
        return OracleVerdict(
            verdict_id=f"oracle-{uuid4().hex}",
            oracle_id=API_ORACLE_ID,
            oracle_kind=OracleKind.HARD,
            criterion_version=DESCRIPTOR.criterion_version,
            observation_id=obs.observation_id,
            outcome=outcome,
            observed=observed[:2000],
            expected="Invalid orders refused; valid orders created with fixed invariants",
            evidence_ids=evidence,
        )

    async def evaluate(
        self, oracle_id: str, plan: AttackSpec, observation: Observation, subject: EvidenceSubject
    ) -> OracleVerdict:
        if oracle_id != API_ORACLE_ID:
            raise UnknownOracleError("oracle ID is not registered")
        if observation.status != "completed" or len(observation.action_log) != len(plan.steps):
            return self._verdict(observation, OracleOutcome.INCONCLUSIVE, "Incomplete", ())
        problems: list[str] = []
        failing: list[str] = []
        checked: list[str] = []
        for index, record in enumerate(observation.action_log):
            if record.step_index != index or not record.evidence_ids:
                return self._verdict(observation, OracleOutcome.INCONCLUSIVE, "No exchange", ())
            artifact_id = record.evidence_ids[0]
            stored = await self._store.get(artifact_id)
            expected = subject.model_copy(update={"step_index": index})
            if (
                stored is None
                or hashlib.sha256(stored.content).hexdigest() != stored.binding.evidence.sha256
                or not (
                    await check_evidence(self._store, stored.binding.evidence, expected)
                ).trusted
            ):
                return self._verdict(observation, OracleOutcome.INCONCLUSIVE, "Bad evidence", ())
            try:
                exchange = json.loads(stored.content)
            except ValueError:
                return self._verdict(observation, OracleOutcome.INCONCLUSIVE, "Malformed", ())
            if not isinstance(exchange, dict) or exchange.get("schema") != _SCHEMA:
                return self._verdict(observation, OracleOutcome.INCONCLUSIVE, "Malformed", ())
            if exchange.get("method") != "POST" or exchange.get("path") != "/api/orders":
                continue
            checked.append(artifact_id)
            status, body = exchange.get("status"), exchange.get("body")
            if _valid_request(exchange.get("request_body")):
                if (
                    status != 201
                    or not isinstance(body, dict)
                    or any(body.get(k) != v for k, v in _INVARIANTS.items())
                ):
                    problems.append(f"valid order returned {status} or broke invariants")
                    failing.append(artifact_id)
            elif not (isinstance(status, int) and 400 <= status < 500):
                problems.append(f"invalid order request was accepted with HTTP {status}")
                failing.append(artifact_id)
        if not checked:
            return self._verdict(observation, OracleOutcome.INCONCLUSIVE, "No order request", ())
        if problems:
            return self._verdict(
                observation, OracleOutcome.FAIL, "; ".join(dict.fromkeys(problems)), (failing[0],)
            )
        return self._verdict(observation, OracleOutcome.PASS, "Order contract held", (checked[0],))
