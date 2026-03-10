"""Compile Unity Catalog metric views into a SemanticGraph."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from the_semantic_layer.compilation.yaml_parser import (
    parse_from_columns_only,
    parse_metric_view_yaml,
)
from the_semantic_layer.errors import CompilationError
from the_semantic_layer.graph import SemanticGraph
from the_semantic_layer.graph.store import GraphStore, InMemoryGraphStore
from the_semantic_layer.models import Dimension, Measure

if TYPE_CHECKING:
    from the_semantic_layer.compilation.warehouse import WarehouseConnection

logger = logging.getLogger(__name__)


def compile_from_warehouse(
    warehouse: WarehouseConnection,
    store: GraphStore | None = None,
) -> SemanticGraph:
    """Introspect all metric views and build a SemanticGraph.

    Args:
        warehouse: An active warehouse connection.
        store: Graph storage backend. Defaults to InMemoryGraphStore.

    Returns:
        A fully populated SemanticGraph.

    Raises:
        CompilationError: If introspection fails.
    """
    if store is None:
        store = InMemoryGraphStore()

    try:
        table_names = warehouse.list_tables()
    except Exception as exc:
        raise CompilationError(f"Failed to list tables: {exc}") from exc

    for table_fqn in table_names:
        try:
            metadata = warehouse.describe_view(table_fqn)
        except Exception:
            logger.warning("Failed to describe %s, skipping", table_fqn)
            continue

        if not _is_metric_view(metadata):
            continue

        logger.info("Compiling metric view: %s", table_fqn)
        _compile_view(table_fqn, metadata, store)

    return SemanticGraph(store=store, warehouse=warehouse)


def _is_metric_view(metadata: dict[str, Any]) -> bool:
    """Check if table metadata indicates a YAML metric view."""
    language = metadata.get("language", "")
    return isinstance(language, str) and language.upper() == "YAML"


def _compile_view(view_fqn: str, metadata: dict[str, Any], store: GraphStore) -> None:
    """Parse a single metric view and write it into the store."""
    columns = _extract_columns(metadata)
    view_short_name = view_fqn.rsplit(".", 1)[-1]

    yaml_text = metadata.get("view_text")
    if yaml_text and isinstance(yaml_text, str):
        parsed = parse_metric_view_yaml(yaml_text, columns)
    else:
        parsed = parse_from_columns_only(columns)

    for m_info in parsed["measures"]:
        canonical = f"{view_short_name}.{m_info['name']}".lower()
        measure = Measure(
            canonical_name=canonical,
            column_name=m_info["name"],
            metric_view=view_fqn,
            display_name=m_info.get("display_name", m_info["name"]),
            description=m_info.get("description", ""),
            data_type=m_info.get("data_type", ""),
            synonyms=tuple(m_info.get("synonyms", ())),
            expression=m_info.get("expression"),
        )
        store.add_measure(measure, view_fqn)
        store.register_synonym(
            canonical,
            [measure.display_name, measure.column_name, *measure.synonyms],
            "measure",
        )

    for d_info in parsed["dimensions"]:
        canonical = d_info["name"].lower()
        dimension = Dimension(
            canonical_name=canonical,
            column_name=d_info["name"],
            display_name=d_info.get("display_name", d_info["name"]),
            description=d_info.get("description", ""),
            data_type=d_info.get("data_type", ""),
            synonyms=tuple(d_info.get("synonyms", ())),
            metric_views=(view_fqn,),
        )
        store.add_or_merge_dimension(dimension, view_fqn)


def _extract_columns(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract column metadata from the DESCRIBE TABLE EXTENDED result."""
    columns = metadata.get("columns", [])
    if columns:
        return columns
    schema = metadata.get("schema", metadata.get("table_schema", {}))
    if isinstance(schema, dict):
        return schema.get("columns", schema.get("fields", []))
    return []
