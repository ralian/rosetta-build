"""Pydantic schemas for root and per-target TOML configuration."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TargetConfig(BaseModel):
    """Schema for an individual target TOML file."""

    model_config = ConfigDict(extra="forbid")

    name: str
    sources: list[Path] = Field(default_factory=list)
    include_dirs: list[Path] = Field(default_factory=list)
    compile_defs: dict[str, str | bool | int] = Field(default_factory=dict)
    compile_opts: list[str] = Field(default_factory=list)
    link_libraries: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target name must be non-empty")
        return value

    @field_validator("sources", "include_dirs", mode="before")
    @classmethod
    def _coerce_paths(cls, value: object) -> object:
        if isinstance(value, list):
            return [Path(item) for item in value]
        return value


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
