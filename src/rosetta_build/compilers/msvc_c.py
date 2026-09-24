"""MSVC C compiler/linker adapter."""

from __future__ import annotations

from rosetta_build.compiler import CompileRequest, LinkRequest
from rosetta_build.compilers._base import ArgvCompiler, ArgvLinker
from rosetta_build.compilers._msvc import msvc_compile_flags, msvc_link_flags
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = ["MsvcCCompiler", "MsvcCLinker"]


class MsvcCCompiler(ArgvCompiler):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.MSVC

    @property
    def language(self) -> Language:
        return Language.C

    @property
    def executable_name(self) -> str:
        return "cl"

    def compile_flags(self, settings: CompileSettings) -> list[str]:
        return msvc_compile_flags(
            settings,
            family=self.family,
            language=self.language,
        )

    def argv_for_compile(self, request: CompileRequest) -> list[str]:
        argv = [self.executable_name, "/c", *self.compile_flags(request.settings)]
        argv.extend(str(path) for path in request.sources)
        argv.append(f"/Fo{request.output}")
        return argv


class MsvcCLinker(ArgvLinker):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.MSVC

    @property
    def language(self) -> Language:
        return Language.C

    @property
    def executable_name(self) -> str:
        return "link"

    def link_flags(self, settings: LinkSettings) -> list[str]:
        return msvc_link_flags(settings)

    def argv_for_link(self, request: LinkRequest) -> list[str]:
        argv = [self.executable_name, *self.link_flags(request.settings)]
        argv.extend(str(obj.name) for obj in request.objects)
        argv.append(f"/OUT:{request.output}")
        return argv
