"""End-to-end build/link execution via the planner (GCC/g++)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from rosetta_build.collect import collect
from rosetta_build.execute import run_build, run_link
from rosetta_build.plan import plan_build

TREES = Path(__file__).parent / "trees"

pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")


def test_build_and_link_non_module_tree(tmp_path: Path) -> None:
    collection = collect(TREES / "build_non_modules")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    asyncio.run(run_build(plan))
    asyncio.run(run_link(plan))

    exe = plan.link_artifact_by_target["hello"]
    assert exe.is_file()
    assert asyncio.run(_run([str(exe)])) == 0


def test_build_and_link_module_tree(tmp_path: Path) -> None:
    collection = collect(TREES / "build_modules")
    build_dir = tmp_path / "build"
    plan = plan_build(collection, build_dir=build_dir)
    asyncio.run(run_build(plan))
    asyncio.run(run_link(plan))

    exe = plan.link_artifact_by_target["app"]
    assert exe.is_file()
    assert (build_dir / "bmi" / "math.gcm").is_file()
    assert asyncio.run(_run([str(exe)])) == 0


async def _run(argv: list[str]) -> int:
    process = await asyncio.create_subprocess_exec(*argv)
    return await process.wait()
