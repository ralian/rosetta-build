"""Command-line interface for rosetta-build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rosetta_build.collect import Collection, CollectionError, collect
from rosetta_build.collect_graphviz import write_collection_dot
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    StaticLibraryTarget,
    Target,
    WheelTarget,
)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(args.handler(args))
    except CollectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rosetta-build",
        description="Experimental multilanguage build tool.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect",
        help="Load and validate targets, then build source, usage, and link graphs.",
    )
    collect_parser.add_argument(
        "source_tree",
        type=Path,
        help="Source tree root containing pyproject.toml.",
    )
    collect_parser.add_argument(
        "--graphviz",
        type=Path,
        metavar="OUT",
        help="Write Graphviz DOT for the collected graphs to OUT.",
    )
    collect_parser.set_defaults(handler=_cmd_collect)

    for name, help_text in (
        ("build", "Compile collected targets (not yet implemented)."),
        ("link", "Link compiled objects (not yet implemented)."),
        ("install", "Install build artifacts (not yet implemented)."),
    ):
        step = subparsers.add_parser(name, help=help_text)
        step.set_defaults(handler=_cmd_not_implemented, step_name=name)

    return parser


def _cmd_collect(args: argparse.Namespace) -> int:
    collection = collect(args.source_tree)
    _print_collection(collection)
    if args.graphviz is not None:
        write_collection_dot(collection, args.graphviz)
        print(f"wrote graphviz: {args.graphviz}")
    return 0


def _cmd_not_implemented(args: argparse.Namespace) -> int:
    print(f"error: '{args.step_name}' is not implemented yet", file=sys.stderr)
    return 1


def _print_collection(collection: Collection) -> None:
    print(f"source tree: {collection.source_tree}")
    print(f"targets: {len(collection.targets)}")
    for name in sorted(collection.targets):
        target = collection.targets[name]
        sources = collection.source_graph.sources_for(name)
        usage = collection.usage_graph.dependencies_of(name)
        links = collection.link_graph.dependencies_of(name)
        print(f"  {name} ({_target_kind(target)})")
        print(f"    config: {target.config_path}")
        print(f"    sources ({len(sources)}):")
        for source in sorted(sources):
            print(f"      {source.relative_to(collection.source_tree)}")
        print(f"    usage ({len(usage)}):")
        for dep in sorted(usage):
            print(f"      {dep}")
        print(f"    dynamic link libraries ({len(links)}):")
        for lib in sorted(links):
            print(f"      {lib}")
    print("dynamic link order:")
    for name in collection.link_graph.topological_order(kind="dynamic link"):
        print(f"  {name}")


def _target_kind(target: Target) -> str:
    if isinstance(target, ExecutableTarget):
        return "executable"
    if isinstance(target, StaticLibraryTarget):
        return "static_library"
    if isinstance(target, DynamicLibraryTarget):
        return "dynamic_library"
    if isinstance(target, WheelTarget):
        return "wheel"
    return type(target).__name__
