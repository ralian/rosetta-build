"""Language and compiler-family identity."""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "CompilerFamily",
    "Language",
]


class Language(StrEnum):
    C = "c"
    CXX = "cxx"
    RUST = "rust"


class CompilerFamily(StrEnum):
    GCC = "gcc"
    CLANG = "clang"
    MSVC = "msvc"
    RUSTC = "rustc"
    GCCRS = "gccrs"
