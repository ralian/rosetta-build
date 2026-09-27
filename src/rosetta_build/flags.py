"""Portable C and C++ options for GCC, Clang, and MSVC.

Each option exists only when all three compilers have a switch for the same
feature. ``compile_flags`` and ``link_flags`` turn one option into that
compiler's argv spellings. Tokens use the ``rosetta.*`` form.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from rosetta_build.language import CompilerFamily

__all__ = [
    "CStandard",
    "CxxStandard",
    "DebugInfo",
    "Exceptions",
    "Lto",
    "Optimize",
    "PortableFlag",
    "Rtti",
    "UnsupportedPortableFlag",
    "Warnings",
    "compile_flags",
    "link_flags",
]


class CStandard(StrEnum):
    """ISO C language version.

    ``C23`` selects ``/std:clatest`` on MSVC.
    """

    C11 = "rosetta.c11"
    C17 = "rosetta.c17"
    C23 = "rosetta.c23"


class CxxStandard(StrEnum):
    """ISO C++ language version.

    ``CXX23`` selects ``/std:c++latest`` on MSVC.
    """

    CXX17 = "rosetta.cxx17"
    CXX20 = "rosetta.cxx20"
    CXX23 = "rosetta.cxx23"


class Optimize(StrEnum):
    """Optimization level.

    ``O0`` disables optimization (``-O0``, ``/Od``). ``O2`` optimizes for
    speed (``-O2``, ``/O2``). ``Os`` optimizes for size (``-Os``, ``/O1``).
    MSVC's ``/Os`` only biases code size and is not this option.
    """

    O0 = "rosetta.O0"
    O2 = "rosetta.O2"
    Os = "rosetta.Os"


class Warnings(StrEnum):
    """Diagnostics switches shared by GCC, Clang, and MSVC.

    ``-Wall`` and ``/Wall`` are not the same feature: MSVC ``/Wall`` turns on
    warnings GCC leaves disabled.
    """

    SUPPRESS = "rosetta.w"
    AS_ERROR = "rosetta.Werror"


class Rtti(StrEnum):
    """C++ run-time type information."""

    ON = "rosetta.rtti"
    OFF = "rosetta.no-rtti"


class Exceptions(StrEnum):
    """C++ exception handling.

    MSVC ``ON`` is ``/EHsc`` (synchronous C++ exceptions, and ``extern "C"``
    functions are nothrow). ``OFF`` is ``/EHs-c-``.
    """

    ON = "rosetta.exceptions"
    OFF = "rosetta.no-exceptions"


class DebugInfo(StrEnum):
    """Emit debug information.

    MSVC compiles with ``/Zi``. Linking that object needs ``/DEBUG``.
    """

    ON = "rosetta.g"


class Lto(StrEnum):
    """Whole-program optimization.

    MSVC compiles with ``/GL``. Linking needs ``/LTCG``.
    """

    ON = "rosetta.lto"


PortableFlag = (
    CStandard | CxxStandard | Optimize | Warnings | Rtti | Exceptions | DebugInfo | Lto
)

_Spellings = Mapping[CompilerFamily, tuple[str, ...]]


class UnsupportedPortableFlag(Exception):
    """Raised when a compiler family has no spelling for a portable flag."""

    def __init__(self, *, family: CompilerFamily, flag: str) -> None:
        self.family = family
        self.flag = flag
        super().__init__(f"{family.value} does not support {flag}")


def _s(gcc: str, clang: str, msvc: str) -> dict[CompilerFamily, tuple[str, ...]]:
    return {
        CompilerFamily.GCC: (gcc,),
        CompilerFamily.CLANG: (clang,),
        CompilerFamily.MSVC: (msvc,),
    }


_COMPILE: Mapping[PortableFlag, _Spellings] = {
    CStandard.C11: _s("-std=c11", "-std=c11", "/std:c11"),
    CStandard.C17: _s("-std=c17", "-std=c17", "/std:c17"),
    CStandard.C23: _s("-std=c23", "-std=c23", "/std:clatest"),
    CxxStandard.CXX17: _s("-std=c++17", "-std=c++17", "/std:c++17"),
    CxxStandard.CXX20: _s("-std=c++20", "-std=c++20", "/std:c++20"),
    CxxStandard.CXX23: _s("-std=c++23", "-std=c++23", "/std:c++latest"),
    Optimize.O0: _s("-O0", "-O0", "/Od"),
    Optimize.O2: _s("-O2", "-O2", "/O2"),
    Optimize.Os: _s("-Os", "-Os", "/O1"),
    Warnings.SUPPRESS: _s("-w", "-w", "/w"),
    Warnings.AS_ERROR: _s("-Werror", "-Werror", "/WX"),
    Rtti.ON: _s("-frtti", "-frtti", "/GR"),
    Rtti.OFF: _s("-fno-rtti", "-fno-rtti", "/GR-"),
    Exceptions.ON: _s("-fexceptions", "-fexceptions", "/EHsc"),
    Exceptions.OFF: _s("-fno-exceptions", "-fno-exceptions", "/EHs-c-"),
    DebugInfo.ON: _s("-g", "-g", "/Zi"),
    Lto.ON: _s("-flto", "-flto", "/GL"),
}

_LINK: Mapping[PortableFlag, _Spellings] = {
    DebugInfo.ON: _s("-g", "-g", "/DEBUG"),
    Lto.ON: _s("-flto", "-flto", "/LTCG"),
}


def _supported(family: CompilerFamily, flag: PortableFlag) -> None:
    if family not in (CompilerFamily.GCC, CompilerFamily.CLANG, CompilerFamily.MSVC):
        raise UnsupportedPortableFlag(family=family, flag=str(flag))


def _lookup(
    table: Mapping[PortableFlag, _Spellings],
    flag: PortableFlag,
    family: CompilerFamily,
) -> tuple[str, ...]:
    _supported(family, flag)
    try:
        spellings = table[flag]
    except KeyError as exc:
        raise UnsupportedPortableFlag(family=family, flag=str(flag)) from exc
    return spellings[family]


def compile_flags(flag: PortableFlag, family: CompilerFamily) -> tuple[str, ...]:
    """Argv spellings for ``flag`` on a compile command."""
    return _lookup(_COMPILE, flag, family)


def link_flags(flag: PortableFlag, family: CompilerFamily) -> tuple[str, ...]:
    """Argv spellings for ``flag`` on a link command.

    Compile-only options return an empty tuple.
    """
    _supported(family, flag)
    spellings = _LINK.get(flag)
    if spellings is None:
        return ()
    return spellings[family]
