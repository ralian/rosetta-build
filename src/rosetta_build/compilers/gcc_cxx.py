"""GCC C++ (g++) compiler/linker adapter."""

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
    gcc_module_flags,
    gcc_module_mapper_path,
    gcc_module_mapper_text,
    gcc_module_mappings,
    gnu_compile_flags,
    gnu_link_flags,
)
from rosetta_build.compilers._process import run_driver
from rosetta_build.depfile import depfile_for_object
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = ["GccCxxCompiler", "GccCxxLinker"]


def _prepare_gcc_module_mapper(request: CompileRequest) -> None:
    if not gcc_module_mappings(request):
        return
    path = gcc_module_mapper_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gcc_module_mapper_text(request), encoding="utf-8")


def _depfile_path(request: CompileRequest) -> Path:
    return request.depfile or depfile_for_object(request.object_output)


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

    def cxx_module_flags(self, request: CompileRequest) -> list[str]:
        return gcc_module_flags(
            request,
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
        if request.bmi_output is not None:
            request.bmi_output.parent.mkdir(parents=True, exist_ok=True)
        _depfile_path(request).parent.mkdir(parents=True, exist_ok=True)
        if request.uses_cxx_modules():
            _prepare_gcc_module_mapper(request)

        returncode, stdout, stderr = await run_driver(self.argv_for_compile(request))
        artifacts = request.expected_artifacts() if returncode == 0 else ()
        return CompileResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
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

    async def link(self, request: LinkRequest) -> LinkResult:
        request.output.parent.mkdir(parents=True, exist_ok=True)
        returncode, stdout, stderr = await run_driver(self.argv_for_link(request))
        return LinkResult(returncode=returncode, stdout=stdout, stderr=stderr)
