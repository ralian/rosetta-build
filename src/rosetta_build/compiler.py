from abc import ABC, abstractmethod
# from dataclasses import dataclass
from pathlib import Path
from pydantic.dataclasses import dataclass

# Open questions:
# Should these also be pydantic models?
# Input paths should be source tree relative. How to enforce this?
# How to handle compiler stdout/stderr... generators?


# Parse from TOML?
# How to handle INTERFACE?
@dataclass
class Target():
    name: str = ""
    _sources: list[Path] = ()
    sources: list[Path] = ()
    _include_dirs: list[Path] = ()
    include_dirs: list[Path] = ()
    _compile_defs: list[Path] = ()
    compile_defs: list[Path] = ()
    _compile_opts: list[Path] = ()
    compile_opts: list[Path] = ()


class TargetGenerator(ABC):
    @abstractmethod
    # What else to put here... what params would be useful?
    def __call__(self) -> Target: ...


class BuildObject(dataclass):
    name: Path = ""


class Compiler(ABC):
    @abstractmethod
    async def build(self, source: Target | TargetGenerator, object: Path) -> None: ...


class Linker(ABC):
    @abstractmethod
    async def link(self, objects: list[BuildObject], output: Path) -> None: ...


# class SourceTreeTool:
# class BuildTreeTool:
# class InstallTreeTool:
