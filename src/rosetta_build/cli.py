"""Command-line interface for rosetta-build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rosetta_build.collect import Collection, CollectionError, collect


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
        help="Load and validate targets, then build source and link graphs.",
    )
    collect_parser.add_argument(
        "source_tree",
        type=Path,
        help="Source tree root containing pyproject.toml.",
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
        links = collection.link_graph.dependencies_of(name)
        print(f"  {name}")
        print(f"    config: {target.config_path}")
        print(f"    sources ({len(sources)}):")
        for source in sorted(sources):
            print(f"      {source.relative_to(collection.source_tree)}")
        print(f"    link libraries ({len(links)}):")
        for lib in sorted(links):
            print(f"      {lib}")
    print("link order:")
    for name in collection.link_graph.topological_order():
        print(f"  {name}")
