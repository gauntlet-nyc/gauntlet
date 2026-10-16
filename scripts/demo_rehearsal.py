"""Rehearse the docs/DEMO.md click-path end to end, offline, in a real browser.

Starts the API and the built dashboard, then drives Chromium through the exact demo path and
asserts what each step must show. With --backup-dir it also saves a screenshot of every page
and the API JSON behind it, so the demo can be shown from recordings if a live service fails.

    pnpm --filter @gauntlet/dashboard build   # once
    uv run --group live-providers python scripts/demo_rehearsal.py
    uv run --group live-providers python scripts/demo_rehearsal.py \
        --backup-dir artifacts/demo-backup

Everything runs offline: RUN_LIVE_INTEGRATIONS and provider keys are removed from the child
processes, so no provider can be called. Exit code 0 means every step passed.
"""

import argparse
import html
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "apps/dashboard"
TOKEN = "rehearsal-reviewer-token-0123456789"
CHROMIUM_CANDIDATES = (
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)
# Removed from child processes so the rehearsal can never reach a live provider.
LIVE_PREFIXES = (
    "RUN_LIVE_INTEGRATIONS",
    "AZURE_OPENAI_",
    "AWS_",
    "BEDROCK_",
    "DAYTONA_",
    "ANCHOR_",
    "ARIZE_",
    "SURREAL_",
    "ELEVENLABS_",
    "VOICE_WEBHOOK_",
    "GITHUB_",
    "CARTWHEEL_BASE_ORIGIN",
    "CARTWHEEL_HEAD_ORIGIN",
    "GAUNTLET_REVIEWER_TOKENS",
    "GAUNTLET_DAYTONA_REGISTRATION",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _offline_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(LIVE_PREFIXES)}
    env.update(extra)
    return env


def _wait(url: str, seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


@contextmanager
def _process(cmd: list[str], cwd: Path, env: dict[str, str], log: Path) -> Iterator[None]:
    with log.open("w") as out:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            yield
        finally:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)


def _chromium(explicit: str | None) -> str:
    for path in (explicit, os.environ.get("GAUNTLET_CHROMIUM_PATH"), *CHROMIUM_CANDIDATES):
        if path and Path(path).exists():
            return path
    raise RuntimeError("no Chromium found; pass --chromium or set GAUNTLET_CHROMIUM_PATH")


