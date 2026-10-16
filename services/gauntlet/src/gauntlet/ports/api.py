"""Typed HTTP requests to one sandbox preview origin (API worker, P9)."""

from typing import Protocol

from gauntlet.contracts import ActionRecord, ApiRequestStep, EvidenceSubject

from .sandbox import EnvironmentHandle


class ApiClient(Protocol):
    async def request(
        self,
        environment: EnvironmentHandle,
        subject: EvidenceSubject,
        step_index: int,
        step: ApiRequestStep,
    ) -> ActionRecord:
        """Send one typed request to the environment's exact origin, no redirects. Store the
        request and response as evidence bound to the step. Off-origin is impossible: only the
        path comes from the plan."""
        ...
