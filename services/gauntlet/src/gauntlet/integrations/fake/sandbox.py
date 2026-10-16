"""In-memory sandbox with explicit target, fixture and source allowlists."""

from dataclasses import dataclass
from uuid import uuid4

from gauntlet.contracts import ReplayMode
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    checksum: str
    allowed_shas: frozenset[str]


class FakeSandboxProvider:
    def __init__(self, fixtures: dict[str, Fixture]) -> None:
        self._fixtures = dict(fixtures)
        self._active: dict[str, EnvironmentHandle] = {}

    async def create(
        self, *, target_id: str, source_sha: str, fixture_id: str, mode: ReplayMode
    ) -> EnvironmentHandle:
        fixture = self._fixtures.get(target_id)
        if (
            fixture is None
            or fixture.fixture_id != fixture_id
            or source_sha not in fixture.allowed_shas
        ):
            raise EnvironmentUnavailableError("target, fixture or source is not registered")
        environment_id = f"fake-env-{uuid4().hex}"
        handle = EnvironmentHandle(
            environment_id=environment_id,
            target_id=target_id,
            source_sha=source_sha,
            fixture_id=fixture_id,
            fixture_checksum=fixture.checksum,
            preview_origin="https://fake-preview.invalid",
        )
        self._active[environment_id] = handle
        return handle

    async def verify_fixture(self, environment_id: str, expected_checksum: str) -> bool:
        handle = self._active.get(environment_id)
        return handle is not None and handle.fixture_checksum == expected_checksum

    async def destroy(self, environment_id: str) -> None:
        self._active.pop(environment_id, None)
