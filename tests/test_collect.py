from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.collect import CollectionError, collect
from rosetta_build.language import Language
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    ModuleImplementationTarget,
    ModuleInterfaceTarget,
    ModulePartitionTarget,
    PackageArtifact,
    StaticLibraryTarget,
    WheelTarget,
)

TREES = Path(__file__).parent / "trees"


def test_collect_builds_source_usage_and_link_graphs() -> None:
    root = TREES / "example"
    collection = collect(root)

    assert set(collection.targets) == {
        "core",
        "util",
        "plugin",
        "hello",
        "example_pkg",
    }
    assert isinstance(collection.targets["core"], StaticLibraryTarget)
    assert isinstance(collection.targets["util"], StaticLibraryTarget)
    assert isinstance(collection.targets["plugin"], DynamicLibraryTarget)
    assert isinstance(collection.targets["hello"], ExecutableTarget)
    assert isinstance(collection.targets["example_pkg"], WheelTarget)

    assert collection.source_graph.sources_for("core") == {
        (root / "libs/core/core.cpp").resolve()
    }

    assert collection.usage_graph.dependencies_of("core") == frozenset({"util"})
    assert collection.usage_graph.dependencies_of("util") == frozenset({"core"})

    assert collection.link_graph.dependencies_of("hello") == frozenset({"plugin"})
    assert collection.link_graph.dependencies_of("plugin") == frozenset()
    assert collection.link_graph.dependencies_of("core") == frozenset()
    assert collection.link_graph.topological_order(kind="dynamic link") == [
        "core",
        "example_pkg",
        "plugin",
        "util",
        "hello",
    ]
    assert collection.module_graph.dependencies_of("hello") == frozenset()

    wheel = collection.targets["example_pkg"]
    assert isinstance(wheel, WheelTarget)
    assert wheel.artifacts == [
        PackageArtifact(
            target="plugin",
            dest=Path("example_pkg"),
            headers=True,
            debug_symbols=False,
        ),
        PackageArtifact(
            target="hello",
            dest=Path("example_pkg/bin"),
            headers=False,
            debug_symbols=True,
        ),
    ]
    assert collection.package_graph.dependencies_of("example_pkg") == frozenset({
        "plugin",
        "hello",
    })
    assert collection.package_graph.dependencies_of("plugin") == frozenset()
    order = collection.package_graph.topological_order(kind="package")
    assert order.index("plugin") < order.index("example_pkg")
    assert order.index("hello") < order.index("example_pkg")


def test_collect_builds_module_graph() -> None:
    root = TREES / "cxx_modules"
    collection = collect(root)

    assert isinstance(collection.targets["math"], ModuleInterfaceTarget)
    assert isinstance(collection.targets["math_detail"], ModulePartitionTarget)
    assert isinstance(collection.targets["math_impl"], ModuleImplementationTarget)
    assert isinstance(collection.targets["app"], ExecutableTarget)

    math = collection.targets["math"]
    assert isinstance(math, ModuleInterfaceTarget)
    assert math.module == "math"
    assert math.language is Language.CXX

    detail = collection.targets["math_detail"]
    assert isinstance(detail, ModulePartitionTarget)
    assert detail.module == "math"
    assert detail.partition == "detail"

    app = collection.targets["app"]
    assert isinstance(app, ExecutableTarget)
    assert app.module_visibility == {"math"}

    assert collection.module_exports == {
        "math": frozenset({"math"}),
        "math_detail": frozenset({"math:detail"}),
    }

    assert collection.module_graph.dependencies_of("math") == frozenset()
    assert collection.module_graph.dependencies_of("math_detail") == frozenset({"math"})
    assert collection.module_graph.dependencies_of("math_impl") == frozenset({
        "math",
        "math_detail",
    })
    assert collection.module_graph.dependencies_of("app") == frozenset({"math"})
    order = collection.module_graph.topological_order(kind="module")
    assert order.index("math") < order.index("app")
    assert order.index("math") < order.index("math_detail")
    assert order.index("math") < order.index("math_impl")
    assert order.index("math_detail") < order.index("math_impl")


def test_collect_rejects_module_visibility_to_non_exporter() -> None:
    with pytest.raises(CollectionError, match="must name module exporters"):
        collect(TREES / "visibility_non_exporter")


