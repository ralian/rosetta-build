"""Collect targets from a source tree and build dependency graphs."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rosetta_build.graph import LinkGraph, SourceGraph
from rosetta_build.schema import RosettaBuildConfig, TargetConfig

TOOL_TABLE = "rosetta-build"


class CollectionError(Exception):
    """Raised when collection fails due to invalid config or references."""


class ResolvedTarget(BaseModel):
    """A validated target with paths resolved under the source tree."""

    model_config = ConfigDict(frozen=True)

    name: str
    config_path: Path
    sources: frozenset[Path]
    include_dirs: frozenset[Path]
    compile_defs: dict[str, str | bool | int] = Field(default_factory=dict)
    compile_opts: tuple[str, ...] = ()
    link_libraries: tuple[str, ...] = ()


class Collection(BaseModel):
    """Result of collecting and validating a source tree."""

    model_config = ConfigDict(frozen=True)

    source_tree: Path
    targets: dict[str, ResolvedTarget]
    source_graph: SourceGraph
    link_graph: LinkGraph


def collect(source_tree: Path) -> Collection:
    """Load, validate, and graph all targets under ``source_tree``."""
    root = source_tree.resolve()
    if not root.is_dir():
        raise CollectionError(f"source tree is not a directory: {root}")

    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise CollectionError(f"missing root pyproject.toml: {pyproject}")

    tool_config = _load_tool_config(pyproject)
    resolved_targets = _load_targets(root, tool_config.targets)
    source_graph = _build_source_graph(resolved_targets)
    link_graph = _build_link_graph(resolved_targets)
    return Collection(
        source_tree=root,
        targets=resolved_targets,
        source_graph=source_graph,
        link_graph=link_graph,
    )


def _load_tool_config(pyproject: Path) -> RosettaBuildConfig:
    raw = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    tool_section = raw.get("tool", {}).get(TOOL_TABLE)
    if tool_section is None:
        raise CollectionError(
            f"{pyproject} has no [tool.{TOOL_TABLE}] table listing target files"
        )
    try:
        return RosettaBuildConfig.model_validate(tool_section)
    except ValidationError as exc:
        raise CollectionError(
            f"invalid [tool.{TOOL_TABLE}] in {pyproject}:\n{exc}"
        ) from exc


def _load_targets(root: Path, target_paths: list[Path]) -> dict[str, ResolvedTarget]:
    if not target_paths:
        raise CollectionError(
            "no target files listed under [tool.rosetta-build].targets"
        )

    resolved: dict[str, ResolvedTarget] = {}
    for rel_path in target_paths:
        config_path = _resolve_under(root, root, rel_path, label="target config")
        if not config_path.is_file():
            raise CollectionError(f"target config not found: {config_path}")

        target = _load_target(root, config_path)
        if target.name in resolved:
            other = resolved[target.name].config_path
            raise CollectionError(
                f"duplicate target name {target.name!r}: {config_path} and {other}"
            )
        resolved[target.name] = target
    return resolved


def _load_target(root: Path, config_path: Path) -> ResolvedTarget:
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    try:
        config = TargetConfig.model_validate(raw)
    except ValidationError as exc:
        raise CollectionError(f"invalid target config {config_path}:\n{exc}") from exc

    base = config_path.parent
    sources = frozenset(
        _resolve_under(root, base, path, label="source") for path in config.sources
    )
    include_dirs = frozenset(
        _resolve_under(root, base, path, label="include dir")
        for path in config.include_dirs
    )
    return ResolvedTarget(
        name=config.name,
        config_path=config_path,
        sources=sources,
        include_dirs=include_dirs,
        compile_defs=dict(config.compile_defs),
        compile_opts=tuple(config.compile_opts),
        link_libraries=tuple(config.link_libraries),
    )


def _resolve_under(root: Path, base: Path, rel: Path, *, label: str) -> Path:
    if rel.is_absolute():
        raise CollectionError(f"{label} path must be source-tree relative: {rel}")
    resolved = (base / rel).resolve()
    if not resolved.is_relative_to(root):
        raise CollectionError(
            f"{label} path escapes source tree ({root}): {rel} -> {resolved}"
        )
    return resolved


def _build_source_graph(targets: dict[str, ResolvedTarget]) -> SourceGraph:
    return SourceGraph(
        edges={name: target.sources for name, target in targets.items()},
    )


def _build_link_graph(targets: dict[str, ResolvedTarget]) -> LinkGraph:
    edges: dict[str, frozenset[str]] = {}
    for name, target in targets.items():
        missing = sorted(set(target.link_libraries) - targets.keys())
        if missing:
            raise CollectionError(
                f"target {name!r} links unknown libraries: {', '.join(missing)}"
            )
        if name in target.link_libraries:
            raise CollectionError(f"target {name!r} cannot link against itself")
        edges[name] = frozenset(target.link_libraries)

    graph = LinkGraph(nodes=frozenset(targets), edges=edges)
    try:
        graph.topological_order()
    except ValueError as exc:
        raise CollectionError(str(exc)) from exc
    return graph
