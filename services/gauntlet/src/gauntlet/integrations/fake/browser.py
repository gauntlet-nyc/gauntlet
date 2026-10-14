"""Recorded browser responses; no browser, HTTP client, or live effects are used."""

from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4

from gauntlet.contracts import ActionRecord, ActionStep, AttackSpec
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle


@dataclass(frozen=True)
class BrowserRecording:
    plan: AttackSpec
    source_sha: str
    fixture_checksum: str
    records: tuple[ActionRecord, ...]
    redirects: tuple[str | None, ...] = ()


@dataclass
class _Session:
    environment: EnvironmentHandle
    recording: BrowserRecording
    next_step: int = 0


class FakeBrowserProvider:
    def __init__(self, recordings: tuple[BrowserRecording, ...]) -> None:
        for recording in recordings:
            if len(recording.records) != len(recording.plan.steps):
                raise ValueError("recording must cover each planned step")
            if recording.redirects and len(recording.redirects) != len(recording.records):
                raise ValueError("redirect recording must cover each step")
            for index, (step, record) in enumerate(
                zip(recording.plan.steps, recording.records, strict=True)
            ):
                if record.step_index != index or record.action != step.action:
                    raise ValueError("recording steps must match the frozen plan")
        self._recordings = recordings
        self._sessions: dict[str, _Session] = {}

    async def open_session(self, environment: EnvironmentHandle) -> str:
        origin = urlsplit(environment.preview_origin)
        if (
            origin.scheme != "https"
            or not (origin.hostname or "").endswith(".invalid")
            or origin.username is not None
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise EnvironmentUnavailableError("offline browser requires a reserved fake origin")
        candidates = [
            item
            for item in self._recordings
            if (
                item.plan.target_id == environment.target_id
                and item.plan.fixture_id == environment.fixture_id
                and item.source_sha == environment.source_sha
                and item.fixture_checksum == environment.fixture_checksum
            )
        ]
        if len(candidates) != 1:
            raise EnvironmentUnavailableError("no unique browser recording matches the environment")
        session_id = f"fake-browser-{uuid4().hex}"
        self._sessions[session_id] = _Session(environment, candidates[0])
        return session_id

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        session = self._sessions.get(session_id)
        if session is None:
            raise EnvironmentUnavailableError("browser session is unavailable")
        recording = session.recording
        if (
            step_index != session.next_step
            or not 0 <= step_index < len(recording.records)
            or step != recording.plan.steps[step_index]
            or step.action in {"chat", "test_api"}
        ):
            return ActionRecord(
                step_index=max(step_index, 0),
                action=step.action,
                outcome="blocked",
                detail="Action is outside the offline recording",
            )
        destination = recording.redirects[step_index] if recording.redirects else None
        if destination is not None:
            actual = urlsplit(destination)
            allowed = urlsplit(session.environment.preview_origin)
            if (actual.scheme, actual.netloc) != (allowed.scheme, allowed.netloc):
                return ActionRecord(
                    step_index=step_index,
                    action=step.action,
                    outcome="blocked",
                    detail="Recorded redirect leaves the allowed origin",
                )
        session.next_step += 1
        return recording.records[step_index].model_copy(deep=True)

    async def close_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
