"""Command-line interface for rosetta-build."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rosetta_build.collect import Collection, CollectionError, collect
from rosetta_build.collect_graphviz import write_collection_dot
from rosetta_build.execute import BuildError, run_build, run_link
from rosetta_build.language import CompilerFamily
from rosetta_build.plan import BuildPlan, PlanError, plan_build
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    ModuleImplementationTarget,
    ModuleInterfaceTarget,
    ModulePartitionTarget,
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
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="")
        raise SystemExit(exc.returncode or 1) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rosetta-build",
        description="Experimental multilanguage build tool.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect",
        help=(
            "Load and validate targets, then build source, usage, link, "
            "and module graphs."
        ),
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

    build_parser = subparsers.add_parser(
        "build",
        help=(
            "Compile native/module targets and build wheel/sdist targets "
            "(GCC/g++ for native for now)."
        ),
    )
    _add_build_args(build_parser)
    build_parser.set_defaults(handler=_cmd_build)

    link_parser = subparsers.add_parser(
        "link",
        help="Link compiled objects into libraries and executables.",
    )
    _add_build_args(link_parser)
    link_parser.set_defaults(handler=_cmd_link)

    install_parser = subparsers.add_parser(
        "install",
        help="Install build artifacts (not yet implemented).",
    )
    install_parser.set_defaults(handler=_cmd_not_implemented, step_name="install")

    return parser


def _add_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source_tree",
        type=Path,
        help="Source tree root containing pyproject.toml.",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="Build output directory (default: <source_tree>/build).",
    )
    parser.add_argument(
        "--family",
        type=str,
        default=CompilerFamily.GCC.value,
        choices=[family.value for family in CompilerFamily],
        help="Compiler family (default: gcc).",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        metavar="N",
        help="Parallel edge jobs (default: CPU count).",
    )
    parser.add_argument(
        "-B",
        "--force",
        action="store_true",
        help="Rebuild all edges, ignoring freshness.",
    )


def _cmd_collect(args: argparse.Namespace) -> int:
    collection = collect(args.source_tree)
    _print_collection(collection)
    if args.graphviz is not None:
        write_collection_dot(collection, args.graphviz)
        print(f"wrote graphviz: {args.graphviz}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    result = asyncio.run(run_build(plan, jobs=args.jobs, force=args.force))
    compiles = result.compiles
    wheels = result.wheels
    print(
        f"compiled {compiles.ran}/{compiles.ran + compiles.skipped} "
        f"translation unit(s) (skipped {compiles.skipped})"
    )
    print(
        f"built {wheels.ran}/{wheels.ran + wheels.skipped} "
        f"wheel/sdist target(s) (skipped {wheels.skipped})"
    )
    for name, path in sorted(plan.wheel_artifact_by_target.items()):
        print(f"  wheel {name}: {path}")
    for name, path in sorted(plan.sdist_artifact_by_target.items()):
        print(f"  sdist {name}: {path}")
    return 0


def _cmd_link(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    result = asyncio.run(run_link(plan, jobs=args.jobs, force=args.force))
    links = result.links
    print(
        f"linked {links.ran}/{links.ran + links.skipped} "
        f"artifact(s) (skipped {links.skipped})"
    )
    for name, path in sorted(plan.link_artifact_by_target.items()):
        print(f"  {name}: {path}")
    return 0


def _plan_from_args(args: argparse.Namespace) -> BuildPlan:
    collection = collect(args.source_tree)
    build_dir = args.build_dir
    if build_dir is None:
        build_dir = collection.source_tree / "build"
    return plan_build(
        collection,
        build_dir=build_dir,
        family=CompilerFamily(args.family),
    )


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
        module_imports = collection.module_graph.dependencies_of(name)
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
        print(f"    module deps ({len(module_imports)}):")
        for dep in sorted(module_imports):
            print(f"      {dep}")
        exports = collection.module_exports.get(name, frozenset())
        if exports:
            print(f"    module exports ({len(exports)}):")
            for exported in sorted(exports):
                print(f"      {exported}")
    print("dynamic link order:")
    for name in collection.link_graph.topological_order(kind="dynamic link"):
        print(f"  {name}")
    print("module order:")
    for name in collection.module_graph.topological_order(kind="module"):
        print(f"  {name}")


def _target_kind(target: Target) -> str:
    if isinstance(target, ExecutableTarget):
        return "executable"
    if isinstance(target, StaticLibraryTarget):
        return "static_library"
    if isinstance(target, DynamicLibraryTarget):
        return "dynamic_library"
    if isinstance(target, ModuleInterfaceTarget):
        return "module_interface"
    if isinstance(target, ModulePartitionTarget):
        return "module_partition"
    if isinstance(target, ModuleImplementationTarget):
        return "module_implementation"
    if isinstance(target, WheelTarget):
        return "wheel"
    return type(target).__name__
