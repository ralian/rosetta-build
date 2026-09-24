"""Registry of compiler and linker adapters by (family, language)."""

from __future__ import annotations

from rosetta_build.compiler import Compiler, Linker
from rosetta_build.compilers.clang_c import ClangCCompiler, ClangCLinker
from rosetta_build.compilers.clang_cxx import ClangCxxCompiler, ClangCxxLinker
from rosetta_build.compilers.gcc_c import GccCCompiler, GccCLinker
from rosetta_build.compilers.gcc_cxx import GccCxxCompiler, GccCxxLinker
from rosetta_build.compilers.gccrs import GccrsCompiler, GccrsLinker
from rosetta_build.compilers.msvc_c import MsvcCCompiler, MsvcCLinker
from rosetta_build.compilers.msvc_cxx import MsvcCxxCompiler, MsvcCxxLinker
from rosetta_build.compilers.rustc import RustcCompiler, RustcLinker
from rosetta_build.language import CompilerFamily, Language

__all__ = [
    "ClangCCompiler",
    "ClangCLinker",
    "ClangCxxCompiler",
    "ClangCxxLinker",
    "GccCCompiler",
    "GccCLinker",
    "GccCxxCompiler",
    "GccCxxLinker",
    "GccrsCompiler",
    "GccrsLinker",
    "MsvcCCompiler",
    "MsvcCLinker",
    "MsvcCxxCompiler",
    "MsvcCxxLinker",
    "RustcCompiler",
    "RustcLinker",
    "get_compiler",
    "get_linker",
]

_COMPILER_REGISTRY: dict[tuple[CompilerFamily, Language], type[Compiler]] = {
    (CompilerFamily.GCC, Language.C): GccCCompiler,
    (CompilerFamily.GCC, Language.CXX): GccCxxCompiler,
    (CompilerFamily.CLANG, Language.C): ClangCCompiler,
    (CompilerFamily.CLANG, Language.CXX): ClangCxxCompiler,
    (CompilerFamily.MSVC, Language.C): MsvcCCompiler,
    (CompilerFamily.MSVC, Language.CXX): MsvcCxxCompiler,
    (CompilerFamily.RUSTC, Language.RUST): RustcCompiler,
    (CompilerFamily.GCCRS, Language.RUST): GccrsCompiler,
}

_LINKER_REGISTRY: dict[tuple[CompilerFamily, Language], type[Linker]] = {
    (CompilerFamily.GCC, Language.C): GccCLinker,
    (CompilerFamily.GCC, Language.CXX): GccCxxLinker,
    (CompilerFamily.CLANG, Language.C): ClangCLinker,
    (CompilerFamily.CLANG, Language.CXX): ClangCxxLinker,
    (CompilerFamily.MSVC, Language.C): MsvcCLinker,
    (CompilerFamily.MSVC, Language.CXX): MsvcCxxLinker,
    (CompilerFamily.RUSTC, Language.RUST): RustcLinker,
    (CompilerFamily.GCCRS, Language.RUST): GccrsLinker,
}


def get_compiler(family: CompilerFamily, language: Language) -> Compiler:
    try:
        cls = _COMPILER_REGISTRY[(family, language)]
    except KeyError as exc:
        raise KeyError(
            f"no compiler registered for {family.value}/{language.value}"
        ) from exc
    return cls()


def get_linker(family: CompilerFamily, language: Language) -> Linker:
    try:
        cls = _LINKER_REGISTRY[(family, language)]
    except KeyError as exc:
        raise KeyError(
            f"no linker registered for {family.value}/{language.value}"
        ) from exc
    return cls()
