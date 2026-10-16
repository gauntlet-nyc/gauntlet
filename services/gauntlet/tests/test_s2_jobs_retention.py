"""P10: job/cost ledger and lease recovery (local SurrealDB), evidence retention (offline)."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from gauntlet.execution.retention import sweep_artifacts
from gauntlet.persistence.jobs import (
    BudgetExceededError,
    JobTransitionError,
    SurrealJobLedger,
    recover_leases,
)
from gauntlet.persistence.surreal_client import SurrealHttpClient

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _touch(path: Path, age: timedelta) -> None:
    path.write_bytes(b"x")
    stamp = (NOW - age).timestamp()
    os.utime(path, (stamp, stamp))


def test_retention_dry_run_then_apply(tmp_path: Path) -> None:
    old, keep, fresh = (f"art-{c * 32}" for c in "abc")
    _touch(tmp_path / f"{old}.artifact", timedelta(days=40))
    _touch(tmp_path / f"{keep}.artifact", timedelta(days=40))
    _touch(tmp_path / f"{fresh}.artifact", timedelta(days=1))
    _touch(tmp_path / ".pending-abc123", timedelta(hours=3))
    _touch(tmp_path / "notes.txt", timedelta(days=400))
    (tmp_path / f"art-{'d' * 32}.artifact").symlink_to(tmp_path / "notes.txt")
    plan = sweep_artifacts(tmp_path, retention_days=30, now=NOW, protected_ids=[keep])
    assert plan.expired == (old,) and plan.protected_kept == (keep,)
    assert plan.abandoned_temp == (".pending-abc123",) and not plan.applied
    assert (tmp_path / f"{old}.artifact").exists()
    sweep_artifacts(tmp_path, retention_days=30, now=NOW, protected_ids=[keep], apply=True)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == sorted(
        [f"{keep}.artifact", f"{fresh}.artifact", "notes.txt", f"art-{'d' * 32}.artifact"]
    )


def test_retention_rejects_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        sweep_artifacts(tmp_path, retention_days=0, now=NOW)
    with pytest.raises(ValueError):
        sweep_artifacts(tmp_path / "missing", retention_days=1, now=NOW)


LOCAL_URL = os.environ.get("SURREAL_TEST_URL")
LOCAL_PASS = os.environ.get("SURREAL_TEST_PASS")


@pytest.mark.skipif(not (LOCAL_URL and LOCAL_PASS), reason="local SurrealDB not configured")
def test_local_job_lifecycle_budget_and_recovery() -> None:
    assert LOCAL_URL and LOCAL_PASS
    assert urlsplit(LOCAL_URL).hostname in {"127.0.0.1", "localhost"}

    async def scenario() -> None:
        client = SurrealHttpClient(
            url=LOCAL_URL,
            namespace="gauntlet_test",
            database=f"j{uuid4().hex[:12]}",
            user="root",
            password=LOCAL_PASS,
        )
        ledger = SurrealJobLedger(client)
        await ledger.ensure_schema()
        await ledger.create_job(
            job_id="j1", run_id="r1", kind="gate", budget_usd_cents=100, now=NOW
        )
        with pytest.raises(JobTransitionError):
            await ledger.create_job(
                job_id="j1", run_id="r1", kind="gate", budget_usd_cents=1, now=NOW
            )
        with pytest.raises(JobTransitionError, match="illegal_transition"):
            await ledger.transition("j1", "succeeded", now=NOW)
        await ledger.transition("j1", "running", now=NOW)
        assert (
            await ledger.record_cost(
                "j1", entry_id="c1", provider="daytona", units=2, usd_cents=60, now=NOW
            )
            == 60
        )
        with pytest.raises(BudgetExceededError) as raised:
            await ledger.record_cost(
                "j1", entry_id="c2", provider="anchor", units=1, usd_cents=50, now=NOW
            )
        assert raised.value.spent == 110
        job = await ledger.get_job("j1")
        assert job is not None and job.spent_usd_cents == 110 and job.state == "running"

        await ledger.acquire(job_id="j1", provider="daytona", resource_id="sb-1", now=NOW)
        await ledger.acquire(job_id="j1", provider="anchor", resource_id="as-1", now=NOW)
        await ledger.acquire(job_id="j1", provider="mystery", resource_id="x-1", now=NOW)
        await ledger.acquire(job_id="j1", provider="daytona", resource_id="sb-2", now=NOW)
        await ledger.release(provider="daytona", resource_id="sb-2", now=NOW)
        deleted: list[str] = []

        async def delete_sandbox(resource_id: str) -> None:
            deleted.append(resource_id)

        async def failing(resource_id: str) -> None:
            raise RuntimeError("token=secret")

        report = await recover_leases(
            ledger,
            {"daytona": delete_sandbox, "anchor": failing},
            acquired_before=NOW + timedelta(seconds=1),
            now=NOW,
        )
        assert report.released == ("daytona:sb-1",) and deleted == ["sb-1"]
        assert report.still_pending == ("anchor:as-1",)
        assert report.unknown_provider == ("mystery:x-1",)
        left = await ledger.open_leases(acquired_before=NOW + timedelta(seconds=1))
        assert {lease.resource_id for lease in left} == {"as-1", "x-1"}

        stale = await ledger.interrupt_stale_jobs(
            stale_before=NOW + timedelta(minutes=5), now=NOW + timedelta(minutes=10)
        )
        assert stale == ["j1"]
        job = await ledger.get_job("j1")
        assert job is not None and job.state == "failed" and job.error_type == "interrupted"
        await client.close()

    asyncio.run(scenario())


def test_offline_budget_and_transition_errors() -> None:
    import httpx

    def reply(*statements: tuple[str, object]) -> httpx.Response:
        return httpx.Response(
            200, json={"result": [{"status": s, "result": r} for s, r in statements]}
        )

    responses = iter(
        [
            reply(
                ("OK", None),
                ("OK", None),
                ("OK", []),
                ("OK", []),
                ("OK", {"spent_usd_cents": 120, "budget_usd_cents": 100}),
                ("OK", None),
            ),
            reply(
                ("ERR", "The query was not executed due to a failed transaction"),
                ("ERR", "An error occurred: illegal_transition"),
            ),
        ]
    )
    client = SurrealHttpClient(
        url="http://127.0.0.1:8001",
        namespace="n",
        database="d",
        user="u",
        password="p",
        transport=httpx.MockTransport(lambda request: next(responses)),
    )
    ledger = SurrealJobLedger(client)

    async def scenario() -> None:
        with pytest.raises(BudgetExceededError):
            await ledger.record_cost(
                "j1", entry_id="c1", provider="daytona", units=1, usd_cents=120, now=NOW
            )
        with pytest.raises(JobTransitionError, match="illegal_transition"):
            await ledger.transition("j1", "succeeded", now=NOW)

    asyncio.run(scenario())
