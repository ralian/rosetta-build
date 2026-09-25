"""PEP 517 build-backend hooks for rosetta-build."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rosetta_build.collect import Collection, CollectionError, collect
from rosetta_build.execute import BuildError, run_build
from rosetta_build.language import CompilerFamily
from rosetta_build.metadata import (
    MetadataError,
    ProjectMetadata,
    load_project_metadata,
    names_match,
)
from rosetta_build.plan import BuildPlan, PlanError, plan_build
from rosetta_build.target import WheelTarget
from rosetta_build.wheel import write_dist_info

__all__ = [
    "BackendError",
    "build_sdist",
    "build_wheel",
    "get_requires_for_build_sdist",
    "get_requires_for_build_wheel",
    "prepare_metadata_for_build_wheel",
]


class BackendError(Exception):
    """Raised when a PEP 517 hook cannot complete."""


def get_requires_for_build_wheel(
    config_settings: dict[str, Any] | None = None,
) -> list[str]:
    del config_settings
    return []


def get_requires_for_build_sdist(
    config_settings: dict[str, Any] | None = None,
) -> list[str]:
    del config_settings
    return []


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    del config_settings
    try:
        metadata = _distribution_metadata(Path.cwd())
        return write_dist_info(metadata, Path(metadata_directory))
    except (CollectionError, MetadataError, PlanError, BackendError) as exc:
        raise BackendError(str(exc)) from exc


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    del metadata_directory
    try:
        plan = _plan_for_cwd(config_settings)
        asyncio.run(run_build(plan))
        target = _primary_wheel_target_name(plan)
        built = plan.wheel_artifact_by_target[target]
        return _copy_artifact(built, Path(wheel_directory))
    except (CollectionError, MetadataError, PlanError, BuildError, BackendError) as exc:
        raise BackendError(str(exc)) from exc


def build_sdist(
    sdist_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    try:
        plan = _plan_for_cwd(config_settings)
        asyncio.run(run_build(plan))
        target = _primary_wheel_target_name(plan)
        built = plan.sdist_artifact_by_target[target]
        return _copy_artifact(built, Path(sdist_directory))
    except (CollectionError, MetadataError, PlanError, BuildError, BackendError) as exc:
        raise BackendError(str(exc)) from exc


def _plan_for_cwd(config_settings: dict[str, Any] | None) -> BuildPlan:
    source_tree = Path.cwd()
    collection = collect(source_tree)
    _primary_wheel_target(collection, load_project_metadata(source_tree))
    build_dir = _build_dir(source_tree, config_settings)
    family = _family(config_settings)
    return plan_build(collection, build_dir=build_dir, family=family)


def _distribution_metadata(source_tree: Path) -> ProjectMetadata:
    collection = collect(source_tree)
    metadata = load_project_metadata(source_tree)
    target = _primary_wheel_target(collection, metadata)
    if names_match(target.name, metadata.name):
        return metadata
    return metadata.with_name(target.name)


def _primary_wheel_target(
    collection: Collection, metadata: ProjectMetadata
) -> WheelTarget:
    wheels = [
        target
        for target in collection.targets.values()
        if isinstance(target, WheelTarget)
    ]
    if not wheels:
        raise BackendError(
            'PEP 517 backend requires at least one type = "wheel" target'
        )
    matching = [target for target in wheels if names_match(target.name, metadata.name)]
    if len(matching) == 1:
        return matching[0]
    if len(wheels) == 1:
        return wheels[0]
    names = ", ".join(sorted(target.name for target in wheels))
    raise BackendError(
        f"ambiguous wheel targets for distribution {metadata.name!r}: {names}"
    )


def _primary_wheel_target_name(plan: BuildPlan) -> str:
    if len(plan.wheel_steps) == 1:
        return plan.wheel_steps[0].target
    if not plan.wheel_steps:
        raise BackendError("planned build has no wheel targets")
    names = ", ".join(step.target for step in plan.wheel_steps)
    raise BackendError(f"planned build has multiple wheel targets: {names}")


def _build_dir(source_tree: Path, config_settings: dict[str, Any] | None) -> Path:
    configured = _config_value(config_settings, "build-dir", "build_dir")
    if configured is not None:
        path = Path(configured)
        if not path.is_absolute():
            path = source_tree / path
        return path
    return Path(tempfile.mkdtemp(prefix="rosetta-build-"))


def _family(config_settings: dict[str, Any] | None) -> CompilerFamily:
    configured = _config_value(config_settings, "family") or CompilerFamily.GCC.value
    try:
        return CompilerFamily(configured)
    except ValueError as exc:
        raise BackendError(f"unknown compiler family: {configured!r}") from exc


def _config_value(config_settings: Mapping[str, Any] | None, *keys: str) -> str | None:
    if not config_settings:
        return None
    for key in keys:
        if key not in config_settings:
            continue
        value = config_settings[key]
        if isinstance(value, list):
            if not value:
                return None
            return str(value[-1])
        return str(value)
    return None


def _copy_artifact(built: Path, destination_dir: Path) -> str:
    destination_dir.mkdir(parents=True, exist_ok=True)
    dest = destination_dir / built.name
    shutil.copy2(built, dest)
    return dest.name
