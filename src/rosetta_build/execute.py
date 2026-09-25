"""Execute planned compile, wheel, and link steps."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from rosetta_build.compilers import get_compiler, get_linker
from rosetta_build.plan import (
    BuildPlan,
    CompileStep,
    LinkStep,
    PlanError,
    WheelStep,
)
from rosetta_build.schedule import (
    BuildEdge,
    ScheduleResult,
    build_edges,
    run_edges,
)
from rosetta_build.wheel import WheelBuildError, build_sdist, build_wheel

__all__ = [
    "BuildError",
    "BuildRunResult",
    "LinkRunResult",
    "run_build",
    "run_link",
]


class BuildError(Exception):
    """Raised when a compile, wheel, or link driver fails."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True, slots=True)
class BuildRunResult:
    """Counts from ``run_build`` (compiles then wheels)."""

    compiles: ScheduleResult
    wheels: ScheduleResult


@dataclass(frozen=True, slots=True)
class LinkRunResult:
    """Counts from ``run_link``."""

    links: ScheduleResult


def _default_jobs(jobs: int | None) -> int:
    if jobs is not None:
        return jobs
    return os.cpu_count() or 1


async def run_build(
    plan: BuildPlan,
    *,
    jobs: int | None = None,
    force: bool = False,
) -> BuildRunResult:
    """Run compile and wheel edges with dirty checks and parallelism."""
    workers = _default_jobs(jobs)

    async def run_compile_edge(edge: BuildEdge) -> None:
        assert isinstance(edge.step, CompileStep)
        await _run_compile(plan, edge.step)

    async def run_wheel_edge(edge: BuildEdge) -> None:
        assert isinstance(edge.step, WheelStep)
        await _run_wheel(edge.step)

    compile_result = await run_edges(
        build_edges(
            plan, include_compile=True, include_wheel=False, include_link=False
        ),
        run_edge=run_compile_edge,
        jobs=workers,
        force=force,
    )
    wheel_result = await run_edges(
        build_edges(
            plan, include_compile=False, include_wheel=True, include_link=False
        ),
        run_edge=run_wheel_edge,
        jobs=workers,
        force=force,
    )
    return BuildRunResult(compiles=compile_result, wheels=wheel_result)


async def run_link(
    plan: BuildPlan,
    *,
    jobs: int | None = None,
    force: bool = False,
) -> LinkRunResult:
    """Run link edges with dirty checks and parallelism."""
    workers = _default_jobs(jobs)

    async def run_link_edge(edge: BuildEdge) -> None:
        assert isinstance(edge.step, LinkStep)
        await _run_link(plan, edge.step)

    result = await run_edges(
        build_edges(
            plan, include_compile=False, include_wheel=False, include_link=True
        ),
        run_edge=run_link_edge,
        jobs=workers,
        force=force,
    )
    return LinkRunResult(links=result)


async def _run_compile(plan: BuildPlan, step: CompileStep) -> None:
    compiler = get_compiler(plan.family, step.language)
    if not compiler.capabilities.separate_link:
        raise PlanError(
            f"{plan.family.value}/{step.language.value} does not use separate "
            "compile/link; planner cannot execute it yet"
        )
    result = await compiler.compile(step.request)
    if result.returncode != 0:
        raise BuildError(
            f"compile failed for target {step.target!r} (exit {result.returncode})",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )


async def _run_wheel(step: WheelStep) -> None:
    try:
        await asyncio.to_thread(_run_wheel_sync, step)
    except WheelBuildError as exc:
        raise BuildError(
            f"wheel/sdist failed for target {step.target!r}: {exc}",
            returncode=1,
        ) from exc


def _run_wheel_sync(step: WheelStep) -> None:
    build_wheel(step.request)
    build_sdist(step.request)


async def _run_link(plan: BuildPlan, step: LinkStep) -> None:
    linker = get_linker(plan.family, step.language)
    result = await linker.link(step.request)
    if result.returncode != 0:
        raise BuildError(
            f"link failed for target {step.target!r} (exit {result.returncode})",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
