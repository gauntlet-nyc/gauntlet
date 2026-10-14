"""Pure parser for `git diff --unified=0` output. No I/O; unparseable input becomes a gap."""

import re
from dataclasses import dataclass, field
from enum import StrEnum

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_HEADER = "diff --git "


class FileStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added: tuple[str, ...]
    removed: tuple[str, ...]


@dataclass(frozen=True)
class FileChange:
    path: str
    old_path: str | None
    status: FileStatus
    binary: bool
    hunks: tuple[Hunk, ...]


@dataclass(frozen=True)
class ParsedDiff:
    files: tuple[FileChange, ...]
    unparsed_sections: tuple[str, ...]
    """Headers of sections that could not be parsed safely (e.g. quoted paths)."""


@dataclass
class _FileBuilder:
    header: str
    old_path: str | None = None
    new_path: str | None = None
    status: FileStatus = FileStatus.MODIFIED
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    unsafe: bool = False


def _strip_side(raw: str, prefix: str) -> str | None:
    value = raw.rstrip("\t")
    if value == "/dev/null":
        return None
    if value.startswith('"'):
        raise ValueError("quoted path")
    if not value.startswith(prefix):
        raise ValueError("unexpected path prefix")
    return value[len(prefix) :]


def _finish(builder: _FileBuilder, files: list[FileChange], unparsed: list[str]) -> None:
    path = builder.new_path or builder.old_path
    if builder.unsafe or path is None:
        unparsed.append(builder.header)
        return
    files.append(
        FileChange(
            path=path,
            old_path=builder.old_path if builder.status is FileStatus.RENAMED else None,
            status=builder.status,
            binary=builder.binary,
            hunks=tuple(builder.hunks),
        )
    )


def _paths_from_header(header: str) -> tuple[str, str] | None:
    body = header[len(_DIFF_HEADER) :]
    if body.startswith('"') or " b/" not in body or not body.startswith("a/"):
        return None
    old, _, new = body.partition(" b/")
    return old[2:], new


def parse_unified_diff(text: str) -> ParsedDiff:
    files: list[FileChange] = []
    unparsed: list[str] = []
    builder: _FileBuilder | None = None
    added: list[str] = []
    removed: list[str] = []
    header: tuple[int, int, int, int] | None = None

    def close_hunk() -> None:
        nonlocal header
        if builder is not None and header is not None:
            builder.hunks.append(Hunk(*header, added=tuple(added), removed=tuple(removed)))
        header = None
        added.clear()
        removed.clear()

    for line in text.splitlines():
        if line.startswith(_DIFF_HEADER):
            close_hunk()
            if builder is not None:
                _finish(builder, files, unparsed)
            builder = _FileBuilder(header=line)
            paths = _paths_from_header(line)
            if paths is None:
                builder.unsafe = True
            else:
                builder.old_path, builder.new_path = paths
            continue
        if builder is None:
            continue
        if line.startswith("@@"):
            close_hunk()
            match = _HUNK_HEADER.match(line)
            if match is None:
                builder.unsafe = True
                continue
            o_start, o_count, n_start, n_count = match.groups()
            header = (
                int(o_start),
                1 if o_count is None else int(o_count),
                int(n_start),
                1 if n_count is None else int(n_count),
            )
        elif header is not None and line.startswith("+"):
            added.append(line[1:])
        elif header is not None and line.startswith("-"):
            removed.append(line[1:])
        elif header is not None and line.startswith("\\"):
            continue
        elif line.startswith("new file mode"):
            builder.status = FileStatus.ADDED
        elif line.startswith("deleted file mode"):
            builder.status = FileStatus.DELETED
        elif line.startswith("rename from "):
            builder.status = FileStatus.RENAMED
        elif line.startswith("Binary files ") or line == "GIT binary patch":
            builder.binary = True
        elif line.startswith("--- "):
            try:
                builder.old_path = _strip_side(line[4:], "a/")
            except ValueError:
                builder.unsafe = True
        elif line.startswith("+++ "):
            try:
                builder.new_path = _strip_side(line[4:], "b/")
            except ValueError:
                builder.unsafe = True

    close_hunk()
    if builder is not None:
        _finish(builder, files, unparsed)
    return ParsedDiff(files=tuple(files), unparsed_sections=tuple(unparsed))
