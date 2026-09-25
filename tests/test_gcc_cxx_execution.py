"""g++ compile/link execution for modules and non-modules builds."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from rosetta_build.compiler import (
    BmiInput,
    BuildObject,
    CompileRequest,
    LinkRequest,
    ModuleUnitKind,
)
from rosetta_build.compilers import get_compiler, get_linker
from rosetta_build.compilers._gnu import gcc_module_mapper_path, gcc_module_mapper_text
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, CxxStandard, LinkSettings

pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")


def test_gcc_cxx_compiles_and_links_non_module(tmp_path: Path) -> None:
    source = tmp_path / "main.cpp"
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    obj = tmp_path / "main.o"
    exe = tmp_path / "main"

    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    compile_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[source],
                object_output=obj,
                settings=CompileSettings(
                    standard=CxxStandard.CXX23,
                    defines={"NDEBUG": True},
                    include_dirs=[tmp_path],
                ),
            )
        )
    )
    assert compile_result.returncode == 0, compile_result.stderr
    assert obj.is_file()
    assert compile_result.artifacts[0].path == obj

    linker = get_linker(CompilerFamily.GCC, Language.CXX)
    link_result = asyncio.run(
        linker.link(
            LinkRequest(
                objects=[BuildObject(name=obj)],
                output=exe,
                settings=LinkSettings(),
            )
        )
    )
    assert link_result.returncode == 0, link_result.stderr
    assert exe.is_file()


def test_gcc_cxx_compiles_module_interface_and_consumer(tmp_path: Path) -> None:
    interface = tmp_path / "math.cppm"
    interface.write_text(
        "export module math;\nexport int add(int a, int b) { return a + b; }\n",
        encoding="utf-8",
    )
    consumer = tmp_path / "app.cpp"
    consumer.write_text(
        "import math;\nint main() { return add(1, 2); }\n",
        encoding="utf-8",
    )

    bmi = tmp_path / "bmi" / "math.gcm"
    interface_obj = tmp_path / "math.o"
    consumer_obj = tmp_path / "app.o"
    exe = tmp_path / "app"

    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    interface_request = CompileRequest(
        sources=[interface],
        object_output=interface_obj,
        bmi_output=bmi,
        module_name="math",
        module_unit=ModuleUnitKind.INTERFACE,
        settings=CompileSettings(standard=CxxStandard.CXX23),
    )
    assert gcc_module_mapper_text(interface_request) == f"math {bmi}\n"

    interface_result = asyncio.run(compiler.compile(interface_request))
    assert interface_result.returncode == 0, interface_result.stderr
    assert interface_obj.is_file()
    assert bmi.is_file()
    assert gcc_module_mapper_path(interface_request).is_file()

    consumer_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[consumer],
                object_output=consumer_obj,
                bmi_inputs=(BmiInput(module="math", path=bmi),),
                settings=CompileSettings(standard=CxxStandard.CXX23),
            )
        )
    )
    assert consumer_result.returncode == 0, consumer_result.stderr
    assert consumer_obj.is_file()

    linker = get_linker(CompilerFamily.GCC, Language.CXX)
    link_result = asyncio.run(
        linker.link(
            LinkRequest(
                objects=[
                    BuildObject(name=interface_obj),
                    BuildObject(name=consumer_obj),
                ],
                output=exe,
                settings=LinkSettings(),
            )
        )
    )
    assert link_result.returncode == 0, link_result.stderr
    assert exe.is_file()
