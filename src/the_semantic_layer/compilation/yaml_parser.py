"""Parse Unity Catalog metric view YAML definitions."""

from __future__ import annotations

import logging
from typing import Any, cast

import yaml

logger = logging.getLogger(__name__)

# Numeric types that indicate a column is likely a measure when YAML is unavailable
_NUMERIC_TYPES = frozenset({
    "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT",
    "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC",
})


def parse_metric_view_yaml(
    yaml_text: str,
    columns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Parse a metric view YAML definition and classify columns.

    Args:
        yaml_text: The raw YAML string from the view_text field.
        columns: Column metadata from DESCRIBE TABLE (name, type, comment).

    Returns:
        A dict with keys:
            "measures": list of measure info dicts
            "dimensions": list of dimension info dicts
            "source": the source table/view reference if present
    """
    try:
        definition = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        logger.warning("Failed to parse YAML definition, falling back to column metadata")
        return _fallback_from_columns(columns)

    if not isinstance(definition, dict):
        logger.warning("YAML definition is not a dict, falling back to column metadata")
        return _fallback_from_columns(columns)

    return _parse_definition(cast("dict[str, Any]", definition), columns)


def parse_from_columns_only(columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify columns as measures/dimensions using type heuristics only."""
    return _fallback_from_columns(columns)


def _parse_definition(
    definition: dict[str, Any],
    columns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract measure/dimension metadata from a parsed YAML definition."""
    col_lookup = {c["name"].lower(): c for c in columns}

    measures: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []

    # The YAML definition may use different structures depending on
    # the Unity Catalog metric view format. We handle common patterns.
    yaml_measures = definition.get("measures", [])
    yaml_dimensions = definition.get("dimensions", [])

    # If the YAML explicitly lists measures and dimensions
    if yaml_measures or yaml_dimensions:
        for measure_entry in yaml_measures:
            if isinstance(measure_entry, dict):
                measures.append(_extract_field_info(cast("dict[str, Any]", measure_entry), col_lookup, is_measure=True))
            elif isinstance(measure_entry, str):
                measures.append(_field_from_column(measure_entry, col_lookup, is_measure=True))

        for dim_entry in yaml_dimensions:
            if isinstance(dim_entry, dict):
                dimensions.append(_extract_field_info(cast("dict[str, Any]", dim_entry), col_lookup, is_measure=False))
            elif isinstance(dim_entry, str):
                dimensions.append(_field_from_column(dim_entry, col_lookup, is_measure=False))
    else:
        # Try column-level is_measure flags from the columns metadata
        for col in columns:
            is_measure = col.get("is_measure", False)
            if is_measure:
                measures.append(_field_from_column(col["name"], col_lookup, is_measure=True))
            else:
                dimensions.append(_field_from_column(col["name"], col_lookup, is_measure=False))

    return {
        "measures": measures,
        "dimensions": dimensions,
        "source": definition.get("source"),
    }


def _extract_field_info(
    field_def: dict[str, Any],
    col_lookup: dict[str, dict[str, Any]],
    is_measure: bool,
) -> dict[str, Any]:
    """Extract info from a YAML field definition dict."""
    name = field_def.get("name", "")
    col_meta = col_lookup.get(name.lower(), {})

    synonyms = field_def.get("synonyms", [])
    if isinstance(synonyms, str):
        synonyms = [synonyms]

    return {
        "name": name,
        "display_name": field_def.get("display_name", name),
        "description": field_def.get("comment", col_meta.get("comment", "")),
        "data_type": col_meta.get("type", field_def.get("type", "")),
        "synonyms": tuple(synonyms),
        "expression": field_def.get("expr") if is_measure else None,
        "is_measure": is_measure,
    }


def _field_from_column(
    column_name: str,
    col_lookup: dict[str, dict[str, Any]],
    is_measure: bool,
) -> dict[str, Any]:
    """Build field info from column metadata only."""
    col = col_lookup.get(column_name.lower(), {})
    return {
        "name": column_name,
        "display_name": column_name,
        "description": col.get("comment", ""),
        "data_type": col.get("type", ""),
        "synonyms": (),
        "expression": None,
        "is_measure": is_measure,
    }


def _fallback_from_columns(columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify columns using type-based heuristics when YAML is unavailable."""
    measures: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    col_lookup = {c["name"].lower(): c for c in columns}

    for col in columns:
        name = col["name"]
        base_type = col.get("type", "").upper().split("(")[0].strip()
        name_lower = name.lower()

        # Numeric columns without id/key/date suffixes are likely measures
        is_likely_measure = (
            base_type in _NUMERIC_TYPES
            and not name_lower.endswith(("_id", "_key", "_date", "_timestamp"))
            and not name_lower.startswith(("id_", "key_"))
        )

        if is_likely_measure:
            measures.append(_field_from_column(name, col_lookup, is_measure=True))
        else:
            dimensions.append(_field_from_column(name, col_lookup, is_measure=False))

    if not measures:
        logger.warning("No measures identified from column metadata heuristics")

    return {
        "measures": measures,
        "dimensions": dimensions,
        "source": None,
    }
