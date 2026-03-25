"""The Semantic Layer: a compiled graph of measures, dimensions, and compatibility."""

from the_semantic_layer.errors import (
    AmbiguousNameError,
    CompilationError,
    IncompatibleDimensionError,
    InvalidFilterError,
    SemanticLayerError,
    UnresolvedNameError,
)
from the_semantic_layer.graph import GraphStore, InMemoryGraphStore, SemanticGraph
from the_semantic_layer.models import Dimension, Measure, QueryResult
from the_semantic_layer.types import (
    DimensionDefinition,
    FilterClause,
    MeasureDefinition,
    NeighborResult,
    NodeResult,
    PathResult,
    QueryPlan,
    SemanticBackend,
    ValidationResult,
    ViewDefinition,
    ViewSummary,
)

__all__ = [
    "AmbiguousNameError",
    "CompilationError",
    "Dimension",
    "DimensionDefinition",
    "FilterClause",
    "GraphStore",
    "InMemoryGraphStore",
    "IncompatibleDimensionError",
    "InvalidFilterError",
    "Measure",
    "MeasureDefinition",
    "NeighborResult",
    "NodeResult",
    "PathResult",
    "QueryPlan",
    "QueryResult",
    "SemanticBackend",
    "SemanticGraph",
    "SemanticLayerError",
    "UnresolvedNameError",
    "ValidationResult",
    "ViewDefinition",
    "ViewSummary",
    "compile",
]


def compile(
    host: str,
    http_path: str,
    catalog: str,
    schema: str,
    access_token: str | None = None,
) -> SemanticGraph:
    """Connect to a Databricks SQL warehouse and compile the Semantic Layer.

    Args:
        host: Databricks workspace hostname.
        http_path: SQL warehouse HTTP path.
        catalog: Unity Catalog name.
        schema: Schema containing metric views.
        access_token: Optional Databricks access token.

    Returns:
        A fully compiled SemanticGraph ready for queries.
    """
    from the_semantic_layer.compilation.compiler import compile_from_warehouse
    from the_semantic_layer.compilation.warehouse import WarehouseConnection

    warehouse = WarehouseConnection(
        host=host,
        http_path=http_path,
        catalog=catalog,
        schema=schema,
        access_token=access_token,
    )
    return compile_from_warehouse(warehouse)
