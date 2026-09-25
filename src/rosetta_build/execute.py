"""Execute planned compile and link steps."""

from __future__ import annotations

from rosetta_build.compilers import get_compiler, get_linker
from rosetta_build.plan import BuildPlan, CompileStep, LinkStep, PlanError

__all__ = [
    "BuildError",
    "run_build",
    "run_link",
]


class BuildError(Exception):
    """Raised when a compile or link driver fails."""

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
    """Run all compile steps in plan order."""
    for step in plan.compile_steps:
        await _run_compile(plan, step)


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
