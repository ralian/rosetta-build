"""Translation of portable C/C++ options to compiler argv."""

from __future__ import annotations

import pytest

from rosetta_build.flags import (
    CStandard,
    CxxStandard,
    DebugInfo,
    Exceptions,
    Lto,
    Optimize,
    PortableFlag,
    Rtti,
    UnsupportedPortableFlag,
    Warnings,
    compile_flags,
    link_flags,
)
from rosetta_build.language import CompilerFamily

_COMPILE_CASES: list[tuple[PortableFlag, CompilerFamily, tuple[str, ...]]] = [
    (CStandard.C11, CompilerFamily.GCC, ("-std=c11",)),
    (CStandard.C11, CompilerFamily.CLANG, ("-std=c11",)),
    (CStandard.C11, CompilerFamily.MSVC, ("/std:c11",)),
    (CStandard.C17, CompilerFamily.GCC, ("-std=c17",)),
    (CStandard.C17, CompilerFamily.CLANG, ("-std=c17",)),
    (CStandard.C17, CompilerFamily.MSVC, ("/std:c17",)),
    (CStandard.C23, CompilerFamily.GCC, ("-std=c23",)),
    (CStandard.C23, CompilerFamily.CLANG, ("-std=c23",)),
    (CStandard.C23, CompilerFamily.MSVC, ("/std:clatest",)),
    (CxxStandard.CXX17, CompilerFamily.GCC, ("-std=c++17",)),
    (CxxStandard.CXX17, CompilerFamily.CLANG, ("-std=c++17",)),
    (CxxStandard.CXX17, CompilerFamily.MSVC, ("/std:c++17",)),
    (CxxStandard.CXX20, CompilerFamily.GCC, ("-std=c++20",)),
    (CxxStandard.CXX20, CompilerFamily.CLANG, ("-std=c++20",)),
    (CxxStandard.CXX20, CompilerFamily.MSVC, ("/std:c++20",)),
    (CxxStandard.CXX23, CompilerFamily.GCC, ("-std=c++23",)),
    (CxxStandard.CXX23, CompilerFamily.CLANG, ("-std=c++23",)),
    (CxxStandard.CXX23, CompilerFamily.MSVC, ("/std:c++latest",)),
    (Optimize.O0, CompilerFamily.GCC, ("-O0",)),
    (Optimize.O0, CompilerFamily.CLANG, ("-O0",)),
    (Optimize.O0, CompilerFamily.MSVC, ("/Od",)),
    (Optimize.O2, CompilerFamily.GCC, ("-O2",)),
    (Optimize.O2, CompilerFamily.CLANG, ("-O2",)),
    (Optimize.O2, CompilerFamily.MSVC, ("/O2",)),
    (Optimize.Os, CompilerFamily.GCC, ("-Os",)),
    (Optimize.Os, CompilerFamily.CLANG, ("-Os",)),
    (Optimize.Os, CompilerFamily.MSVC, ("/O1",)),
    (Warnings.SUPPRESS, CompilerFamily.GCC, ("-w",)),
    (Warnings.SUPPRESS, CompilerFamily.CLANG, ("-w",)),
    (Warnings.SUPPRESS, CompilerFamily.MSVC, ("/w",)),
    (Warnings.AS_ERROR, CompilerFamily.GCC, ("-Werror",)),
    (Warnings.AS_ERROR, CompilerFamily.CLANG, ("-Werror",)),
    (Warnings.AS_ERROR, CompilerFamily.MSVC, ("/WX",)),
    (Rtti.ON, CompilerFamily.GCC, ("-frtti",)),
    (Rtti.ON, CompilerFamily.CLANG, ("-frtti",)),
    (Rtti.ON, CompilerFamily.MSVC, ("/GR",)),
    (Rtti.OFF, CompilerFamily.GCC, ("-fno-rtti",)),
    (Rtti.OFF, CompilerFamily.CLANG, ("-fno-rtti",)),
    (Rtti.OFF, CompilerFamily.MSVC, ("/GR-",)),
    (Exceptions.ON, CompilerFamily.GCC, ("-fexceptions",)),
    (Exceptions.ON, CompilerFamily.CLANG, ("-fexceptions",)),
    (Exceptions.ON, CompilerFamily.MSVC, ("/EHsc",)),
    (Exceptions.OFF, CompilerFamily.GCC, ("-fno-exceptions",)),
    (Exceptions.OFF, CompilerFamily.CLANG, ("-fno-exceptions",)),
    (Exceptions.OFF, CompilerFamily.MSVC, ("/EHs-c-",)),
    (DebugInfo.ON, CompilerFamily.GCC, ("-g",)),
    (DebugInfo.ON, CompilerFamily.CLANG, ("-g",)),
    (DebugInfo.ON, CompilerFamily.MSVC, ("/Zi",)),
    (Lto.ON, CompilerFamily.GCC, ("-flto",)),
    (Lto.ON, CompilerFamily.CLANG, ("-flto",)),
    (Lto.ON, CompilerFamily.MSVC, ("/GL",)),
]

