"""Live smokes for Arize, GitHub App and ElevenLabs. One provider per invocation.

  arize        export one synthetic span tree + one experiment trace; prints trace IDs
  github       publish a neutral check run on --repo/--sha (checks: write only)
  elevenlabs   fetch a signed conversation URL (redacted) and synthesize a short briefing

All need RUN_LIVE_INTEGRATIONS=1 and that provider's keys. Prints IDs/status, no secrets.
"""

import argparse
import asyncio
import json
from uuid import uuid4

from gauntlet.contracts import ReplayResult, VoiceBriefing
from gauntlet.integrations.arize.experiments import record_counterfactual_experiment
from gauntlet.integrations.arize.experiments_sdk import (
    ArizeExperimentPublisher,
    RecallExperimentRow,
)
from gauntlet.integrations.arize.tracing import OtlpTracer, tracer_from_settings
from gauntlet.integrations.elevenlabs import ElevenLabsVoice
from gauntlet.integrations.github_app import GitHubAppCheckRunPublisher
from gauntlet.ports.code_host import CheckRunReport
from gauntlet.settings import SettingsError, load_settings, require, require_live


async def _arize() -> dict[str, object]:
    settings = load_settings()
    require("arize", settings.arize)
    tracer = tracer_from_settings(settings)
    assert isinstance(tracer, OtlpTracer)
    async with tracer.span("smoke.gate.run", "CHAIN", {"gauntlet.run_id": "smoke"}) as root:
        async with tracer.span("smoke.oracle", "EVALUATOR", {"eval.label": "passed"}):
            pass
    experiment = await record_counterfactual_experiment(
        tracer,
        experiment_id=f"smoke-{uuid4().hex[:8]}",
        decision_id="smoke-decision",
        control=ReplayResult(replay_id="smoke-control", status="matched"),
        counterfactual=ReplayResult(replay_id="smoke-cf", status="different"),
        control_matches=True,
        material_change=True,
        verdict="tainted",
    )
    await tracer.flush()
    experiment_object: str | None = None
    try:
        publisher = ArizeExperimentPublisher.from_settings(settings)
        experiment_object = await publisher.publish(
            f"gauntlet-smoke-{uuid4().hex[:8]}",
            [
                RecallExperimentRow(
                    "smoke-decision",
                    "smoke-control",
                    "matched",
                    "refund",
                    "smoke-cf",
                    "different",
                    "deny",
                    True,
                    True,
                    "tainted",
                )
            ],
        )
    except Exception as exc:  # noqa: BLE001 - report type only; SDK is optional
        experiment_object = f"not created ({type(exc).__name__})"
    return {
        "arize_experiment_id": experiment_object,
        "trace_id": root.trace_id,
        "experiment_trace_id": experiment.trace_id,
        "exported": tracer.exported,
        "dropped": tracer.dropped,
        "status": "passed" if tracer.exported and not tracer.dropped else "failed",
    }


async def _github(repo: str, sha: str) -> dict[str, object]:
    publisher = GitHubAppCheckRunPublisher.from_settings(load_settings())
    report = CheckRunReport(
        "Gauntlet (smoke)", "neutral", "Connectivity smoke", "Synthetic smoke check.", None
    )
    check_id = await publisher.publish(repo, sha, f"smoke-{uuid4().hex[:8]}", report)
    return {"check_run_id": check_id, "status": "passed"}


async def _elevenlabs() -> dict[str, object]:
    voice = ElevenLabsVoice.from_settings(load_settings())
    url = await voice.signed_conversation_url()
    result: dict[str, object] = {"signed_url_scheme": url.split(":", 1)[0]}
    briefing = VoiceBriefing(
        run_id="smoke",
        source_event_sequence=0,
        findings=(),
        confirmed=0,
        suspected=0,
        not_tested=0,
        coverage_gaps=0,
        spoken_summary="Gauntlet voice smoke test.",
    )
    try:
        audio = await voice.speak_briefing(briefing)
        result["audio_bytes"] = len(audio)
    except Exception as exc:  # noqa: BLE001 - optional voice ID
        result["tts"] = f"skipped ({type(exc).__name__})"
    result["status"] = "passed"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("arize", "github", "elevenlabs"))
    parser.add_argument("--repo", help="owner/name for the GitHub check run")
    parser.add_argument("--sha", help="full 40-char commit SHA for the GitHub check run")
    args = parser.parse_args()
    try:
        require_live(load_settings())
        if args.provider == "arize":
            report = asyncio.run(_arize())
        elif args.provider == "github":
            if not args.repo or not args.sha:
                parser.error("github needs --repo and --sha")
            report = asyncio.run(_github(args.repo, args.sha))
        else:
            report = asyncio.run(_elevenlabs())
    except SettingsError as exc:
        print(json.dumps({"provider": args.provider, "status": "not_run", "error": str(exc)}))
        raise SystemExit(2) from None
    print(json.dumps({"provider": args.provider, **report}, indent=2))


if __name__ == "__main__":
    main()
