"""OFFLINE SIMULATION of a rendered page, for credential-free Gate runs and contract tests.

This is not a browser. A small layout model (boxes per test ID, fixed positioning rules
transcribed from the fixture CSS) answers the collector's fixed geometry, click and
screenshot calls. Evidence still flows through the real ``BrowserEvidenceCollector`` and the
write-once artifact store, so the trusted oracle path is identical to a live run. Reports from
this provider must be labeled ``offline_simulated`` and never presented as a browser result.
"""

import struct
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import uuid4

from gauntlet.contracts import (
    ActionRecord,
    ActionStep,
    CaptureStep,
    ClickStep,
    EvidenceSubject,
    InspectStep,
    NavigateStep,
    PressStep,
    ResizeStep,
    ScrollStep,
    TypeStep,
)
from gauntlet.integrations.browser_evidence import BrowserEvidenceCollector
from gauntlet.ports.browser import is_browser_subject_for
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.ports.sandbox import EnvironmentHandle

Rect = tuple[float, float, float, float]
"""x, y, width, height in CSS pixels."""


@dataclass(frozen=True)
class SimulatedBox:
    test_id: str
    z_index: int
    place: Callable[[int, int], Rect | None]
    """Viewport (width, height) -> rect, or None when not rendered at that size."""


@dataclass(frozen=True)
class SimulatedLayout:
    routes: Mapping[str, tuple[SimulatedBox, ...]]


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(rgb) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


@dataclass
class _Mouse:
    page: "_SimulatedPage"

    async def click(self, x: float, y: float) -> None:
        self.page.receipt = {"received_target": self.page.hit(x, y), "trusted": True}


@dataclass
class _SimulatedPage:
    layout: SimulatedLayout
    route: str | None = None
    width: int = 1280
    height: int = 720
    receipt: dict[str, object] | None = None
    mouse: _Mouse = field(init=False)

    def __post_init__(self) -> None:
        self.mouse = _Mouse(self)

    def _boxes(self) -> list[tuple[SimulatedBox, Rect]]:
        boxes = self.layout.routes.get(self.route or "", ())
        placed = [(box, box.place(self.width, self.height)) for box in boxes]
        return [(box, rect) for box, rect in placed if rect is not None]

    def hit(self, x: float, y: float) -> str | None:
        hits = [
            (box.z_index, index, box.test_id)
            for index, (box, (bx, by, bw, bh)) in enumerate(self._boxes())
            if bx <= x < bx + bw and by <= y < by + bh
        ]
        return max(hits)[2] if hits else None

    async def evaluate(self, expression: str, arg: object = None) -> object:
        if "getBoundingClientRect" in expression:
            matches = [rect for box, rect in self._boxes() if box.test_id == arg]
            if len(matches) != 1:
                return {"matches": len(matches)}
            x, y, w, h = matches[0]
            return {
                "matches": 1,
                "rect": {"x": x, "y": y, "width": w, "height": h},
                "viewport": {"width": self.width, "height": self.height},
                "hit_target": self.hit(x + w / 2, y + h / 2),
            }
        if "__gauntletClickReceipt = null" in expression:
            self.receipt = None
            return None
        if "delete window.__gauntletClickReceipt" in expression:
            receipt, self.receipt = self.receipt, None
            return receipt
        raise EnvironmentUnavailableError("simulated page accepts only the collector's scripts")

    async def screenshot(self) -> bytes:
        shade = 200 if self.route else 255
        return _png(4, 4, (shade, shade, shade))


@dataclass
class _Session:
    subject: EvidenceSubject
    page: _SimulatedPage
    next_step: int = 0


