"""GCC C compiler/linker adapter."""

from __future__ import annotations

from rosetta_build.compilers._base import ArgvCompiler, ArgvLinker
from rosetta_build.compilers._gnu import gnu_compile_flags, gnu_link_flags
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = ["GccCCompiler", "GccCLinker"]


class GccCCompiler(ArgvCompiler):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.GCC

    @property
    def language(self) -> Language:
        return Language.C

    @property
    def executable_name(self) -> str:
        return "gcc"

    def compile_flags(self, settings: CompileSettings) -> list[str]:
        return gnu_compile_flags(
            settings,
            family=self.family,
            language=self.language,
        )


class GccCLinker(ArgvLinker):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.GCC

    @property
    def language(self) -> Language:
        return Language.C

    @property
    def executable_name(self) -> str:
        return "gcc"

    def link_flags(self, settings: LinkSettings) -> list[str]:
        return gnu_link_flags(settings)
