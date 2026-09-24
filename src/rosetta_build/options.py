"""Portable compile/link settings and map-or-raise errors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from rosetta_build.language import CompilerFamily, Language

__all__ = [
    "CStandard",
    "CompileSettings",
    "CxxStandard",
    "LanguageStandard",
    "LinkSettings",
    "RustEdition",
    "UnsupportedCompileOption",
    "UnsupportedLinkOption",
    "UnsupportedOption",
]


class CStandard(StrEnum):
    C11 = "c11"
    C17 = "c17"
    C23 = "c23"


class CxxStandard(StrEnum):
    CXX17 = "cxx17"
    CXX20 = "cxx20"
    CXX23 = "cxx23"


class RustEdition(StrEnum):
    E2018 = "2018"
    E2021 = "2021"
    E2024 = "2024"


LanguageStandard = CStandard | CxxStandard | RustEdition


@dataclass(frozen=True, slots=True)
class CompileSettings:
    standard: LanguageStandard | None = None
    defines: Mapping[str, str | bool | int] = field(default_factory=dict)
    include_dirs: Sequence[Path] = ()
    raw_flags: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class LinkSettings:
    raw_flags: Sequence[str] = ()


class UnsupportedOption(Exception):
    """Raised when an adapter cannot honor a portable option."""

    def __init__(
        self,
        *,
        family: CompilerFamily,
        language: Language,
        key: str,
        detail: str | None = None,
    ) -> None:
        self.family = family
        self.language = language
        self.key = key
        message = f"{family.value}/{language.value} does not support {key}"
        if detail is not None:
            message = f"{message}: {detail}"
        super().__init__(message)


class UnsupportedCompileOption(UnsupportedOption):
    """Raised for unsupported portable compile settings."""


class UnsupportedLinkOption(UnsupportedOption):
    """Raised for unsupported portable link settings."""
