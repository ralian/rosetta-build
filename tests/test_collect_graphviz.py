from __future__ import annotations

from pathlib import Path

import pytest

from rosetta_build.collect import CollectionError, collect
from rosetta_build.collect_graphviz import collection_to_dot

TREES = Path(__file__).parent / "trees"

# Valid trees ship a golden graph.dot for Graphviz output comparison.
VALID_TREES = ("example", "static_link_cycle", "all_edge_types")


@pytest.mark.parametrize("tree_name", VALID_TREES)
def test_graphviz_matches_golden_dot(tree_name: str) -> None:
    root = TREES / tree_name
    expected = (root / "graph.dot").read_text(encoding="utf-8")
    actual = collection_to_dot(collect(root))
    assert actual == expected


def test_all_edge_types_uses_distinct_styles() -> None:
    dot = collection_to_dot(collect(TREES / "all_edge_types"))

    assert 'color="#6b7280"' in dot  # source
    assert 'color="#2563eb"' in dot  # usage
    assert 'color="#16a34a"' in dot  # static link
    assert 'color="#dc2626"' in dot  # dynamic link

    assert '"target:app" -> "source:apps/app/main.cpp"' in dot
    assert '"target:static_a" -> "target:static_b"' in dot
    assert "style=dashed" in dot
    assert '"target:dyn" -> "target:static_a"' in dot
    assert "style=dotted" in dot
    assert '"target:app" -> "target:dyn"' in dot
    assert "style=bold" in dot


def test_graphviz_not_generated_for_invalid_trees() -> None:
    for tree_name in (
        "dynamic_link_cycle",
        "invalid_wheel",
        "unknown_link",
        "missing_pyproject",
    ):
        assert not (TREES / tree_name / "graph.dot").exists()
        with pytest.raises(CollectionError):
            collect(TREES / tree_name)
