"""Read-only union of registered oracle descriptors for planner validation and workers."""

from collections.abc import Sequence

from gauntlet.contracts import Observation, OracleVerdict
from gauntlet.ports.errors import UnknownOracleError
from gauntlet.ports.oracle import (
    OracleDescriptor,
    PrimaryActionContract,
    PrimaryActionContractSource,
    TrustedOracleRegistry,
)


class OracleCatalog:
    """Descriptors only. Evaluation happens in the evidence oracles, never here."""

    def __init__(
        self, registries: Sequence[TrustedOracleRegistry], *extra: OracleDescriptor
    ) -> None:
        by_id: dict[str, OracleDescriptor] = {}
        sources: dict[str, TrustedOracleRegistry] = {}
        for descriptor in [d for r in registries for d in r.descriptors()] + list(extra):
            if descriptor.oracle_id in by_id:
                raise ValueError("oracle IDs must be unique")
            by_id[descriptor.oracle_id] = descriptor
        for registry in registries:
            for descriptor in registry.descriptors():
                sources[descriptor.oracle_id] = registry
        self._by_id = by_id
        self._sources = sources

    def is_registered(self, oracle_id: str) -> bool:
        return oracle_id in self._by_id

    def descriptors(self) -> tuple[OracleDescriptor, ...]:
        return tuple(self._by_id.values())

    def descriptor(self, oracle_id: str) -> OracleDescriptor:
        try:
            return self._by_id[oracle_id]
        except KeyError:
            raise UnknownOracleError("oracle ID is not registered") from None

    def primary_action_contract(
        self, oracle_id: str, target_id: str
    ) -> PrimaryActionContract | None:
        source = self._sources.get(oracle_id)
        if isinstance(source, PrimaryActionContractSource):
            return source.primary_action_contract(oracle_id, target_id)
        return None

    def evaluate(self, oracle_id: str, observation: Observation) -> OracleVerdict:
        raise UnknownOracleError("the catalog does not evaluate; use the evidence oracle")
