"""Named use-case failures. Messages are safe to show to an authenticated operator."""


class ApplicationError(Exception):
    """Base for use-case level refusals."""


class TargetNotAuthorizedError(ApplicationError):
    """The target or fixture is not in the server-side registry; nothing may be planned or run."""


class StaleApprovalError(ApplicationError):
    """The reviewer approved a plan hash that is no longer the current plan."""


class ApprovalDeniedError(ApplicationError):
    """An execution request does not match a valid, unexpired, unspent approval."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons
