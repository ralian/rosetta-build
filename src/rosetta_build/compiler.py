from abc import ABC, abstractmethod
from pathlib import Path

from pydantic.dataclasses import dataclass

from rosetta_build.target import Target, TargetGenerator

__all__ = [
    "BuildObject",
    "Compiler",
    "Linker",
    "Project",
    "ProjectGenerator",
    "Target",
    "TargetGenerator",
]


@dataclass
class Project:
    name: str = ""


class ProjectGenerator(ABC):
    @abstractmethod
    def __call__(self) -> Project: ...


@dataclass
class BuildObject:
    name: Path = Path()


class Compiler(ABC):
    @abstractmethod
    async def build(self, source: Target | TargetGenerator, object: Path) -> None: ...


class Linker(ABC):
    @abstractmethod
    async def link(self, objects: list[BuildObject], output: Path) -> None: ...
