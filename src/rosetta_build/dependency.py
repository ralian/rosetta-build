"""Project-level external dependencies (FetchContent-style)."""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from rosetta_build.schema import DependencyConfig, GitDependencyConfig

__all__ = [
    "DependencyError",
    "DependencyProvider",
    "GitDependencyProvider",
    "populate_dependencies",
    "populate_dependency",
    "provider_for",
]


class DependencyError(Exception):
    """Raised when a project dependency cannot be resolved or populated."""


class DependencyProvider(ABC):
    """Materializes a declared dependency into a local source tree."""

    @abstractmethod
    def populate(self, dest: Path) -> Path:
        """Fetch this dependency into ``dest`` and return that path."""


@dataclass(frozen=True, slots=True)
class GitDependencyProvider(DependencyProvider):
    """Clone a git repository at a fixed tag (https://, ssh://, or file://)."""

    uri: str
    tag: str

    def populate(self, dest: Path) -> Path:
        return _clone_at_tag(uri=self.uri, tag=self.tag, dest=dest)


def provider_for(spec: DependencyConfig) -> DependencyProvider:
    if isinstance(spec, GitDependencyConfig):
        return GitDependencyProvider(uri=spec.uri, tag=spec.tag)
    raise DependencyError(f"unsupported dependency provider: {spec!r}")


def populate_dependency(
    name: str,
    spec: DependencyConfig,
    deps_root: Path,
) -> Path:
    """Populate one named dependency under ``deps_root / name``."""
    if not name.strip():
        raise DependencyError("dependency name must be non-empty")
    dest = deps_root / name
    return provider_for(spec).populate(dest)


def populate_dependencies(
    specs: Mapping[str, DependencyConfig],
    deps_root: Path,
) -> dict[str, Path]:
    """Populate all declared dependencies under ``deps_root``.

    Each dependency is fetched into ``deps_root / <name>``, similar to CMake
    FetchContent's per-content source directory.
    """
    deps_root.mkdir(parents=True, exist_ok=True)
    return {
        name: populate_dependency(name, spec, deps_root) for name, spec in specs.items()
    }


def _clone_at_tag(*, uri: str, tag: str, dest: Path) -> Path:
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        _run_git([
            "clone",
            "--depth",
            "1",
            "--branch",
            tag,
            uri,
            str(dest),
        ])
    except DependencyError as exc:
        raise DependencyError(
            f"failed to clone {uri!r} at tag {tag!r} into {dest}: {exc}"
        ) from exc
    return dest


def _run_git(args: list[str]) -> None:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DependencyError("git executable not found on PATH") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise DependencyError(detail or f"git {' '.join(args)} failed")
