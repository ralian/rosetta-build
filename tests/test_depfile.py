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


def test_parse_depfile_missing_colon() -> None:
    with pytest.raises(DepfileError, match="missing ':'"):
        parse_depfile_text("not a depfile line")
