"""Tests for FetchContent-style project dependencies."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from rosetta_build.collect import collect
from rosetta_build.compiler import Project
from rosetta_build.dependency import (
    DependencyError,
    GitDependencyProvider,
    populate_dependencies,
    populate_dependency,
    provider_for,
    sha256_checkout,
)
from rosetta_build.schema import (
    GitDependencyConfig,
    RosettaBuildConfig,
    parse_dependency_config,
)


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _ephemeral_git_repo(root: Path, *, tag: str, content: str = "hello\n") -> Path:
    """Create a throwaway git repo with one commit and ``tag``, then return it."""
    repo = root / "upstream"
    repo.mkdir(parents=True)
    (repo / "README").write_text(content, encoding="utf-8")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "add", "README")
    _run_git(repo, "commit", "-m", "initial")
    _run_git(repo, "tag", tag)
    return repo


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def test_parse_git_dependency_config() -> None:
    spec = parse_dependency_config({
        "provider": "git",
        "uri": "https://example.com/repo.git",
        "tag": "v1.2.3",
        "hash": "sha256:" + ("ab" * 32),
    })
    assert isinstance(spec, GitDependencyConfig)
    assert spec.uri == "https://example.com/repo.git"
    assert spec.tag == "v1.2.3"
    assert spec.hash == "sha256:" + ("ab" * 32)


def test_git_dependency_hash_optional() -> None:
    spec = GitDependencyConfig(
        provider="git",
        uri="https://example.com/repo.git",
        tag="v1",
    )
    assert spec.hash is None


def test_git_dependency_hash_normalizes_case() -> None:
    digest = "AB" * 32
    spec = GitDependencyConfig(
        provider="git",
        uri="https://example.com/repo.git",
        tag="v1",
        hash=f"SHA256:{digest}",
    )
    assert spec.hash == f"sha256:{digest.lower()}"


@pytest.mark.parametrize(
    ("hash_value", "match"),
    [
        ("sha1:" + ("ab" * 20), "sha256:<hex>"),
        ("blake2b:" + ("ab" * 32), "sha256:<hex>"),
        ("ab" * 32, "sha256:<hex>"),
        ("sha256:" + ("ab" * 31), "64 hexadecimal"),
        ("sha256:" + ("ab" * 33), "64 hexadecimal"),
        ("sha256:" + ("gg" * 32), "64 hexadecimal"),
        ("sha256:", "64 hexadecimal"),
        ("  ", "sha256:<hex>"),
    ],
)
def test_git_dependency_rejects_invalid_hash(hash_value: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        GitDependencyConfig(
            provider="git",
            uri="https://example.com/repo.git",
            tag="v1",
            hash=hash_value,
        )


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/repo.git",
        "ssh://git@example.com/repo.git",
        "file:///tmp/repo.git",
    ],
)
def test_git_dependency_accepts_supported_uri_schemes(uri: str) -> None:
    spec = GitDependencyConfig(provider="git", uri=uri, tag="v1")
    assert spec.uri == uri


@pytest.mark.parametrize(
    "uri",
    [
        "git@example.com:repo.git",
        "ftp://example.com/repo.git",
        "/absolute/path",
        "example.com/repo.git",
    ],
)
def test_git_dependency_rejects_unsupported_uri_schemes(uri: str) -> None:
    with pytest.raises(ValidationError, match="https://, ssh://, or file://"):
        GitDependencyConfig(provider="git", uri=uri, tag="v1")


def test_git_dependency_rejects_empty_tag() -> None:
    with pytest.raises(ValidationError, match="tag must be non-empty"):
        GitDependencyConfig(
            provider="git",
            uri="https://example.com/repo.git",
            tag="  ",
        )


def test_rosetta_build_config_dependencies() -> None:
    config = RosettaBuildConfig.model_validate({
        "targets": ["libs/core/target.toml"],
        "dependencies": {
            "fmt": {
                "provider": "git",
                "uri": "https://example.com/fmt.git",
                "tag": "11.0.0",
            }
        },
    })
    assert set(config.dependencies) == {"fmt"}
    assert config.dependencies["fmt"].provider == "git"
    assert config.dependencies["fmt"].tag == "11.0.0"


def test_provider_for_git() -> None:
    digest = "cd" * 32
    spec = GitDependencyConfig(
        provider="git",
        uri="file:///tmp/repo",
        tag="v1",
        hash=f"sha256:{digest}",
    )
    provider = provider_for(spec)
    assert isinstance(provider, GitDependencyProvider)
    assert provider.uri == spec.uri
    assert provider.tag == spec.tag
    assert provider.hash == spec.hash


def test_populate_git_dependency_from_file_uri(tmp_path: Path) -> None:
    tag = "v1.0.0"
    upstream = _ephemeral_git_repo(tmp_path / "src", tag=tag, content="dep-content\n")
    uri = _file_uri(upstream)
    dest = tmp_path / "deps" / "mylib"

    populated = populate_dependency(
        "mylib",
        GitDependencyConfig(provider="git", uri=uri, tag=tag),
        tmp_path / "deps",
    )

    assert populated == dest.resolve()
    assert (dest / "README").read_text(encoding="utf-8") == "dep-content\n"
    assert dest.is_dir()

    shutil.rmtree(upstream)
    assert not upstream.exists()
    assert (dest / "README").is_file()


def test_populate_git_dependency_accepts_matching_sha256(tmp_path: Path) -> None:
    tag = "v1.0.0"
    upstream = _ephemeral_git_repo(tmp_path / "src", tag=tag, content="pinned\n")
    uri = _file_uri(upstream)
    probe = tmp_path / "probe"
    GitDependencyProvider(uri=uri, tag=tag).populate(probe)
    expected = f"sha256:{sha256_checkout(probe)}"
    shutil.rmtree(probe)

    dest = tmp_path / "deps" / "mylib"
    populated = populate_dependency(
        "mylib",
        GitDependencyConfig(provider="git", uri=uri, tag=tag, hash=expected),
        tmp_path / "deps",
    )
    assert populated == dest.resolve()
    assert (dest / "README").read_text(encoding="utf-8") == "pinned\n"
    assert f"sha256:{sha256_checkout(dest)}" == expected

    shutil.rmtree(upstream)


def test_populate_git_dependency_rejects_mismatched_sha256(tmp_path: Path) -> None:
    tag = "v1.0.0"
    upstream = _ephemeral_git_repo(tmp_path / "src", tag=tag, content="pinned\n")
    uri = _file_uri(upstream)
    dest = tmp_path / "deps" / "mylib"
    wrong = "sha256:" + ("00" * 32)

    with pytest.raises(DependencyError, match="hash mismatch"):
        populate_dependency(
            "mylib",
            GitDependencyConfig(provider="git", uri=uri, tag=tag, hash=wrong),
            tmp_path / "deps",
        )
    assert not dest.exists()

    shutil.rmtree(upstream)


def test_sha256_checkout_ignores_git_metadata(tmp_path: Path) -> None:
    tag = "v1.0.0"
    upstream = _ephemeral_git_repo(tmp_path / "src", tag=tag, content="same\n")
    uri = _file_uri(upstream)
    first = GitDependencyProvider(uri=uri, tag=tag).populate(tmp_path / "a")
    second = GitDependencyProvider(uri=uri, tag=tag).populate(tmp_path / "b")
    assert sha256_checkout(first) == sha256_checkout(second)
    shutil.rmtree(upstream)


def test_sha256_checkout_changes_when_content_changes(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "README").write_text("a\n", encoding="utf-8")
    (right / "README").write_text("b\n", encoding="utf-8")
    assert sha256_checkout(left) != sha256_checkout(right)


def test_populate_dependencies_and_project(tmp_path: Path) -> None:
    tag = "release-1"
    upstream = _ephemeral_git_repo(tmp_path / "src", tag=tag)
    uri = _file_uri(upstream)
    specs = {
        "mylib": GitDependencyConfig(provider="git", uri=uri, tag=tag),
    }
    deps_root = tmp_path / "_deps"

    populated = populate_dependencies(specs, deps_root)
    assert set(populated) == {"mylib"}
    assert (populated["mylib"] / "README").is_file()

    project = Project(name="demo", dependencies=populated)
    assert project.name == "demo"
    assert project.dependencies["mylib"] == populated["mylib"]

    shutil.rmtree(upstream)
    assert not upstream.exists()


def test_populate_git_missing_tag_raises(tmp_path: Path) -> None:
    upstream = _ephemeral_git_repo(tmp_path / "src", tag="v1.0.0")
    uri = _file_uri(upstream)
    try:
        with pytest.raises(DependencyError, match="failed to clone"):
            GitDependencyProvider(uri=uri, tag="missing-tag").populate(
                tmp_path / "deps" / "mylib"
            )
    finally:
        shutil.rmtree(upstream)


def test_collect_loads_declared_dependencies(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "hello.cpp").write_text(
        "int main() { return 0; }\n", encoding="utf-8"
    )
    (root / "lib" / "target.toml").write_text(
        'type = "static_library"\n'
        'name = "hello"\n'
        'language = "cxx"\n'
        'sources = ["hello.cpp"]\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "with-deps"\n'
        'version = "0.0.0"\n'
        "\n"
        "[tool.rosetta-build]\n"
        'targets = ["lib/target.toml"]\n'
        "\n"
        "[tool.rosetta-build.dependencies.vendor]\n"
        'provider = "git"\n'
        'uri = "https://example.com/vendor.git"\n'
        'tag = "v2.0.0"\n'
        f'hash = "sha256:{"ab" * 32}"\n',
        encoding="utf-8",
    )

    collection = collect(root)
    assert set(collection.dependencies) == {"vendor"}
    dep = collection.dependencies["vendor"]
    assert isinstance(dep, GitDependencyConfig)
    assert dep.uri == "https://example.com/vendor.git"
    assert dep.tag == "v2.0.0"
    assert dep.hash == f"sha256:{'ab' * 32}"
