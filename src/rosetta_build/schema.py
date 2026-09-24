"""Pydantic schemas for root and per-target TOML configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from rosetta_build.language import Language


class _TargetConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sources: list[Path] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target name must be non-empty")
        return value

    @field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, value: object) -> object:
        if isinstance(value, list):
            return [Path(item) for item in value]
        return value


class _NativeTargetConfigBase(_TargetConfigBase):
    language: Language
    include_dirs: list[Path] = Field(default_factory=list)
    compile_defs: dict[str, str | bool | int] = Field(default_factory=dict)
    compile_opts: list[str] = Field(default_factory=list)
    link_opts: list[str] = Field(default_factory=list)
    usage: list[str] = Field(default_factory=list)
    link_libraries: list[str] = Field(default_factory=list)

    @field_validator("include_dirs", mode="before")
    @classmethod
    def _coerce_include_dirs(cls, value: object) -> object:
        if isinstance(value, list):
            return [Path(item) for item in value]
        return value


class ExecutableTargetConfig(_NativeTargetConfigBase):
    type: Literal["executable"]


class StaticLibraryTargetConfig(_NativeTargetConfigBase):
    type: Literal["static_library"]


class DynamicLibraryTargetConfig(_NativeTargetConfigBase):
    type: Literal["dynamic_library"]


class WheelTargetConfig(_TargetConfigBase):
    type: Literal["wheel"]


TargetConfig = Annotated[
    ExecutableTargetConfig
    | StaticLibraryTargetConfig
    | DynamicLibraryTargetConfig
    | WheelTargetConfig,
    Field(discriminator="type"),
]

_TARGET_CONFIG_ADAPTER: TypeAdapter[TargetConfig] = TypeAdapter(TargetConfig)


def parse_target_config(raw: object) -> TargetConfig:
    return _TARGET_CONFIG_ADAPTER.validate_python(raw)


class RosettaBuildConfig(BaseModel):
    """Schema for ``[tool.rosetta-build]`` in the root ``pyproject.toml``."""

    model_config = ConfigDict(extra="forbid")

    targets: list[Path] = Field(default_factory=list)

    @field_validator("targets", mode="before")
    @classmethod
    def _coerce_target_paths(cls, value: object) -> object:
        if isinstance(value, list):
            return [Path(item) for item in value]
        return value
