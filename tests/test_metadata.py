"""Tests for PEP 621 metadata mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.metadata import MetadataError, load_project_metadata

TREES = Path(__file__).parent / "trees"


def test_load_project_metadata_maps_pep621_fields() -> None:
    meta = load_project_metadata(TREES / "build_wheel")
    assert meta.name == "example_pkg"
    assert meta.version == "1.2.3"
    assert meta.summary == "Wheel build fixture"
    assert meta.requires_python == ">=3.14"
    assert meta.license_expression == "MIT"
    assert meta.description is not None
    assert "Example package" in meta.description
    assert meta.description_content_type == "text/markdown"
    assert meta.authors[0].name == "Test Author"
    assert meta.dependencies == ("pydantic>=2",)
    assert meta.optional_dependencies["dev"] == ("pytest>=8",)
    assert meta.scripts["example-pkg"] == "example_pkg:main"
    assert meta.urls == (("Homepage", "https://example.com/example_pkg"),)

    text = meta.to_core_metadata()
    assert "Name: example_pkg" in text
    assert "License-Expression: MIT" in text
    assert "Requires-Dist: pydantic>=2" in text
    assert "Provides-Extra: dev" in text
    assert "Requires-Dist: pytest>=8 ; extra == 'dev'" in text
    assert "Author-email: Test Author <test@example.com>" in text
    assert "Project-URL: Homepage, https://example.com/example_pkg" in text
    assert "Description-Content-Type: text/markdown" in text
    assert "Example package" in text

    entry_points = meta.entry_points_text()
    assert entry_points is not None
    assert "[console_scripts]" in entry_points
    assert "example-pkg = example_pkg:main" in entry_points


def test_load_project_metadata_requires_version(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\n',
        encoding="utf-8",
    )
    with pytest.raises(MetadataError, match="version is required"):
        load_project_metadata(tmp_path)
