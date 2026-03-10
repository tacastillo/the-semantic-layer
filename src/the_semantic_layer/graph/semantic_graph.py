"""SemanticGraph: the consumer-facing API over the compiled measure/dimension graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from the_semantic_layer.errors import (
    IncompatibleDimensionError,
    InvalidFilterError,
)
from the_semantic_layer.graph import query_builder
from the_semantic_layer.models import QueryResult

if TYPE_CHECKING:
    from the_semantic_layer.compilation.warehouse import WarehouseConnection
    from the_semantic_layer.graph.store import GraphStore


class SemanticGraph:
    """In-memory graph of measures, dimensions, and their compatibility.

    Constructed by the compiler; consumed by application code, agents, notebooks.
    The backing store is injectable — swap GraphStore implementations to change
    how the graph is persisted or queried.
    """

    def __init__(
        self,
        store: GraphStore,
        warehouse: WarehouseConnection | None = None,
    ) -> None:
        self._store = store
        self._warehouse = warehouse

    def list_measures(self) -> list[dict]:
        """Return every measure the Semantic Layer knows about."""
        return [
            {
                "canonical_name": measure.canonical_name,
                "display_name": measure.display_name,
                "description": measure.description,
                "synonyms": list(measure.synonyms),
                "metric_view": measure.metric_view,
                "data_type": measure.data_type,
            }
            for measure in self._store.all_measures()
        ]

    def get_dimensions_for_measures(self, measure_names: list[str]) -> list[dict]:
        """Return dimensions compatible with all requested measures.

        Args:
            measure_names: One or more measure names (canonical, display, or synonym).

        Returns:
            List of dimension dicts for the intersection of compatible dimensions.

        Raises:
            UnresolvedNameError: If any measure name cannot be resolved.
        """
        resolved = [self._store.resolve_name(name, "measure") for name in measure_names]
        compatible = self._store.get_compatible_dimensions(resolved)

        return [
            {
                "canonical_name": dim.canonical_name,
                "display_name": dim.display_name,
                "description": dim.description,
                "synonyms": list(dim.synonyms),
                "data_type": dim.data_type,
            }
            for cn in sorted(compatible)
            if (dim := self._store.get_dimension(cn))
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

        resolved_measures = [
            self._store.resolve_name(name, "measure") for name in measure_names
        ]
        measures = [self._store.get_measure(cn) for cn in resolved_measures]

        resolved_dims = [
            self._store.resolve_name(name, "dimension") for name in dimension_names
        ]
        compatible = self._store.get_compatible_dimensions(resolved_measures)

        for dim_cn in resolved_dims:
            if dim_cn not in compatible:
                raise IncompatibleDimensionError(dim_cn, resolved_measures)

        dimensions = [self._store.get_dimension(cn) for cn in resolved_dims]

        resolved_filters: dict[str, str] = {}
        if filters:
            for filter_name, value in filters.items():
                filter_cn = self._store.resolve_name(filter_name, "dimension")
                if filter_cn not in resolved_dims:
                    raise InvalidFilterError(filter_cn)
                resolved_filters[filter_cn] = value

        measure_to_view = {
            cn: self._store.get_view_for_measure(cn) for cn in resolved_measures
        }
        sql, params = query_builder.build_query(
            measures, dimensions, resolved_filters, measure_to_view
        )
        rows = self._warehouse.execute_query(sql, params)
        return QueryResult(rows=rows, row_count=len(rows), sql=sql)
