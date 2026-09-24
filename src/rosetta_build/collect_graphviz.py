"""Render a collected source tree as Graphviz DOT."""

from __future__ import annotations

from pathlib import Path

from rosetta_build.collect import Collection
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    ModuleImplementationTarget,
    ModuleInterfaceTarget,
    ModulePartitionTarget,
    NativeTarget,
    StaticLibraryTarget,
    Target,
    WheelTarget,
)

# Distinct styles per connection kind.
_SOURCE_EDGE = 'style=solid,color="#6b7280",arrowhead=vee'
_USAGE_EDGE = 'style=dashed,color="#2563eb",arrowhead=normal'
_STATIC_LINK_EDGE = 'style=dotted,color="#16a34a",arrowhead=normal'
_DYNAMIC_LINK_EDGE = 'style=bold,color="#dc2626",arrowhead=normal'
_MODULE_EDGE = 'style=solid,color="#7c3aed",arrowhead=normal,penwidth=1.5'


def collection_to_dot(collection: Collection) -> str:
    """Return Graphviz DOT for source, usage, link, and module edges."""
    root = collection.source_tree
    lines: list[str] = [
        "digraph Collection {",
        "  rankdir=LR;",
        '  graph [fontname="Helvetica"];',
        '  node [fontname="Helvetica"];',
        '  edge [fontname="Helvetica"];',
        "",
        "  // Target nodes",
    ]

    for name in sorted(collection.targets):
        target = collection.targets[name]
        lines.append(
            f"  {_quote(_target_id(name))} "
            f"[label={_quote(name)},{_target_attrs(target)}];"
        )

    source_nodes: dict[str, str] = {}
    for target_name in sorted(collection.source_graph.edges):
        for source in sorted(collection.source_graph.sources_for(target_name)):
            rel = source.relative_to(root).as_posix()
            source_nodes[_source_id(rel)] = rel

    if source_nodes:
        lines.append("")
        lines.append("  // Source file nodes")
        for node_id, rel in sorted(source_nodes.items(), key=lambda item: item[1]):
            lines.append(
                f"  {_quote(node_id)} "
                f"[label={_quote(rel)},shape=note,style=filled,"
                f'fillcolor="#f3f4f6",color="#9ca3af"];'
            )

    lines.append("")
    lines.append("  // Source edges")
    for target_name in sorted(collection.source_graph.edges):
        for source in sorted(collection.source_graph.sources_for(target_name)):
            rel = source.relative_to(root).as_posix()
            lines.append(
                f"  {_quote(_target_id(target_name))} -> {_quote(_source_id(rel))} "
                f"[{_SOURCE_EDGE}];"
            )

    lines.append("")
    lines.append("  // Usage edges")
    for target_name in sorted(collection.usage_graph.edges):
        for dep in sorted(collection.usage_graph.dependencies_of(target_name)):
            lines.append(
                f"  {_quote(_target_id(target_name))} -> {_quote(_target_id(dep))} "
                f"[{_USAGE_EDGE}];"
            )

    lines.append("")
    lines.append("  // Static link edges")
    for target_name in sorted(collection.targets):
        for dep in sorted(_static_link_deps(collection, target_name)):
            lines.append(
                f"  {_quote(_target_id(target_name))} -> {_quote(_target_id(dep))} "
                f"[{_STATIC_LINK_EDGE}];"
            )

    lines.append("")
    lines.append("  // Dynamic link edges")
    for target_name in sorted(collection.link_graph.edges):
        for dep in sorted(collection.link_graph.dependencies_of(target_name)):
            lines.append(
                f"  {_quote(_target_id(target_name))} -> {_quote(_target_id(dep))} "
                f"[{_DYNAMIC_LINK_EDGE}];"
            )

    lines.append("")
    lines.append("  // Module import edges")
    for target_name in sorted(collection.module_graph.edges):
        for dep in sorted(collection.module_graph.dependencies_of(target_name)):
            lines.append(
                f"  {_quote(_target_id(target_name))} -> {_quote(_target_id(dep))} "
                f"[{_MODULE_EDGE}];"
            )

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def write_collection_dot(collection: Collection, path: Path) -> None:
    """Write ``collection_to_dot`` output to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(collection_to_dot(collection), encoding="utf-8")


def _static_link_deps(collection: Collection, target_name: str) -> frozenset[str]:
    target = collection.targets[target_name]
    if not isinstance(target, NativeTarget):
        return frozenset()
    return frozenset(
        dep
        for dep in target.link_libraries
        if isinstance(collection.targets[dep], StaticLibraryTarget)
    )


def _target_id(name: str) -> str:
    return f"target:{name}"


def _source_id(rel: str) -> str:
    return f"source:{rel}"


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _target_attrs(target: Target) -> str:
    if isinstance(target, ExecutableTarget):
        return 'shape=box,style=filled,fillcolor="#dbeafe",color="#1d4ed8"'
    if isinstance(target, StaticLibraryTarget):
        return 'shape=component,style=filled,fillcolor="#dcfce7",color="#15803d"'
    if isinstance(target, DynamicLibraryTarget):
        return 'shape=hexagon,style=filled,fillcolor="#fee2e2",color="#b91c1c"'
    if isinstance(target, ModuleInterfaceTarget):
        return 'shape=tab,style=filled,fillcolor="#ede9fe",color="#6d28d9"'
    if isinstance(target, ModulePartitionTarget):
        return 'shape=folder,style=filled,fillcolor="#f3e8ff",color="#7e22ce"'
    if isinstance(target, ModuleImplementationTarget):
        return 'shape=parallelogram,style=filled,fillcolor="#fae8ff",color="#a21caf"'
    if isinstance(target, WheelTarget):
        return 'shape=cylinder,style=filled,fillcolor="#fef3c7",color="#b45309"'
    return "shape=ellipse"