class SimulatedBrowserProvider:
    """BrowserProvider over per-revision layout models. Offline only; reserved origins only."""

    label = "offline_simulated"

    def __init__(
        self, layouts: Mapping[str, SimulatedLayout], collector: BrowserEvidenceCollector
    ) -> None:
        self._layouts = dict(layouts)
        self._collector = collector
        self._sessions: dict[str, _Session] = {}

    async def open_session(self, environment: EnvironmentHandle, subject: EvidenceSubject) -> str:
        if not is_browser_subject_for(environment, subject):
            raise EnvironmentUnavailableError("browser evidence subject does not match environment")
        if not (urlsplit(environment.preview_origin).hostname or "").endswith(".invalid"):
            raise EnvironmentUnavailableError("simulated browser requires a reserved fake origin")
        layout = self._layouts.get(environment.source_sha)
        if layout is None:
            raise EnvironmentUnavailableError("no simulated layout for this revision")
        session_id = f"simulated-browser-{uuid4().hex}"
        self._sessions[session_id] = _Session(subject, _SimulatedPage(layout))
        return session_id

    async def perform(self, session_id: str, step_index: int, step: ActionStep) -> ActionRecord:
        session = self._sessions.get(session_id)
        if session is None or step_index != session.next_step:
            raise EnvironmentUnavailableError("browser session or step sequence is unavailable")
        session.next_step += 1
        page = session.page
        if isinstance(step, NavigateStep):
            if step.path not in page.layout.routes:
                return ActionRecord(
                    step_index=step_index, action="navigate", outcome="error", detail="404"
                )
            page.route = step.path
            return ActionRecord(step_index=step_index, action="navigate", outcome="ok")
        if isinstance(step, ResizeStep):
            page.width, page.height = step.width, step.height
            return ActionRecord(step_index=step_index, action="resize", outcome="ok")
        if isinstance(step, InspectStep):
            return await self._collector.inspect(page, step.target, session.subject, step_index)
        if isinstance(step, ClickStep):
            return await self._collector.click(page, step.target, session.subject, step_index)
        if isinstance(step, CaptureStep):
            return await self._collector.capture(page, session.subject, step_index)
        if isinstance(step, ScrollStep | TypeStep | PressStep):
            return ActionRecord(step_index=step_index, action=step.action, outcome="ok")
        return ActionRecord(
            step_index=step_index,
            action=step.action,
            outcome="blocked",
            detail="Action is outside the browser port",
        )

    async def close_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# --- Cartwheel layout model, transcribed from apps/cartwheel/fixture CSS ----------------------

_CHECKOUT_BUTTON = (110.0, 42.0)  # padding 12px 20px around "Place order"
_HELP_BUTTON = (66.0, 42.0)  # padding 12px 20px around "Help"


def _checkout(width: int, height: int) -> Rect:
    # footer: position fixed; bottom 0; padding 16; justify-content flex-end
    w, h = _CHECKOUT_BUTTON
    return (width - 16 - w, height - 16 - h, w, h)


def _help(width: int, height: int) -> Rect:
    # .floatingHelp: fixed; bottom 16px; right 16px; z-index 50; >=900px: bottom 96px
    w, h = _HELP_BUTTON
    bottom = 96 if width >= 900 else 16
    return (width - 16 - w, height - bottom - h, w, h)


def _product(width: int, height: int) -> Rect:
    return (16.0, 80.0, min(400.0, width - 32.0), 200.0)


def cartwheel_layouts(
    base_sha: str, head_sha: str, *, head_adds_help: bool = True
) -> dict[str, SimulatedLayout]:
    """Base: storefront without the floating Help widget. Head: Help added in layout.tsx.

    ``head_adds_help=False`` models the clean product-copy commit (layout equals base).
    """
    page_boxes = {
        "/checkout": (SimulatedBox("checkout-primary-action", 1, _checkout),),
        "/products/demo": (SimulatedBox("product-detail", 1, _product),),
    }
    help_box = SimulatedBox("help-button", 50, _help)
    head_boxes = (
        {route: (*boxes, help_box) for route, boxes in page_boxes.items()}
        if head_adds_help
        else page_boxes
    )
    return {base_sha: SimulatedLayout(page_boxes), head_sha: SimulatedLayout(head_boxes)}
