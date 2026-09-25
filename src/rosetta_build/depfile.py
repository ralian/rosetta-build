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

    Supports line continuations (``\\``) and multiple ``target: deps`` rules.
    Target names are ignored; only prerequisites are returned.
    """
    collapsed = _collapse_continuations(text)
    prereqs: list[Path] = []
    seen: set[Path] = set()
    for line in collapsed.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise DepfileError(f"depfile line missing ':': {stripped!r}")
        _, _, right = stripped.partition(":")
        for token in _split_make_tokens(right):
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


def _split_make_tokens(fragment: str) -> list[str]:
    """Split make prerequisites on unescaped whitespace."""
    tokens: list[str] = []
    current: list[str] = []
    escaped = False
    for char in fragment:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char.isspace():
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    if current:
        tokens.append("".join(current))
    return tokens
