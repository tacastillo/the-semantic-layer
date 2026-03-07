"""SQL generation for single-view and multi-view queries."""

from __future__ import annotations

from the_semantic_layer.models import Dimension, Measure


def build_query(
    measures: list[Measure],
    dimensions: list[Dimension],
    filters: dict[str, str] | None,
    measure_to_view: dict[str, str],
) -> tuple[str, list]:
    """Build a SQL query for the requested measures and dimensions.

    Args:
        measures: Resolved Measure objects.
        dimensions: Resolved Dimension objects.
        filters: Dimension canonical_name -> filter value (equality only).
        measure_to_view: Mapping of measure canonical_name -> metric view FQN.

    Returns:
        A tuple of (sql_string, parameters) where parameters is a list of
        bind-parameter values corresponding to %s placeholders in the SQL.
    """
    filters = filters or {}

    # Group measures by their metric view
    views: dict[str, list[Measure]] = {}
    for m in measures:
        view = measure_to_view[m.canonical_name]
        views.setdefault(view, []).append(m)

    if len(views) == 1:
        return _build_single_view_query(measures, dimensions, filters, views)
    return _build_multi_view_query(measures, dimensions, filters, views)


def _build_single_view_query(
    measures: list[Measure],
    dimensions: list[Dimension],
    filters: dict[str, str],
    views: dict[str, list[Measure]],
) -> tuple[str, list]:
    """Build a simple SELECT for measures from a single metric view."""
    view_name = next(iter(views))
    params: list = []

    dim_cols = [f"{d.column_name}" for d in dimensions]
    measure_cols = [_measure_select(m) for m in measures]

    select_parts = dim_cols + measure_cols
    sep = ",\n    "
    sql = f"SELECT\n    {sep.join(select_parts)}"
    sql += f"\nFROM {view_name}"

    where_clause, where_params = _build_where(dimensions, filters)
    if where_clause:
        sql += f"\n{where_clause}"
        params.extend(where_params)

    if dim_cols:
        group_indices = ", ".join(str(i + 1) for i in range(len(dim_cols)))
        sql += f"\nGROUP BY {group_indices}"

    return sql, params


def _build_multi_view_query(
    measures: list[Measure],
    dimensions: list[Dimension],
    filters: dict[str, str],
    views: dict[str, list[Measure]],
) -> tuple[str, list]:
    """Build a CTE-based query joining measures from multiple metric views."""
    params: list = []
    cte_names: list[str] = []
    cte_definitions: list[str] = []

    dim_cols = [d.column_name for d in dimensions]

    for view_fqn, view_measures in views.items():
        # Create a safe CTE alias from the view name
        cte_alias = _cte_alias(view_fqn)
        cte_names.append(cte_alias)

        select_parts = list(dim_cols) + [_measure_select(m) for m in view_measures]
        cte_sep = ",\n        "
        cte_sql = f"SELECT\n        {cte_sep.join(select_parts)}"
        cte_sql += f"\n    FROM {view_fqn}"

        where_clause, where_params = _build_where(dimensions, filters, indent=4)
        if where_clause:
            cte_sql += f"\n    {where_clause}"
            params.extend(where_params)

        if dim_cols:
            group_indices = ", ".join(str(i + 1) for i in range(len(dim_cols)))
            cte_sql += f"\n    GROUP BY {group_indices}"

        cte_definitions.append(f"{cte_alias} AS (\n    {cte_sql}\n)")

    # Build final SELECT
    first_cte = cte_names[0]
    final_dims = [f"{first_cte}.{col}" for col in dim_cols]
    final_measures: list[str] = []
    for cte_alias, (_, view_measures) in zip(cte_names, views.items()):
        for m in view_measures:
            final_measures.append(f"{cte_alias}.{m.column_name}")

    final_select = final_dims + final_measures
    cte_join = ",\n"
    final_sep = ",\n    "
    sql = f"WITH {cte_join.join(cte_definitions)}"
    sql += f"\nSELECT\n    {final_sep.join(final_select)}"
    sql += f"\nFROM {first_cte}"

    # INNER JOIN remaining CTEs on shared dimensions
    for cte_alias in cte_names[1:]:
        join_on = " AND ".join(
            f"{first_cte}.{col} = {cte_alias}.{col}" for col in dim_cols
        )
        sql += f"\nINNER JOIN {cte_alias}\n    ON {join_on}"

    return sql, params


def _measure_select(m: Measure) -> str:
    """Build the SELECT expression for a measure."""
    if m.expression:
        return f"{m.expression} AS {m.column_name}"
    return m.column_name


def _build_where(
    dimensions: list[Dimension],
    filters: dict[str, str],
    indent: int = 0,
) -> tuple[str, list]:
    """Build a WHERE clause from equality filters."""
    if not filters:
        return "", []

    dim_by_canonical = {d.canonical_name: d for d in dimensions}
    clauses: list[str] = []
    params: list = []

    for dim_canonical, value in sorted(filters.items()):
        dim = dim_by_canonical.get(dim_canonical)
        if dim is None:
            continue
        clauses.append(f"{dim.column_name} = %s")
        params.append(value)

    if not clauses:
        return "", []

    prefix = " " * indent
    return f"{prefix}WHERE {' AND '.join(clauses)}", params


def _cte_alias(view_fqn: str) -> str:
    """Derive a CTE alias from a fully qualified view name."""
    # "catalog.schema.view_name" -> "cte_view_name"
    short_name = view_fqn.rsplit(".", 1)[-1]
    return f"cte_{short_name}"
