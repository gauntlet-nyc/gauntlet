"""SandboxProvider over operator-started local Cartwheel servers (one per revision).

No process is started here. The operator runs the base and head checkouts on exact loopback
origins; ``create`` verifies each server's compiled build receipt names the requested SHA.
This is weaker than Daytona isolation and is labeled ``local`` in every report.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from uuid import uuid4

from gauntlet.contracts import ReplayMode
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

from .fixture_identity import canonical_loopback_origin, verify_fixture_build_receipt

ReceiptCheck = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class LocalRevision:
    source_sha: str
    origin: str


class PreStartedLocalSandbox:
    label = "local_prestarted"

    def __init__(
        self,
        *,
        target_id: str,
        fixture_id: str,
        fixture_checksum: str,
        revisions: Mapping[str, str],
        receipt_check: ReceiptCheck = verify_fixture_build_receipt,
    ) -> None:
        self._target_id = target_id
        self._fixture_id = fixture_id
        self._checksum = fixture_checksum
        self._origins = {sha: canonical_loopback_origin(o) for sha, o in revisions.items()}
        self._receipt_check = receipt_check
        self._active: dict[str, EnvironmentHandle] = {}

    async def create(
        self, *, target_id: str, source_sha: str, fixture_id: str, mode: ReplayMode
    ) -> EnvironmentHandle:
        origin = self._origins.get(source_sha)
        if target_id != self._target_id or fixture_id != self._fixture_id or origin is None:
            raise EnvironmentUnavailableError("target, fixture or revision is not registered")
        await self._receipt_check(origin, source_sha)
        handle = EnvironmentHandle(
            environment_id=f"local-env-{uuid4().hex}",
            target_id=target_id,
            source_sha=source_sha,
            fixture_id=fixture_id,
            fixture_checksum=self._checksum,
            preview_origin=origin,
        )
        self._active[handle.environment_id] = handle
        return handle

    async def verify_fixture(self, environment_id: str, expected_checksum: str) -> bool:
        handle = self._active.get(environment_id)
        if handle is None or expected_checksum != self._checksum:
            return False
        try:
            await self._receipt_check(handle.preview_origin, handle.source_sha)
        except EnvironmentUnavailableError:
            return False
        return True

    async def destroy(self, environment_id: str) -> None:
        self._active.pop(environment_id, None)
