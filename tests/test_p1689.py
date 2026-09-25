"""Tests for the P1689R5 module dependency interchange format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rosetta_build.compiler import BmiInput
from rosetta_build.p1689 import (
    LookupMethod,
    P1689Document,
    P1689Error,
    P1689Rule,
    ProvidedModule,
    RequiredModule,
    bmi_inputs_from_rule,
    dump_p1689,
    merge_documents,
    module_identity_key,
    parse_p1689,
    parse_p1689_file,
    provider_index,
    resolve_compile_edges,
)

# Example from P1689R5 §8 (named modules).
PAPER_NAMED_MODULES = """
{
  "version": 1,
  "revision": 0,
  "rules": [
    {
      "primary-output": "duplicate.mpp.o",
      "provides": [
        {
          "logical-name": "duplicate"
        }
      ]
    },
    {
      "primary-output": "another.mpp.o",
      "provides": [
        {
          "logical-name": "another"
        }
      ],
      "requires": [
        {
          "logical-name": "duplicate"
        }
      ]
    },
    {
      "primary-output": "use.mpp.o",
      "requires": [
        {
          "logical-name": "duplicate"
        },
        {
          "logical-name": "another"
        }
      ]
    }
  ]
}
"""

# Example from P1689R5 §8 (header unit correlation via source-path).
PAPER_HEADER_UNIT = """
{
  "version": 1,
  "revision": 0,
  "rules": [
    {
      "primary-output": "use-header.mpp.o",
      "requires": [
        {
          "logical-name": "<header.hpp>",
          "source-path": "/path/to/found/header.hpp",
          "unique-on-source-path": true,
          "lookup-method": "include-angle"
        }
      ]
    },
    {
      "primary-output": "header.hpp.bmi",
      "provides": [
        {
          "logical-name": "header.hpp",
          "source-path": "/path/to/found/header.hpp",
          "unique-on-source-path": true
        }
      ]
    }
  ]
}
"""


def test_parse_paper_named_modules_example() -> None:
    document = parse_p1689(PAPER_NAMED_MODULES)
    assert document.version == 1
    assert document.revision == 0
    assert len(document.rules) == 3
    assert document.rules[0].primary_output == Path("duplicate.mpp.o")
    assert document.rules[0].provides[0].logical_name == "duplicate"
    assert document.rules[0].provides[0].is_interface is True
    assert document.rules[1].requires[0].lookup_method is LookupMethod.BY_NAME


def test_resolve_compile_edges_from_paper_example() -> None:
    document = parse_p1689(PAPER_NAMED_MODULES)
    edges = resolve_compile_edges(document)
    assert edges[Path("duplicate.mpp.o")] == frozenset()
    assert edges[Path("another.mpp.o")] == frozenset({Path("duplicate.mpp.o")})
    assert edges[Path("use.mpp.o")] == frozenset({
        Path("duplicate.mpp.o"),
        Path("another.mpp.o"),
    })


def test_header_unit_correlated_by_source_path() -> None:
    document = parse_p1689(PAPER_HEADER_UNIT)
    required = document.rules[0].requires[0]
    provided = document.rules[1].provides[0]
    assert module_identity_key(required) == module_identity_key(provided)
    assert required.lookup_method is LookupMethod.INCLUDE_ANGLE

    edges = resolve_compile_edges(document)
    assert edges[Path("use-header.mpp.o")] == frozenset({Path("header.hpp.bmi")})


def test_roundtrip_dump_and_parse() -> None:
    original = parse_p1689(PAPER_NAMED_MODULES)
    text = dump_p1689(original)
    assert '"logical-name"' in text
    assert '"primary-output"' in text
    restored = parse_p1689(text)
    assert restored == original


def test_parse_file(tmp_path: Path) -> None:
    path = tmp_path / "deps.json"
    path.write_text(PAPER_NAMED_MODULES, encoding="utf-8")
    document = parse_p1689_file(path)
    assert len(document.rules) == 3


def test_bmi_inputs_from_compiled_module_paths() -> None:
    rule = P1689Rule(
        primary_output=Path("app.o"),
        requires=(
            RequiredModule(
                logical_name="math",
                compiled_module_path=Path("bmi/math.pcm"),
            ),
            RequiredModule(logical_name="sys"),
        ),
    )
    assert bmi_inputs_from_rule(rule) == (
        BmiInput(module="math", path=Path("bmi/math.pcm")),
    )


def test_provider_index_and_merge() -> None:
    first = parse_p1689({
        "version": 1,
        "rules": [
            {
                "primary-output": "a.o",
                "provides": [{"logical-name": "a"}],
            }
        ],
    })
    second = parse_p1689({
        "version": 1,
        "rules": [
            {
                "primary-output": "b.o",
                "provides": [{"logical-name": "b"}],
                "requires": [{"logical-name": "a"}],
            }
        ],
    })
    merged = merge_documents([first, second])
    index = provider_index(merged)
    assert index["name:a"].primary_output == Path("a.o")
    assert resolve_compile_edges(merged)[Path("b.o")] == frozenset({Path("a.o")})


def test_rejects_unsupported_version() -> None:
    with pytest.raises(P1689Error, match="unsupported P1689 version"):
        parse_p1689({"version": 2, "rules": [{"primary-output": "a.o"}]})


def test_rejects_empty_rules() -> None:
    with pytest.raises(P1689Error, match="invalid P1689 document"):
        parse_p1689({"version": 1, "rules": []})


def test_rejects_duplicate_outputs() -> None:
    with pytest.raises(P1689Error, match="duplicate output path"):
        parse_p1689({
            "version": 1,
            "rules": [
                {"primary-output": "a.o"},
                {"primary-output": "a.o"},
            ],
        })


def test_rejects_duplicate_providers() -> None:
    with pytest.raises(P1689Error, match="duplicate module provider"):
        parse_p1689({
            "version": 1,
            "rules": [
                {
                    "primary-output": "a.o",
                    "provides": [{"logical-name": "m"}],
                },
                {
                    "primary-output": "b.o",
                    "provides": [{"logical-name": "m"}],
                },
            ],
        })


def test_ignores_vendor_extensions() -> None:
    document = parse_p1689({
        "version": 1,
        "rules": [
            {
                "primary-output": "a.o",
                "_VENDOR_extension": True,
                "provides": [
                    {
                        "logical-name": "a",
                        "_VENDOR_note": "ignored",
                    }
                ],
            }
        ],
    })
    assert document.rules[0].provides[0].logical_name == "a"


def test_unique_on_source_path_requires_source_path() -> None:
    with pytest.raises(P1689Error, match="no source-path"):
        module_identity_key(
            RequiredModule(
                logical_name="<h>",
                unique_on_source_path=True,
            )
        )


def test_construct_document_programmatically() -> None:
    document = P1689Document(
        version=1,
        rules=(
            P1689Rule(
                primary_output=Path("math.o"),
                provides=(
                    ProvidedModule(
                        logical_name="math",
                        compiled_module_path=Path("math.pcm"),
                        is_interface=True,
                    ),
                ),
            ),
        ),
    )
    payload = json.loads(dump_p1689(document))
    assert payload["rules"][0]["provides"][0]["compiled-module-path"] == "math.pcm"
