"""GCC C compiler/linker adapter."""

from __future__ import annotations

from pathlib import Path

from rosetta_build.compiler import (
    CompileRequest,
    CompileResult,
    LinkRequest,
    LinkResult,
)
from rosetta_build.compilers._base import ArgvCompiler, ArgvLinker
from rosetta_build.compilers._gnu import (
    gnu_compile_flags,
    gnu_link_flags,
    move_mingw_appended_exe,
)
from rosetta_build.compilers._process import run_driver
from rosetta_build.depfile import depfile_for_object
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = ["GccCCompiler", "GccCLinker"]


def _depfile_path(request: CompileRequest) -> Path:
    return request.depfile or depfile_for_object(request.object_output)


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

    def argv_for_compile(self, request: CompileRequest) -> list[str]:
        depfile = _depfile_path(request)
        argv = [
            self.executable_name,
            "-c",
            *self.compile_flags(request.settings),
            *self.module_compile_flags(request),
            "-MD",
            "-MF",
            str(depfile),
        ]
        argv.extend(str(path) for path in request.sources)
        argv.extend(["-o", str(request.object_output)])
        return argv

    async def compile(self, request: CompileRequest) -> CompileResult:
        request.object_output.parent.mkdir(parents=True, exist_ok=True)
        _depfile_path(request).parent.mkdir(parents=True, exist_ok=True)

        returncode, stdout, stderr = await run_driver(self.argv_for_compile(request))
        artifacts = request.expected_artifacts() if returncode == 0 else ()
        return CompileResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
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

    async def link(self, request: LinkRequest) -> LinkResult:
        request.output.parent.mkdir(parents=True, exist_ok=True)
        returncode, stdout, stderr = await run_driver(self.argv_for_link(request))
        if returncode == 0:
            move_mingw_appended_exe(request.output)
        return LinkResult(returncode=returncode, stdout=stdout, stderr=stderr)
