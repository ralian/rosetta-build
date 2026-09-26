"""Shared pytest helpers."""

from __future__ import annotations

import pytest

from rosetta_build.language import CompilerFamily, Language
from rosetta_build.toolchain import detect_compiler, gcc_supports_fmodules


def requires_compiler(
    family: CompilerFamily, language: Language
) -> pytest.MarkDecorator:
    found = detect_compiler(family, language)
    return pytest.mark.skipif(
        found.path is None,
        reason=f"{found.executable} not on PATH",
    )


def requires_gcc_fmodules() -> pytest.MarkDecorator:
    found = detect_compiler(CompilerFamily.GCC, Language.CXX)
    if found.path is None:
        reason = f"{found.executable} not on PATH"
        missing = True
    elif gcc_supports_fmodules(found):
        reason = "g++ supports -fmodules"
        missing = False
    else:
        version = found.version or "unknown version"
        reason = f"g++ {version} does not support -fmodules"
        missing = True
    return pytest.mark.skipif(missing, reason=reason)
