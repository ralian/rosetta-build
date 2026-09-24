"""Compiler and linker interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic.dataclasses import dataclass as pydantic_dataclass

from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, LinkSettings
from rosetta_build.target import Target, TargetGenerator

__all__ = [
    "BmiInput",
    "BuildObject",
    "CompileArtifact",
    "CompileArtifactKind",
    "CompileRequest",
    "CompileResult",
    "Compiler",
    "CompilerCapabilities",
    "LinkRequest",
    "LinkResult",
    "Linker",
    "ModuleUnitKind",
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


class CompileArtifactKind(StrEnum):
    OBJECT = "object"
    BMI = "bmi"


class ModuleUnitKind(StrEnum):
    NONE = "none"
    INTERFACE = "interface"
    PARTITION = "partition"
    IMPLEMENTATION = "implementation"


@dataclass(frozen=True, slots=True)
class CompileArtifact:
    kind: CompileArtifactKind
    path: Path


@dataclass(frozen=True, slots=True)
class BmiInput:
    """Prebuilt BMI visible to a compile (logical module name -> path)."""

    module: str
    path: Path


@dataclass(frozen=True, slots=True)
class CompilerCapabilities:
    separate_link: bool
    supports_language: frozenset[Language]
    cxx_modules: bool = False


@dataclass(frozen=True, slots=True)
class CompileRequest:
    """One compile invocation; may emit an object and optionally a BMI."""

    sources: Sequence[Path]
    object_output: Path
    settings: CompileSettings
    bmi_output: Path | None = None
    module_name: str | None = None
    module_unit: ModuleUnitKind = ModuleUnitKind.NONE
    bmi_inputs: tuple[BmiInput, ...] = ()

    def expected_artifacts(self) -> tuple[CompileArtifact, ...]:
        artifacts: list[CompileArtifact] = [
            CompileArtifact(CompileArtifactKind.OBJECT, self.object_output),
        ]
        if self.bmi_output is not None:
            artifacts.append(CompileArtifact(CompileArtifactKind.BMI, self.bmi_output))
        return tuple(artifacts)

    def uses_cxx_modules(self) -> bool:
        return (
            self.bmi_output is not None
            or bool(self.bmi_inputs)
            or self.module_unit is not ModuleUnitKind.NONE
        )


@dataclass(frozen=True, slots=True)
class CompileResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    artifacts: tuple[CompileArtifact, ...] = ()


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
