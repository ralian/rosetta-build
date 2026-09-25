"""P1689R5 interchange format for C++ module dependency scanning.

See: https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2022/p1689r5.html
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from rosetta_build.compiler import BmiInput

__all__ = [
    "SUPPORTED_REVISION",
    "SUPPORTED_VERSION",
    "LookupMethod",
    "P1689Document",
    "P1689Error",
    "P1689Rule",
    "ProvidedModule",
    "RequiredModule",
    "bmi_inputs_from_rule",
    "dump_p1689",
    "dump_p1689_bytes",
    "merge_documents",
    "module_identity_key",
    "parse_p1689",
    "parse_p1689_file",
    "provider_index",
    "resolve_compile_edges",
]

SUPPORTED_VERSION = 1
SUPPORTED_REVISION = 0


class P1689Error(ValueError):
    """Raised when a P1689 document is invalid or unsupported."""


class LookupMethod(StrEnum):
    BY_NAME = "by-name"
    INCLUDE_ANGLE = "include-angle"
    INCLUDE_QUOTE = "include-quote"


def _kebab(*names: str) -> AliasChoices:
    """Accept kebab-case JSON keys and snake_case Python names."""
    return AliasChoices(*names)


class _P1689Model(BaseModel):
    """Base for P1689 objects: kebab-case wire names, ignore vendor extensions."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        frozen=True,
    )


