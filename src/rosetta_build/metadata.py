"""PEP 621 project metadata → Core Metadata (PEP 566 / 639)."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "MetadataError",
    "Person",
    "ProjectMetadata",
    "canonicalize_name",
    "load_project_metadata",
    "names_match",
]


class MetadataError(Exception):
    """Raised when ``[project]`` cannot be mapped to Core Metadata."""


def canonicalize_name(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def names_match(left: str, right: str) -> bool:
    return canonicalize_name(left) == canonicalize_name(right)


@dataclass(frozen=True, slots=True)
class Person:
    name: str | None = None
    email: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Normalized PEP 621 metadata for one distribution."""

    name: str
    version: str
    summary: str | None = None
    description: str | None = None
    description_content_type: str | None = None
    requires_python: str | None = None
    license_expression: str | None = None
    license_text: str | None = None
    license_files: tuple[str, ...] = ()
    authors: tuple[Person, ...] = ()
    maintainers: tuple[Person, ...] = ()
    keywords: tuple[str, ...] = ()
    classifiers: tuple[str, ...] = ()
    urls: tuple[tuple[str, str], ...] = ()
    dependencies: tuple[str, ...] = ()
    optional_dependencies: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    scripts: Mapping[str, str] = field(default_factory=dict)
    gui_scripts: Mapping[str, str] = field(default_factory=dict)
    entry_points: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    dynamic: tuple[str, ...] = ()

    def with_name(self, name: str) -> ProjectMetadata:
        if name == self.name:
            return self
        return ProjectMetadata(
            name=name,
            version=self.version,
            summary=self.summary,
            description=self.description,
            description_content_type=self.description_content_type,
            requires_python=self.requires_python,
            license_expression=self.license_expression,
            license_text=self.license_text,
            license_files=self.license_files,
            authors=self.authors,
            maintainers=self.maintainers,
            keywords=self.keywords,
            classifiers=self.classifiers,
            urls=self.urls,
            dependencies=self.dependencies,
            optional_dependencies=dict(self.optional_dependencies),
            scripts=dict(self.scripts),
            gui_scripts=dict(self.gui_scripts),
            entry_points={group: dict(eps) for group, eps in self.entry_points.items()},
            dynamic=self.dynamic,
        )

    def to_core_metadata(self) -> str:
        """Render Core Metadata 2.4 text (METADATA / PKG-INFO body)."""
        if "version" in self.dynamic and not self.version:
            raise MetadataError("dynamic version is not supported yet")
        lines: list[str] = [
            "Metadata-Version: 2.4",
            f"Name: {self.name}",
            f"Version: {self.version}",
        ]
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        if self.requires_python:
            lines.append(f"Requires-Python: {self.requires_python}")
        if self.license_expression:
            lines.append(f"License-Expression: {self.license_expression}")
        if self.license_text and not self.license_expression:
            lines.append(f"License: {_single_line(self.license_text)}")
        for path in self.license_files:
            lines.append(f"License-File: {path}")
        for person in self.authors:
            lines.extend(_person_fields("Author", person))
        for person in self.maintainers:
            lines.extend(_person_fields("Maintainer", person))
        if self.keywords:
            lines.append(f"Keywords: {','.join(self.keywords)}")
        for classifier in self.classifiers:
            lines.append(f"Classifier: {classifier}")
        for label, url in self.urls:
            lines.append(f"Project-URL: {label}, {url}")
        for dep in self.dependencies:
            lines.append(f"Requires-Dist: {dep}")
        for extra, deps in sorted(self.optional_dependencies.items()):
            lines.append(f"Provides-Extra: {extra}")
            for dep in deps:
                lines.append(f"Requires-Dist: {dep} ; extra == '{extra}'")
        if self.description_content_type:
            lines.append(f"Description-Content-Type: {self.description_content_type}")
        body = "\n".join(lines) + "\n"
        if self.description:
            body += f"\n{self.description}"
            if not self.description.endswith("\n"):
                body += "\n"
        return body

    def entry_points_text(self) -> str | None:
        """Render ``entry_points.txt``, or ``None`` when empty."""
        groups: dict[str, dict[str, str]] = {
            group: dict(eps) for group, eps in self.entry_points.items()
        }
        if self.scripts:
            groups["console_scripts"] = {
                **groups.get("console_scripts", {}),
                **dict(self.scripts),
            }
        if self.gui_scripts:
            groups["gui_scripts"] = {
                **groups.get("gui_scripts", {}),
                **dict(self.gui_scripts),
            }
        if not groups:
            return None
        chunks: list[str] = []
        for group in sorted(groups):
            chunks.append(f"[{group}]")
            for name, value in sorted(groups[group].items()):
                chunks.append(f"{name} = {value}")
            chunks.append("")
        return "\n".join(chunks)


