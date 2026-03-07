"""The Semantic Layer: a compiled graph of measures, dimensions, and compatibility."""

from the_semantic_layer.errors import (
    AmbiguousNameError,
    CompilationError,
    IncompatibleDimensionError,
    InvalidFilterError,
    SemanticLayerError,
    UnresolvedNameError,
)
from the_semantic_layer.graph import SemanticGraph
from the_semantic_layer.models import Dimension, Measure, QueryResult

__all__ = [
    "compile",
    "AmbiguousNameError",
    "CompilationError",
    "Dimension",
    "IncompatibleDimensionError",
    "InvalidFilterError",
    "Measure",
    "QueryResult",
    "SemanticGraph",
    "SemanticLayerError",
    "UnresolvedNameError",
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
    from the_semantic_layer.compiler import compile_from_warehouse
    from the_semantic_layer.warehouse import WarehouseConnection

    warehouse = WarehouseConnection(
        host=host,
        http_path=http_path,
        catalog=catalog,
        schema=schema,
        access_token=access_token,
    )
    return compile_from_warehouse(warehouse)
