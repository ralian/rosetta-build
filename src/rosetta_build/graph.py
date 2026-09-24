"""Source, usage, link, and module dependency graphs built during collection."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SourceGraph(BaseModel):
    """Directed edges from each target to the source files it compiles."""

    model_config = ConfigDict(frozen=True)

    edges: dict[str, frozenset[Path]] = Field(default_factory=dict)

    def sources_for(self, target: str) -> frozenset[Path]:
        return self.edges.get(target, frozenset())


class TargetDepGraph(BaseModel):
    """Directed target-to-target dependency graph."""

    model_config = ConfigDict(frozen=True)

    nodes: frozenset[str] = Field(default_factory=frozenset)
    edges: dict[str, frozenset[str]] = Field(default_factory=dict)

    def dependencies_of(self, target: str) -> frozenset[str]:
        return self.edges.get(target, frozenset())

    def topological_order(self, *, kind: str = "dependency") -> list[str]:
        """Return targets with dependencies before dependents.

        Raises:
            ValueError: if the graph contains a cycle.
        """
        dependents: dict[str, set[str]] = {node: set() for node in self.nodes}
        in_degree: dict[str, int] = {node: 0 for node in self.nodes}
        for node, deps in self.edges.items():
            for dep in deps:
                dependents.setdefault(dep, set()).add(node)
                in_degree[node] = in_degree.get(node, 0) + 1
                in_degree.setdefault(dep, 0)

        queue = sorted(node for node, degree in in_degree.items() if degree == 0)
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for dependent in sorted(dependents.get(node, ())):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(in_degree):
            remaining = sorted(node for node, degree in in_degree.items() if degree > 0)
            raise ValueError(
                f"{kind} dependency cycle involving: {', '.join(remaining)}"
            )
        return order


class UsageGraph(TargetDepGraph):
    """Usage/interface dependencies between targets; cycles are allowed."""


class LinkGraph(TargetDepGraph):
    """Hard dynamic-link dependencies; must form a DAG."""


class ModuleGraph(TargetDepGraph):
    """C++ module BMI import dependencies; must form a DAG."""
