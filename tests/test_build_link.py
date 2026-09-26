"""End-to-end build/link execution via the planner (GCC/g++)."""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

from rosetta_build.collect import collect
from rosetta_build.execute import run_build, run_link
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.plan import plan_build
from tests.conftest import requires_compiler, requires_gcc_fmodules

TREES = Path(__file__).parent / "trees"

pytestmark = requires_compiler(CompilerFamily.GCC, Language.CXX)


def test_build_and_link_non_module_tree(tmp_path: Path) -> None:
    collection = collect(TREES / "build_non_modules")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    asyncio.run(run_build(plan))
    asyncio.run(run_link(plan))

    exe = plan.link_artifact_by_target["hello"]
    assert exe.is_file()
    assert asyncio.run(_run([str(exe)])) == 0


@requires_gcc_fmodules()
def test_build_and_link_module_tree(tmp_path: Path) -> None:
    collection = collect(TREES / "build_modules")
    build_dir = tmp_path / "build"
    plan = plan_build(collection, build_dir=build_dir)
    asyncio.run(run_build(plan, jobs=4))
    asyncio.run(run_link(plan, jobs=4))

    exe = plan.link_artifact_by_target["app"]
    assert exe.is_file()
    assert (build_dir / "bmi" / "math.gcm").is_file()
    assert asyncio.run(_run([str(exe)])) == 0


def test_incremental_skips_clean_compiles(tmp_path: Path) -> None:
    collection = collect(TREES / "build_non_modules")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    first = asyncio.run(run_build(plan))
    assert first.compiles.ran == len(plan.compile_steps)
    assert first.compiles.skipped == 0

    second = asyncio.run(run_build(plan))
    assert second.compiles.ran == 0
    assert second.compiles.skipped == len(plan.compile_steps)


def test_incremental_rebuilds_on_header_edit(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    shutil.copytree(TREES / "build_non_modules", tree)
    collection = collect(tree)
    plan = plan_build(collection, build_dir=tmp_path / "build")
    asyncio.run(run_build(plan))

    header = tree / "libs" / "core" / "include" / "core.h"
    main_obj = next(
        step.request.object_output
        for step in plan.compile_steps
        if step.target == "hello"
    )
    core_obj = next(
        step.request.object_output
        for step in plan.compile_steps
        if step.target == "core"
    )
    main_mtime = main_obj.stat().st_mtime_ns
    core_mtime = core_obj.stat().st_mtime_ns

    time.sleep(0.02)
    header.write_text(header.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = asyncio.run(run_build(plan))
    assert result.compiles.ran >= 1
    assert core_obj.stat().st_mtime_ns > core_mtime
    # hello includes core.h, so its depfile should dirty it too.
    assert main_obj.stat().st_mtime_ns > main_mtime


def test_force_rebuilds_all(tmp_path: Path) -> None:
    collection = collect(TREES / "build_non_modules")
    plan = plan_build(collection, build_dir=tmp_path / "build")
    asyncio.run(run_build(plan))
    forced = asyncio.run(run_build(plan, force=True))
    assert forced.compiles.ran == len(plan.compile_steps)
    assert forced.compiles.skipped == 0


async def _run(argv: list[str]) -> int:
    process = await asyncio.create_subprocess_exec(*argv)
    return await process.wait()
