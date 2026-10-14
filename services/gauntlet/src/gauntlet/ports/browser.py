"""Browser sessions bound to one sandbox preview origin (Anchor + Playwright in production)."""

from typing import Protocol

from gauntlet.contracts import ActionRecord, ActionStep

from .sandbox import EnvironmentHandle


class BrowserProvider(Protocol):
    async def open_session(self, environment: EnvironmentHandle) -> str:
        """Return a session ID locked to ``environment.preview_origin``."""
        ...

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        """Execute one typed step. Off-origin navigation or redirects yield outcome 'blocked'."""
        ...

    async def close_session(self, session_id: str) -> None: ...
