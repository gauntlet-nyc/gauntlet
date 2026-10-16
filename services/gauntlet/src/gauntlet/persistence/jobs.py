"""Durable job, cost and resource-lease ledger (SurrealDB core). P10 hardening.

- Jobs move only along `queued -> running -> succeeded|failed|cancelled` (or
  `queued -> cancelled`); transitions are checked inside a transaction.
- Cost entries are append-only and roll up into the job; crossing the job budget records
  the cost (it was already spent) and raises `BudgetExceededError` so the caller stops.
- Every provider resource (sandbox, browser session, snapshot) is leased before use and
  released after cleanup. After a crash, `open_leases` lists what may have leaked and
  `recover_leases` retries the provider cleanup; `interrupt_stale_jobs` fails jobs whose
  worker stopped heartbeating. Nothing is retried that is not idempotent cleanup.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from gauntlet.ports.errors import EnvironmentUnavailableError, PortError

from .surreal_client import JsonValue, SurrealHttpClient, SurrealQueryError, rows

JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
_STATES: Final[tuple[JobState, ...]] = ("queued", "running", "succeeded", "failed", "cancelled")
_ALLOWED: Final[dict[str, frozenset[str]]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "cancelled"}),
}

JOBS_SCHEMA: Final = """
DEFINE TABLE IF NOT EXISTS job SCHEMALESS;
DEFINE INDEX IF NOT EXISTS job_state ON job FIELDS state, heartbeat_at;
DEFINE TABLE IF NOT EXISTS cost_entry SCHEMALESS;
DEFINE INDEX IF NOT EXISTS cost_entry_job ON cost_entry FIELDS job_id;
DEFINE TABLE IF NOT EXISTS resource_lease SCHEMALESS;
DEFINE INDEX IF NOT EXISTS resource_lease_open ON resource_lease FIELDS released, acquired_at;
"""


class JobTransitionError(PortError):
    pass


class BudgetExceededError(PortError):
    def __init__(self, job_id: str, spent: int, budget: int) -> None:
        super().__init__(f"job {job_id} spent {spent} of {budget} US cents")
        self.spent = spent
        self.budget = budget


@dataclass(frozen=True)
class Job:
    job_id: str
    run_id: str
    kind: str
    state: JobState
    budget_usd_cents: int
    spent_usd_cents: int
    error_type: str | None


@dataclass(frozen=True)
class Lease:
    provider: str
    resource_id: str
    job_id: str
    acquired_at: str


@dataclass(frozen=True)
class RecoveryReport:
    released: tuple[str, ...]
    still_pending: tuple[str, ...]
    unknown_provider: tuple[str, ...]


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.isoformat()


class SurrealJobLedger:
    def __init__(self, client: SurrealHttpClient) -> None:
        self._client = client

    async def ensure_schema(self) -> None:
        await self._client.query(JOBS_SCHEMA)

    async def create_job(
        self, *, job_id: str, run_id: str, kind: str, budget_usd_cents: int, now: datetime
    ) -> None:
        if budget_usd_cents < 0:
            raise ValueError("budget must be non-negative")
        try:
            await self._client.query(
                "CREATE type::thing('job', $job_id) CONTENT { job_id: $job_id, run_id: $run_id, "
                "kind: $kind, state: 'queued', budget_usd_cents: $budget, spent_usd_cents: 0, "
                "error_type: NONE, created_at: <datetime>$now, heartbeat_at: <datetime>$now };",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "kind": kind,
                    "budget": budget_usd_cents,
                    "now": _iso(now),
                },
            )
        except SurrealQueryError as exc:
            if "already exists" in exc.detail:
                raise JobTransitionError(f"job {job_id} already exists") from None
            raise

    async def transition(
        self, job_id: str, to: JobState, *, now: datetime, error_type: str | None = None
    ) -> None:
        allowed_from = [state for state, targets in _ALLOWED.items() if to in targets]
        try:
            await self._client.query(
                """
                BEGIN TRANSACTION;
                LET $job = (SELECT state FROM type::thing('job', $job_id))[0];
                IF $job = NONE { THROW "unknown_job" };
                IF $job.state NOTINSIDE $from { THROW "illegal_transition" };
                UPDATE type::thing('job', $job_id) SET state = $to, error_type = $error,
                    heartbeat_at = <datetime>$now;
                COMMIT TRANSACTION;
                """,
                {
                    "job_id": job_id,
                    "to": to,
                    "from": list(allowed_from),
                    "error": error_type,
                    "now": _iso(now),
                },
            )
        except SurrealQueryError as exc:
            for reason in ("unknown_job", "illegal_transition"):
                if reason in exc.detail:
                    raise JobTransitionError(f"{reason}: {job_id} -> {to}") from None
            raise

    async def heartbeat(self, job_id: str, *, now: datetime) -> None:
        await self._client.query(
            "UPDATE type::thing('job', $job_id) SET heartbeat_at = <datetime>$now "
            "WHERE state = 'running';",
            {"job_id": job_id, "now": _iso(now)},
        )

    async def record_cost(
        self,
        job_id: str,
        *,
        entry_id: str,
        provider: str,
        units: float,
        usd_cents: int,
        now: datetime,
    ) -> int:
        """Append a cost entry; return total spent. Raise `BudgetExceededError` past budget."""
        if usd_cents < 0:
            raise ValueError("cost must be non-negative")
        try:
            result = await self._client.query(
                """
                BEGIN TRANSACTION;
                LET $job = (SELECT budget_usd_cents, spent_usd_cents
                            FROM type::thing('job', $job_id))[0];
                IF $job = NONE { THROW "unknown_job" };
                CREATE type::thing('cost_entry', $entry_id) CONTENT { job_id: $job_id,
                    provider: $provider, units: $units, usd_cents: $cents,
                    recorded_at: <datetime>$now };
                UPDATE type::thing('job', $job_id) SET spent_usd_cents += $cents;
                RETURN (SELECT spent_usd_cents, budget_usd_cents
                        FROM type::thing('job', $job_id))[0];
                COMMIT TRANSACTION;
                """,
                {
                    "job_id": job_id,
                    "entry_id": entry_id,
                    "provider": provider,
                    "units": float(units),
                    "cents": usd_cents,
                    "now": _iso(now),
                },
            )
        except SurrealQueryError as exc:
            if "unknown_job" in exc.detail:
                raise JobTransitionError(f"unknown_job: {job_id}") from None
            if "already exists" in exc.detail:
                raise JobTransitionError(f"cost entry {entry_id} already recorded") from None
            raise
        totals = next(
            (item.result for item in reversed(result) if isinstance(item.result, dict)), None
        )
        if not isinstance(totals, dict):
            raise EnvironmentUnavailableError("job totals were not returned")
        spent, budget = totals.get("spent_usd_cents"), totals.get("budget_usd_cents")
        if not isinstance(spent, int) or not isinstance(budget, int):
            raise EnvironmentUnavailableError("job totals are malformed")
        if spent > budget:
            raise BudgetExceededError(job_id, spent, budget)
        return spent

    async def get_job(self, job_id: str) -> Job | None:
        result = await self._client.query(
            "SELECT * FROM type::thing('job', $job_id);", {"job_id": job_id}
        )
        found = rows(result[0])
        return _job(found[0]) if found else None

    async def interrupt_stale_jobs(self, *, stale_before: datetime, now: datetime) -> list[str]:
        """Fail running jobs whose heartbeat is older than `stale_before` (crash recovery)."""
        result = await self._client.query(
            "UPDATE job SET state = 'failed', error_type = 'interrupted', "
            "heartbeat_at = <datetime>$now WHERE state = 'running' "
            "AND heartbeat_at < <datetime>$stale RETURN job_id;",
            {"stale": _iso(stale_before), "now": _iso(now)},
        )
        return sorted(str(row.get("job_id")) for row in rows(result[0]))

    async def acquire(self, *, job_id: str, provider: str, resource_id: str, now: datetime) -> None:
        await self._client.query(
            "UPSERT type::thing('resource_lease', [$provider, $resource]) CONTENT { "
            "job_id: $job_id, provider: $provider, resource_id: $resource, released: false, "
            "acquired_at: <datetime>$now };",
            {"job_id": job_id, "provider": provider, "resource": resource_id, "now": _iso(now)},
        )

    async def release(self, *, provider: str, resource_id: str, now: datetime) -> None:
        await self._client.query(
            "UPDATE type::thing('resource_lease', [$provider, $resource]) SET released = true, "
            "released_at = <datetime>$now;",
            {"provider": provider, "resource": resource_id, "now": _iso(now)},
        )

    async def open_leases(self, *, acquired_before: datetime) -> list[Lease]:
        result = await self._client.query(
            "SELECT job_id, provider, resource_id, <string>acquired_at AS acquired_at "
            "FROM resource_lease WHERE released = false AND acquired_at < <datetime>$before "
            "ORDER BY acquired_at ASC;",
            {"before": _iso(acquired_before)},
        )
        return [
            Lease(
                provider=str(row.get("provider")),
                resource_id=str(row.get("resource_id")),
                job_id=str(row.get("job_id")),
                acquired_at=str(row.get("acquired_at")),
            )
            for row in rows(result[0])
        ]


Cleaner = Callable[[str], Awaitable[None]]


async def recover_leases(
    ledger: SurrealJobLedger,
    cleaners: Mapping[str, Cleaner],
    *,
    acquired_before: datetime,
    now: datetime,
) -> RecoveryReport:
    """Retry idempotent provider cleanup (delete sandbox/session) for leaked resources."""
    released: list[str] = []
    pending: list[str] = []
    unknown: list[str] = []
    for lease in await ledger.open_leases(acquired_before=acquired_before):
        key = f"{lease.provider}:{lease.resource_id}"
        cleaner = cleaners.get(lease.provider)
        if cleaner is None:
            unknown.append(key)
            continue
        try:
            await cleaner(lease.resource_id)
        except Exception:  # noqa: BLE001 - provider errors may contain secrets; keep the ID only
            pending.append(key)
            continue
        await ledger.release(provider=lease.provider, resource_id=lease.resource_id, now=now)
        released.append(key)
    return RecoveryReport(tuple(released), tuple(pending), tuple(unknown))


def _job(row: Mapping[str, JsonValue]) -> Job:
    raw_state = row.get("state")
    state = next((item for item in _STATES if item == raw_state), None)
    if state is None:
        raise EnvironmentUnavailableError("stored job has an unknown state")
    budget, spent = row.get("budget_usd_cents"), row.get("spent_usd_cents")
    if not isinstance(budget, int) or not isinstance(spent, int):
        raise EnvironmentUnavailableError("stored job totals are malformed")
    error = row.get("error_type")
    return Job(
        job_id=str(row.get("job_id")),
        run_id=str(row.get("run_id")),
        kind=str(row.get("kind")),
        state=state,
        budget_usd_cents=budget,
        spent_usd_cents=spent,
        error_type=error if isinstance(error, str) else None,
    )