_LINK_CASES: list[tuple[PortableFlag, CompilerFamily, tuple[str, ...]]] = [
    (DebugInfo.ON, CompilerFamily.GCC, ("-g",)),
    (DebugInfo.ON, CompilerFamily.CLANG, ("-g",)),
    (DebugInfo.ON, CompilerFamily.MSVC, ("/DEBUG",)),
    (Lto.ON, CompilerFamily.GCC, ("-flto",)),
    (Lto.ON, CompilerFamily.CLANG, ("-flto",)),
    (Lto.ON, CompilerFamily.MSVC, ("/LTCG",)),
]

_COMPILE_ONLY: tuple[PortableFlag, ...] = (
    *CStandard,
    *CxxStandard,
    *Optimize,
    *Warnings,
    *Rtti,
    *Exceptions,
)


def _all_flags() -> set[PortableFlag]:
    return {
        *CStandard,
        *CxxStandard,
        *Optimize,
        *Warnings,
        *Rtti,
        *Exceptions,
        *DebugInfo,
        *Lto,
    }


def test_tokens_are_unique_rosetta_names() -> None:
    tokens = [str(flag) for flag in _all_flags()]
    assert len(tokens) == len(set(tokens))
    assert all(token.startswith("rosetta.") for token in tokens)
    assert Optimize.O2.value == "rosetta.O2"


def test_compile_table_covers_every_flag_and_family() -> None:
    families = {CompilerFamily.GCC, CompilerFamily.CLANG, CompilerFamily.MSVC}
    by_flag: dict[PortableFlag, set[CompilerFamily]] = {}
    for flag, family, _expected in _COMPILE_CASES:
        by_flag.setdefault(flag, set()).add(family)
    assert set(by_flag) == _all_flags()
    assert all(seen == families for seen in by_flag.values())


@pytest.mark.parametrize(("flag", "family", "expected"), _COMPILE_CASES)
def test_compile_flags(
    flag: PortableFlag,
    family: CompilerFamily,
    expected: tuple[str, ...],
) -> None:
    assert compile_flags(flag, family) == expected


@pytest.mark.parametrize(("flag", "family", "expected"), _LINK_CASES)
def test_link_flags(
    flag: PortableFlag,
    family: CompilerFamily,
    expected: tuple[str, ...],
) -> None:
    assert link_flags(flag, family) == expected


@pytest.mark.parametrize("flag", _COMPILE_ONLY)
@pytest.mark.parametrize(
    "family",
    [CompilerFamily.GCC, CompilerFamily.CLANG, CompilerFamily.MSVC],
)
def test_compile_only_options_add_no_link_flags(
    flag: PortableFlag,
    family: CompilerFamily,
) -> None:
    assert link_flags(flag, family) == ()


@pytest.mark.parametrize("family", [CompilerFamily.RUSTC, CompilerFamily.GCCRS])
@pytest.mark.parametrize("flag", [Optimize.O2, DebugInfo.ON])
def test_non_c_family_raises(flag: PortableFlag, family: CompilerFamily) -> None:
    with pytest.raises(UnsupportedPortableFlag, match="does not support"):
        compile_flags(flag, family)
    with pytest.raises(UnsupportedPortableFlag, match="does not support"):
        link_flags(flag, family)
