"""gcc compile/link execution for C translation units."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rosetta_build.compiler import BuildObject, CompileRequest, LinkRequest
from rosetta_build.compilers import get_compiler, get_linker
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, CStandard, LinkSettings
from tests.conftest import requires_compiler

pytestmark = requires_compiler(CompilerFamily.GCC, Language.C)


def test_gcc_c_compiles_and_links(tmp_path: Path) -> None:
    include = tmp_path / "include"
    include.mkdir()
    (include / "greet.h").write_text(
        "#ifndef GREET_H\n#define GREET_H\nint greet(void);\n#endif\n",
        encoding="utf-8",
    )
    lib_src = tmp_path / "greet.c"
    lib_src.write_text(
        '#include "greet.h"\nint greet(void) { return 42; }\n',
        encoding="utf-8",
    )
    main_src = tmp_path / "main.c"
    main_src.write_text(
        '#include "greet.h"\nint main(void) { return greet() - 42; }\n',
        encoding="utf-8",
    )

    lib_obj = tmp_path / "out" / "greet.o"
    main_obj = tmp_path / "out" / "main.o"
    exe = tmp_path / "out" / "hello"
    depfile = tmp_path / "out" / "main.d"

    compiler = get_compiler(CompilerFamily.GCC, Language.C)
    settings = CompileSettings(
        standard=CStandard.C17,
        include_dirs=[include],
        defines={"GREET_ENABLED": True},
    )
    lib_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[lib_src],
                object_output=lib_obj,
                settings=settings,
            )
        )
    )
    assert lib_result.returncode == 0, lib_result.stderr
    assert lib_obj.is_file()

    main_result = asyncio.run(
        compiler.compile(
            CompileRequest(
                sources=[main_src],
                object_output=main_obj,
                settings=settings,
            )
        )
    )
    assert main_result.returncode == 0, main_result.stderr
    assert main_obj.is_file()
    assert depfile.is_file()
    assert "greet.h" in depfile.read_text(encoding="utf-8")

    linker = get_linker(CompilerFamily.GCC, Language.C)
    link_result = asyncio.run(
        linker.link(
            LinkRequest(
                objects=[BuildObject(name=main_obj), BuildObject(name=lib_obj)],
                output=exe,
                settings=LinkSettings(),
            )
        )
    )
    assert link_result.returncode == 0, link_result.stderr
    assert exe.is_file()
