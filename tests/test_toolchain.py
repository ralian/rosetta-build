"""Compiler presence detection and version parsing."""

from __future__ import annotations

import re

import pytest

from rosetta_build.compilers import _COMPILER_REGISTRY, get_compiler
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.toolchain import (
    detect_compiler,
    detect_compilers,
    parse_compiler_version,
)

_VERSION = re.compile(r"^\d+(?:\.\d+)+$")


@pytest.mark.parametrize(
    ("family", "text", "expected"),
    [
        (CompilerFamily.GCC, "14.2.0\n", "14.2.0"),
        (
            CompilerFamily.GCC,
            "g++ (GCC) 14.2.0\n",
            "14.2.0",
        ),
        (
            CompilerFamily.GCC,
            "g++.exe (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r8) 13.2.0\n",
            "13.2.0",
        ),
        (CompilerFamily.GCCRS, "gccrs (GCC) 14.0.0\n", "14.0.0"),
        (
            CompilerFamily.CLANG,
            "clang version 18.1.8\nTarget: x86_64-pc-windows-msvc\n",
            "18.1.8",
        ),
        (
            CompilerFamily.CLANG,
            "Apple clang version 15.0.0 (clang-1500.3.9.4)\n",
            "15.0.0",
        ),
        (
            CompilerFamily.RUSTC,
            "rustc 1.81.0 (eeb90cda1 2024-09-04)\n",
            "1.81.0",
        ),
        (
            CompilerFamily.MSVC,
            "Microsoft (R) C/C++ Optimizing Compiler Version 19.44.35207.1 for x64\n",
            "19.44.35207.1",
        ),
    ],
)
def test_parse_compiler_version(
    family: CompilerFamily, text: str, expected: str
) -> None:
    assert parse_compiler_version(family, text) == expected


def test_parse_compiler_version_rejects_unrecognized_text() -> None:
    assert parse_compiler_version(CompilerFamily.GCC, "not a version") is None
    assert parse_compiler_version(CompilerFamily.MSVC, "") is None


def test_missing_executable_has_no_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rosetta_build.toolchain.shutil.which", lambda _name: None)
    found = detect_compiler(CompilerFamily.GCC, Language.CXX)
    assert found.executable == "g++"
    assert found.path is None
    assert found.version is None


def test_detect_compilers_covers_registry() -> None:
    found = detect_compilers()
    assert len(found) == len(_COMPILER_REGISTRY)
    seen = {(item.family, item.language) for item in found}
    assert seen == set(_COMPILER_REGISTRY)
    for item in found:
        compiler = get_compiler(item.family, item.language)
        assert item.executable == compiler.executable_name
        if item.path is None:
            assert item.version is None
            continue
        assert item.version is not None
        assert _VERSION.fullmatch(item.version)
