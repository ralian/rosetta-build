"""Make-style compiler depfile parsing (GCC/Clang ``-MD -MF``)."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "DepfileError",
    "depfile_for_object",
    "parse_depfile",
    "parse_depfile_text",
]


class DepfileError(ValueError):
    """Raised when a depfile cannot be parsed."""


def depfile_for_object(object_output: Path) -> Path:
    """Sidecar ``.d`` path for an object file (``foo.o`` → ``foo.d``)."""
    return object_output.with_suffix(".d")


def parse_depfile(path: Path) -> tuple[Path, ...]:
    """Parse a make depfile and return prerequisite paths."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DepfileError(f"cannot read depfile {path}: {exc}") from exc
    return parse_depfile_text(text)


def parse_depfile_text(text: str) -> tuple[Path, ...]:
    """Parse make-style dependency rules; return unique prerequisite paths.

    The rule separator is a colon at the end of a filename. Colons inside a
    path, including Windows drive letters, stay part of that path. Escape
    rules match Ninja's GCC/Clang depfile lexer; see ``docs/depfile.md``.
    """
    collapsed = _collapse_continuations(text)
    prereqs: list[Path] = []
    seen: set[Path] = set()
    for line in collapsed.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        deps = _prerequisite_tokens(line)
        if deps is None:
            raise DepfileError(f"depfile line missing ':': {line.strip()!r}")
        for token in deps:
            path = Path(token)
            if path not in seen:
                seen.add(path)
                prereqs.append(path)
    return tuple(prereqs)


def _collapse_continuations(text: str) -> str:
    lines: list[str] = []
    pending = ""
    for raw in text.splitlines():
        if raw.endswith("\\"):
            pending += raw[:-1]
            continue
        lines.append(pending + raw)
        pending = ""
    if pending:
        lines.append(pending)
    return "\n".join(lines)


def _prerequisite_tokens(line: str) -> list[str] | None:
    """Return prerequisite filenames, or None when the line has no rule colon."""
    prereqs: list[str] = []
    saw_separator = False
    index = 0
    length = len(line)
    while index < length:
        while index < length and line[index].isspace():
            index += 1
        if index >= length:
            break
        token, index, comment = _lex_filename(line, index)
        if token.endswith(":"):
            token = token[:-1]
            if not saw_separator:
                saw_separator = True
                token = ""
        if token and saw_separator:
            prereqs.append(token)
        if comment:
            break
    if not saw_separator:
        return None
    return prereqs


def _lex_filename(line: str, index: int) -> tuple[str, int, bool]:
    """Read one filename. Return its text, the next index, and whether a comment follows."""
    parts: list[str] = []
    length = len(line)
    while index < length:
        char = line[index]
        if char.isspace():
            break
        if char == "#":
            return "".join(parts), index, True
        if char == "\\":
            start = index
            while index < length and line[index] == "\\":
                index += 1
            count = index - start
            if index >= length:
                parts.append("\\" * count)
                break
            nxt = line[index]
            if nxt == " ":
                if count % 2 == 1:
                    parts.append("\\" * (count // 2))
                    parts.append(" ")
                    index += 1
                    continue
                parts.append("\\" * count)
                break
            if nxt == "#":
                parts.append("\\" * (count - 1))
                parts.append("#")
                index += 1
                continue
            if nxt == ":":
                rest = index + 1
                if rest >= length or line[rest].isspace():
                    parts.append("\\" * count)
                    parts.append(":")
                    return "".join(parts), rest, False
                parts.append("\\" * (count - 1))
                parts.append(":")
                index += 1
                continue
            parts.append("\\" * count)
            continue
        if char == "$" and index + 1 < length and line[index + 1] == "$":
            parts.append("$")
            index += 2
            continue
        parts.append(char)
        index += 1
    return "".join(parts), index, False
