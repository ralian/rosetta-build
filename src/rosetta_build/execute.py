"""Execute planned compile, wheel, and link steps."""

from __future__ import annotations

from rosetta_build.compilers import get_compiler, get_linker
from rosetta_build.plan import BuildPlan, CompileStep, LinkStep, PlanError, WheelStep
from rosetta_build.wheel import WheelBuildError, build_sdist, build_wheel

__all__ = [
    "BuildError",
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


async def run_build(plan: BuildPlan) -> None:
    """Run compile steps, then wheel/sdist assembly, in plan order."""
    for compile_step in plan.compile_steps:
        await _run_compile(plan, compile_step)
    for wheel_step in plan.wheel_steps:
        _run_wheel(wheel_step)


async def run_link(plan: BuildPlan) -> None:
    """Run all link steps in plan order."""
    for step in plan.link_steps:
        await _run_link(plan, step)


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


def _run_wheel(step: WheelStep) -> None:
    try:
        build_wheel(step.request)
        build_sdist(step.request)
    except WheelBuildError as exc:
        raise BuildError(
            f"wheel/sdist failed for target {step.target!r}: {exc}",
            returncode=1,
        ) from exc


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