class ProvidedModule(_P1689Model):
    logical_name: str = Field(
        min_length=1,
        validation_alias=_kebab("logical-name", "logical_name"),
        serialization_alias="logical-name",
    )
    source_path: Path | None = Field(
        default=None,
        validation_alias=_kebab("source-path", "source_path"),
        serialization_alias="source-path",
    )
    compiled_module_path: Path | None = Field(
        default=None,
        validation_alias=_kebab("compiled-module-path", "compiled_module_path"),
        serialization_alias="compiled-module-path",
    )
    unique_on_source_path: bool = Field(
        default=False,
        validation_alias=_kebab("unique-on-source-path", "unique_on_source_path"),
        serialization_alias="unique-on-source-path",
    )
    is_interface: bool = Field(
        default=True,
        validation_alias=_kebab("is-interface", "is_interface"),
        serialization_alias="is-interface",
    )

    @field_validator("source_path", "compiled_module_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        if value is None or isinstance(value, Path):
            return value
        return Path(str(value))


class RequiredModule(_P1689Model):
    logical_name: str = Field(
        min_length=1,
        validation_alias=_kebab("logical-name", "logical_name"),
        serialization_alias="logical-name",
    )
    source_path: Path | None = Field(
        default=None,
        validation_alias=_kebab("source-path", "source_path"),
        serialization_alias="source-path",
    )
    compiled_module_path: Path | None = Field(
        default=None,
        validation_alias=_kebab("compiled-module-path", "compiled_module_path"),
        serialization_alias="compiled-module-path",
    )
    unique_on_source_path: bool = Field(
        default=False,
        validation_alias=_kebab("unique-on-source-path", "unique_on_source_path"),
        serialization_alias="unique-on-source-path",
    )
    lookup_method: LookupMethod = Field(
        default=LookupMethod.BY_NAME,
        validation_alias=_kebab("lookup-method", "lookup_method"),
        serialization_alias="lookup-method",
    )

    @field_validator("source_path", "compiled_module_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        if value is None or isinstance(value, Path):
            return value
        return Path(str(value))


class P1689Rule(_P1689Model):
    primary_output: Path | None = Field(
        default=None,
        validation_alias=_kebab("primary-output", "primary_output"),
        serialization_alias="primary-output",
    )
    outputs: tuple[Path, ...] = ()
    provides: tuple[ProvidedModule, ...] = ()
    requires: tuple[RequiredModule, ...] = ()
    work_directory: Path | None = Field(
        default=None,
        validation_alias=_kebab("work-directory", "work_directory"),
        serialization_alias="work-directory",
    )

    @field_validator("primary_output", "work_directory", mode="before")
    @classmethod
    def _coerce_optional_path(cls, value: object) -> object:
        if value is None or isinstance(value, Path):
            return value
        return Path(str(value))

    @field_validator("outputs", mode="before")
    @classmethod
    def _coerce_outputs(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, list | tuple):
            return tuple(Path(str(item)) for item in value)
        return value

    @field_validator("provides", "requires", mode="before")
    @classmethod
    def _coerce_module_lists(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, list):
            return tuple(value)
        return value


class P1689Document(_P1689Model):
    version: int
    revision: int = 0
    rules: tuple[P1689Rule, ...]

    @field_validator("rules", mode="before")
    @classmethod
    def _coerce_rules(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("rules")
    @classmethod
    def _rules_nonempty(cls, value: tuple[P1689Rule, ...]) -> tuple[P1689Rule, ...]:
        if not value:
            raise ValueError("rules must contain at least one rule")
        return value


def parse_p1689(raw: str | bytes | Mapping[str, Any]) -> P1689Document:
    """Parse a P1689R5 document from JSON text or a decoded mapping."""
    if isinstance(raw, bytes):
        payload: object = json.loads(raw.decode("utf-8"))
    elif isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw
    try:
        document = P1689Document.model_validate(payload)
    except Exception as exc:
        raise P1689Error(f"invalid P1689 document: {exc}") from exc
    if document.version != SUPPORTED_VERSION:
        raise P1689Error(
            f"unsupported P1689 version {document.version}; "
            f"only version {SUPPORTED_VERSION} is supported"
        )
    _validate_unique_outputs(document)
    provider_index(document)
    return document


def parse_p1689_file(path: Path) -> P1689Document:
    return parse_p1689(path.read_text(encoding="utf-8"))


def dump_p1689(document: P1689Document, *, indent: int | None = 2) -> str:
    """Serialize a P1689 document to UTF-8 JSON text (kebab-case keys)."""
    payload = document.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    text = json.dumps(payload, indent=indent, ensure_ascii=False)
    return text if indent is None else f"{text}\n"


def dump_p1689_bytes(document: P1689Document, *, indent: int | None = 2) -> bytes:
    return dump_p1689(document, indent=indent).encode("utf-8")


def module_identity_key(module: ProvidedModule | RequiredModule) -> str:
    """Stable key for correlating provides/requires (named module or header unit)."""
    if module.unique_on_source_path:
        if module.source_path is None:
            raise P1689Error(
                f"module {module.logical_name!r} has unique-on-source-path but "
                f"no source-path"
            )
        return f"source:{module.source_path.as_posix()}"
    return f"name:{module.logical_name}"


def provider_index(document: P1689Document) -> dict[str, P1689Rule]:
    """Map module identity keys to the rule that provides them."""
    index: dict[str, P1689Rule] = {}
    for rule in document.rules:
        for provided in rule.provides:
            key = module_identity_key(provided)
            if key in index:
                raise P1689Error(f"duplicate module provider for {key}")
            index[key] = rule
    return index


def resolve_compile_edges(
    document: P1689Document,
) -> dict[Path, frozenset[Path]]:
    """Build primary-output → prerequisite primary-output edges from a scan.

    Rules without ``primary-output`` are skipped. Requires that cannot be
    resolved to a providing rule in the same document are omitted (e.g. system
    modules); the planner may still need them via other means.
    """
    providers = provider_index(document)
    edges: dict[Path, frozenset[Path]] = {}
    for rule in document.rules:
        if rule.primary_output is None:
            continue
        deps: set[Path] = set()
        for required in rule.requires:
            key = module_identity_key(required)
            provider = providers.get(key)
            if provider is None or provider.primary_output is None:
                continue
            if provider.primary_output != rule.primary_output:
                deps.add(provider.primary_output)
        edges[rule.primary_output] = frozenset(deps)
    return edges


def bmi_inputs_from_rule(rule: P1689Rule) -> tuple[BmiInput, ...]:
    """Convert requires that include ``compiled-module-path`` into ``BmiInput``s."""
    inputs: list[BmiInput] = []
    for required in rule.requires:
        if required.compiled_module_path is None:
            continue
        inputs.append(
            BmiInput(module=required.logical_name, path=required.compiled_module_path)
        )
    return tuple(inputs)


def _validate_unique_outputs(document: P1689Document) -> None:
    seen: set[str] = set()
    for rule in document.rules:
        paths: list[Path] = []
        if rule.primary_output is not None:
            paths.append(rule.primary_output)
        paths.extend(rule.outputs)
        for path in paths:
            key = path.as_posix()
            if key in seen:
                raise P1689Error(f"duplicate output path in P1689 rules: {key}")
            seen.add(key)


def merge_documents(documents: Sequence[P1689Document]) -> P1689Document:
    """Combine multiple scan files into one document (same version)."""
    if not documents:
        raise P1689Error("cannot merge an empty document list")
    rules: list[P1689Rule] = []
    for document in documents:
        if document.version != SUPPORTED_VERSION:
            raise P1689Error(
                f"unsupported P1689 version {document.version} while merging"
            )
        rules.extend(document.rules)
    merged = P1689Document(
        version=SUPPORTED_VERSION,
        revision=max(doc.revision for doc in documents),
        rules=tuple(rules),
    )
    _validate_unique_outputs(merged)
    provider_index(merged)
    return merged
