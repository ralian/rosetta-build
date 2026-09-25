"""Scaffolding tests for C++ module compiles that emit objects + BMIs."""

from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.compiler import (
    BmiInput,
    CompileArtifact,
    CompileArtifactKind,
    CompileRequest,
    ModuleUnitKind,
)
from rosetta_build.compilers import get_compiler
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, CxxStandard, UnsupportedCompileOption


def _interface_request() -> CompileRequest:
    return CompileRequest(
        sources=[Path("math.cppm")],
        object_output=Path("build/math.o"),
        bmi_output=Path("build/bmi/math.pcm"),
        module_name="math",
        module_unit=ModuleUnitKind.INTERFACE,
        settings=CompileSettings(standard=CxxStandard.CXX23),
    )


def test_expected_artifacts_object_only() -> None:
    request = CompileRequest(
        sources=[Path("a.cpp")],
        object_output=Path("a.o"),
        settings=CompileSettings(),
    )
    assert request.expected_artifacts() == (
        CompileArtifact(CompileArtifactKind.OBJECT, Path("a.o")),
    )
    assert request.uses_cxx_modules() is False


def test_expected_artifacts_object_and_bmi() -> None:
    request = _interface_request()
    assert request.expected_artifacts() == (
        CompileArtifact(CompileArtifactKind.OBJECT, Path("build/math.o")),
        CompileArtifact(CompileArtifactKind.BMI, Path("build/bmi/math.pcm")),
    )
    assert request.uses_cxx_modules() is True


def test_cxx_compilers_advertise_module_capability() -> None:
    for family in (CompilerFamily.GCC, CompilerFamily.CLANG, CompilerFamily.MSVC):
        compiler = get_compiler(family, Language.CXX)
        assert compiler.capabilities.cxx_modules is True


def test_gcc_interface_uses_modules_and_mapper() -> None:
    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    argv = compiler.argv_for_compile(_interface_request())
    assert argv == [
        "g++",
        "-c",
        "-std=c++23",
        "-fmodules",
        "-fmodule-mapper=build/math.o.modulemap",
        "math.cppm",
        "-o",
        "build/math.o",
    ]


def test_clang_interface_emits_object_and_bmi_flags() -> None:
    compiler = get_compiler(CompilerFamily.CLANG, Language.CXX)
    argv = compiler.argv_for_compile(_interface_request())
    assert argv == [
        "clang++",
        "-c",
        "-std=c++23",
        "-fmodule-output=build/bmi/math.pcm",
        "math.cppm",
        "-o",
        "build/math.o",
    ]


def test_gcc_consumer_passes_bmi_inputs_via_mapper() -> None:
    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    request = CompileRequest(
        sources=[Path("app.cpp")],
        object_output=Path("app.o"),
        bmi_inputs=(BmiInput(module="math", path=Path("build/bmi/math.pcm")),),
        settings=CompileSettings(standard=CxxStandard.CXX23),
    )
    assert compiler.argv_for_compile(request) == [
        "g++",
        "-c",
        "-std=c++23",
        "-fmodules",
        "-fmodule-mapper=app.o.modulemap",
        "app.cpp",
        "-o",
        "app.o",
    ]
    assert request.expected_artifacts() == (
        CompileArtifact(CompileArtifactKind.OBJECT, Path("app.o")),
    )


def test_msvc_interface_emits_object_and_ifc() -> None:
    compiler = get_compiler(CompilerFamily.MSVC, Language.CXX)
    request = CompileRequest(
        sources=[Path("math.ixx")],
        object_output=Path("math.obj"),
        bmi_output=Path("math.ifc"),
        module_name="math",
        module_unit=ModuleUnitKind.INTERFACE,
        settings=CompileSettings(standard=CxxStandard.CXX23),
        bmi_inputs=(BmiInput(module="other", path=Path("other.ifc")),),
    )
    assert compiler.argv_for_compile(request) == [
        "cl",
        "/c",
        "/std:c++latest",
        "/interface",
        "/referenceother=other.ifc",
        "/ifcOutputmath.ifc",
        "math.ixx",
        "/Fomath.obj",
    ]


def test_bmi_without_module_name_raises() -> None:
    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    request = CompileRequest(
        sources=[Path("math.cppm")],
        object_output=Path("math.o"),
        bmi_output=Path("math.pcm"),
        module_unit=ModuleUnitKind.INTERFACE,
        settings=CompileSettings(),
    )
    with pytest.raises(UnsupportedCompileOption, match="module_name is required"):
        compiler.argv_for_compile(request)


@pytest.mark.parametrize(
    ("family", "language"),
    [
        (CompilerFamily.GCC, Language.C),
        (CompilerFamily.RUSTC, Language.RUST),
    ],
)
def test_non_cxx_rejects_module_compile(
    family: CompilerFamily,
    language: Language,
) -> None:
    compiler = get_compiler(family, language)
    request = CompileRequest(
        sources=[Path("x")],
        object_output=Path("x.o"),
        bmi_output=Path("x.bmi"),
        module_name="x",
        module_unit=ModuleUnitKind.INTERFACE,
        settings=CompileSettings(),
    )
    with pytest.raises(UnsupportedCompileOption, match="does not support cxx_modules"):
        compiler.argv_for_compile(request)
