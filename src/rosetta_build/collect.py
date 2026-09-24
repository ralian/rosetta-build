"""Collect targets from a source tree and build dependency graphs."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from rosetta_build.graph import LinkGraph, ModuleGraph, SourceGraph, UsageGraph
from rosetta_build.schema import (
    DynamicLibraryTargetConfig,
    ExecutableTargetConfig,
    ModuleImplementationTargetConfig,
    ModuleInterfaceTargetConfig,
    ModulePartitionTargetConfig,
    RosettaBuildConfig,
    StaticLibraryTargetConfig,
    TargetConfig,
    WheelTargetConfig,
    parse_target_config,
)
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    ModuleImplementationTarget,
    ModuleInterfaceTarget,
    ModulePartitionTarget,
    ModuleTarget,
    NativeTarget,
    StaticLibraryTarget,
    Target,
    WheelTarget,
)

TOOL_TABLE = "rosetta-build"


class CollectionError(Exception):
    """Raised when collection fails due to invalid config or references."""


class Collection(BaseModel):
    """Result of collecting and validating a source tree."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    source_tree: Path
    targets: dict[str, Target]
    source_graph: SourceGraph
    usage_graph: UsageGraph
    link_graph: LinkGraph
    module_graph: ModuleGraph
    # Target name -> logical module names it exports (``M`` or ``M:part``).
    module_exports: dict[str, frozenset[str]]


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
    usage_graph = _build_usage_graph(resolved_targets)
    link_graph = _build_link_graph(resolved_targets)
    module_exports = _module_exports_map(resolved_targets)
    module_graph = _build_module_graph(resolved_targets, module_exports)
    return Collection(
        source_tree=root,
        targets=resolved_targets,
        source_graph=source_graph,
        usage_graph=usage_graph,
        link_graph=link_graph,
        module_graph=module_graph,
        module_exports=module_exports,
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


def _load_targets(root: Path, target_paths: list[Path]) -> dict[str, Target]:
    if not target_paths:
        raise CollectionError(
            "no target files listed under [tool.rosetta-build].targets"
        )

    resolved: dict[str, Target] = {}
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


def _load_target(root: Path, config_path: Path) -> Target:
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    try:
        config = parse_target_config(raw)
    except ValidationError as exc:
        raise CollectionError(f"invalid target config {config_path}:\n{exc}") from exc
    return _resolve_target(root, config_path, config)


def _resolve_target(root: Path, config_path: Path, config: TargetConfig) -> Target:
    base = config_path.parent
    sources = {
        _resolve_under(root, base, path, label="source") for path in config.sources
    }

    if isinstance(config, WheelTargetConfig):
        return WheelTarget(name=config.name, sources=sources, config_path=config_path)

    include_dirs = {
        _resolve_under(root, base, path, label="include dir")
        for path in config.include_dirs
    }
    if isinstance(config, ExecutableTargetConfig):
        return ExecutableTarget(
            name=config.name,
            sources=sources,
            config_path=config_path,
            language=config.language,
            include_dirs=include_dirs,
            compile_defs=dict(config.compile_defs),
            compile_opts=list(config.compile_opts),
            link_opts=list(config.link_opts),
            usage=set(config.usage),
            link_libraries=set(config.link_libraries),
            module_visibility=set(config.module_visibility),
        )
    if isinstance(config, StaticLibraryTargetConfig):
        return StaticLibraryTarget(
            name=config.name,
            sources=sources,
            config_path=config_path,
            language=config.language,
            include_dirs=include_dirs,
            compile_defs=dict(config.compile_defs),
            compile_opts=list(config.compile_opts),
            link_opts=list(config.link_opts),
            usage=set(config.usage),
            link_libraries=set(config.link_libraries),
            module_visibility=set(config.module_visibility),
        )
    if isinstance(config, DynamicLibraryTargetConfig):
        return DynamicLibraryTarget(
            name=config.name,
            sources=sources,
            config_path=config_path,
            language=config.language,
            include_dirs=include_dirs,
            compile_defs=dict(config.compile_defs),
            compile_opts=list(config.compile_opts),
            link_opts=list(config.link_opts),
            usage=set(config.usage),
            link_libraries=set(config.link_libraries),
            module_visibility=set(config.module_visibility),
        )
    if isinstance(config, ModuleInterfaceTargetConfig):
        return ModuleInterfaceTarget(
            name=config.name,
            sources=sources,
            config_path=config_path,
            language=config.language,
            include_dirs=include_dirs,
            compile_defs=dict(config.compile_defs),
            compile_opts=list(config.compile_opts),
            link_opts=list(config.link_opts),
            usage=set(config.usage),
            link_libraries=set(config.link_libraries),
            module_visibility=set(config.module_visibility),
            module=config.module,
            imports=set(config.imports),
        )
    if isinstance(config, ModulePartitionTargetConfig):
        return ModulePartitionTarget(
            name=config.name,
            sources=sources,
            config_path=config_path,
            language=config.language,
            include_dirs=include_dirs,
            compile_defs=dict(config.compile_defs),
            compile_opts=list(config.compile_opts),
            link_opts=list(config.link_opts),
            usage=set(config.usage),
            link_libraries=set(config.link_libraries),
            module_visibility=set(config.module_visibility),
            module=config.module,
            partition=config.partition,
            imports=set(config.imports),
        )
    if isinstance(config, ModuleImplementationTargetConfig):
        return ModuleImplementationTarget(
            name=config.name,
            sources=sources,
            config_path=config_path,
            language=config.language,
            include_dirs=include_dirs,
            compile_defs=dict(config.compile_defs),
            compile_opts=list(config.compile_opts),
            link_opts=list(config.link_opts),
            usage=set(config.usage),
            link_libraries=set(config.link_libraries),
            module_visibility=set(config.module_visibility),
            module=config.module,
            imports=set(config.imports),
        )
    raise CollectionError(f"unsupported target type in {config_path}")


def _resolve_under(root: Path, base: Path, rel: Path, *, label: str) -> Path:
    if rel.is_absolute():
        raise CollectionError(f"{label} path must be source-tree relative: {rel}")
    resolved = (base / rel).resolve()
    if not resolved.is_relative_to(root):
        raise CollectionError(
            f"{label} path escapes source tree ({root}): {rel} -> {resolved}"
        )
    return resolved


def _build_source_graph(targets: dict[str, Target]) -> SourceGraph:
    return SourceGraph(
        edges={name: frozenset(target.sources) for name, target in targets.items()},
    )


def _validate_refs(
    target_name: str,
    refs: set[str],
    targets: dict[str, Target],
    *,
    label: str,
) -> None:
    missing = sorted(refs - targets.keys())
    if missing:
        raise CollectionError(
            f"target {target_name!r} references unknown {label} targets: "
            f"{', '.join(missing)}"
        )
    if target_name in refs:
        raise CollectionError(
            f"target {target_name!r} cannot reference itself as a {label} dependency"
        )


def _build_usage_graph(targets: dict[str, Target]) -> UsageGraph:
    edges: dict[str, frozenset[str]] = {}
    for name, target in targets.items():
        usage = target.usage if isinstance(target, NativeTarget) else set()
        _validate_refs(name, usage, targets, label="usage")
        edges[name] = frozenset(usage)
    return UsageGraph(nodes=frozenset(targets), edges=edges)


def _build_link_graph(targets: dict[str, Target]) -> LinkGraph:
    """Build the hard dynamic-link DAG.

    An edge ``A -> B`` is recorded only when ``A`` lists ``B`` in
    ``link_libraries`` and ``B`` is a ``DynamicLibraryTarget``. Static and
    other link refs remain on the target but are not cycle-checked here.
    """
    edges: dict[str, frozenset[str]] = {}
    for name, target in targets.items():
        link_libraries = (
            target.link_libraries if isinstance(target, NativeTarget) else set()
        )
        _validate_refs(name, link_libraries, targets, label="link")
        dynamic_deps = frozenset(
            dep
            for dep in link_libraries
            if isinstance(targets[dep], DynamicLibraryTarget)
        )
        edges[name] = dynamic_deps

    graph = LinkGraph(nodes=frozenset(targets), edges=edges)
    try:
        graph.topological_order(kind="dynamic link")
    except ValueError as exc:
        raise CollectionError(str(exc)) from exc
    return graph


def _logical_exports(target: Target) -> frozenset[str]:
    """Return logical module names exported by ``target`` (BMI providers only)."""
    if isinstance(target, ModuleInterfaceTarget):
        return frozenset({target.module})
    if isinstance(target, ModulePartitionTarget):
        return frozenset({f"{target.module}:{target.partition}"})
    return frozenset()


def _module_exports_map(targets: dict[str, Target]) -> dict[str, frozenset[str]]:
    return {
        name: exports
        for name, target in targets.items()
        if (exports := _logical_exports(target))
    }


def _build_module_graph(
    targets: dict[str, Target],
    module_exports: dict[str, frozenset[str]],
) -> ModuleGraph:
    """Build the C++ module BMI DAG from ``imports`` and ``module_visibility``.

    - ``imports`` on module targets order BMI production among module units.
    - ``module_visibility`` on any native target names exporters whose modules
      the target may ``import`` (explicit cross-target visibility; not ``usage``).
    """
    interfaces_by_module: dict[str, list[str]] = {}
    for name, target in targets.items():
        if isinstance(target, ModuleInterfaceTarget):
            interfaces_by_module.setdefault(target.module, []).append(name)

    for module_name, providers in sorted(interfaces_by_module.items()):
        if len(providers) > 1:
            raise CollectionError(
                f"logical module {module_name!r} has multiple interface targets: "
                f"{', '.join(sorted(providers))}"
            )

    edges: dict[str, frozenset[str]] = {name: frozenset() for name in targets}
    for name, target in targets.items():
        deps: set[str] = set()

        if isinstance(target, ModuleTarget):
            if (
                not isinstance(target, ModuleInterfaceTarget)
                and target.module not in interfaces_by_module
            ):
                raise CollectionError(
                    f"target {name!r} refers to logical module {target.module!r} "
                    f"which has no module_interface target"
                )

            imports = set(target.imports)
            _validate_refs(name, imports, targets, label="module import")
            non_module = sorted(
                dep for dep in imports if not isinstance(targets[dep], ModuleTarget)
            )
            if non_module:
                raise CollectionError(
                    f"target {name!r} module imports must name module targets; "
                    f"not module targets: {', '.join(non_module)}"
                )
            deps |= imports

        if isinstance(target, NativeTarget):
            visibility = set(target.module_visibility)
            _validate_refs(name, visibility, targets, label="module visibility")
            non_exporters = sorted(
                dep for dep in visibility if dep not in module_exports
            )
            if non_exporters:
                raise CollectionError(
                    f"target {name!r} module_visibility must name module exporters "
                    f"(module_interface or module_partition); "
                    f"not exporters: {', '.join(non_exporters)}"
                )
            deps |= visibility

        edges[name] = frozenset(deps)

    graph = ModuleGraph(nodes=frozenset(targets), edges=edges)
    try:
        graph.topological_order(kind="module")
    except ValueError as exc:
        raise CollectionError(str(exc)) from exc
    return graph
