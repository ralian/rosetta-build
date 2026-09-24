"""Shared helpers for Rust (rustc / gccrs) adapters."""

from __future__ import annotations

from collections.abc import Mapping

from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import (
    CompileSettings,
    LanguageStandard,
    LinkSettings,
    RustEdition,
    UnsupportedCompileOption,
)

__all__ = [
    "reject_c_style_settings",
    "rust_compile_flags",
    "rust_edition_flag",
    "rust_link_flags",
]


_EDITIONS: Mapping[RustEdition, str] = {
    RustEdition.E2018: "2018",
    RustEdition.E2021: "2021",
    RustEdition.E2024: "2024",
}


def rust_edition_flag(
    standard: LanguageStandard | None,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    if standard is None:
        return []
    if not isinstance(standard, RustEdition):
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="standard",
            detail=f"expected a RustEdition, got {type(standard).__name__}",
        )
    return [f"--edition={_EDITIONS[standard]}"]


def reject_c_style_settings(
    settings: CompileSettings,
    *,
    family: CompilerFamily,
    language: Language,
) -> None:
    if settings.defines:
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="defines",
            detail="Rust compilers do not accept C-style preprocessor defines",
        )
    if settings.include_dirs:
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="include_dirs",
            detail="Rust compilers do not accept C-style include directories",
        )


def rust_compile_flags(
    settings: CompileSettings,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    reject_c_style_settings(settings, family=family, language=language)
    flags = rust_edition_flag(settings.standard, family=family, language=language)
    flags.extend(settings.raw_flags)
    return flags


def rust_link_flags(settings: LinkSettings) -> list[str]:
    return list(settings.raw_flags)