class Rehearsal:
    def __init__(self, page: "Page", web: str, api: str, backup: Path | None) -> None:
        self.page = page
        self.web = web
        self.api = api
        self.backup = backup
        self.steps: list[dict[str, object]] = []

    def step(self, name: str, action: Callable[[], None]) -> None:
        started = time.monotonic()
        action()
        elapsed = round(time.monotonic() - started, 2)
        self.steps.append({"step": name, "ok": True, "seconds": elapsed})
        print(f"  ok  {name} ({elapsed}s)", flush=True)

    def shot(self, name: str) -> None:
        if self.backup:
            self.page.screenshot(path=str(self.backup / "pages" / f"{name}.png"), full_page=True)

    def save_json(self, name: str, path: str) -> object:
        with urllib.request.urlopen(f"{self.api}{path}", timeout=30) as response:
            data: object = json.loads(response.read())
        if self.backup:
            (self.backup / "api" / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
        return data

    def expect_text(self, text: str) -> None:
        self.page.get_by_text(text, exact=False).first.wait_for(timeout=30_000)

    def start_run(self, change_id: str) -> str:
        self.page.goto(f"{self.web}/gate")
        self.page.select_option("select[name=change_id]", change_id)
        self.page.click("text=Start Gate run")
        self.page.wait_for_url("**/gate/runs/**", timeout=120_000)
        return self.page.url.split("/gate/runs/")[1].split("?")[0]


def rehearse(page: "Page", web: str, api: str, backup: Path | None) -> list[dict[str, object]]:
    r = Rehearsal(page, web, api, backup)
    runs: dict[str, str] = {}

    def sponsors() -> None:
        page.goto(f"{web}/sponsors")
        r.expect_text("offline-tested, live NOT RUN")
        assert page.get_by_text("live verified", exact=True).count() == 0
        r.shot("01-sponsors")
        r.save_json("sponsors", "/sponsors")

    def login() -> None:
        page.goto(f"{web}/login")
        page.fill("input[name=token]", TOKEN)
        page.click("text=Store token")
        page.wait_for_url("**ok=1")

    def help_button() -> None:
        runs["help"] = r.start_run("help-button")
        r.expect_text("OFFLINE / live NOT RUN")
        r.expect_text("regression introduced by this PR")
        r.expect_text("Head: 2/2 failed · Base: 0/2 failed")
        images = page.locator("figure img")
        assert images.count() >= 4, "expected evidence screenshots"
        loaded = page.evaluate(
            "() => [...document.querySelectorAll('figure img')].every(i => i.naturalWidth > 0)"
        )
        assert loaded, "evidence screenshots did not load"
        r.shot("02-gate-help-button")
        r.save_json("gate-help-button", f"/gate/runs/{runs['help']}")

    def approve_ui_fix() -> None:
        page.click("text=Approve fix plan")
        page.wait_for_url("**approval=recorded**")
        r.expect_text("bound to this exact plan hash")
        r.shot("03-gate-help-button-approved")

    def clean_change() -> None:
        runs["clean"] = r.start_run("clean")
        r.expect_text("Verdict:")
        assert page.locator("[data-testid=status-pill]").first.inner_text().strip() == "passed"
        r.shot("04-gate-clean")
        r.save_json("gate-clean", f"/gate/runs/{runs['clean']}")

    def refund_tool() -> None:
        runs["refund"] = r.start_run("refund-tool")
        r.expect_text("regression introduced by this PR")
        r.expect_text("Forbidden refund recorded")
        r.shot("05-gate-refund-tool")

    def repair_refused_before_approval() -> None:
        page.click("text=Apply approved plan")
        page.wait_for_url("**repair=409**")
        r.expect_text("approve this exact hash first")

    def repair_after_approval() -> None:
        page.goto(f"{web}/gate/runs/{runs['refund']}")
        page.click("text=Approve fix plan")
        page.wait_for_url("**approval=recorded**")
        page.click("text=Apply approved plan")
        page.wait_for_url("**repair=done**", timeout=120_000)
        r.expect_text("Release verdict: fix verified review required")
        r.shot("06-gate-refund-repaired")
        r.save_json("gate-refund-tool-repaired", f"/gate/runs/{runs['refund']}")

    def memory() -> None:
        runs["help2"] = r.start_run("help-button")
        page.goto(f"{web}/memory")
        r.expect_text("Planning with vs without memory")
        row = page.locator("tr", has_text=runs["help2"])
        assert "fact-" in row.inner_text(), "second run should receive the remembered fact"
        r.shot("07-memory")
        r.save_json("memory", "/memory")

    def recall() -> None:
        page.goto(f"{web}/recall")
        r.expect_text("36 operations audited")
        r.expect_text("second-order")
        for label in ("tainted", "cleared", "not replayable"):
            r.expect_text(label)
        r.shot("08-recall")
        r.save_json("recall-audit", "/recall/audit")
        r.save_json("recall-counterfactual", "/recall/counterfactual")
        r.save_json("recall-timeline", "/recall/timeline")

    def review_queue() -> None:
        page.goto(f"{web}/recall/review")
        page.locator("text=Approve for review").first.click()
        page.wait_for_url("**approval=recorded**")
        r.expect_text("Nothing was merged, deployed, refunded or sent")
        r.shot("09-review-queue")
        r.save_json("review-queue", "/recall/review-queue")

    def onboarding() -> None:
        page.goto(f"{web}/onboarding")
        r.expect_text("Registered targets")
        r.shot("10-onboarding")

    r.step("sponsor panel shows nothing live", sponsors)
    r.step("reviewer login", login)
    r.step("Act A: Help-button run is a confirmed regression with screenshots", help_button)
    r.step("Act A: fix plan approval bound to the hash", approve_ui_fix)
    r.step("Act A: unrelated clean change passes", clean_change)
    r.step("Act B: refund-tool run is a confirmed regression", refund_tool)
    r.step("Act B: repair refused before approval", repair_refused_before_approval)
    r.step("Act B: approved repair is re-verified", repair_after_approval)
    r.step("Memory: second run receives the verified fact", memory)
    r.step("Act C: Recall audit and counterfactual", recall)
    r.step("Act C: review queue is review-only", review_queue)
    r.step("Onboarding page", onboarding)
    return r.steps


CAPTIONS = {
    "01-sponsors": "Sponsor proof: every provider offline-tested, live NOT RUN",
    "02-gate-help-button": "Act A: Help-button PR, regression introduced (head 2/2, base 0/2)",
    "03-gate-help-button-approved": "Act A: fix plan approved, bound to its exact hash",
    "04-gate-clean": "Act A: unrelated change passes on both revisions",
    "05-gate-refund-tool": "Act B: refund-tool PR, forbidden refund recorded on head only",
    "06-gate-refund-repaired": "Act B: approved patch re-verified (original, variant, legitimate)",
    "07-memory": "Memory: the second run receives the verified fact",
    "08-recall": "Act C: Recall audit and counterfactual (tainted, cleared, not replayable)",
    "09-review-queue": "Act C: review-only queue",
    "10-onboarding": "Onboarding: registered synthetic targets",
}


def write_playback(backup: Path, summary: dict[str, object]) -> None:
    """A self-contained page that shows the recorded demo in order, clearly labelled."""
    figures = "".join(
        f"<figure><figcaption>{html.escape(caption)}</figcaption>"
        f"<img src='pages/{name}.png' alt='{html.escape(caption)}' loading='lazy'></figure>"
        for name, caption in CAPTIONS.items()
        if (backup / "pages" / f"{name}.png").exists()
    )
    (backup / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Gauntlet demo backup</title>"
        "<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 16px}"
        "figure{margin:0 0 2rem}img{width:100%;border:1px solid #ccc}"
        ".rec{background:#111;color:#ffd400;padding:8px;font-weight:700}</style>"
        f"<p class='rec'>RECORDED offline rehearsal from {html.escape(str(summary['recorded_at']))}"
        " — not a live run. JSON for every page is in api/.</p>"
        f"{figures}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, help="save page screenshots and API JSON here")
    parser.add_argument("--chromium", help="Chromium/Chrome executable")
    args = parser.parse_args()
    if not (DASHBOARD / ".next" / "BUILD_ID").exists():
        print("build the dashboard first: pnpm --filter @gauntlet/dashboard build", file=sys.stderr)
        return 2
    from playwright.sync_api import sync_playwright

    backup: Path | None = args.backup_dir
    logs = backup or Path(os.environ.get("TMPDIR", "/tmp")) / "gauntlet-rehearsal"
    if backup:
        if backup.exists():
            shutil.rmtree(backup)
        (backup / "pages").mkdir(parents=True)
        (backup / "api").mkdir()
    logs.mkdir(parents=True, exist_ok=True)
    api_port, web_port = _free_port(), _free_port()
    api, web = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    api_env = _offline_env(GAUNTLET_REVIEWER_TOKENS=f"rehearsal:{TOKEN}")
    web_env = _offline_env(GAUNTLET_API_URL=api, NEXT_PUBLIC_GAUNTLET_API_URL=api)
    started = time.monotonic()
    uvicorn = [sys.executable, "-m", "uvicorn", "gauntlet.api.main:app", "--port", str(api_port)]
    next_bin = DASHBOARD / "node_modules" / ".bin" / "next"
    with (
        _process(uvicorn, ROOT, api_env, logs / "api.log"),
        _process(
            [str(next_bin), "start", "-p", str(web_port)], DASHBOARD, web_env, logs / "web.log"
        ),
    ):
        _wait(f"{api}/health")
        _wait(f"{web}/")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_chromium(args.chromium))
            page = browser.new_page(viewport={"width": 1100, "height": 900})
            try:
                steps = rehearse(page, web, api, backup)
            except Exception:
                if backup:
                    page.screenshot(path=str(backup / "pages" / "FAILED.png"), full_page=True)
                raise
            finally:
                browser.close()
    seconds = round(time.monotonic() - started, 1)
    summary = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "mode": "offline (no provider contacted)",
        "seconds": seconds,
        "steps": steps,
    }
    if backup:
        (backup / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        write_playback(backup, summary)
    print(f"rehearsal passed: {len(steps)} steps in {seconds}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
