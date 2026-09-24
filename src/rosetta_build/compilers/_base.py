"""Base classes for compiler/linker adapters that only assemble argv for now."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rosetta_build.compiler import (
    Compiler,
    CompilerCapabilities,
    CompileRequest,
    CompileResult,
    Linker,
    LinkRequest,
    LinkResult,
)
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings

__all__ = [
    "ArgvCompiler",
    "ArgvLinker",
]


class ArgvCompiler(Compiler, ABC):
    """Compiler that maps settings to argv; process execution comes later."""

    @property
    @abstractmethod
    def family(self) -> CompilerFamily: ...

    @property
    @abstractmethod
    def language(self) -> Language: ...

    @property
    @abstractmethod
    def executable_name(self) -> str: ...

    @property
    def capabilities(self) -> CompilerCapabilities:
        return CompilerCapabilities(
            separate_link=True,
            supports_language=frozenset({self.language}),
        )

    @abstractmethod
    def compile_flags(self, settings: CompileSettings) -> list[str]: ...

    def argv_for_compile(self, request: CompileRequest) -> list[str]:
        argv = [self.executable_name, "-c", *self.compile_flags(request.settings)]
        argv.extend(str(path) for path in request.sources)
        argv.extend(["-o", str(request.output)])
        return argv

    async def compile(self, request: CompileRequest) -> CompileResult:
        _ = request
        raise NotImplementedError("process execution is not implemented yet")


class ArgvLinker(Linker, ABC):
    """Linker that maps settings to argv; process execution comes later."""

    @property
    @abstractmethod
    def family(self) -> CompilerFamily: ...

    @property
    @abstractmethod
    def language(self) -> Language: ...

    @property
    @abstractmethod
    def executable_name(self) -> str: ...

    @abstractmethod
    def link_flags(self, settings: LinkSettings) -> list[str]: ...

    def argv_for_link(self, request: LinkRequest) -> list[str]:
        argv = [self.executable_name, *self.link_flags(request.settings)]
        argv.extend(str(obj.name) for obj in request.objects)
        argv.extend(["-o", str(request.output)])
        return argv

    async def link(self, request: LinkRequest) -> LinkResult:
        _ = request
        raise NotImplementedError("process execution is not implemented yet")
