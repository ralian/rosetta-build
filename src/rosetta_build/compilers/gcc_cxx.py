"""GCC C++ (g++) compiler/linker adapter."""

from __future__ import annotations

from rosetta_build.compilers._base import ArgvCompiler, ArgvLinker
from rosetta_build.compilers._gnu import gnu_compile_flags, gnu_link_flags
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = ["GccCxxCompiler", "GccCxxLinker"]


class GccCxxCompiler(ArgvCompiler):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.GCC

    @property
    def language(self) -> Language:
        return Language.CXX

    @property
    def executable_name(self) -> str:
        return "g++"

    def compile_flags(self, settings: CompileSettings) -> list[str]:
        return gnu_compile_flags(
            settings,
            family=self.family,
            language=self.language,
        )


class GccCxxLinker(ArgvLinker):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.GCC

    @property
    def language(self) -> Language:
        return Language.CXX

    @property
    def executable_name(self) -> str:
        return "g++"

    def link_flags(self, settings: LinkSettings) -> list[str]:
        return gnu_link_flags(settings)
