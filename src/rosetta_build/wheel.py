"""Assemble pure-Python wheels and sdists from ``WheelTarget`` sources."""

from __future__ import annotations

import base64
import hashlib
import io
import tarfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rosetta_build.metadata import ProjectMetadata, canonicalize_name

__all__ = [
    "WheelBuildError",
    "WheelRequest",
    "build_sdist",
    "build_wheel",
    "canonicalize_name",
    "sdist_filename",
    "wheel_dist_name",
    "wheel_filename",
    "write_dist_info",
]


class WheelBuildError(Exception):
    """Raised when a wheel or sdist cannot be assembled."""


@dataclass(frozen=True, slots=True)
class WheelRequest:
    """Inputs for one pure-Python wheel + sdist pair."""

    metadata: ProjectMetadata
    sources: tuple[Path, ...]
    wheel_output: Path
    sdist_output: Path
    pyproject_text: str | None = None

    @property
    def distribution_name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version


def wheel_dist_name(name: str) -> str:
    """Distribution segment used in wheel / dist-info filenames."""
    return canonicalize_name(name).replace("-", "_")


def build_wheel(request: WheelRequest) -> Path:
    """Write a ``py3-none-any`` wheel to ``request.wheel_output``."""
    files = _collect_payload_files(request.sources)
    if not files:
        raise WheelBuildError(
            f"wheel {request.distribution_name!r} has no files under sources"
        )

    dist = wheel_dist_name(request.distribution_name)
    version = request.version
    dist_info = f"{dist}-{version}.dist-info"
    metadata = request.metadata.to_core_metadata()
    entry_points = request.metadata.entry_points_text()
    wheel_text = (
        "Wheel-Version: 1.0\n"
        "Generator: rosetta-build\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )

    records: list[tuple[str, str, str]] = []
    output = request.wheel_output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arcname in files:
            data = abs_path.read_bytes()
            zf.writestr(arcname, data)
            records.append((arcname, _hash_digest(data), str(len(data))))

        meta_bytes = metadata.encode("utf-8")
        meta_name = f"{dist_info}/METADATA"
        zf.writestr(meta_name, meta_bytes)
        records.append((meta_name, _hash_digest(meta_bytes), str(len(meta_bytes))))

        wheel_bytes = wheel_text.encode("utf-8")
        wheel_name = f"{dist_info}/WHEEL"
        zf.writestr(wheel_name, wheel_bytes)
        records.append((wheel_name, _hash_digest(wheel_bytes), str(len(wheel_bytes))))

        if entry_points is not None:
            ep_bytes = entry_points.encode("utf-8")
            ep_name = f"{dist_info}/entry_points.txt"
            zf.writestr(ep_name, ep_bytes)
            records.append((ep_name, _hash_digest(ep_bytes), str(len(ep_bytes))))

        record_name = f"{dist_info}/RECORD"
        record_body = "".join(
            f"{path},{digest},{size}\n" for path, digest, size in records
        )
        record_body += f"{record_name},,\n"
        zf.writestr(record_name, record_body.encode("utf-8"))

    return output


def build_sdist(request: WheelRequest) -> Path:
    """Write a source distribution tarball to ``request.sdist_output``."""
    files = _collect_payload_files(request.sources)
    if not files:
        raise WheelBuildError(
            f"sdist {request.distribution_name!r} has no files under sources"
        )

    dist = canonicalize_name(request.distribution_name)
    version = request.version
    root = f"{dist}-{version}"
    metadata = request.metadata.to_core_metadata()
    pyproject = request.pyproject_text or _sdist_pyproject(request.metadata)

    output = request.sdist_output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tarfile.open(output, "w:gz") as tf:
        _add_tar_bytes(tf, f"{root}/PKG-INFO", metadata.encode("utf-8"))
        _add_tar_bytes(tf, f"{root}/pyproject.toml", pyproject.encode("utf-8"))
        for abs_path, arcname in files:
            _add_tar_bytes(tf, f"{root}/{arcname}", abs_path.read_bytes())

    return output


def write_dist_info(metadata: ProjectMetadata, metadata_directory: Path) -> str:
    """Write a ``.dist-info`` directory for ``prepare_metadata_for_build_wheel``.

    Returns the basename of the created directory.
    """
    dist = wheel_dist_name(metadata.name)
    dirname = f"{dist}-{metadata.version}.dist-info"
    dest = metadata_directory / dirname
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "METADATA").write_text(metadata.to_core_metadata(), encoding="utf-8")
    wheel_text = (
        "Wheel-Version: 1.0\n"
        "Generator: rosetta-build\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )
    (dest / "WHEEL").write_text(wheel_text, encoding="utf-8")
    entry_points = metadata.entry_points_text()
    if entry_points is not None:
        (dest / "entry_points.txt").write_text(entry_points, encoding="utf-8")
    return dirname


def _collect_payload_files(sources: Sequence[Path]) -> list[tuple[Path, str]]:
    collected: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for source in sources:
        if not source.exists():
            raise WheelBuildError(f"wheel source does not exist: {source}")
        if source.is_file():
            candidates = [(source, source.name)]
        elif source.is_dir():
            candidates = []
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                if _should_skip(path):
                    continue
                rel = path.relative_to(source).as_posix()
                candidates.append((path, f"{source.name}/{rel}"))
        else:
            raise WheelBuildError(f"wheel source is not a file or directory: {source}")

        for abs_path, arcname in candidates:
            if arcname in seen:
                raise WheelBuildError(
                    f"duplicate archive path in wheel payload: {arcname}"
                )
            seen.add(arcname)
            collected.append((abs_path, arcname))
    return collected


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts or ".git" in parts:
        return True
    return path.suffix in {".pyc", ".pyo"}


def _sdist_pyproject(metadata: ProjectMetadata) -> str:
    lines = [
        "[project]",
        f'name = "{metadata.name}"',
        f'version = "{metadata.version}"',
    ]
    if metadata.summary:
        lines.append(f'description = "{_escape_toml(metadata.summary)}"')
    if metadata.requires_python:
        lines.append(f'requires-python = "{_escape_toml(metadata.requires_python)}"')
    lines.append("")
    lines.append("[build-system]")
    lines.append('requires = ["rosetta-build"]')
    lines.append('build-backend = "rosetta_build.backend"')
    lines.append("")
    return "\n".join(lines)


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _hash_digest(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}"


def _add_tar_bytes(tf: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def wheel_filename(distribution_name: str, version: str) -> str:
    return f"{wheel_dist_name(distribution_name)}-{version}-py3-none-any.whl"


def sdist_filename(distribution_name: str, version: str) -> str:
    return f"{canonicalize_name(distribution_name)}-{version}.tar.gz"
