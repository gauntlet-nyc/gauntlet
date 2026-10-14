"""Trusted, immutable oracle registry. Attackers and planners can only reference IDs."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gauntlet.contracts import Observation, OracleVerdict, WorkerKind
from gauntlet.domain import OracleKind


@dataclass(frozen=True)
class OracleDescriptor:
    """Read-only description shown to the planner. Never contains the oracle's logic."""

    oracle_id: str
    kind: OracleKind
    criterion_version: str
    worker_kinds: frozenset[WorkerKind]
    description: str


class TrustedOracleRegistry(Protocol):
    def is_registered(self, oracle_id: str) -> bool: ...

    def descriptors(self) -> Sequence[OracleDescriptor]: ...

    def descriptor(self, oracle_id: str) -> OracleDescriptor:
        """Raise UnknownOracleError for unregistered IDs."""
        ...

    def evaluate(self, oracle_id: str, observation: Observation) -> OracleVerdict:
        """Raise UnknownOracleError for unregistered IDs."""
        ...
