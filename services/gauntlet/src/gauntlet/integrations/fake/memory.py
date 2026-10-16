"""Process-local temporal memory: append-only, supersession by new facts, as-of reads."""

import json
from pathlib import Path

from gauntlet.contracts import TemporalMemoryFact
from gauntlet.ports.errors import PortError
from gauntlet.ports.memory import MemoryQuery


class InMemoryTemporalMemory:
    label = "offline_in_memory"

    def __init__(self, facts: tuple[TemporalMemoryFact, ...] = ()) -> None:
        self._facts: dict[str, TemporalMemoryFact] = {}
        for fact in facts:
            self._append(fact)

    def _append(self, fact: TemporalMemoryFact) -> None:
        if fact.fact_id in self._facts:
            raise PortError("memory is append-only; write a superseding fact instead")
        if fact.supersedes is not None and fact.supersedes not in self._facts:
            raise PortError("superseded fact does not exist")
        self._facts[fact.fact_id] = fact.model_copy(deep=True)

    async def remember(self, fact: TemporalMemoryFact) -> None:
        self._append(fact)

    async def recall(self, query: MemoryQuery) -> tuple[TemporalMemoryFact, ...]:
        visible = [
            f.model_copy(deep=True)
            for f in self._facts.values()
            if f.scope == query.scope
            and f.known_at <= query.as_of
            and query.surface_kinds.intersection(f.surface_kinds)
        ]
        visible.sort(key=lambda f: (f.known_at, f.fact_id), reverse=True)
        return tuple(visible[: query.limit])

    def all(self) -> tuple[TemporalMemoryFact, ...]:
        return tuple(self._facts.values())


class JsonFileTemporalMemory(InMemoryTemporalMemory):
    """Local file-backed variant so separate offline runs share memory. Append-only."""

    label = "offline_local_file"

    def __init__(self, path: Path) -> None:
        self._path = path
        facts: tuple[TemporalMemoryFact, ...] = ()
        if path.exists():
            facts = tuple(
                TemporalMemoryFact.model_validate(item) for item in json.loads(path.read_text())
            )
        super().__init__(facts)

    async def remember(self, fact: TemporalMemoryFact) -> None:
        self._append(fact)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps([f.model_dump(mode="json") for f in self.all()], indent=2))
        tmp.replace(self._path)
