"""Tests for the PEP 517 build-backend hooks."""

from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path

from rosetta_build import backend

TREES = Path(__file__).parent / "trees"


def test_pep517_hooks_build_wheel_and_sdist(tmp_path: Path) -> None:
    source = TREES / "build_wheel"
    wheel_dir = tmp_path / "wheels"
    sdist_dir = tmp_path / "sdists"
    meta_dir = tmp_path / "meta"
    wheel_dir.mkdir()
    sdist_dir.mkdir()
    meta_dir.mkdir()

    previous = Path.cwd()
    os.chdir(source)
    try:
        assert backend.get_requires_for_build_wheel() == []
        assert backend.get_requires_for_build_sdist() == []

        dist_info = backend.prepare_metadata_for_build_wheel(str(meta_dir))
        assert dist_info == "example_pkg-1.2.3.dist-info"
        metadata = (meta_dir / dist_info / "METADATA").read_text(encoding="utf-8")
        assert "Name: example_pkg" in metadata
        assert "License-Expression: MIT" in metadata
        assert (meta_dir / dist_info / "entry_points.txt").is_file()

        wheel_name = backend.build_wheel(
            str(wheel_dir),
            config_settings={"build-dir": str(tmp_path / "build")},
        )
        assert wheel_name == "example_pkg-1.2.3-py3-none-any.whl"
        wheel_path = wheel_dir / wheel_name
        assert wheel_path.is_file()
        with zipfile.ZipFile(wheel_path) as zf:
            assert "example_pkg/__init__.py" in zf.namelist()
            assert "example_pkg-1.2.3.dist-info/entry_points.txt" in zf.namelist()
            text = zf.read("example_pkg-1.2.3.dist-info/METADATA").decode()
            assert "Requires-Dist: pydantic>=2" in text

        sdist_name = backend.build_sdist(
            str(sdist_dir),
            config_settings={"build-dir": str(tmp_path / "build-sdist")},
        )
        assert sdist_name == "example-pkg-1.2.3.tar.gz"
        with tarfile.open(sdist_dir / sdist_name, "r:gz") as tf:
            names = set(tf.getnames())
            assert "example-pkg-1.2.3/pyproject.toml" in names
            assert "example-pkg-1.2.3/python/pkg/target.toml" in names
            assert "example-pkg-1.2.3/python/pkg/src/example_pkg/__init__.py" in names
            pkg = tf.extractfile("example-pkg-1.2.3/PKG-INFO")
            assert pkg is not None
            assert b"Name: example_pkg" in pkg.read()
    finally:
        os.chdir(previous)
