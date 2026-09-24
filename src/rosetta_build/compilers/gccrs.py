"""gccrs compiler adapter (compile and link are typically one invocation)."""

from __future__ import annotations

from rosetta_build.compiler import (
    CompilerCapabilities,
    CompileRequest,
    LinkRequest,
    LinkResult,
)
from rosetta_build.compilers._base import ArgvCompiler, ArgvLinker
from rosetta_build.compilers._rust import rust_compile_flags, rust_link_flags
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = ["GccrsCompiler", "GccrsLinker"]


class GccrsCompiler(ArgvCompiler):
    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.GCCRS

    @property
    def language(self) -> Language:
        return Language.RUST

    @property
    def executable_name(self) -> str:
        return "gccrs"

    @property
    def capabilities(self) -> CompilerCapabilities:
        return CompilerCapabilities(
            separate_link=False,
            supports_language=frozenset({Language.RUST}),
        )

    def compile_flags(self, settings: CompileSettings) -> list[str]:
        return rust_compile_flags(
            settings,
            family=self.family,
            language=self.language,
        )

    def argv_for_compile(self, request: CompileRequest) -> list[str]:
        self.module_compile_flags(request)
        argv = [self.executable_name, *self.compile_flags(request.settings)]
        argv.extend(str(path) for path in request.sources)
        argv.extend(["-o", str(request.object_output)])
        return argv


class GccrsLinker(ArgvLinker):
    """Placeholder linker; gccrs usually emits the final artifact itself."""

    @property
    def family(self) -> CompilerFamily:
        return CompilerFamily.GCCRS

    @property
    def language(self) -> Language:
        return Language.RUST

    @property
    def executable_name(self) -> str:
        return "gccrs"

    def link_flags(self, settings: LinkSettings) -> list[str]:
        return rust_link_flags(settings)

    def argv_for_link(self, request: LinkRequest) -> list[str]:
        raise NotImplementedError(
            "gccrs uses a single compile invocation; separate link is unsupported"
        )

    async def link(self, request: LinkRequest) -> LinkResult:
        _ = request
        raise NotImplementedError(
            "gccrs uses a single compile invocation; separate link is unsupported"
        )
