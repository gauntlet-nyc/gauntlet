"""Collect fixed browser measurements from an authorized synthetic page.

The browser adapter owns navigation and network policy. This collector accepts no
page- or planner-supplied JavaScript; its expressions are fixed below. Browser
measurements remain data until an independent verifier checks stored bindings.
"""

import json
import math
from collections.abc import Mapping
from typing import Literal, Protocol

from gauntlet.application.image_format import screenshot_media_type
from gauntlet.contracts import ActionRecord, EvidenceSubject
from gauntlet.ports import ArtifactStore
from gauntlet.ports.errors import EnvironmentUnavailableError

_GEOMETRY_SCRIPT = """(testId) => {
  const matches = Array.from(document.querySelectorAll('[data-testid]'))
    .filter(el => el.getAttribute('data-testid') === testId);
  if (matches.length !== 1) return {matches: matches.length};
  const r = matches[0].getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const hit = document.elementFromPoint(x, y);
  return {
    matches: 1,
    rect: {x: r.left, y: r.top, width: r.width, height: r.height},
    viewport: {width: innerWidth, height: innerHeight},
    hit_target: hit?.closest('[data-testid]')?.getAttribute('data-testid') ?? null
  };
}"""

_ARM_CLICK_SCRIPT = """() => {
  window.__gauntletClickReceipt = null;
  document.addEventListener('click', event => {
    window.__gauntletClickReceipt = {
      received_target: event.target?.closest('[data-testid]')?.getAttribute('data-testid') ?? null,
      trusted: event.isTrusted
    };
  }, {capture: true, once: true});
}"""

_READ_CLICK_SCRIPT = """() => {
  const receipt = window.__gauntletClickReceipt;
  delete window.__gauntletClickReceipt;
  return receipt;
}"""


class _Mouse(Protocol):
    async def click(self, x: float, y: float) -> None: ...


class BrowserPage(Protocol):
    @property
    def mouse(self) -> _Mouse: ...

    async def evaluate(self, expression: str, arg: object = None) -> object: ...

    async def screenshot(self, *, type: Literal["png"]) -> bytes: ...


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _test_id(value: object) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= 512 else None


def _geometry(raw: object) -> tuple[dict[str, object], float, float] | None:
    if not isinstance(raw, Mapping) or type(raw.get("matches")) is not int or raw["matches"] != 1:
        return None
    rect = raw.get("rect")
    viewport = raw.get("viewport")
    if not isinstance(rect, Mapping) or not isinstance(viewport, Mapping):
        return None
    x = _number(rect.get("x"))
    y = _number(rect.get("y"))
    width = _number(rect.get("width"))
    height = _number(rect.get("height"))
    viewport_width = _number(viewport.get("width"))
    viewport_height = _number(viewport.get("height"))
    if None in (x, y, width, height, viewport_width, viewport_height):
        return None
    assert x is not None and y is not None and width is not None and height is not None
    assert viewport_width is not None and viewport_height is not None
    center_x, center_y = x + width / 2, y + height / 2
    if (
        width <= 0
        or height <= 0
        or not 0 <= center_x < viewport_width
        or not 0 <= center_y < viewport_height
    ):
        return None
    hit = raw.get("hit_target")
    if hit is not None and _test_id(hit) is None:
        return None
    measurement: dict[str, object] = {
        "rect": {"x": x, "y": y, "width": width, "height": height},
        "viewport": {"width": viewport_width, "height": viewport_height},
        "hit_target": hit,
    }
    return measurement, center_x, center_y


def _step_subject(subject: EvidenceSubject, step_index: int) -> EvidenceSubject:
    if subject.collector != "browser_collector" or subject.step_index is not None or step_index < 0:
        raise EnvironmentUnavailableError("invalid browser evidence subject")
    return EvidenceSubject.model_validate({**subject.model_dump(), "step_index": step_index})


class BrowserEvidenceCollector:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    async def capture(
        self, page: BrowserPage, subject: EvidenceSubject, step_index: int
    ) -> ActionRecord:
        step_subject = _step_subject(subject, step_index)
        try:
            screenshot = await page.screenshot(type="png")
            media_type = screenshot_media_type(screenshot)
            if media_type is None:
                raise EnvironmentUnavailableError(
                    "browser did not return a complete PNG or JPEG screenshot"
                )
            binding = await self._artifacts.put(screenshot, media_type, step_subject)
        except Exception as exc:
            raise EnvironmentUnavailableError("browser screenshot capture failed") from exc
        return ActionRecord(
            step_index=step_index,
            action="capture",
            outcome="ok",
            evidence_ids=(binding.evidence.artifact_id,),
        )

    async def inspect(
        self, page: BrowserPage, target: str, subject: EvidenceSubject, step_index: int
    ) -> ActionRecord:
        step_subject = _step_subject(subject, step_index)
        try:
            result = _geometry(await page.evaluate(_GEOMETRY_SCRIPT, target))
            if result is None:
                return ActionRecord(step_index=step_index, action="inspect", outcome="error")
            measurement, _, _ = result
            binding = await self._artifacts.put(
                json.dumps({"target": target, **measurement}, sort_keys=True).encode(),
                "application/json",
                step_subject,
            )
        except Exception as exc:
            raise EnvironmentUnavailableError("browser inspection capture failed") from exc
        return ActionRecord(
            step_index=step_index,
            action="inspect",
            outcome="ok",
            evidence_ids=(binding.evidence.artifact_id,),
        )

    async def click(
        self, page: BrowserPage, target: str, subject: EvidenceSubject, step_index: int
    ) -> ActionRecord:
        step_subject = _step_subject(subject, step_index)
        evidence_ids: list[str] = []
        try:
            result = _geometry(await page.evaluate(_GEOMETRY_SCRIPT, target))
            if result is None:
                return ActionRecord(step_index=step_index, action="click", outcome="error")
            measurement, x, y = result
            await page.evaluate(_ARM_CLICK_SCRIPT)
            await page.mouse.click(x, y)
            raw_receipt = await page.evaluate(_READ_CLICK_SCRIPT)
            received = (
                raw_receipt.get("received_target") if isinstance(raw_receipt, Mapping) else None
            )
            trusted = (
                raw_receipt.get("trusted") is True if isinstance(raw_receipt, Mapping) else False
            )
            if received is not None and _test_id(received) is None:
                received, trusted = None, False
            binding = await self._artifacts.put(
                json.dumps(
                    {
                        "target": target,
                        **measurement,
                        "received_target": received,
                        "trusted": trusted,
                    },
                    sort_keys=True,
                ).encode(),
                "application/json",
                step_subject,
            )
            evidence_ids.append(binding.evidence.artifact_id)
            screenshot = await page.screenshot(type="png")
            media_type = screenshot_media_type(screenshot)
            if media_type is None:
                raise EnvironmentUnavailableError(
                    "browser did not return a complete PNG or JPEG screenshot"
                )
            image = await self._artifacts.put(screenshot, media_type, step_subject)
            evidence_ids.append(image.evidence.artifact_id)
        except Exception as exc:
            raise EnvironmentUnavailableError("browser click capture failed") from exc
        outcome: Literal["ok", "error", "blocked"] = "error"
        if trusted and received is not None and measurement["hit_target"] == received:
            outcome = "ok" if received == target else "blocked"
        return ActionRecord(
            step_index=step_index,
            action="click",
            outcome=outcome,
            evidence_ids=tuple(evidence_ids),
        )
