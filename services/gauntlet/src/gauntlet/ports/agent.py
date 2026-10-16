"""Conversations with a target's synthetic AI agent inside one sandbox environment.

The channel owns the agent, its tools and the trusted state capture. It stores the
authoritative state snapshot (for example the ledger after the turn) as evidence bound to
the step subject, so an oracle can judge actual side effects, never the agent's words.
"""

from dataclasses import dataclass
from typing import Protocol

from gauntlet.contracts import ActionRecord, ChatStep, EvidenceSubject, ToolCallRecord

from .sandbox import EnvironmentHandle


@dataclass(frozen=True)
class AgentExchange:
    record: ActionRecord
    tool_calls: tuple[ToolCallRecord, ...]
    reply: str


class AgentChannel(Protocol):
    async def converse(
        self,
        environment: EnvironmentHandle,
        subject: EvidenceSubject,
        step_index: int,
        step: ChatStep,
    ) -> AgentExchange:
        """Run one chat turn. Raise EnvironmentUnavailableError if the target cannot run."""
        ...
