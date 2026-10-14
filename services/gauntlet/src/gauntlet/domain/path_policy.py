"""Which repository paths analysis may read and which a fix may write. Stdlib only."""

import re
from typing import Final


def _compile(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


_READ_DENIED: Final = _compile(
    r"(^|/)\.env($|\.)",
    r"(^|/)\.git(/|$)",
    r"(^|/)bench/private(/|$)",
    r"(^|/)bench/heldout(/|$)",
    r"(^|/)node_modules(/|$)",
    r"(^|/)\.venv(/|$)",
    r"(^|/)artifacts(/|$)",
    r"\.(pem|key|p12|pfx|keystore)$",
    r"(^|/)id_(rsa|ed25519|ecdsa)(\.pub)?$",
    r"(^|/)(secrets?|credentials?)(/|\.|$)",
)

_WRITE_DENIED: Final = _compile(
    r"(^|/)(tests?|__tests__|e2e|spec|fixtures)(/|$)",
    r"\.(test|spec)\.[cm]?[jt]sx?$",
    r"(^|/)test_[^/]*\.py$|_test\.py$",
    r"(^|/)(verification|oracles?)(/|$)",
    r"(^|/)bench(/|$)",
    r"(^|/)\.github(/|$)",
    r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|uv\.lock|poetry\.lock)$",
)


def _is_safe_relative(path: str) -> bool:
    if not path or path.startswith(("/", "~")) or "\\" in path:
        return False
    return not any(part in ("", ".", "..") for part in path.split("/"))


def is_path_allowed(path: str) -> bool:
    """Readable by analysis and visible to models."""
    return _is_safe_relative(path) and not any(p.search(path) for p in _READ_DENIED)


def is_patch_path_allowed(path: str) -> bool:
    """Writable by an approved fix. Trusted tests, oracles, benchmark, CI and locks never are."""
    return is_path_allowed(path) and not any(p.search(path) for p in _WRITE_DENIED)
