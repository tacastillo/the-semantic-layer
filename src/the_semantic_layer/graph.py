"""SemanticGraph: the consumer-facing API over the compiled measure/dimension graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from the_semantic_layer import query_builder
from the_semantic_layer.errors import (
    IncompatibleDimensionError,
    InvalidFilterError,
    UnresolvedNameError,
)
from the_semantic_layer.models import Dimension, Measure, QueryResult
from the_semantic_layer.synonym_index import SynonymIndex

if TYPE_CHECKING:
    from the_semantic_layer.warehouse import WarehouseConnection


class SemanticGraph:
    """In-memory graph of measures, dimensions, and their compatibility.

    Constructed by the compiler; consumed by application code, agents, notebooks.
    """

    def __init__(
        self,
        measures: dict[str, Measure],
        dimensions: dict[str, Dimension],
        view_measures: dict[str, list[str]],
        view_dimensions: dict[str, list[str]],
        measure_to_view: dict[str, str],
        synonym_index: SynonymIndex,
        warehouse: WarehouseConnection | None = None,
    ) -> None:
        self._measures = measures
        self._dimensions = dimensions
        self._view_measures = view_measures
        self._view_dimensions = view_dimensions
        self._measure_to_view = measure_to_view
        self._synonym_index = synonym_index
        self._warehouse = warehouse

    def list_measures(self) -> list[dict]:
        """Return every measure the Semantic Layer knows about."""
        return [
            {
                "canonical_name": m.canonical_name,
                "display_name": m.display_name,
                "description": m.description,
                "synonyms": list(m.synonyms),
                "metric_view": m.metric_view,
                "data_type": m.data_type,
            }
            for m in self._measures.values()
        ]

    def get_dimensions_for_measures(
        self, measure_names: list[str]
    ) -> list[dict]:
        """Return dimensions compatible with all requested measures.

        Args:
            measure_names: One or more measure names (canonical, display, or synonym).

        Returns:
            List of dimension dicts for the intersection of compatible dimensions.

        Raises:
            UnresolvedNameError: If any measure name cannot be resolved.
        """
        resolved = [
            self._synonym_index.resolve(name, "measure")
            for name in measure_names
        ]

        # Find the metric views involved
        involved_views = {self._measure_to_view[cn] for cn in resolved}

        # Intersect dimension sets across all involved views
        dim_sets = [
            set(self._view_dimensions[view]) for view in involved_views
        ]
        compatible = set.intersection(*dim_sets) if dim_sets else set()

        return [
            {
                "canonical_name": d.canonical_name,
                "display_name": d.display_name,
                "description": d.description,
                "synonyms": list(d.synonyms),
                "data_type": d.data_type,
            }
            for cn in sorted(compatible)
            if (d := self._dimensions[cn])
        ]

    def query(
        self,
        measure_names: list[str],
        dimension_names: list[str],
        filters: dict[str, str] | None = None,
    ) -> QueryResult:
        """Query the Semantic Layer for data.

        Args:
            measure_names: Measure names to include (resolved via synonyms).
            dimension_names: Dimension names to group/slice by (resolved via synonyms).
            filters: Optional dimension_name -> value equality filters.

        Returns:
            QueryResult with rows, row_count, and generated SQL.

        Raises:
            UnresolvedNameError: If any name cannot be resolved.
            IncompatibleDimensionError: If a dimension is not compatible with the measures.
            InvalidFilterError: If a filter references a non-requested dimension.
            RuntimeError: If no warehouse connection is available.
        """
        if self._warehouse is None:
            raise RuntimeError(
                "No warehouse connection available. "
                "Construct the SemanticGraph with a warehouse to use query()."
            )

        # Resolve measures
        resolved_measures = [
            self._synonym_index.resolve(name, "measure")
            for name in measure_names
        ]
        measures = [self._measures[cn] for cn in resolved_measures]

        # Resolve dimensions and validate compatibility
        resolved_dims = [
            self._synonym_index.resolve(name, "dimension")
            for name in dimension_names
        ]

        involved_views = {self._measure_to_view[cn] for cn in resolved_measures}
        dim_sets = [set(self._view_dimensions[v]) for v in involved_views]
        compatible = set.intersection(*dim_sets) if dim_sets else set()

        for dim_cn in resolved_dims:
            if dim_cn not in compatible:
                raise IncompatibleDimensionError(dim_cn, resolved_measures)

        dimensions = [self._dimensions[cn] for cn in resolved_dims]

        # Resolve and validate filters
        resolved_filters: dict[str, str] = {}
        if filters:
            for filter_name, value in filters.items():
                filter_cn = self._synonym_index.resolve(filter_name, "dimension")
                if filter_cn not in resolved_dims:
                    raise InvalidFilterError(filter_cn)
                resolved_filters[filter_cn] = value

        # Build and execute
        sql, params = query_builder.build_query(
            measures, dimensions, resolved_filters, self._measure_to_view
        )

        rows = self._warehouse.execute_query(sql, params)

        return QueryResult(rows=rows, row_count=len(rows), sql=sql)
