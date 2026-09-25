"""Unit tests for the file-edge scheduler and dirty checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from rosetta_build.compiler import BuildObject, CompileRequest, LinkRequest
from rosetta_build.language import Language
from rosetta_build.options import CompileSettings, LinkSettings
from rosetta_build.plan import CompileStep, LinkStep
from rosetta_build.schedule import (
    BuildEdge,
    ScheduleError,
    build_edges,
    effective_inputs,
    is_dirty,
    run_edges,
)


def _compile_edge(
    tmp_path: Path,
    *,
    name: str,
    source: Path,
    obj: Path,
    inputs: tuple[Path, ...] | None = None,
    bmi: Path | None = None,
    depfile: Path | None = None,
) -> BuildEdge:
    request = CompileRequest(
        sources=[source],
        object_output=obj,
        settings=CompileSettings(),
        bmi_output=bmi,
        depfile=depfile,
    )
    step = CompileStep(target=name, language=Language.CXX, request=request)
    outputs = (obj,) if bmi is None else (obj, bmi)
    return BuildEdge(
        id=f"compile:{name}",
        inputs=inputs if inputs is not None else (source,),
        outputs=outputs,
        step=step,
        depfile=depfile,
    )


def test_is_dirty_missing_output(tmp_path: Path) -> None:
    source = tmp_path / "a.cpp"
    source.write_text("int x;\n", encoding="utf-8")
    obj = tmp_path / "a.o"
    edge = _compile_edge(tmp_path, name="a", source=source, obj=obj)
    assert is_dirty(edge) is True


def test_is_dirty_missing_depfile(tmp_path: Path) -> None:
    source = tmp_path / "a.cpp"
    source.write_text("int x;\n", encoding="utf-8")
    obj = tmp_path / "a.o"
    obj.write_text("obj", encoding="utf-8")
    depfile = tmp_path / "a.d"
    edge = _compile_edge(tmp_path, name="a", source=source, obj=obj, depfile=depfile)
    assert is_dirty(edge) is True


def test_is_dirty_header_from_depfile(tmp_path: Path) -> None:
    source = tmp_path / "a.cpp"
    header = tmp_path / "a.h"
    source.write_text('#include "a.h"\n', encoding="utf-8")
    header.write_text("int x;\n", encoding="utf-8")
    obj = tmp_path / "a.o"
    obj.write_text("obj", encoding="utf-8")
    depfile = tmp_path / "a.d"
    depfile.write_text(f"{obj}: {source} {header}\n", encoding="utf-8")
    edge = _compile_edge(tmp_path, name="a", source=source, obj=obj, depfile=depfile)
    os.utime(obj, (1, 1))
    os.utime(source, (1, 1))
    os.utime(header, (1, 1))
    os.utime(depfile, (1, 1))
    assert is_dirty(edge) is False

    os.utime(header, (100, 100))
    assert is_dirty(edge) is True
    assert header in effective_inputs(edge)


def test_run_edges_respects_file_deps(tmp_path: Path) -> None:
    src_a = tmp_path / "a.cpp"
    src_b = tmp_path / "b.cpp"
    src_a.write_text("a", encoding="utf-8")
    src_b.write_text("b", encoding="utf-8")
    obj_a = tmp_path / "a.o"
    obj_b = tmp_path / "b.o"
    bmi = tmp_path / "a.gcm"
    order: list[str] = []

    edge_a = _compile_edge(
        tmp_path, name="a", source=src_a, obj=obj_a, bmi=bmi, depfile=tmp_path / "a.d"
    )
    edge_b = _compile_edge(
        tmp_path,
        name="b",
        source=src_b,
        obj=obj_b,
        inputs=(src_b, bmi),
        depfile=tmp_path / "b.d",
    )

    async def run_edge(edge: BuildEdge) -> None:
        order.append(edge.id)
        for output in edge.outputs:
            output.write_text("out", encoding="utf-8")
        if edge.depfile is not None:
            edge.depfile.write_text(
                f"{edge.outputs[0]}: {' '.join(str(p) for p in edge.inputs)}\n",
                encoding="utf-8",
            )

    result = asyncio.run(run_edges((edge_a, edge_b), run_edge=run_edge, jobs=2))
    assert order == ["compile:a", "compile:b"]
    assert result.ran == 2
    assert result.skipped == 0

    order.clear()
    result = asyncio.run(run_edges((edge_a, edge_b), run_edge=run_edge, jobs=2))
    assert order == []
    assert result.ran == 0
    assert result.skipped == 2


def test_run_edges_duplicate_outputs_raise(tmp_path: Path) -> None:
    source = tmp_path / "a.cpp"
    source.write_text("a", encoding="utf-8")
    obj = tmp_path / "a.o"
    edge1 = _compile_edge(tmp_path, name="a", source=source, obj=obj)
    edge2 = _compile_edge(tmp_path, name="b", source=source, obj=obj)
    with pytest.raises(ScheduleError, match="multiple edges"):
        asyncio.run(run_edges((edge1, edge2), run_edge=lambda e: asyncio.sleep(0)))


def test_build_edges_from_plan_smoke() -> None:
    # Imported lazily to avoid unused if collect fails; kept as type check aid.
    _ = (build_edges, LinkStep, LinkRequest, BuildObject, LinkSettings)
