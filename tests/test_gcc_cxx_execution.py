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

TREES = Path(__file__).parent / "trees"
NON_MODULES = TREES / "build_non_modules"
MODULES = TREES / "build_modules"

pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")


def test_gcc_cxx_compiles_and_links_non_module(tmp_path: Path) -> None:
    source = NON_MODULES / "apps" / "hello" / "main.cpp"
    include = NON_MODULES / "libs" / "core" / "include"
    core_source = NON_MODULES / "libs" / "core" / "core.cpp"
    core_obj = tmp_path / "core.o"
    hello_obj = tmp_path / "hello.o"
    exe = tmp_path / "hello"

    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    settings = CompileSettings(
        standard=CxxStandard.CXX23,
        include_dirs=[include],
    )
    core_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[core_source],
                object_output=core_obj,
                settings=settings,
            )
        )
    )
    assert core_result.returncode == 0, core_result.stderr

    hello_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[source],
                object_output=hello_obj,
                settings=settings,
            )
        )
    )
    assert hello_result.returncode == 0, hello_result.stderr
    assert hello_obj.is_file()

    linker = get_linker(CompilerFamily.GCC, Language.CXX)
    link_result = asyncio.run(
        linker.link(
            LinkRequest(
                objects=[BuildObject(name=hello_obj), BuildObject(name=core_obj)],
                output=exe,
                settings=LinkSettings(),
            )
        )
    )
    assert link_result.returncode == 0, link_result.stderr
    assert exe.is_file()


def test_gcc_cxx_compiles_module_interface_and_consumer(tmp_path: Path) -> None:
    interface = MODULES / "modules" / "math" / "math.cppm"
    impl = MODULES / "modules" / "math_impl" / "math.cpp"
    consumer = MODULES / "apps" / "app" / "main.cpp"

    bmi = tmp_path / "bmi" / "math.gcm"
    interface_obj = tmp_path / "math.o"
    impl_obj = tmp_path / "math_impl.o"
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

    impl_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[impl],
                object_output=impl_obj,
                bmi_inputs=(BmiInput(module="math", path=bmi),),
                module_unit=ModuleUnitKind.IMPLEMENTATION,
                settings=CompileSettings(standard=CxxStandard.CXX23),
            )
        )
    )
    assert impl_result.returncode == 0, impl_result.stderr

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
                    BuildObject(name=impl_obj),
                    BuildObject(name=consumer_obj),
                ],
                output=exe,
                settings=LinkSettings(),
            )
        )
    )
    assert link_result.returncode == 0, link_result.stderr
    assert exe.is_file()
