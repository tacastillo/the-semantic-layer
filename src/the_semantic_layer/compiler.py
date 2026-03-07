"""Compile Unity Catalog metric views into a SemanticGraph."""

from __future__ import annotations

import logging
from typing import Any

from the_semantic_layer.errors import CompilationError
from the_semantic_layer.graph import SemanticGraph
from the_semantic_layer.models import Dimension, Measure
from the_semantic_layer.synonym_index import SynonymIndex
from the_semantic_layer.warehouse import WarehouseConnection
from the_semantic_layer.yaml_parser import parse_from_columns_only, parse_metric_view_yaml

logger = logging.getLogger(__name__)


def compile_from_warehouse(warehouse: WarehouseConnection) -> SemanticGraph:
    """Introspect all metric views and build a SemanticGraph.

    Args:
        warehouse: An active warehouse connection.

    Returns:
        A fully populated SemanticGraph.

    Raises:
        CompilationError: If introspection fails.
    """
    try:
        table_names = warehouse.list_tables()
    except Exception as exc:
        raise CompilationError(f"Failed to list tables: {exc}") from exc

    measures: dict[str, Measure] = {}
    dimensions: dict[str, Dimension] = {}
    view_measures: dict[str, list[str]] = {}
    view_dimensions: dict[str, list[str]] = {}
    measure_to_view: dict[str, str] = {}
    synonym_index = SynonymIndex()

    for table_fqn in table_names:
        try:
            metadata = warehouse.describe_view(table_fqn)
        except Exception:
            logger.warning("Failed to describe %s, skipping", table_fqn)
            continue

        if not _is_metric_view(metadata):
            continue

        logger.info("Compiling metric view: %s", table_fqn)
        _compile_view(
            table_fqn,
            metadata,
            measures,
            dimensions,
            view_measures,
            view_dimensions,
            measure_to_view,
            synonym_index,
        )

    return SemanticGraph(
        measures=measures,
        dimensions=dimensions,
        view_measures=view_measures,
        view_dimensions=view_dimensions,
        measure_to_view=measure_to_view,
        synonym_index=synonym_index,
        warehouse=warehouse,
    )


def _is_metric_view(metadata: dict[str, Any]) -> bool:
    """Check if a table's metadata indicates it is a YAML metric view."""
    # Check table properties or language field
    props = metadata.get("table_properties", metadata.get("properties", {}))
    if isinstance(props, dict):
        language = props.get("language", props.get("Language", ""))
        if language.upper() == "YAML":
            return True

    # Also check top-level language field
    language = metadata.get("language", "")
    if isinstance(language, str) and language.upper() == "YAML":
        return True

    return False


def _compile_view(
    view_fqn: str,
    metadata: dict[str, Any],
    measures: dict[str, Measure],
    dimensions: dict[str, Dimension],
    view_measures: dict[str, list[str]],
    view_dimensions: dict[str, list[str]],
    measure_to_view: dict[str, str],
    synonym_index: SynonymIndex,
) -> None:
    """Compile a single metric view into the graph structures."""
    columns = _extract_columns(metadata)
    view_short_name = view_fqn.rsplit(".", 1)[-1]

    # Parse YAML if available, otherwise fall back to column heuristics
    yaml_text = metadata.get("view_text", metadata.get("viewText"))
    if yaml_text and isinstance(yaml_text, str):
        parsed = parse_metric_view_yaml(yaml_text, columns)
    else:
        parsed = parse_from_columns_only(columns)

    view_measure_names: list[str] = []
    view_dimension_names: list[str] = []

    # Build measures
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
        measures[canonical] = measure
        measure_to_view[canonical] = view_fqn
        view_measure_names.append(canonical)

        # Register in synonym index
        aliases = [
            measure.display_name,
            measure.column_name,
            *measure.synonyms,
        ]
        synonym_index.register(canonical, aliases, "measure")

    # Build dimensions (merge if already exists from another view)
    for d_info in parsed["dimensions"]:
        canonical = d_info["name"].lower()

        if canonical in dimensions:
            # Merge: add this view to the dimension's metric_views
            existing = dimensions[canonical]
            merged_views = tuple(set(existing.metric_views) | {view_fqn})
            merged_synonyms = tuple(set(existing.synonyms) | set(d_info.get("synonyms", ())))
            dimensions[canonical] = Dimension(
                canonical_name=canonical,
                column_name=existing.column_name,
                display_name=existing.display_name,
                description=existing.description or d_info.get("description", ""),
                data_type=existing.data_type or d_info.get("data_type", ""),
                synonyms=merged_synonyms,
                metric_views=merged_views,
            )
        else:
            dimensions[canonical] = Dimension(
                canonical_name=canonical,
                column_name=d_info["name"],
                display_name=d_info.get("display_name", d_info["name"]),
                description=d_info.get("description", ""),
                data_type=d_info.get("data_type", ""),
                synonyms=tuple(d_info.get("synonyms", ())),
                metric_views=(view_fqn,),
            )
            # Register in synonym index (only on first encounter)
            dim = dimensions[canonical]
            aliases = [
                dim.display_name,
                dim.column_name,
                *dim.synonyms,
            ]
            synonym_index.register(canonical, aliases, "dimension")

        view_dimension_names.append(canonical)

    view_measures[view_fqn] = view_measure_names
    view_dimensions[view_fqn] = view_dimension_names


def _extract_columns(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract column metadata from the DESCRIBE TABLE EXTENDED result."""
    columns = metadata.get("columns", [])
    if columns:
        return columns

    # Try alternative structures
    schema = metadata.get("schema", metadata.get("table_schema", {}))
    if isinstance(schema, dict):
        return schema.get("columns", schema.get("fields", []))

    return []
