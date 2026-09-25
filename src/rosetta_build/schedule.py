"""Ninja-like file edge DAG, dirty checks, and parallel ready-set execution."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from rosetta_build.depfile import depfile_for_object, parse_depfile
from rosetta_build.plan import BuildPlan, CompileStep, LinkStep, WheelStep

__all__ = [
    "BuildEdge",
    "ScheduleError",
    "ScheduleResult",
    "build_edges",
    "effective_inputs",
    "is_dirty",
    "run_edges",
]


class ScheduleError(Exception):
    """Raised when the edge DAG is invalid."""


@dataclass(frozen=True, slots=True)
class BuildEdge:
    """One file-producing build action (compile, wheel, or link)."""

    id: str
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    step: CompileStep | WheelStep | LinkStep
    depfile: Path | None = None


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    ran: int
    skipped: int


def build_edges(
    plan: BuildPlan,
    *,
    include_compile: bool = True,
    include_wheel: bool = True,
    include_link: bool = True,
) -> tuple[BuildEdge, ...]:
    """Lower a ``BuildPlan`` to file-centric edges."""
    edges: list[BuildEdge] = []
    if include_compile:
        for compile_step in plan.compile_steps:
            compile_request = compile_step.request
            source = compile_request.sources[0]
            depfile = compile_request.depfile
            if depfile is None:
                depfile = depfile_for_object(compile_request.object_output)
            inputs = [
                *compile_request.sources,
                *(bmi.path for bmi in compile_request.bmi_inputs),
            ]
            outputs = [compile_request.object_output]
            if compile_request.bmi_output is not None:
                outputs.append(compile_request.bmi_output)
            edges.append(
                BuildEdge(
                    id=f"compile:{compile_step.target}:{source}",
                    inputs=tuple(inputs),
                    outputs=tuple(outputs),
                    step=compile_step,
                    depfile=depfile,
                )
            )
    if include_wheel:
        for wheel_step in plan.wheel_steps:
            wheel_request = wheel_step.request
            inputs = list(wheel_request.sources)
            inputs.extend(wheel_request.config_paths)
            pyproject = wheel_request.source_tree / "pyproject.toml"
            inputs.append(pyproject)
            edges.append(
                BuildEdge(
                    id=f"wheel:{wheel_step.target}",
                    inputs=tuple(dict.fromkeys(inputs)),
                    outputs=(wheel_request.wheel_output, wheel_request.sdist_output),
                    step=wheel_step,
                )
            )
    if include_link:
        for link_step in plan.link_steps:
            link_request = link_step.request
            edges.append(
                BuildEdge(
                    id=f"link:{link_step.target}",
                    inputs=tuple(obj.name for obj in link_request.objects),
                    outputs=(link_request.output,),
                    step=link_step,
                )
            )
    return tuple(edges)


def effective_inputs(edge: BuildEdge) -> tuple[Path, ...]:
    """Declared inputs plus depfile prerequisites when the depfile exists."""
    extras: list[Path] = []
    if edge.depfile is not None and edge.depfile.is_file():
        extras.extend(parse_depfile(edge.depfile))
    return tuple(dict.fromkeys([*edge.inputs, *extras]))


def is_dirty(edge: BuildEdge, *, force: bool = False) -> bool:
    """Return whether ``edge`` must run (Ninja-style mtime + depfile rules)."""
    if force:
        return True
    if any(not path.is_file() for path in edge.outputs):
        return True
    if edge.depfile is not None and not edge.depfile.is_file():
        return True
    inputs = effective_inputs(edge)
    if not inputs:
        return True
    if any(not path.is_file() for path in inputs):
        return True
    newest_in = max(path.stat().st_mtime_ns for path in inputs)
    oldest_out = min(path.stat().st_mtime_ns for path in edge.outputs)
    return newest_in > oldest_out


def _dependents_by_producer(
    edges: Sequence[BuildEdge],
) -> tuple[dict[str, set[str]], dict[str, int], dict[str, BuildEdge]]:
    by_id = {edge.id: edge for edge in edges}
    producer: dict[Path, str] = {}
    for edge in edges:
        for output in edge.outputs:
            if output in producer and producer[output] != edge.id:
                raise ScheduleError(
                    f"multiple edges produce {output}: "
                    f"{producer[output]!r} and {edge.id!r}"
                )
            producer[output] = edge.id

    dependents: dict[str, set[str]] = {edge.id: set() for edge in edges}
    indegree: dict[str, int] = {edge.id: 0 for edge in edges}
    for edge in edges:
        seen_deps: set[str] = set()
        for input_path in edge.inputs:
            producer_id = producer.get(input_path)
            if producer_id is None or producer_id == edge.id:
                continue
            if producer_id in seen_deps:
                continue
            seen_deps.add(producer_id)
            dependents[producer_id].add(edge.id)
            indegree[edge.id] += 1

    if _has_cycle(dependents, indegree):
        raise ScheduleError("build edge dependency cycle detected")
    return dependents, indegree, by_id


def _has_cycle(
    dependents: dict[str, set[str]],
    indegree: dict[str, int],
) -> bool:
    remaining = dict(indegree)
    queue = sorted(node for node, degree in remaining.items() if degree == 0)
    seen = 0
    while queue:
        node = queue.pop(0)
        seen += 1
        for dependent in sorted(dependents.get(node, ())):
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                queue.append(dependent)
    return seen != len(remaining)


async def run_edges(
    edges: Sequence[BuildEdge],
    *,
    run_edge: Callable[[BuildEdge], Awaitable[None]],
    jobs: int | None = None,
    force: bool = False,
) -> ScheduleResult:
    """Run dirty edges when ready, up to ``jobs`` at a time."""
    if not edges:
        return ScheduleResult(ran=0, skipped=0)

    workers = jobs if jobs is not None else (os.cpu_count() or 1)
    if workers < 1:
        raise ScheduleError(f"jobs must be >= 1, got {workers}")

    dependents, indegree, by_id = _dependents_by_producer(edges)
    semaphore = asyncio.Semaphore(workers)
    ran = 0
    skipped = 0
    lock = asyncio.Lock()

    try:
        async with asyncio.TaskGroup() as group:

            async def schedule(edge_id: str) -> None:
                nonlocal ran, skipped
                edge = by_id[edge_id]
                if is_dirty(edge, force=force):
                    async with semaphore:
                        await run_edge(edge)
                    async with lock:
                        ran += 1
                else:
                    async with lock:
                        skipped += 1

                async with lock:
                    newly_ready = []
                    for dependent in sorted(dependents.get(edge_id, ())):
                        indegree[dependent] -= 1
                        if indegree[dependent] == 0:
                            newly_ready.append(dependent)
                for dependent in newly_ready:
                    group.create_task(schedule(dependent))

            for edge_id, degree in indegree.items():
                if degree == 0:
                    group.create_task(schedule(edge_id))
    except* Exception as errors:
        raise errors.exceptions[0] from errors

    return ScheduleResult(ran=ran, skipped=skipped)
