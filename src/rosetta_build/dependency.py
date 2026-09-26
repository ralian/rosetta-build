"""Project-level external dependencies (FetchContent-style)."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
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
    "sha256_checkout",
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
    """Clone a git repository at a fixed tag (https://, ssh://, or file://).

    When ``hash`` is set (``sha256:<hex>``), the populated working tree is
    hashed (excluding ``.git``) and must match.
    """

    uri: str
    tag: str
    hash: str | None = None

    def populate(self, dest: Path) -> Path:
        populated = _clone_at_tag(uri=self.uri, tag=self.tag, dest=dest)
        if self.hash is not None:
            try:
                _verify_checkout_hash(populated, expected=self.hash)
            except DependencyError:
                _rmtree(populated)
                raise
        return populated


def provider_for(spec: DependencyConfig) -> DependencyProvider:
    if isinstance(spec, GitDependencyConfig):
        return GitDependencyProvider(uri=spec.uri, tag=spec.tag, hash=spec.hash)
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


def sha256_checkout(root: Path) -> str:
    """Return the SHA-256 hex digest of tracked working-tree files under ``root``.

    Paths are hashed relative to ``root`` in sorted POSIX order. The ``.git``
    directory is excluded so the digest is stable across clones.
    """
    root = root.resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(root).parts:
            continue
        rel = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _verify_checkout_hash(root: Path, *, expected: str) -> None:
    actual = f"sha256:{sha256_checkout(root)}"
    if actual != expected:
        raise DependencyError(
            f"dependency hash mismatch for {root}: expected {expected}, got {actual}"
        )


def _clone_at_tag(*, uri: str, tag: str, dest: Path) -> Path:
    dest = dest.resolve()
    if dest.exists():
        _rmtree(dest)
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


def _rmtree(path: Path) -> None:
    """Remove ``path``, clearing the read-only bit Git sets on Windows."""

    def _onexc(func: Callable[..., object], name: str, exc: BaseException) -> None:
        if not isinstance(exc, PermissionError):
            raise exc
        os.chmod(name, stat.S_IWRITE)
        func(name)

    shutil.rmtree(path, onexc=_onexc)


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
