"""Compiler and linker interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic.dataclasses import dataclass as pydantic_dataclass

from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings
from rosetta_build.target import Target, TargetGenerator

__all__ = [
    "BuildObject",
    "CompileRequest",
    "CompileResult",
    "Compiler",
    "CompilerCapabilities",
    "LinkRequest",
    "LinkResult",
    "Linker",
    "Project",
    "ProjectGenerator",
    "Target",
    "TargetGenerator",
]


@pydantic_dataclass
class Project:
    name: str = ""


class ProjectGenerator(ABC):
    @abstractmethod
    def __call__(self) -> Project: ...


@pydantic_dataclass
class BuildObject:
    name: Path = Path()


@dataclass(frozen=True, slots=True)
class CompilerCapabilities:
    separate_link: bool
    supports_language: frozenset[Language]


@dataclass(frozen=True, slots=True)
class CompileRequest:
    sources: Sequence[Path]
    output: Path
    settings: CompileSettings


@dataclass(frozen=True, slots=True)
class CompileResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class LinkRequest:
    objects: Sequence[BuildObject]
    output: Path
    settings: LinkSettings


@dataclass(frozen=True, slots=True)
class LinkResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Compiler(ABC):
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
    @abstractmethod
    def capabilities(self) -> CompilerCapabilities: ...

    @abstractmethod
    def argv_for_compile(self, request: CompileRequest) -> list[str]: ...

    @abstractmethod
    async def compile(self, request: CompileRequest) -> CompileResult: ...


class Linker(ABC):
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
    def argv_for_link(self, request: LinkRequest) -> list[str]: ...

    @abstractmethod
    async def link(self, request: LinkRequest) -> LinkResult: ...
