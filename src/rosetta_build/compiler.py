from abc import ABC, abstractmethod
from pathlib import Path

from pydantic.dataclasses import dataclass


@dataclass
class Target:
    name: str = ""
    sources: set[Path] | None = None
    include_dirs: set[Path] | None = None
    compile_defs: dict[str, str | bool | int] | None = None
    compile_opts: list[str] | None = None
    link_libraries: set[str] | None = None

    def __post_init__(self) -> None:
        if self.sources is None:
            self.sources = set()
        if self.include_dirs is None:
            self.include_dirs = set()
        if self.compile_defs is None:
            self.compile_defs = {}
        if self.compile_opts is None:
            self.compile_opts = []
        if self.link_libraries is None:
            self.link_libraries = set()


class TargetGenerator(ABC):
    @abstractmethod
    def __call__(self) -> Target: ...


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
