"""Evidence retention for the local write-once artifact store. Dry-run by default.

Deletes only `art-<32 hex>.artifact` files and abandoned `.pending-*` temp files directly
inside the root, older than the retention window, and never an artifact a caller marks as
protected (e.g. evidence cited by an open finding or pending approval). Symlinks and
anything else are left alone.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

_ARTIFACT: Final = re.compile(r"^(art-[0-9a-f]{32})\.artifact$")
_PENDING: Final = re.compile(r"^\.pending-[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class RetentionPlan:
    expired: tuple[str, ...]
    protected_kept: tuple[str, ...]
    abandoned_temp: tuple[str, ...]
    applied: bool


def sweep_artifacts(
    root: Path,
    *,
    retention_days: int,
    now: datetime,
    protected_ids: Iterable[str] = (),
    apply: bool = False,
) -> RetentionPlan:
    if retention_days < 1:
        raise ValueError("retention must be at least one day")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact root must be an existing real directory")
    cutoff = (now - timedelta(days=retention_days)).timestamp()
    temp_cutoff = (now - timedelta(hours=1)).timestamp()
    protected = set(protected_ids)
    expired: list[Path] = []
    kept: list[str] = []
    temps: list[Path] = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        modified = path.stat().st_mtime
        match = _ARTIFACT.fullmatch(path.name)
        if match is not None and modified < cutoff:
            if match.group(1) in protected:
                kept.append(match.group(1))
            else:
                expired.append(path)
        elif _PENDING.fullmatch(path.name) and modified < temp_cutoff:
            temps.append(path)
    if apply:
        for path in (*expired, *temps):
            path.unlink(missing_ok=True)
    return RetentionPlan(
        expired=tuple(sorted(p.name.removesuffix(".artifact") for p in expired)),
        protected_kept=tuple(sorted(kept)),
        abandoned_temp=tuple(sorted(p.name for p in temps)),
        applied=apply,
    )
