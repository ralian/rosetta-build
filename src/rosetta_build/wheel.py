"""Assemble pure-Python wheels and sdists from ``WheelTarget`` sources."""

from __future__ import annotations

import base64
import hashlib
import io
import re
import tarfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "WheelBuildError",
    "WheelRequest",
    "build_sdist",
    "build_wheel",
    "canonicalize_name",
    "sdist_filename",
    "wheel_dist_name",
    "wheel_filename",
]


class WheelBuildError(Exception):
    """Raised when a wheel or sdist cannot be assembled."""


@dataclass(frozen=True, slots=True)
class WheelRequest:
    """Inputs for one pure-Python wheel + sdist pair."""

    distribution_name: str
    version: str
    sources: tuple[Path, ...]
    wheel_output: Path
    sdist_output: Path
    summary: str | None = None
    requires_python: str | None = None
    metadata_extra: Mapping[str, str] = field(default_factory=dict)


def canonicalize_name(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


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
    metadata = _core_metadata(request)
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
    metadata = _core_metadata(request)
    pyproject = _sdist_pyproject(request)

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


def _core_metadata(request: WheelRequest) -> str:
    lines = [
        "Metadata-Version: 2.4",
        f"Name: {request.distribution_name}",
        f"Version: {request.version}",
    ]
    if request.summary:
        lines.append(f"Summary: {request.summary}")
    if request.requires_python:
        lines.append(f"Requires-Python: {request.requires_python}")
    for key, value in request.metadata_extra.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _sdist_pyproject(request: WheelRequest) -> str:
    lines = [
        "[project]",
        f'name = "{request.distribution_name}"',
        f'version = "{request.version}"',
    ]
    if request.summary:
        lines.append(f'description = "{_escape_toml(request.summary)}"')
    if request.requires_python:
        lines.append(f'requires-python = "{_escape_toml(request.requires_python)}"')
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
