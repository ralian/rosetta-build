"""Tests for compile/link planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.collect import collect
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.plan import PlanError, plan_build
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    ModuleInterfaceTarget,
)

TREES = Path(__file__).parent / "trees"


def test_plan_example_tree_compiles_native_and_wheels(tmp_path: Path) -> None:
    collection = collect(TREES / "example")
    plan = plan_build(collection, build_dir=tmp_path / "build")

    assert plan.family is CompilerFamily.GCC
    targets = {step.target for step in plan.compile_steps}
    assert targets == {"core", "util", "plugin", "hello"}
    assert "example_pkg" not in targets
    assert len(plan.compile_steps) == 4

    assert [step.target for step in plan.wheel_steps] == ["example_pkg"]
    assert plan.wheel_artifact_by_target["example_pkg"].name == (
        "example_pkg-0.0.0-py3-none-any.whl"
    )
    assert plan.sdist_artifact_by_target["example_pkg"].name == (
        "example-pkg-0.0.0.tar.gz"
    )

    link_targets = [step.target for step in plan.link_steps]
    assert link_targets == ["plugin", "hello"]
    assert isinstance(collection.targets["plugin"], DynamicLibraryTarget)
    assert "-shared" in plan.link_steps[0].request.settings.raw_flags

    hello_step = plan.link_steps[1]
    assert hello_step.target == "hello"
    linked = [obj.name.name for obj in hello_step.request.objects]
    assert "main.cpp.o" in linked
    assert "core.cpp.o" in linked
    assert "libplugin.so" in linked


def test_plan_propagates_includes_across_usage(tmp_path: Path) -> None:
    collection = collect(TREES / "example")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    util_step = next(step for step in plan.compile_steps if step.target == "util")
    include_dirs = {path.name for path in util_step.request.settings.include_dirs}
    assert "include" in include_dirs


def test_plan_adds_pic_for_dynamic_library_and_static_deps(tmp_path: Path) -> None:
    collection = collect(TREES / "example")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    plugin = next(step for step in plan.compile_steps if step.target == "plugin")
    core = next(step for step in plan.compile_steps if step.target == "core")
    hello = next(step for step in plan.compile_steps if step.target == "hello")
    assert "-fPIC" in plugin.request.settings.raw_flags
    assert "-fPIC" in core.request.settings.raw_flags
    assert "-fPIC" not in hello.request.settings.raw_flags


def test_plan_modules_orders_bmi_producers_before_consumers(tmp_path: Path) -> None:
    collection = collect(TREES / "build_modules")
    plan = plan_build(collection, build_dir=tmp_path / "build")

    compile_order = [step.target for step in plan.compile_steps]
    assert compile_order.index("math") < compile_order.index("math_impl")
    assert compile_order.index("math") < compile_order.index("app")

    math = next(step for step in plan.compile_steps if step.target == "math")
    assert isinstance(collection.targets["math"], ModuleInterfaceTarget)
    assert math.request.bmi_output == tmp_path / "build" / "bmi" / "math.gcm"
    assert math.request.settings.standard is not None

    app = next(step for step in plan.compile_steps if step.target == "app")
    assert [bmi.module for bmi in app.request.bmi_inputs] == ["math"]

    assert [step.target for step in plan.link_steps] == ["app"]
    app_link = plan.link_steps[0]
    linked = [obj.name.name for obj in app_link.request.objects]
    assert "main.cpp.o" in linked
    assert "math.cpp.o" in linked
    assert "math.cppm.o" in linked


def test_plan_cxx_modules_tree_includes_partitions(tmp_path: Path) -> None:
    collection = collect(TREES / "cxx_modules")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    compile_order = [step.target for step in plan.compile_steps]
    assert compile_order.index("math") < compile_order.index("math_detail")
    assert "detail.cppm.o" in [
        obj.name.name for obj in plan.link_steps[0].request.objects
    ]


def test_plan_rejects_non_gcc_family(tmp_path: Path) -> None:
    collection = collect(TREES / "example")
    with pytest.raises(PlanError, match="only gcc"):
        plan_build(
            collection,
            build_dir=tmp_path / "build",
            family=CompilerFamily.CLANG,
        )


def test_compile_steps_are_cxx(tmp_path: Path) -> None:
    collection = collect(TREES / "example")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    assert all(step.language is Language.CXX for step in plan.compile_steps)
    assert isinstance(collection.targets["hello"], ExecutableTarget)
