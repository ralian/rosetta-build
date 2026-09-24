"""Tests for portable option mapping across compiler adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.compiler import BuildObject, CompileRequest, LinkRequest
from rosetta_build.compilers import get_compiler, get_linker
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import (
    CompileSettings,
    CStandard,
    CxxStandard,
    LinkSettings,
    RustEdition,
    UnsupportedCompileOption,
)


def test_get_compiler_unknown_pair_raises() -> None:
    with pytest.raises(KeyError, match="no compiler registered"):
        get_compiler(CompilerFamily.GCC, Language.RUST)


def test_gcc_cxx_maps_standard_define_include_and_raw() -> None:
    compiler = get_compiler(CompilerFamily.GCC, Language.CXX)
    request = CompileRequest(
        sources=[Path("main.cpp")],
        output=Path("main.o"),
        settings=CompileSettings(
            standard=CxxStandard.CXX23,
            defines={"DEBUG": True, "VERSION": 2},
            include_dirs=[Path("include")],
            raw_flags=["-Wall"],
        ),
    )
    assert compiler.argv_for_compile(request) == [
        "g++",
        "-c",
        "-std=c++23",
        "-DDEBUG",
        "-DVERSION=2",
        "-Iinclude",
        "-Wall",
        "main.cpp",
        "-o",
        "main.o",
    ]
    assert compiler.capabilities.separate_link is True


def test_clang_c_maps_c_standard() -> None:
    compiler = get_compiler(CompilerFamily.CLANG, Language.C)
    request = CompileRequest(
        sources=[Path("a.c")],
        output=Path("a.o"),
        settings=CompileSettings(standard=CStandard.C17),
    )
    assert compiler.argv_for_compile(request) == [
        "clang",
        "-c",
        "-std=c17",
        "a.c",
        "-o",
        "a.o",
    ]


def test_msvc_cxx_maps_msvc_style_flags() -> None:
    compiler = get_compiler(CompilerFamily.MSVC, Language.CXX)
    request = CompileRequest(
        sources=[Path("main.cpp")],
        output=Path("main.obj"),
        settings=CompileSettings(
            standard=CxxStandard.CXX20,
            defines={"FOO": "bar"},
            include_dirs=[Path("inc")],
        ),
    )
    assert compiler.argv_for_compile(request) == [
        "cl",
        "/c",
        "/std:c++20",
        "/DFOO=bar",
        "/Iinc",
        "main.cpp",
        "/Fomain.obj",
    ]


def test_msvc_linker_uses_out_flag() -> None:
    linker = get_linker(CompilerFamily.MSVC, Language.C)
    request = LinkRequest(
        objects=[BuildObject(name=Path("a.obj"))],
        output=Path("a.exe"),
        settings=LinkSettings(raw_flags=["/DEBUG"]),
    )
    assert linker.argv_for_link(request) == [
        "link",
        "/DEBUG",
        "a.obj",
        "/OUT:a.exe",
    ]


def test_rustc_maps_edition_without_separate_link() -> None:
    compiler = get_compiler(CompilerFamily.RUSTC, Language.RUST)
    request = CompileRequest(
        sources=[Path("main.rs")],
        output=Path("main"),
        settings=CompileSettings(standard=RustEdition.E2021),
    )
    assert compiler.argv_for_compile(request) == [
        "rustc",
        "--edition=2021",
        "main.rs",
        "-o",
        "main",
    ]
    assert compiler.capabilities.separate_link is False


def test_gccrs_maps_edition() -> None:
    compiler = get_compiler(CompilerFamily.GCCRS, Language.RUST)
    request = CompileRequest(
        sources=[Path("lib.rs")],
        output=Path("lib.rlib"),
        settings=CompileSettings(standard=RustEdition.E2024, raw_flags=["-O"]),
    )
    assert compiler.argv_for_compile(request) == [
        "gccrs",
        "--edition=2024",
        "-O",
        "lib.rs",
        "-o",
        "lib.rlib",
    ]


@pytest.mark.parametrize(
    ("family", "language", "standard"),
    [
        (CompilerFamily.GCC, Language.CXX, CStandard.C17),
        (CompilerFamily.CLANG, Language.C, CxxStandard.CXX23),
        (CompilerFamily.MSVC, Language.CXX, RustEdition.E2021),
        (CompilerFamily.RUSTC, Language.RUST, CxxStandard.CXX23),
        (CompilerFamily.GCCRS, Language.RUST, CStandard.C11),
    ],
)
def test_wrong_standard_type_raises(
    family: CompilerFamily,
    language: Language,
    standard: CStandard | CxxStandard | RustEdition,
) -> None:
    compiler = get_compiler(family, language)
    request = CompileRequest(
        sources=[Path("src")],
        output=Path("out"),
        settings=CompileSettings(standard=standard),
    )
    with pytest.raises(UnsupportedCompileOption, match="does not support standard"):
        compiler.argv_for_compile(request)


def test_rustc_rejects_defines() -> None:
    compiler = get_compiler(CompilerFamily.RUSTC, Language.RUST)
    request = CompileRequest(
        sources=[Path("main.rs")],
        output=Path("main"),
        settings=CompileSettings(defines={"N": 1}),
    )
    with pytest.raises(UnsupportedCompileOption, match="does not support defines"):
        compiler.argv_for_compile(request)


def test_gcc_linker_appends_raw_flags() -> None:
    linker = get_linker(CompilerFamily.GCC, Language.CXX)
    request = LinkRequest(
        objects=[BuildObject(name=Path("a.o")), BuildObject(name=Path("b.o"))],
        output=Path("app"),
        settings=LinkSettings(raw_flags=["-lm"]),
    )
    assert linker.argv_for_link(request) == [
        "g++",
        "-lm",
        "a.o",
        "b.o",
        "-o",
        "app",
    ]


def test_collected_native_targets_expose_language() -> None:
    from rosetta_build.collect import collect
    from rosetta_build.target import ExecutableTarget

    collection = collect(Path(__file__).parent / "trees" / "example")
    hello = collection.targets["hello"]
    assert isinstance(hello, ExecutableTarget)
    assert hello.language == Language.CXX