def load_project_metadata(source_tree: Path) -> ProjectMetadata:
    """Load and validate ``[project]`` from ``source_tree / pyproject.toml``."""
    pyproject = source_tree / "pyproject.toml"
    if not pyproject.is_file():
        raise MetadataError(f"missing pyproject.toml: {pyproject}")
    raw = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = raw.get("project")
    if not isinstance(project, dict):
        raise MetadataError(f"{pyproject} has no [project] table")
    return _parse_project(project, source_tree=source_tree, pyproject=pyproject)


def _parse_project(
    project: Mapping[str, object],
    *,
    source_tree: Path,
    pyproject: Path,
) -> ProjectMetadata:
    name = _require_str(project, "name", pyproject=pyproject)
    dynamic = _str_tuple(project.get("dynamic"), field="dynamic", pyproject=pyproject)
    version = _optional_str(project.get("version"))
    if version is None and "version" not in dynamic:
        raise MetadataError(f"{pyproject}: [project].version is required")
    if version is None:
        raise MetadataError(f"{pyproject}: dynamic version is not supported yet")

    unsupported = sorted(set(dynamic) - {"version"})
    if unsupported:
        raise MetadataError(
            f"{pyproject}: unsupported dynamic fields: {', '.join(unsupported)}"
        )

    summary = _optional_str(project.get("description"))
    description, content_type = _parse_readme(
        project.get("readme"), source_tree=source_tree, pyproject=pyproject
    )
    license_expression, license_text = _parse_license(
        project.get("license"), source_tree=source_tree, pyproject=pyproject
    )
    license_files = _parse_license_files(
        project.get("license-files"), pyproject=pyproject
    )

    return ProjectMetadata(
        name=name,
        version=version,
        summary=summary,
        description=description,
        description_content_type=content_type,
        requires_python=_optional_str(project.get("requires-python")),
        license_expression=license_expression,
        license_text=license_text,
        license_files=license_files,
        authors=_parse_people(
            project.get("authors"), field="authors", pyproject=pyproject
        ),
        maintainers=_parse_people(
            project.get("maintainers"), field="maintainers", pyproject=pyproject
        ),
        keywords=_parse_keywords(project.get("keywords"), pyproject=pyproject),
        classifiers=_str_tuple(
            project.get("classifiers"), field="classifiers", pyproject=pyproject
        ),
        urls=_parse_urls(project.get("urls"), pyproject=pyproject),
        dependencies=_str_tuple(
            project.get("dependencies"), field="dependencies", pyproject=pyproject
        ),
        optional_dependencies=_parse_optional_dependencies(
            project.get("optional-dependencies"), pyproject=pyproject
        ),
        scripts=_parse_str_table(
            project.get("scripts"), field="scripts", pyproject=pyproject
        ),
        gui_scripts=_parse_str_table(
            project.get("gui-scripts"), field="gui-scripts", pyproject=pyproject
        ),
        entry_points=_parse_entry_points(
            project.get("entry-points"), pyproject=pyproject
        ),
        dynamic=dynamic,
    )


def _parse_readme(
    value: object,
    *,
    source_tree: Path,
    pyproject: Path,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, str):
        path = _resolve_project_path(
            source_tree, value, pyproject=pyproject, label="readme"
        )
        return path.read_text(encoding="utf-8"), _content_type_for(path)
    if isinstance(value, dict):
        file_name = value.get("file")
        text = value.get("text")
        content_type = _optional_str(value.get("content-type"))
        if file_name is not None and text is not None:
            raise MetadataError(f"{pyproject}: readme cannot set both file and text")
        if isinstance(file_name, str):
            path = _resolve_project_path(
                source_tree, file_name, pyproject=pyproject, label="readme.file"
            )
            body = path.read_text(encoding="utf-8")
            return body, content_type or _content_type_for(path)
        if isinstance(text, str):
            if content_type is None:
                raise MetadataError(f"{pyproject}: readme.text requires content-type")
            return text, content_type
    raise MetadataError(f"{pyproject}: invalid [project].readme")


