"""Origin-locked HTTP client for the API worker. The plan supplies only method, path, body.

No redirects, no proxy environment, bounded bodies. The trusted client records the request it
sent and the response it received as one JSON artifact bound to the step subject.
"""

import json
from typing import Final, Literal

import httpx

from gauntlet.contracts import ActionRecord, ApiRequestStep, EvidenceSubject
from gauntlet.ports.artifacts import ArtifactStore
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

API_EXCHANGE_SCHEMA: Final = "gauntlet-api-exchange-1"
_MAX_BODY: Final = 64 * 1024


class HttpxApiClient:
    label = "origin_locked_httpx"

    def __init__(
        self, artifacts: ArtifactStore, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._artifacts = artifacts
        self._transport = transport

    async def request(
        self,
        environment: EnvironmentHandle,
        subject: EvidenceSubject,
        step_index: int,
        step: ApiRequestStep,
    ) -> ActionRecord:
        url = environment.preview_origin + step.path
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(10, connect=3),
            ) as client:
                response = await client.request(
                    step.method,
                    url,
                    content=step.body_json.encode() if step.body_json is not None else None,
                    headers={
                        "content-type": "application/json",
                        "x-synthetic-actor": step.actor_id,
                    },
                )
            raw = response.content[: _MAX_BODY + 1]
        except httpx.HTTPError as exc:
            raise EnvironmentUnavailableError("API request failed") from exc
        try:
            body: object = json.loads(raw) if len(raw) <= _MAX_BODY else None
        except ValueError:
            body = None
        exchange = {
            "schema": API_EXCHANGE_SCHEMA,
            "method": step.method,
            "path": step.path,
            "request_body": step.body_json,
            "status": response.status_code,
            "body": body,
        }
        binding = await self._artifacts.put(
            json.dumps(exchange, sort_keys=True).encode(),
            "application/json",
            subject.model_copy(update={"step_index": step_index}),
        )
        outcome: Literal["ok", "blocked"] = "blocked" if 300 <= response.status_code < 400 else "ok"
        return ActionRecord(
            step_index=step_index,
            action="test_api",
            outcome=outcome,
            detail=f"HTTP {response.status_code}",
            evidence_ids=(binding.evidence.artifact_id,),
        )
