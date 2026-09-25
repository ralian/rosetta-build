"""Tests for wheel/sdist planning and execution."""

from __future__ import annotations

import asyncio
import tarfile
import zipfile
from pathlib import Path

from rosetta_build.collect import collect
from rosetta_build.execute import run_build
from rosetta_build.plan import plan_build

TREES = Path(__file__).parent / "trees"


def test_plan_wheel_tree(tmp_path: Path) -> None:
    collection = collect(TREES / "build_wheel")
    plan = plan_build(collection, build_dir=tmp_path / "build")

    assert plan.compile_steps == ()
    assert plan.link_steps == ()
    assert len(plan.wheel_steps) == 1
    step = plan.wheel_steps[0]
    assert step.target == "example_pkg"
    assert step.request.version == "1.2.3"
    assert step.request.metadata.summary == "Wheel build fixture"
    assert step.request.metadata.requires_python == ">=3.14"
    assert step.request.metadata.license_expression == "MIT"
    assert plan.wheel_artifact_by_target["example_pkg"] == (
        tmp_path / "build" / "wheels" / "example_pkg-1.2.3-py3-none-any.whl"
    )
    assert plan.sdist_artifact_by_target["example_pkg"] == (
        tmp_path / "build" / "sdists" / "example-pkg-1.2.3.tar.gz"
    )


def test_build_wheel_and_sdist(tmp_path: Path) -> None:
    collection = collect(TREES / "build_wheel")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    asyncio.run(run_build(plan))

    wheel = plan.wheel_artifact_by_target["example_pkg"]
    sdist = plan.sdist_artifact_by_target["example_pkg"]
    assert wheel.is_file()
    assert sdist.is_file()

    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        assert "example_pkg/__init__.py" in names
        assert "example_pkg-1.2.3.dist-info/METADATA" in names
        assert "example_pkg-1.2.3.dist-info/WHEEL" in names
        assert "example_pkg-1.2.3.dist-info/RECORD" in names
        metadata = zf.read("example_pkg-1.2.3.dist-info/METADATA").decode()
        assert "Name: example_pkg" in metadata
        assert "Version: 1.2.3" in metadata
        assert "License-Expression: MIT" in metadata
        assert "example_pkg-1.2.3.dist-info/entry_points.txt" in names
        assert "example_pkg-1.2.3.dist-info/licenses/LICENSE" in names
        wheel_text = zf.read("example_pkg-1.2.3.dist-info/WHEEL").decode()
        assert "Root-Is-Purelib: true" in wheel_text
        assert "Tag: py3-none-any" in wheel_text

    with tarfile.open(sdist, "r:gz") as tf:
        names = set(tf.getnames())
        assert "example-pkg-1.2.3/PKG-INFO" in names
        assert "example-pkg-1.2.3/pyproject.toml" in names
        assert "example-pkg-1.2.3/README.md" in names
        assert "example-pkg-1.2.3/LICENSE" in names
        assert "example-pkg-1.2.3/python/pkg/target.toml" in names
        assert "example-pkg-1.2.3/python/pkg/src/example_pkg/__init__.py" in names
        pkg_info = tf.extractfile("example-pkg-1.2.3/PKG-INFO")
        assert pkg_info is not None
        text = pkg_info.read().decode()
        assert "Name: example_pkg" in text
        assert "Version: 1.2.3" in text
        assert "License-File: LICENSE" in text


def test_sdist_round_trip_rebuilds_wheel(tmp_path: Path) -> None:
    collection = collect(TREES / "build_wheel")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    asyncio.run(run_build(plan))
    sdist = plan.sdist_artifact_by_target["example_pkg"]

    unpack = tmp_path / "unpack"
    unpack.mkdir()
    with tarfile.open(sdist, "r:gz") as tf:
        tf.extractall(unpack, filter="data")
    source_root = unpack / "example-pkg-1.2.3"
    assert (source_root / "pyproject.toml").is_file()
    assert (source_root / "python/pkg/target.toml").is_file()

    rebuilt = plan_build(collect(source_root), build_dir=tmp_path / "rebuild")
    asyncio.run(run_build(rebuilt))
    wheel = rebuilt.wheel_artifact_by_target["example_pkg"]
    assert wheel.is_file()
    with zipfile.ZipFile(wheel) as zf:
        assert "example_pkg/__init__.py" in zf.namelist()
