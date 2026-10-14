"""Named domain errors. Raised when callers hand pure policies impossible evidence."""


class GauntletDomainError(Exception):
    """Base for errors raised by pure domain policy."""


class InvalidEvidenceError(GauntletDomainError, ValueError):
    """Evidence counts or flags are internally inconsistent (e.g. failures > attempts)."""
