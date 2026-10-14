"""Trusted, immutable oracle registry. Attackers and planners can only reference IDs."""

from typing import Protocol

from gauntlet.contracts import Observation, OracleVerdict
from gauntlet.domain import OracleKind


class TrustedOracleRegistry(Protocol):
    def is_registered(self, oracle_id: str) -> bool: ...

    def kind_of(self, oracle_id: str) -> OracleKind:
        """Raise UnknownOracleError for unregistered IDs."""
        ...

    def evaluate(self, oracle_id: str, observation: Observation) -> OracleVerdict:
        """Raise UnknownOracleError for unregistered IDs."""
        ...
