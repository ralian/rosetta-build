"""Plan compile and link steps from a collected source tree."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from rosetta_build.collect import Collection
from rosetta_build.compiler import (
    BmiInput,
    BuildObject,
    CompileRequest,
    LinkRequest,
    ModuleUnitKind,
)
from rosetta_build.language import CompilerFamily, Language
from rosetta_build.options import CompileSettings, CxxStandard, LinkSettings
from rosetta_build.target import (
    DynamicLibraryTarget,
    ExecutableTarget,
    ModuleImplementationTarget,
    ModuleInterfaceTarget,
    ModulePartitionTarget,
    ModuleTarget,
    NativeTarget,
    StaticLibraryTarget,
    Target,
    WheelTarget,
)
from rosetta_build.wheel import (
    WheelRequest,
    sdist_filename,
    wheel_filename,
)

__all__ = [
    "BuildPlan",
    "CompileStep",
    "LinkStep",
    "PlanError",
    "WheelStep",
    "plan_build",
]


class PlanError(Exception):
    """Raised when a collection cannot be lowered to compile/link steps."""


@dataclass(frozen=True, slots=True)
class CompileStep:
    target: str
    language: Language
    request: CompileRequest


@dataclass(frozen=True, slots=True)
class LinkStep:
    target: str
    language: Language
    request: LinkRequest


@dataclass(frozen=True, slots=True)
class WheelStep:
    """Build a pure-Python wheel and matching sdist for one ``WheelTarget``."""

    target: str
    request: WheelRequest


@dataclass(frozen=True, slots=True)
class BuildPlan:
    """Ordered compile, wheel, then link work for one toolchain family."""

    family: CompilerFamily
    build_dir: Path
    compile_steps: tuple[CompileStep, ...]
    wheel_steps: tuple[WheelStep, ...]
    link_steps: tuple[LinkStep, ...]
    objects_by_target: Mapping[str, tuple[Path, ...]]
    link_artifact_by_target: Mapping[str, Path]
    wheel_artifact_by_target: Mapping[str, Path]
    sdist_artifact_by_target: Mapping[str, Path]


def plan_build(
    collection: Collection,
    *,
    build_dir: Path,
    family: CompilerFamily = CompilerFamily.GCC,
) -> BuildPlan:
    """Lower ``collection`` into compile, wheel/sdist, and link steps.

    Supported for now: ``CompilerFamily.GCC`` + ``Language.CXX`` native/module
    targets, plus pure-Python ``WheelTarget`` rows (wheel + sdist). Static
    libraries contribute objects only (no ``ar`` archive step yet); dynamic
    libraries and executables get link steps. Install only relocates built
    wheels later.
    """
    if family is not CompilerFamily.GCC:
        raise PlanError(
            f"planner currently supports only {CompilerFamily.GCC.value}, "
            f"got {family.value}"
        )

    build_dir = build_dir.resolve()
    targets = collection.targets
    pic_targets = _targets_needing_pic(targets)
    project = _load_project_table(collection.source_tree)

    objects_by_target: dict[str, tuple[Path, ...]] = {}
    bmi_by_exporter: dict[str, Path] = {}
    compile_steps: list[CompileStep] = []

    for name in collection.module_graph.topological_order(kind="module"):
        target = targets[name]
        if isinstance(target, WheelTarget):
            continue
        if not isinstance(target, NativeTarget):
            continue
        if target.language is not Language.CXX:
            raise PlanError(
                f"target {name!r} language {target.language.value} is not "
                f"supported by the {family.value} planner yet"
            )

        object_paths: list[Path] = []
        for source in sorted(target.sources):
            object_output = _object_path(build_dir, name, source)
            object_paths.append(object_output)
            compile_steps.append(
                CompileStep(
                    target=name,
                    language=target.language,
                    request=_compile_request(
                        collection,
                        build_dir=build_dir,
                        target_name=name,
                        source=source,
                        object_output=object_output,
                        needs_pic=name in pic_targets,
                        bmi_by_exporter=bmi_by_exporter,
                    ),
                )
            )
        objects_by_target[name] = tuple(object_paths)

        bmi = _bmi_output_path(build_dir, target)
        if bmi is not None:
            bmi_by_exporter[name] = bmi

    wheel_steps: list[WheelStep] = []
    wheel_artifact_by_target: dict[str, Path] = {}
    sdist_artifact_by_target: dict[str, Path] = {}
    for name in sorted(n for n, t in targets.items() if isinstance(t, WheelTarget)):
        target = targets[name]
        assert isinstance(target, WheelTarget)
        if not target.sources:
            raise PlanError(f"wheel target {name!r} has no sources")
        version = _project_version(project, wheel_target=name)
        wheel_out = build_dir / "wheels" / wheel_filename(name, version)
        sdist_out = build_dir / "sdists" / sdist_filename(name, version)
        wheel_artifact_by_target[name] = wheel_out
        sdist_artifact_by_target[name] = sdist_out
        wheel_steps.append(
            WheelStep(
                target=name,
                request=WheelRequest(
                    distribution_name=name,
                    version=version,
                    sources=tuple(sorted(target.sources)),
                    wheel_output=wheel_out,
                    sdist_output=sdist_out,
                    summary=_optional_str(project.get("description")),
                    requires_python=_optional_str(project.get("requires-python")),
                ),
            )
        )

    link_artifact_by_target: dict[str, Path] = {}
    link_steps: list[LinkStep] = []

    for name in _link_target_order(collection):
        target = targets[name]
        assert isinstance(target, NativeTarget)
        artifact = _link_artifact_path(build_dir, target)
        link_artifact_by_target[name] = artifact
        objects = _link_inputs(
            collection,
            target_name=name,
            objects_by_target=objects_by_target,
            link_artifact_by_target=link_artifact_by_target,
        )
        raw_flags: list[str] = []
        if isinstance(target, DynamicLibraryTarget):
            raw_flags.append("-shared")
        raw_flags.extend(target.link_opts)
        link_steps.append(
            LinkStep(
                target=name,
                language=target.language,
                request=LinkRequest(
                    objects=[BuildObject(name=path) for path in objects],
                    output=artifact,
                    settings=LinkSettings(raw_flags=tuple(raw_flags)),
                ),
            )
        )

    return BuildPlan(
        family=family,
        build_dir=build_dir,
        compile_steps=tuple(compile_steps),
        wheel_steps=tuple(wheel_steps),
        link_steps=tuple(link_steps),
        objects_by_target=objects_by_target,
        link_artifact_by_target=link_artifact_by_target,
        wheel_artifact_by_target=wheel_artifact_by_target,
        sdist_artifact_by_target=sdist_artifact_by_target,
    )


def _object_path(build_dir: Path, target_name: str, source: Path) -> Path:
    return build_dir / "obj" / target_name / f"{source.name}.o"


def _bmi_output_path(build_dir: Path, target: Target) -> Path | None:
    if isinstance(target, ModuleInterfaceTarget):
        return build_dir / "bmi" / f"{target.module}.gcm"
    if isinstance(target, ModulePartitionTarget):
        return build_dir / "bmi" / f"{target.module}-{target.partition}.gcm"
    return None


def _logical_export_name(target: Target) -> str | None:
    if isinstance(target, ModuleInterfaceTarget):
        return target.module
    if isinstance(target, ModulePartitionTarget):
        return f"{target.module}:{target.partition}"
    return None


def _link_artifact_path(build_dir: Path, target: NativeTarget) -> Path:
    out_dir = build_dir / "artifacts"
    if isinstance(target, ExecutableTarget):
        return out_dir / target.name
    if isinstance(target, DynamicLibraryTarget):
        return out_dir / f"lib{target.name}.so"
    raise PlanError(f"target {target.name!r} does not produce a link artifact")


def _compile_request(
    collection: Collection,
    *,
    build_dir: Path,
    target_name: str,
    source: Path,
    object_output: Path,
    needs_pic: bool,
    bmi_by_exporter: Mapping[str, Path],
) -> CompileRequest:
    target = collection.targets[target_name]
    assert isinstance(target, NativeTarget)

    module_unit = ModuleUnitKind.NONE
    module_name: str | None = None
    bmi_output: Path | None = None
    if isinstance(target, ModuleInterfaceTarget):
        module_unit = ModuleUnitKind.INTERFACE
        module_name = target.module
        bmi_output = _bmi_output_path(build_dir, target)
    elif isinstance(target, ModulePartitionTarget):
        module_unit = ModuleUnitKind.PARTITION
        module_name = f"{target.module}:{target.partition}"
        bmi_output = _bmi_output_path(build_dir, target)
    elif isinstance(target, ModuleImplementationTarget):
        module_unit = ModuleUnitKind.IMPLEMENTATION

    bmi_inputs = _bmi_inputs_for(collection, target_name, bmi_by_exporter)
    raw_flags = list(target.compile_opts)
    if needs_pic and "-fPIC" not in raw_flags:
        raw_flags.append("-fPIC")

    return CompileRequest(
        sources=[source],
        object_output=object_output,
        settings=_compile_settings(collection, target, raw_flags=raw_flags),
        bmi_output=bmi_output,
        module_name=module_name,
        module_unit=module_unit,
        bmi_inputs=bmi_inputs,
    )


def _compile_settings(
    collection: Collection,
    target: NativeTarget,
    *,
    raw_flags: Sequence[str],
) -> CompileSettings:
    standard: CxxStandard | None = None
    if target.language is Language.CXX and (
        isinstance(target, ModuleTarget) or target.module_visibility
    ):
        standard = CxxStandard.CXX23
    return CompileSettings(
        standard=standard,
        defines=dict(target.compile_defs),
        include_dirs=tuple(sorted(_include_dirs_for(collection, target))),
        raw_flags=tuple(raw_flags),
    )


def _include_dirs_for(collection: Collection, target: NativeTarget) -> set[Path]:
    dirs = set(target.include_dirs)
    seen = {target.name}
    stack = list(target.usage) + list(target.link_libraries)
    while stack:
        dep_name = stack.pop()
        if dep_name in seen:
            continue
        seen.add(dep_name)
        dep = collection.targets[dep_name]
        if not isinstance(dep, NativeTarget):
            continue
        dirs |= dep.include_dirs
        stack.extend(dep.usage)
        stack.extend(dep.link_libraries)
    return dirs


def _bmi_inputs_for(
    collection: Collection,
    target_name: str,
    bmi_by_exporter: Mapping[str, Path],
) -> tuple[BmiInput, ...]:
    target = collection.targets[target_name]
    assert isinstance(target, NativeTarget)
    dep_names: set[str] = set(target.module_visibility)
    if isinstance(target, ModuleTarget):
        dep_names |= target.imports

    inputs: list[BmiInput] = []
    for dep_name in sorted(dep_names):
        dep = collection.targets[dep_name]
        logical = _logical_export_name(dep)
        path = bmi_by_exporter.get(dep_name)
        if logical is None or path is None:
            continue
        inputs.append(BmiInput(module=logical, path=path))
    return tuple(inputs)


def _targets_needing_pic(targets: Mapping[str, Target]) -> set[str]:
    needed: set[str] = set()
    for name, target in targets.items():
        if not isinstance(target, DynamicLibraryTarget):
            continue
        needed.add(name)
        stack = list(target.link_libraries)
        while stack:
            dep_name = stack.pop()
            if dep_name in needed:
                continue
            dep = targets[dep_name]
            if isinstance(dep, StaticLibraryTarget):
                needed.add(dep_name)
                stack.extend(dep.link_libraries)
            elif isinstance(dep, ModuleTarget):
                needed.add(dep_name)
                stack.extend(dep.link_libraries)
                stack.extend(dep.imports)
    return needed


def _link_target_order(collection: Collection) -> list[str]:
    """Dynamic libraries first (link DAG order), then executables."""
    dynamic_order = [
        name
        for name in collection.link_graph.topological_order(kind="dynamic link")
        if isinstance(collection.targets[name], DynamicLibraryTarget)
    ]
    executables = sorted(
        name
        for name, target in collection.targets.items()
        if isinstance(target, ExecutableTarget)
    )
    return dynamic_order + executables


def _link_inputs(
    collection: Collection,
    *,
    target_name: str,
    objects_by_target: Mapping[str, tuple[Path, ...]],
    link_artifact_by_target: Mapping[str, Path],
) -> list[Path]:
    """Resolve object files and shared libraries for one link step."""
    objects: list[Path] = []
    shared: list[Path] = []
    visited: set[str] = set()

    def walk(name: str, *, root: bool) -> None:
        if name in visited:
            return
        visited.add(name)
        target = collection.targets[name]
        if isinstance(target, DynamicLibraryTarget) and not root:
            shared.append(link_artifact_by_target[name])
            return
        if name in objects_by_target:
            objects.extend(objects_by_target[name])
        if not isinstance(target, NativeTarget):
            return
        for dep in sorted(target.link_libraries):
            walk(dep, root=False)
        if isinstance(target, ModuleTarget):
            for dep in sorted(target.imports):
                walk(dep, root=False)

    walk(target_name, root=True)
    return objects + shared


def _load_project_table(source_tree: Path) -> dict[str, object]:
    pyproject = source_tree / "pyproject.toml"
    raw = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = raw.get("project")
    if project is None:
        return {}
    if not isinstance(project, dict):
        raise PlanError(f"{pyproject}: [project] must be a table")
    return project


def _project_version(project: Mapping[str, object], *, wheel_target: str) -> str:
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PlanError(
            f"wheel target {wheel_target!r} requires root [project].version "
            "to build a wheel/sdist"
        )
    return version.strip()


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
