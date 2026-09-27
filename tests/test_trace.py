"""Tests for Chrome Trace Event Format recording."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from rosetta_build.cli import main
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.schedule import BuildEdge, run_edges
from rosetta_build.trace import TraceRecorder, edge_category
from tests.conftest import requires_compiler, requires_gcc_fmodules
from tests.test_schedule import _compile_edge

TREES = Path(__file__).parent / "trees"


def stage_key(event_name: str) -> str:
    """Stable stage id from an edge name, dropping any absolute source path."""
    kind, sep, rest = event_name.partition(":")
    if not sep:
        return event_name
    target, _, _ = rest.partition(":")
    return f"{kind}:{target}"


def stages_from_trace(path: Path) -> set[str]:
    events: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return {stage_key(str(event["name"])) for event in events if event.get("ph") == "X"}


def test_edge_category() -> None:
    assert edge_category("compile:core:/tmp/a.cpp") == "compile"
    assert edge_category("wheel:pkg") == "wheel"
    assert edge_category("link:hello") == "link"
    assert edge_category("other") == "build"


def test_stage_key_drops_source_path() -> None:
    assert stage_key("compile:core:/abs/path/core.cpp") == "compile:core"
    assert stage_key("link:hello") == "link:hello"
    assert stage_key("wheel:pkg") == "wheel:pkg"


def test_trace_recorder_complete_events(tmp_path: Path) -> None:
    recorder = TraceRecorder()
    recorder.complete(
        name="compile:a",
        cat="compile",
        tid=0,
        ts=10.0,
        dur=5.5,
        args={"outputs": ["/tmp/a.o"]},
    )
    events = recorder.events()
    assert events[0] == {
        "name": "process_name",
        "ph": "M",
        "pid": 1,
        "args": {"name": "rosetta-build"},
    }
    assert events[1] == {
        "name": "thread_name",
        "ph": "M",
        "pid": 1,
        "tid": 0,
        "args": {"name": "job 0"},
    }
    assert events[2] == {
        "name": "compile:a",
        "cat": "compile",
        "ph": "X",
        "ts": 10.0,
        "dur": 5.5,
        "pid": 1,
        "tid": 0,
        "args": {"outputs": ["/tmp/a.o"]},
    }

    out = tmp_path / "trace.json"
    recorder.write(out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == events


def test_run_edges_records_trace(tmp_path: Path) -> None:
    src_a = tmp_path / "a.cpp"
    src_b = tmp_path / "b.cpp"
    src_a.write_text("a", encoding="utf-8")
    src_b.write_text("b", encoding="utf-8")
    obj_a = tmp_path / "a.o"
    obj_b = tmp_path / "b.o"
    bmi = tmp_path / "a.gcm"

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
        await asyncio.sleep(0.01)
        for output in edge.outputs:
            output.write_text("out", encoding="utf-8")
        if edge.depfile is not None:
            edge.depfile.write_text(
                f"{edge.outputs[0]}: {' '.join(str(p) for p in edge.inputs)}\n",
                encoding="utf-8",
            )

    trace = TraceRecorder()
    result = asyncio.run(
        run_edges((edge_a, edge_b), run_edge=run_edge, jobs=2, trace=trace)
    )
    assert result.ran == 2
    complete = [event for event in trace.events() if event["ph"] == "X"]
    assert {event["name"] for event in complete} == {"compile:a", "compile:b"}
    assert all(event["cat"] == "compile" for event in complete)
    assert all(event["dur"] > 0 for event in complete)
    assert {event["tid"] for event in complete} <= {0, 1}

    # Clean rebuild: no new complete events.
    before = len(complete)
    result = asyncio.run(
        run_edges((edge_a, edge_b), run_edge=run_edge, jobs=2, trace=trace)
    )
    assert result.skipped == 2
    assert len([e for e in trace.events() if e["ph"] == "X"]) == before


def test_cli_build_writes_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = TREES / "build_wheel"
    out = tmp_path / "build" / "trace.json"
    with pytest.raises(SystemExit) as exc:
        main([
            "build",
            str(tree),
            "--build-dir",
            str(tmp_path / "out"),
            "--trace",
            str(out),
        ])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert f"wrote trace: {out}" in captured.out
    events = json.loads(out.read_text(encoding="utf-8"))
    assert events[0]["name"] == "process_name"
    complete = [event for event in events if event["ph"] == "X"]
    assert any(event["cat"] == "wheel" for event in complete)


@requires_compiler(CompilerFamily.GCC, Language.CXX)
def test_build_non_modules_trace_stages(tmp_path: Path) -> None:
    tree = TREES / "build_non_modules"
    build_dir = tmp_path / "build"
    compile_out = tmp_path / "compile-trace.json"
    link_out = tmp_path / "link-trace.json"

    with pytest.raises(SystemExit) as build_exc:
        main([
            "build",
            str(tree),
            "--build-dir",
            str(build_dir),
            "-B",
            "--trace",
            str(compile_out),
        ])
    assert build_exc.value.code == 0
    assert stages_from_trace(compile_out) == stages_from_trace(
        tree / "compile-trace.json"
    )

    with pytest.raises(SystemExit) as link_exc:
        main([
            "link",
            str(tree),
            "--build-dir",
            str(build_dir),
            "-B",
            "--trace",
            str(link_out),
        ])
    assert link_exc.value.code == 0
    assert stages_from_trace(link_out) == stages_from_trace(tree / "link-trace.json")


@requires_gcc_fmodules()
def test_build_modules_trace_stages(tmp_path: Path) -> None:
    tree = TREES / "build_modules"
    build_dir = tmp_path / "build"
    compile_out = tmp_path / "compile-trace.json"
    link_out = tmp_path / "link-trace.json"

    with pytest.raises(SystemExit) as build_exc:
        main([
            "build",
            str(tree),
            "--build-dir",
            str(build_dir),
            "-B",
            "--trace",
            str(compile_out),
        ])
    assert build_exc.value.code == 0
    assert stages_from_trace(compile_out) == stages_from_trace(
        tree / "compile-trace.json"
    )

    with pytest.raises(SystemExit) as link_exc:
        main([
            "link",
            str(tree),
            "--build-dir",
            str(build_dir),
            "-B",
            "--trace",
            str(link_out),
        ])
    assert link_exc.value.code == 0
    assert stages_from_trace(link_out) == stages_from_trace(tree / "link-trace.json")


def test_example_trace_files_list_expected_stages() -> None:
    assert stages_from_trace(TREES / "build_non_modules" / "compile-trace.json") == {
        "compile:core",
        "compile:hello",
    }
    assert stages_from_trace(TREES / "build_non_modules" / "link-trace.json") == {
        "link:hello",
    }
    assert stages_from_trace(TREES / "build_modules" / "compile-trace.json") == {
        "compile:math",
        "compile:app",
        "compile:math_impl",
    }
    assert stages_from_trace(TREES / "build_modules" / "link-trace.json") == {
        "link:app",
    }
