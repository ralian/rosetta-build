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
    "gcc_module_flags",
    "gcc_module_mapper_path",
    "gcc_module_mapper_text",
    "gcc_module_mappings",
    "gnu_c_standard_flag",
    "gnu_compile_flags",
    "gnu_cxx_standard_flag",
    "gnu_define_flags",
    "gnu_include_flags",
    "gnu_link_flags",
    "gnu_module_flags",
    "move_mingw_appended_exe",
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


def move_mingw_appended_exe(output: Path) -> None:
    """Move ``<output>.exe`` onto ``output`` when the MinGW driver appended it.

    MinGW ``gcc`` / ``g++`` add ``.exe`` to ``-o`` names that do not already end
    in ``.exe``. A fresh ``<output>.exe`` replaces a stale extensionless file
    left by an earlier link.
    """
    if output.name.endswith(".exe"):
        return
    written = output.with_name(f"{output.name}.exe")
    if written.is_file():
        written.replace(output)


def _require_module_name_for_bmi(
    request: CompileRequest,
    *,
    family: CompilerFamily,
    language: Language,
) -> None:
    if request.bmi_output is not None and request.module_name is None:
        raise UnsupportedCompileOption(
            family=family,
            language=language,
            key="bmi_output",
            detail="module_name is required when emitting a BMI",
        )


def gnu_module_flags(
    request: CompileRequest,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    """Map portable module fields to Clang-style module argv fragments."""
    _require_module_name_for_bmi(request, family=family, language=language)

    flags: list[str] = []
    for bmi in request.bmi_inputs:
        flags.append(f"-fmodule-file={bmi.module}={bmi.path}")
    if request.bmi_output is not None:
        flags.append(f"-fmodule-output={request.bmi_output}")
    return flags


def gcc_module_mapper_path(request: CompileRequest) -> Path:
    """Sidecar mapping file path for ``-fmodule-mapper=`` (GCC C++ Modules)."""
    return request.object_output.with_suffix(
        f"{request.object_output.suffix}.modulemap"
    )


def gcc_module_mappings(request: CompileRequest) -> list[tuple[str, Path]]:
    """Module name -> CMI path pairs for a GCC module mapper file."""
    mappings: dict[str, Path] = {bmi.module: bmi.path for bmi in request.bmi_inputs}
    if request.bmi_output is not None and request.module_name is not None:
        mappings[request.module_name] = request.bmi_output
    return list(mappings.items())


def gcc_module_mapper_text(request: CompileRequest) -> str:
    """Space-separated module-name/filename lines for ``-fmodule-mapper=file``."""
    lines = [f"{module} {path}" for module, path in gcc_module_mappings(request)]
    return "\n".join(lines) + ("\n" if lines else "")


def gcc_module_flags(
    request: CompileRequest,
    *,
    family: CompilerFamily,
    language: Language,
) -> list[str]:
    """Map portable module fields to GCC ``-fmodules`` / mapper argv fragments.

    GCC does not accept Clang's ``-fmodule-output`` / ``-fmodule-file=name=path``.
    CMI locations are controlled via ``-fmodule-mapper=`` (see GCC C++ Modules).
    """
    _require_module_name_for_bmi(request, family=family, language=language)

    flags: list[str] = ["-fmodules"]
    if gcc_module_mappings(request):
        flags.append(f"-fmodule-mapper={gcc_module_mapper_path(request)}")
    return flags
