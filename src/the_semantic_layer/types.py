"""Typed intermediate representations for the Semantic Layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from the_semantic_layer.models import Dimension, Measure


# ---------------------------------------------------------------------------
# Discovery types (compiler output)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasureDefinition:
    """A measure as extracted from a metric view, before graph hydration."""

    name: str
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...]
    expression: str | None = None


@dataclass(frozen=True)
class DimensionDefinition:
    """A dimension as extracted from a metric view, before graph hydration."""

    name: str
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class ViewDefinition:
    """A compiled metric view with its measures and dimensions."""

    name: str  # short name (e.g. "sales")
    fqn: str  # fully qualified name (e.g. "catalog.schema.sales")
    description: str
    measures: list[MeasureDefinition]
    dimensions: list[DimensionDefinition]


# ---------------------------------------------------------------------------
# Query types (graph output, query builder input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterClause:
    """A resolved filter on a dimension. Single value = equality, multiple = IN."""

    dimension: str  # canonical dimension name (resolved by SemanticGraph)
    values: list[str]


@dataclass(frozen=True)
class QueryPlan:
    """Everything the query builder needs to generate SQL."""

    measures: list[Measure]
    dimensions: list[Dimension]
    filters: list[FilterClause]
    measure_to_view: dict[str, str]
    max_rows: int | None = None


# ---------------------------------------------------------------------------
# Backend protocol (documented contract for future extraction)
# ---------------------------------------------------------------------------


class SemanticBackend(Protocol):
    """Contract for a semantic layer backend.

    Not extracted yet — exists to document the interface boundary.
    """

    def discover(self) -> list[ViewDefinition]: ...

    def execute(self, plan: QueryPlan) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Traversal return types (WS4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeResult:
    """Result from get_node(). A fully described graph node with its neighbors."""

    kind: str  # "measure" or "dimension"
    canonical_name: str
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...]
    metric_view: str | None = None  # set for measures (owning view)
    metric_views: tuple[str, ...] = ()  # set for dimensions (all views)
    compatible_measures: tuple[str, ...] = ()  # for dimensions
    compatible_dimensions: tuple[str, ...] = ()  # for measures


@dataclass(frozen=True)
class NeighborResult:
    """A compact graph node reference returned from get_neighbors()."""

    canonical_name: str
    kind: str  # "measure" or "dimension"
    display_name: str


@dataclass(frozen=True)
class PathResult:
    """Result from find_path(). Describes the relationship between two nodes."""

    node_a: str
    node_b: str
    connected: bool
    relationship: str  # "joinable", "compatible", "co_occurring", "none"
    shared_dimensions: tuple[str, ...] = ()  # for measure-measure paths
    co_occurring_views: tuple[str, ...] = ()  # for dimension-dimension paths


@dataclass(frozen=True)
class ValidationResult:
    """Result from validate_combination(). Pre-flight check for a query."""

    valid: bool
    measures: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    compatible_dimensions: tuple[str, ...] = ()
    incompatible: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ViewSummary:
    """A view's measures and dimensions, for list_entry_points()."""

    view: str
    view_fqn: str
    measures: tuple[str, ...]  # canonical names
    dimensions: tuple[str, ...]  # canonical names