def _parse_license(
    value: object,
    *,
    source_tree: Path,
    pyproject: Path,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, str):
        return value.strip(), None
    if isinstance(value, dict):
        text = value.get("text")
        file_name = value.get("file")
        if text is not None and file_name is not None:
            raise MetadataError(f"{pyproject}: license cannot set both text and file")
        if isinstance(text, str):
            return None, text
        if isinstance(file_name, str):
            path = _resolve_project_path(
                source_tree, file_name, pyproject=pyproject, label="license.file"
            )
            return None, path.read_text(encoding="utf-8")
    raise MetadataError(f"{pyproject}: invalid [project].license")


def _parse_license_files(value: object, *, pyproject: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(item for item in value)
    raise MetadataError(
        f"{pyproject}: [project].license-files must be a list of strings"
    )


def _parse_people(value: object, *, field: str, pyproject: Path) -> tuple[Person, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise MetadataError(f"{pyproject}: [project].{field} must be a list of tables")
    people: list[Person] = []
    for item in value:
        if not isinstance(item, dict):
            raise MetadataError(
                f"{pyproject}: [project].{field} entries must be tables"
            )
        name = _optional_str(item.get("name"))
        email = _optional_str(item.get("email"))
        if name is None and email is None:
            raise MetadataError(
                f"{pyproject}: [project].{field} entry needs name and/or email"
            )
        people.append(Person(name=name, email=email))
    return tuple(people)


def _parse_keywords(value: object, *, pyproject: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(item for item in value)
    raise MetadataError(f"{pyproject}: [project].keywords must be a string or list")


def _parse_urls(value: object, *, pyproject: Path) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise MetadataError(f"{pyproject}: [project].urls must be a table")
    urls: list[tuple[str, str]] = []
    for label, url in value.items():
        if not isinstance(label, str) or not isinstance(url, str):
            raise MetadataError(f"{pyproject}: [project].urls values must be strings")
        urls.append((label, url))
    return tuple(urls)


def _parse_optional_dependencies(
    value: object, *, pyproject: Path
) -> dict[str, tuple[str, ...]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MetadataError(
            f"{pyproject}: [project].optional-dependencies must be a table"
        )
    result: dict[str, tuple[str, ...]] = {}
    for extra, deps in value.items():
        if not isinstance(extra, str):
            raise MetadataError(
                f"{pyproject}: optional-dependencies keys must be strings"
            )
        result[extra] = _str_tuple(
            deps, field=f"optional-dependencies.{extra}", pyproject=pyproject
        )
    return result


def _parse_str_table(value: object, *, field: str, pyproject: Path) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MetadataError(f"{pyproject}: [project].{field} must be a table")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise MetadataError(
                f"{pyproject}: [project].{field} entries must be strings"
            )
        result[key] = item
    return result


def _parse_entry_points(value: object, *, pyproject: Path) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MetadataError(f"{pyproject}: [project].entry-points must be a table")
    result: dict[str, dict[str, str]] = {}
    for group, entries in value.items():
        if not isinstance(group, str):
            raise MetadataError(
                f"{pyproject}: entry-points group names must be strings"
            )
        result[group] = _parse_str_table(
            entries, field=f"entry-points.{group}", pyproject=pyproject
        )
    return result


def _person_fields(kind: str, person: Person) -> list[str]:
    if person.name and person.email:
        return [f"{kind}-email: {person.name} <{person.email}>"]
    if person.email:
        return [f"{kind}-email: {person.email}"]
    assert person.name is not None
    return [f"{kind}: {person.name}"]


def _require_str(table: Mapping[str, object], key: str, *, pyproject: Path) -> str:
    value = _optional_str(table.get(key))
    if value is None:
        raise MetadataError(f"{pyproject}: [project].{key} is required")
    return value


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _str_tuple(value: object, *, field: str, pyproject: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(item for item in value)
    raise MetadataError(f"{pyproject}: [project].{field} must be a list of strings")


def _resolve_project_path(
    source_tree: Path, rel: str, *, pyproject: Path, label: str
) -> Path:
    path = (source_tree / rel).resolve()
    if not path.is_relative_to(source_tree.resolve()):
        raise MetadataError(f"{pyproject}: {label} escapes source tree: {rel}")
    if not path.is_file():
        raise MetadataError(f"{pyproject}: {label} not found: {rel}")
    return path


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "text/markdown"
    if suffix in {".rst", ".rest"}:
        return "text/x-rst"
    return "text/plain"


def _single_line(text: str) -> str:
    return " ".join(text.split())
