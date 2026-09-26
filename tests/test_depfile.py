"""Unit tests for make-style depfile parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.depfile import (
    DepfileError,
    depfile_for_object,
    parse_depfile,
    parse_depfile_text,
)


def test_depfile_for_object() -> None:
    assert depfile_for_object(Path("obj/foo.o")) == Path("obj/foo.d")


def test_parse_depfile_with_continuations(tmp_path: Path) -> None:
    path = tmp_path / "foo.d"
    path.write_text(
        "foo.o: foo.cpp \\\n  include/a.h include/b.h\n",
        encoding="utf-8",
    )
    assert parse_depfile(path) == (
        Path("foo.cpp"),
        Path("include/a.h"),
        Path("include/b.h"),
    )


def test_parse_depfile_text_dedupes() -> None:
    text = "a.o: src.cpp hdr.h\nb.o: hdr.h other.h\n"
    assert parse_depfile_text(text) == (
        Path("src.cpp"),
        Path("hdr.h"),
        Path("other.h"),
    )


def test_parse_depfile_escaped_space() -> None:
    assert parse_depfile_text(r"a.o: weird\ name.h") == (Path("weird name.h"),)
    assert parse_depfile_text(r"a\ bc\ def: a\ b c d") == (
        Path("a b"),
        Path("c"),
        Path("d"),
    )


def test_parse_depfile_windows_forward_slashes() -> None:
    assert parse_depfile_text("C:/build/foo.o: C:/src/foo.cpp C:/include/bar.h") == (
        Path("C:/src/foo.cpp"),
        Path("C:/include/bar.h"),
    )


def test_parse_depfile_windows_backslashes() -> None:
    assert parse_depfile_text(
        "C:\\build\\foo.obj: C:\\src\\foo.cpp C:\\include\\bar.h"
    ) == (
        Path("C:\\src\\foo.cpp"),
        Path("C:\\include\\bar.h"),
    )


def test_parse_depfile_windows_escaped_space() -> None:
    assert parse_depfile_text("foo.obj: C:\\Program\\ Files\\bar.h") == (
        Path("C:\\Program Files\\bar.h"),
    )


def test_parse_depfile_windows_continuations() -> None:
    text = "foo.obj: C:\\src\\foo.cpp \\\n  C:\\include\\bar.h\n"
    assert parse_depfile_text(text) == (
        Path("C:\\src\\foo.cpp"),
        Path("C:\\include\\bar.h"),
    )


def test_parse_depfile_escaped_colon() -> None:
    assert parse_depfile_text(r"foo.obj: C\:/src/foo.h") == (Path("C:/src/foo.h"),)
    assert parse_depfile_text("foo.o: c\\:\\gcc\\stddef.h") == (
        Path("c:\\gcc\\stddef.h"),
    )
    assert parse_depfile_text(r"foo.o: c\\:/src.h") == (Path(r"c\:/src.h"),)


def test_parse_depfile_escaped_colon_ends_target() -> None:
    assert parse_depfile_text("foo1\\: x") == (Path("x"),)
    assert parse_depfile_text("C:\\build\\foo.obj\\: C:\\src\\foo.cpp") == (
        Path("C:\\src\\foo.cpp"),
    )


def test_parse_depfile_even_backslashes_end_filename() -> None:
    assert parse_depfile_text("foo.o: " + ("\\" * 4) + " file.h") == (
        Path("\\" * 4),
        Path("file.h"),
    )


def test_parse_depfile_odd_backslashes_keep_space() -> None:
    assert parse_depfile_text("foo.o: pre" + ("\\" * 3) + " mid.h") == (
        Path("pre\\ mid.h"),
    )


def test_parse_depfile_hash_and_dollar() -> None:
    assert parse_depfile_text(r"foo.o: weird\#name.h") == (Path("weird#name.h"),)
    assert parse_depfile_text(r"foo.o: weird\\#name.h") == (Path(r"weird\#name.h"),)
    assert parse_depfile_text(r"foo.o: $$HOME.h") == (Path("$HOME.h"),)
    assert parse_depfile_text("foo.o: bar.h # trailing comment") == (Path("bar.h"),)


def test_parse_depfile_ninja_backslash_mix() -> None:
    text = (
        "a\\ b\\#c.h: " + ("\\" * 5) + "  " + ("\\" * 4) + " " + "\\\\share\\info\\\\#1"
    )
    assert parse_depfile_text(text) == (
        Path("\\\\ "),
        Path("\\\\" * 2),
        Path("\\\\share\\info\\#1"),
    )


def test_parse_depfile_unc_path() -> None:
    assert parse_depfile_text("foo.o: //?/c:/bar.h") == (Path("//?/c:/bar.h"),)


def test_parse_depfile_missing_colon() -> None:
    with pytest.raises(DepfileError, match="missing ':'"):
        parse_depfile_text("not a depfile line")
    with pytest.raises(DepfileError, match="missing ':'"):
        parse_depfile_text("C:\\src\\foo.cpp")
