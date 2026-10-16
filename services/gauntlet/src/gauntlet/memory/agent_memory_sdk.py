"""`MemoryReader`/`MemoryWriter` on SurrealDB Agent Memory via the official SDK
(`surrealdb[memory]==3.0.0b10`, prerelease, `live-providers` group, imported lazily).

How typed facts map onto Agent Memory:
- `remember` stores the fact's summary as the memory text, followed by a marker line with
  the full canonical fact JSON (base64), plus labels (`gauntlet`, `fact:<id>`, `kind:`,
  `trust:`, `verification:`, `surface:`, `supersedes:`) and the fact scope as the scope.
  `infer` is never used, so the service does not rewrite the text.
- `recall` queries semantically within the scope, decodes each hit's marker back into a
  validated `TemporalMemoryFact`, and drops hits it cannot decode (counted, never guessed).
- as-of and supersession are applied here on the decoded facts' own `known_at`/
  `supersedes`. The service's `asOf` is not used for filtering: it refers to the service's
  ingestion time, which is not when Gauntlet learned the fact.
- Append-only: Gauntlet never calls `forget`. Corrections are new facts with `supersedes`.

`memory_store` picks this adapter when the SDK is installed (and `GAUNTLET_MEMORY_BACKEND`
is not `http`), otherwise the HTTP SurrealDB memory context (`surreal_memory.py`).
"""

import base64
import binascii
import logging
from collections.abc import Sequence
from typing import Any, Final

from pydantic import ValidationError

from gauntlet.contracts import TemporalMemoryFact
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.memory import MemoryQuery

from .surreal_memory import LENS_KINDS

_log = logging.getLogger("gauntlet.memory.agent_memory")
MARKER: Final = "gauntlet-fact:"
_MAX_K: Final = 50


def encode_fact_text(fact: TemporalMemoryFact) -> str:
    payload = base64.b64encode(fact.model_dump_json().encode("utf-8")).decode("ascii")
    return f"{fact.summary}\n{MARKER}{payload}"


def decode_fact_text(text: str) -> TemporalMemoryFact | None:
    for line in reversed(text.splitlines()):
        if line.startswith(MARKER):
            try:
                raw = base64.b64decode(line[len(MARKER) :], validate=True)
                return TemporalMemoryFact.model_validate_json(raw)
            except (binascii.Error, ValueError, ValidationError):
                return None
    return None


def fact_labels(fact: TemporalMemoryFact) -> list[str]:
    labels = [
        "gauntlet",
        f"fact:{fact.fact_id}",
        f"kind:{fact.kind}",
        f"trust:{fact.trust}",
        f"verification:{fact.verification}",
        *(f"surface:{kind}" for kind in fact.surface_kinds),
    ]
    if fact.supersedes:
        labels.append(f"supersedes:{fact.supersedes}")
    return labels


class AgentMemorySdkStore:
    """Adapter over an `AsyncMemory` client (injected; see `from_settings`)."""

    backend = "surrealdb_agent_memory_sdk"

    def __init__(self, client: Any) -> None:  # noqa: ANN401 - optional SDK boundary
        self._client = client
        self.undecodable_hits = 0

    async def remember(self, fact: TemporalMemoryFact) -> None:
        try:
            await self._client.remember(
                encode_fact_text(fact),
                scopes=[fact.scope],
                memory_category="gauntlet_fact",
                labels=fact_labels(fact),
            )
        except Exception as exc:
            raise EnvironmentUnavailableError(
                f"Agent Memory remember failed ({type(exc).__name__})"
            ) from None

    async def recall(self, query: MemoryQuery) -> tuple[TemporalMemoryFact, ...]:
        kinds = LENS_KINDS[query.lens]
        text = " ".join(sorted(str(kind) for kind in query.surface_kinds)) or "gauntlet"
        try:
            response = await self._client.recall(
                f"gauntlet findings for {query.scope}: {text}",
                k=min(_MAX_K, max(query.limit * 3, query.limit)),
                lens=[query.scope],
                labels=["gauntlet"],
            )
        except Exception as exc:
            raise EnvironmentUnavailableError(
                f"Agent Memory recall failed ({type(exc).__name__})"
            ) from None
        facts: list[TemporalMemoryFact] = []
        for hit in getattr(response, "hits", ()):
            fact = decode_fact_text(str(getattr(hit, "text", "")))
            if fact is None:
                self.undecodable_hits += 1
                continue
            facts.append(fact)
        if self.undecodable_hits:
            _log.warning("Agent Memory returned %d undecodable hits", self.undecodable_hits)
        return _visible(facts, query, kinds)

    async def close(self) -> None:
        await self._client.close()


def _visible(
    facts: Sequence[TemporalMemoryFact], query: MemoryQuery, kinds: frozenset[str]
) -> tuple[TemporalMemoryFact, ...]:
    unique = {fact.fact_id: fact for fact in facts}.values()
    known = [
        fact
        for fact in unique
        if fact.scope == query.scope
        and fact.kind in kinds
        and fact.known_at <= query.as_of
        and query.surface_kinds.intersection(fact.surface_kinds)
    ]
    superseded = {fact.supersedes for fact in known if fact.supersedes}
    valid = [
        fact
        for fact in known
        if fact.fact_id not in superseded
        and fact.valid_from <= query.as_of
        and (fact.valid_until is None or query.as_of < fact.valid_until)
    ]
    valid.sort(key=lambda fact: (fact.known_at, fact.fact_id), reverse=True)
    return tuple(valid[: query.limit])
