"""Line-level change signals. Regex heuristics that point the planner at risk; never verdicts."""

import re
from dataclasses import dataclass
from typing import Final, Literal

from gauntlet.contracts import ChangeSignal, SignalKind, SourceRef

from .diff_parser import Hunk

MAX_SIGNALS_PER_FILE: Final = 20
_EXCERPT_CHARS: Final = 300

_AUTH_TERM = re.compile(
    r"owner_?id|actor_?id|user_?id|authori[sz]e|permission|is_?admin|\brole\b|forbidden"
    r"|unauthori[sz]ed|\b40[13]\b|can_?access|has_?access",
    re.IGNORECASE,
)
_GUARD = re.compile(r"\b(if|throw|raise|assert|require|deny|return)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _LineRule:
    kind: SignalKind
    side: Literal["added", "removed"]
    pattern: re.Pattern[str]


_LINE_RULES: Final[tuple[_LineRule, ...]] = (
    _LineRule(
        "side_effect_call",
        "added",
        re.compile(
            r"\b\w*(refund|charge|transfer|payout|withdraw|send_?e?mail|delete|ledger)\w*\s*[.(]",
            re.IGNORECASE,
        ),
    ),
    _LineRule(
        "tool_definition",
        "added",
        re.compile(r"\b(define_?tool|create_?tool|input_?schema|tool_choice)\b|\btool\s*\(", re.I),
    ),
    _LineRule(
        "layout_positioning",
        "added",
        re.compile(
            r"position['\"]?\s*:\s*['\"]?(fixed|sticky)|z-?index|\bz-\d+\b"
            r"|\b(fixed|sticky)\b[^\n]*\b(top|bottom|left|right|inset)-",
            re.IGNORECASE,
        ),
    ),
)


def _is_auth_guard(line: str) -> bool:
    return bool(_AUTH_TERM.search(line) and _GUARD.search(line))


def _signal(kind: SignalKind, path: str, sha: str, line_no: int, text: str) -> ChangeSignal:
    return ChangeSignal(
        kind=kind,
        source_ref=SourceRef(path=path, sha=sha, start_line=line_no, end_line=line_no),
        excerpt=text.strip()[:_EXCERPT_CHARS],
    )


def _merge_adjacent(signals: list[ChangeSignal]) -> list[ChangeSignal]:
    """Consecutive lines of the same kind (e.g. `if (...)` + `throw`) become one ranged signal."""
    merged: list[ChangeSignal] = []
    for signal in signals:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev.kind == signal.kind
            and prev.source_ref.sha == signal.source_ref.sha
            and prev.source_ref.end_line + 1 == signal.source_ref.start_line
        ):
            ref = prev.source_ref.model_copy(update={"end_line": signal.source_ref.end_line})
            merged[-1] = prev.model_copy(update={"source_ref": ref})
        else:
            merged.append(signal)
    return merged


def extract_signals(
    path: str, hunks: tuple[Hunk, ...], base_sha: str, head_sha: str
) -> tuple[ChangeSignal, ...]:
    signals: list[ChangeSignal] = []
    for hunk in hunks:
        for offset, line in enumerate(hunk.removed):
            if _is_auth_guard(line):
                signals.append(
                    _signal("auth_check_removed", path, base_sha, hunk.old_start + offset, line)
                )
        for offset, line in enumerate(hunk.added):
            line_no = hunk.new_start + offset
            if _is_auth_guard(line):
                signals.append(_signal("auth_check_added", path, head_sha, line_no, line))
            signals.extend(
                _signal(rule.kind, path, head_sha, line_no, line)
                for rule in _LINE_RULES
                if rule.side == "added" and rule.pattern.search(line)
            )
    return tuple(_merge_adjacent(signals)[:MAX_SIGNALS_PER_FILE])
