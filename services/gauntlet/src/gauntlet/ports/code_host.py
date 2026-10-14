"""Publishing results back to the code host (GitHub check runs). Write access is checks-only."""

from dataclasses import dataclass
from typing import Literal, Protocol

CheckConclusion = Literal["success", "failure", "neutral"]


@dataclass(frozen=True)
class CheckRunReport:
    name: str
    conclusion: CheckConclusion
    title: str
    summary: str
    details_url: str | None


class CheckRunPublisher(Protocol):
    async def publish(
        self, repository_full_name: str, head_sha: str, external_id: str, report: CheckRunReport
    ) -> str:
        """Create or update the check run identified by `external_id` (the run ID) on
        `head_sha`; return GitHub's check-run ID. Must not push, comment, approve or merge."""
        ...
