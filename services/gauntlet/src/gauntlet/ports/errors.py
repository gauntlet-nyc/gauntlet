"""Typed errors that every port implementation (real or fake) raises instead of bare exceptions."""


class PortError(Exception):
    """Base for adapter-boundary failures. Never carries secrets in its message."""


class EnvironmentUnavailableError(PortError):
    """A sandbox, preview or browser session could not be provisioned or reached."""


class UnknownOracleError(PortError):
    """An oracle ID is not in the trusted registry; the plan must be rejected, not executed."""


class EventSequenceConflictError(PortError):
    """An appended RunEvent's sequence is not exactly the next one for its run."""


class DuplicateIdempotencyKeyError(PortError):
    """A RunEvent reused an idempotency key already recorded for its run."""
