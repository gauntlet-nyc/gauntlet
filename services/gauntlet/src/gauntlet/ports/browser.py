"""Browser sessions bound to one sandbox preview origin (Anchor + Playwright in production)."""

from typing import Protocol

from gauntlet.contracts import ActionRecord, ActionStep, EvidenceSubject

from .sandbox import EnvironmentHandle


def is_browser_subject_for(environment: EnvironmentHandle, subject: EvidenceSubject) -> bool:
    """A session may capture evidence only for its exact environment and whole observation."""
    return (
        subject.environment_id == environment.environment_id
        and subject.source_sha == environment.source_sha
        and subject.fixture_checksum == environment.fixture_checksum
        and subject.collector == "browser_collector"
        and subject.step_index is None
    )


class BrowserProvider(Protocol):
    async def open_session(self, environment: EnvironmentHandle, subject: EvidenceSubject) -> str:
        """Lock the session to one preview origin and preallocated browser evidence subject."""
        ...

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        """Execute one typed step. Off-origin navigation or redirects yield outcome 'blocked'."""
        ...

    async def close_session(self, session_id: str) -> None: ...
