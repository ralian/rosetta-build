"""Target types collected from a source tree."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import field
from pathlib import Path

from pydantic.dataclasses import dataclass

from rosetta_build.language import Language


@dataclass
class Target:
    """Base target: a named unit with a source set."""

    name: str
    sources: set[Path] = field(default_factory=set)
    config_path: Path | None = None


@dataclass
class NativeTarget(Target):
    """Compiled native target with compile and link settings."""

    language: Language = Language.CXX
    include_dirs: set[Path] = field(default_factory=set)
    compile_defs: dict[str, str | bool | int] = field(default_factory=dict)
    compile_opts: list[str] = field(default_factory=list)
    link_opts: list[str] = field(default_factory=list)
    usage: set[str] = field(default_factory=set)
    link_libraries: set[str] = field(default_factory=set)
    # Target names whose exported modules this target may ``import``.
    module_visibility: set[str] = field(default_factory=set)


@dataclass
class ExecutableTarget(NativeTarget):
    """Native executable artifact."""


@dataclass
class StaticLibraryTarget(NativeTarget):
    """Native static library artifact."""


@dataclass
class DynamicLibraryTarget(NativeTarget):
    """Native shared/dynamic library artifact."""


@dataclass
class ModuleTarget(NativeTarget):
    """C++ named-module compile unit with BMI import dependencies."""

    module: str = ""
    imports: set[str] = field(default_factory=set)


@dataclass
class ModuleInterfaceTarget(ModuleTarget):
    """Primary module interface unit (``export module M``)."""


@dataclass
class ModulePartitionTarget(ModuleTarget):
    """Module partition interface unit (``export module M:part``)."""

    partition: str = ""


@dataclass
class ModuleImplementationTarget(ModuleTarget):
    """Module implementation unit (``module M;``)."""


@dataclass
class WheelTarget(Target):
    """Python wheel artifact: name and sources only."""


class TargetGenerator(ABC):
    @abstractmethod
    def __call__(self) -> Target: ...