def test_collect_allows_static_link_cycles() -> None:
    collection = collect(TREES / "static_link_cycle")
    assert collection.link_graph.dependencies_of("a") == frozenset()
    assert collection.link_graph.dependencies_of("b") == frozenset()


def test_collect_rejects_dynamic_link_cycle() -> None:
    with pytest.raises(CollectionError, match="dynamic link dependency cycle"):
        collect(TREES / "dynamic_link_cycle")


def test_collect_rejects_module_cycle() -> None:
    with pytest.raises(CollectionError, match="module dependency cycle"):
        collect(TREES / "module_cycle")


def test_collect_rejects_duplicate_module_interface() -> None:
    with pytest.raises(CollectionError, match="multiple interface targets"):
        collect(TREES / "duplicate_module_interface")


def test_collect_rejects_missing_module_interface() -> None:
    with pytest.raises(CollectionError, match="has no module_interface target"):
        collect(TREES / "missing_module_interface")


def test_collect_rejects_non_module_import() -> None:
    with pytest.raises(CollectionError, match="must name module targets"):
        collect(TREES / "non_module_import")


def test_collect_rejects_unknown_package_artifact() -> None:
    with pytest.raises(CollectionError, match="unknown package targets"):
        collect(TREES / "unknown_package")


def test_collect_rejects_non_packable_package_artifact() -> None:
    with pytest.raises(CollectionError, match="must name dynamic_library"):
        collect(TREES / "invalid_package_type")


def test_collect_rejects_invalid_package_dest(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    (root / "python" / "pkg" / "src" / "pkg").mkdir(parents=True)
    (root / "apps" / "hello").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "pkg"\n'
        'version = "0.0.0"\n'
        "\n"
        "[tool.rosetta-build]\n"
        'targets = ["apps/hello/target.toml", "python/pkg/target.toml"]\n',
        encoding="utf-8",
    )
    (root / "apps" / "hello" / "target.toml").write_text(
        'type = "executable"\n'
        'language = "cxx"\n'
        'name = "hello"\n'
        'sources = ["main.cpp"]\n',
        encoding="utf-8",
    )
    (root / "apps" / "hello" / "main.cpp").write_text(
        "int main() { return 0; }\n",
        encoding="utf-8",
    )
    (root / "python" / "pkg" / "src" / "pkg" / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (root / "python" / "pkg" / "target.toml").write_text(
        'type = "wheel"\n'
        'name = "pkg"\n'
        'sources = ["src/pkg"]\n'
        'artifacts = [{ target = "hello", dest = "../escape" }]\n',
        encoding="utf-8",
    )
    with pytest.raises(CollectionError, match="must not contain '\\.\\.'"):
        collect(root)


def test_collect_rejects_duplicate_package_artifact(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    (root / "python" / "pkg" / "src" / "pkg").mkdir(parents=True)
    (root / "apps" / "hello").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "pkg"\n'
        'version = "0.0.0"\n'
        "\n"
        "[tool.rosetta-build]\n"
        'targets = ["apps/hello/target.toml", "python/pkg/target.toml"]\n',
        encoding="utf-8",
    )
    (root / "apps" / "hello" / "target.toml").write_text(
        'type = "executable"\n'
        'language = "cxx"\n'
        'name = "hello"\n'
        'sources = ["main.cpp"]\n',
        encoding="utf-8",
    )
    (root / "apps" / "hello" / "main.cpp").write_text(
        "int main() { return 0; }\n",
        encoding="utf-8",
    )
    (root / "python" / "pkg" / "src" / "pkg" / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (root / "python" / "pkg" / "target.toml").write_text(
        'type = "wheel"\n'
        'name = "pkg"\n'
        'sources = ["src/pkg"]\n'
        'artifacts = ["hello", "hello"]\n',
        encoding="utf-8",
    )
    with pytest.raises(CollectionError, match="duplicate package artifact"):
        collect(root)


def test_collect_rejects_native_fields_on_wheel() -> None:
    with pytest.raises(CollectionError, match="invalid target config"):
        collect(TREES / "invalid_wheel")


def test_collect_rejects_unknown_link_library() -> None:
    with pytest.raises(CollectionError, match="unknown link targets"):
        collect(TREES / "unknown_link")


def test_collect_requires_pyproject() -> None:
    with pytest.raises(CollectionError, match="missing root pyproject.toml"):
        collect(TREES / "missing_pyproject")
