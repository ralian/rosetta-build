from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.collect import CollectionError, collect


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_source_tree(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    _write(
        root / "pyproject.toml",
        """\
[project]
name = "example"
version = "0.0.0"

[tool.rosetta-build]
targets = [
  "libs/core/target.toml",
  "apps/hello/target.toml",
]
""",
    )
    _write(
        root / "libs/core/target.toml",
        """\
name = "core"
sources = ["core.cpp"]
include_dirs = ["include"]
compile_opts = ["-Wall"]
""",
    )
    _write(root / "libs/core/core.cpp", "int core() { return 1; }\n")
    _write(root / "libs/core/include/core.h", "#pragma once\n")
    _write(
        root / "apps/hello/target.toml",
        """\
name = "hello"
sources = ["main.cpp"]
link_libraries = ["core"]
""",
    )
    _write(root / "apps/hello/main.cpp", "int main() { return 0; }\n")
    return root


def test_collect_builds_source_and_link_graphs(tmp_path: Path) -> None:
    root = _make_source_tree(tmp_path)
    collection = collect(root)

    assert set(collection.targets) == {"core", "hello"}
    assert collection.source_graph.sources_for("core") == {
        (root / "libs/core/core.cpp").resolve()
    }
    assert collection.link_graph.dependencies_of("hello") == frozenset({"core"})
    assert collection.link_graph.dependencies_of("core") == frozenset()
    assert collection.link_graph.topological_order() == ["core", "hello"]


def test_collect_rejects_unknown_link_library(tmp_path: Path) -> None:
    root = _make_source_tree(tmp_path)
    _write(
        root / "apps/hello/target.toml",
        """\
name = "hello"
sources = ["main.cpp"]
link_libraries = ["missing"]
""",
    )
    with pytest.raises(CollectionError, match="unknown libraries"):
        collect(root)


def test_collect_rejects_link_cycle(tmp_path: Path) -> None:
    root = tmp_path / "cycle"
    _write(
        root / "pyproject.toml",
        """\
[tool.rosetta-build]
targets = ["a/target.toml", "b/target.toml"]
""",
    )
    _write(
        root / "a/target.toml",
        """\
name = "a"
link_libraries = ["b"]
""",
    )
    _write(
        root / "b/target.toml",
        """\
name = "b"
link_libraries = ["a"]
""",
    )
    with pytest.raises(CollectionError, match="cycle"):
        collect(root)


def test_collect_requires_pyproject(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(CollectionError, match="missing root pyproject.toml"):
        collect(empty)
