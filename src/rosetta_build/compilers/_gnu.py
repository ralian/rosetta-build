"""Shared helpers for GNU-style (GCC/Clang) C and C++ adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from rosetta_build.compiler import CompileRequest
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import (
    CompileSettings,
    CStandard,
    CxxStandard,
    LanguageStandard,
    LinkSettings,
    UnsupportedCompileOption,
)

__all__ = [
    "gnu_c_standard_flag",
    "gnu_compile_flags",
    "gnu_cxx_standard_flag",
    "gnu_define_flags",
    "gnu_include_flags",
    "gnu_link_flags",
    "gnu_module_flags",
]


_C_STANDARDS: Mapping[CStandard, str] = {
    CStandard.C11: "-std=c11",
    CStandard.C17: "-std=c17",
    CStandard.C23: "-std=c23",
}

_CXX_STANDARDS: Mapping[CxxStandard, str] = {
    CxxStandard.CXX17: "-std=c++17",
    CxxStandard.CXX20: "-std=c++20",
    CxxStandard.CXX23: "-std=c++23",
}


def gnu_c_standard_flag(
    standard: LanguageStandard | None,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    if standard is None:
        return []
    if not isinstance(standard, CStandard):
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="standard",
            detail=f"expected a CStandard, got {type(standard).__name__}",
        )
    return [_C_STANDARDS[standard]]


def gnu_cxx_standard_flag(
    standard: LanguageStandard | None,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    if standard is None:
        return []
    if not isinstance(standard, CxxStandard):
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="standard",
            detail=f"expected a CxxStandard, got {type(standard).__name__}",
        )
    return [_CXX_STANDARDS[standard]]


def gnu_define_flags(defines: Mapping[str, str | bool | int]) -> list[str]:
    flags: list[str] = []
    for name, value in defines.items():
        if value is True:
            flags.append(f"-D{name}")
        elif value is False:
            flags.append(f"-U{name}")
        else:
            flags.append(f"-D{name}={value}")
    return flags


def gnu_include_flags(include_dirs: Sequence[Path]) -> list[str]:
    return [f"-I{path}" for path in include_dirs]


def gnu_compile_flags(
    settings: CompileSettings,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    flags: list[str] = []
    if language is Language.C:
        flags.extend(
            gnu_c_standard_flag(settings.standard, family=family, language=language)
        )
    elif language is Language.CXX:
        flags.extend(
            gnu_cxx_standard_flag(settings.standard, family=family, language=language)
        )
    else:
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="standard",
            detail="GNU C/C++ helpers do not map this language",
        )
    flags.extend(gnu_define_flags(settings.defines))
    flags.extend(gnu_include_flags(settings.include_dirs))
    flags.extend(settings.raw_flags)
    return flags


def gnu_link_flags(settings: LinkSettings) -> list[str]:
    return list(settings.raw_flags)


def gnu_module_flags(
    request: CompileRequest,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    """Map portable module fields to GCC/Clang-style module argv fragments."""
    if request.bmi_output is not None and request.module_name is None:
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="bmi_output",
            detail="module_name is required when emitting a BMI",
        )

    flags: list[str] = []
    for bmi in request.bmi_inputs:
        flags.append(f"-fmodule-file={bmi.module}={bmi.path}")
    if request.bmi_output is not None:
        flags.append(f"-fmodule-output={request.bmi_output}")
    return flags
