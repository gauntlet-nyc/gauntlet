"""Which repository paths analysis may read. Denied paths never reach the planner or a model."""

import re
from typing import Final

_DENIED: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
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
)


def is_path_allowed(path: str) -> bool:
    if not path or path.startswith(("/", "~")) or "\\" in path:
        return False
    if any(part in ("", ".", "..") for part in path.split("/")):
        return False
    return not any(pattern.search(path) for pattern in _DENIED)
