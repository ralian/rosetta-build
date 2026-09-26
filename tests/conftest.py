"""Shared pytest helpers."""

from __future__ import annotations

import pytest

from rosetta_build.language import CompilerFamily, Language
from rosetta_build.toolchain import detect_compiler


def requires_compiler(
    family: CompilerFamily, language: Language
) -> pytest.MarkDecorator:
    found = detect_compiler(family, language)
    return pytest.mark.skipif(
        found.path is None,
        reason=f"{found.executable} not on PATH",
    )
