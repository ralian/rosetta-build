"""Detect compilers that are on PATH and read their versions."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rosetta_build.compilers import _COMPILER_REGISTRY, get_compiler
from rosetta_build.language import CompilerFamily, Language

__all__ = [
    "CompilerDetection",
    "detect_compiler",
    "detect_compilers",
    "parse_compiler_version",
]

_PROBE_TIMEOUT_SECONDS = 10
_DOTTED_VERSION = r"\d+(?:\.\d+)+"


@dataclass(frozen=True, slots=True)
class CompilerDetection:
    family: CompilerFamily
    language: Language
    executable: str
    path: Path | None
    version: str | None


def detect_compiler(family: CompilerFamily, language: Language) -> CompilerDetection:
    """Locate one registered compiler and, when present, its version."""
    return _detect(family, language, {})


def detect_compilers() -> tuple[CompilerDetection, ...]:
    """Locate every registered compiler, probing each executable once."""
    probed: dict[str, str | None] = {}
    return tuple(
        _detect(family, language, probed) for family, language in _COMPILER_REGISTRY
    )


def parse_compiler_version(family: CompilerFamily, text: str) -> str | None:
    """Extract a dotted version from probe output, or None if it is not there."""
    if family in {CompilerFamily.GCC, CompilerFamily.GCCRS}:
        return _parse_gcc_version(text)
    if family is CompilerFamily.CLANG:
        return _search(rf"clang version\s+({_DOTTED_VERSION})", text)
    if family is CompilerFamily.RUSTC:
        return _search(rf"rustc\s+({_DOTTED_VERSION})", text)
    if family is CompilerFamily.MSVC:
        return _search(rf"Version\s+({_DOTTED_VERSION})", text)
    return None


def _detect(
    family: CompilerFamily,
    language: Language,
    probed: dict[str, str | None],
) -> CompilerDetection:
    executable = get_compiler(family, language).executable_name
    located = shutil.which(executable)
    if located is None:
        return CompilerDetection(
            family=family,
            language=language,
            executable=executable,
            path=None,
            version=None,
        )
    path = Path(located)
    key = os.path.normcase(str(path.resolve()))
    if key not in probed:
        probed[key] = _probe_version(family, path)
    return CompilerDetection(
        family=family,
        language=language,
        executable=executable,
        path=path,
        version=probed[key],
    )


def _parse_gcc_version(text: str) -> str | None:
    lines = text.strip().splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    if re.fullmatch(_DOTTED_VERSION, first):
        return first
    # Banner form is "... ) 13.2.0". The version after ")" skips tokens such as x86_64.
    match = re.search(rf"\)\s*({_DOTTED_VERSION})\s*$", first)
    if match is None:
        return None
    return match.group(1)


def _search(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(1)


def _probe_version(family: CompilerFamily, path: Path) -> str | None:
    if family in {CompilerFamily.GCC, CompilerFamily.GCCRS}:
        for args in (("-dumpfullversion",), ("-dumpversion",)):
            result = _run(path, args)
            if result is None or result[0] != 0:
                continue
            version = parse_compiler_version(family, result[1])
            if version is not None:
                return version
        return None
    if family is CompilerFamily.CLANG or family is CompilerFamily.RUSTC:
        result = _run(path, ("--version",))
        if result is None or result[0] != 0:
            return None
        return parse_compiler_version(family, result[1])
    if family is CompilerFamily.MSVC:
        # cl has no --version; with no inputs it prints a banner and exits non-zero.
        result = _run(path, ())
        if result is None:
            return None
        return parse_compiler_version(family, result[1])
    return None


def _run(executable: Path, args: tuple[str, ...]) -> tuple[int, str] | None:
    try:
        completed = subprocess.run(
            [str(executable), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    returncode = completed.returncode
    if returncode is None:
        return None
    text = _decode_output(completed.stdout) + _decode_output(completed.stderr)
    return returncode, text


def _decode_output(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    sample = data[:200]
    # A pipe from cl.exe is often UTF-16-LE without a BOM.
    if sample.count(b"\x00") > len(sample) // 4:
        return data.decode("utf-16-le", errors="replace")
    return data.decode(errors="replace")
