"""SemanticGraph: the consumer-facing API over the compiled measure/dimension graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from the_semantic_layer.errors import (
    AmbiguousNameError,
    IncompatibleDimensionError,
    InvalidFilterError,
    UnresolvedNameError,
)
from the_semantic_layer.graph import query_builder
from the_semantic_layer.models import Dimension, Measure, QueryResult
from the_semantic_layer.types import (
    FilterClause,
    NeighborResult,
    NodeResult,
    PathResult,
    QueryPlan,
    ValidationResult,
    ViewSummary,
)

if TYPE_CHECKING:
    from the_semantic_layer.compilation.warehouse import WarehouseConnection
    from the_semantic_layer.graph.store import GraphStore


class SemanticGraph:
    """In-memory graph of measures, dimensions, and their compatibility.

    Constructed by the compiler; consumed by application code, agents, notebooks.
    The backing store is injectable -- swap GraphStore implementations to change
    how the graph is persisted or queried.
    """

    def __init__(
        self,
        store: GraphStore,
        warehouse: WarehouseConnection | None = None,
    ) -> None:
        self._store = store
        self._warehouse = warehouse

    # ------------------------------------------------------------------
    # Listing / discovery
    # ------------------------------------------------------------------

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

    def list_dimensions(self) -> list[dict]:
        """Return every dimension the Semantic Layer knows about."""
        return [
            {
                "canonical_name": dim.canonical_name,
                "display_name": dim.display_name,
                "description": dim.description,
                "synonyms": list(dim.synonyms),
                "data_type": dim.data_type,
                "metric_views": list(dim.metric_views),
            }
            for dim in self._store.all_dimensions()
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
        resolved = []
        for name in measure_names:
            try:
                resolved.append(self._store.resolve_name(name, "measure"))
            except UnresolvedNameError:
                suggestions = self._store.suggest_name(name, "measure")
                raise UnresolvedNameError(name, "measure", suggestions=suggestions) from None

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

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def query(
        self,
        measure_names: list[str],
        dimension_names: list[str],
        filters: list[FilterClause] | None = None,
        max_rows: int | None = None,
    ) -> QueryResult:
        """Query the Semantic Layer for data.

        Args:
            measure_names: Measure names to include (resolved via synonyms).
            dimension_names: Dimension names to group/slice by (resolved via synonyms).
            filters: Optional FilterClause objects for dimension filtering.
            max_rows: Optional row limit for the query.

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

        resolved_measures = []
        for name in measure_names:
            try:
                resolved_measures.append(self._store.resolve_name(name, "measure"))
            except UnresolvedNameError:
                suggestions = self._store.suggest_name(name, "measure")
                raise UnresolvedNameError(name, "measure", suggestions=suggestions) from None

        measures = [self._store.get_measure(cn) for cn in resolved_measures]

        resolved_dims = []
        for name in dimension_names:
            try:
                resolved_dims.append(self._store.resolve_name(name, "dimension"))
            except UnresolvedNameError:
                suggestions = self._store.suggest_name(name, "dimension")
                raise UnresolvedNameError(name, "dimension", suggestions=suggestions) from None

        compatible = self._store.get_compatible_dimensions(resolved_measures)

        for dim_cn in resolved_dims:
            if dim_cn not in compatible:
                raise IncompatibleDimensionError(
                    dim_cn,
                    resolved_measures,
                    compatible_dimensions=sorted(compatible),
                )

        dimensions = [self._store.get_dimension(cn) for cn in resolved_dims]

        resolved_filters: list[FilterClause] = []
        if filters:
            for fc in filters:
                try:
                    filter_cn = self._store.resolve_name(fc.dimension, "dimension")
                except UnresolvedNameError:
                    suggestions = self._store.suggest_name(fc.dimension, "dimension")
                    raise UnresolvedNameError(
                        fc.dimension, "dimension", suggestions=suggestions
                    ) from None
                if filter_cn not in resolved_dims:
                    raise InvalidFilterError(
                        filter_cn,
                        valid_dimensions=sorted(resolved_dims),
                    )
                resolved_filters.append(FilterClause(dimension=filter_cn, values=fc.values))

        measure_to_view = {cn: self._store.get_view_for_measure(cn) for cn in resolved_measures}

        plan = QueryPlan(
            measures=measures,
            dimensions=dimensions,
            filters=resolved_filters,
            measure_to_view=measure_to_view,
            max_rows=max_rows,
        )
        sql, params = query_builder.build_query(plan)
        rows = self._warehouse.execute_query(sql, params)
        return QueryResult(rows=rows, row_count=len(rows), sql=sql)

    # ------------------------------------------------------------------
    # Filter value discovery (WS2)
    # ------------------------------------------------------------------

    def get_filter_values(self, dimension_name: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Fetch distinct values for a dimension from the warehouse.

        Args:
            dimension_name: Dimension name (canonical, display, or synonym).
            limit: Optional max number of values to return.

        Returns:
            List of dicts with 'value' and 'count' keys, ordered by count descending.

        Raises:
            UnresolvedNameError: If the dimension name cannot be resolved.
            RuntimeError: If no warehouse connection is available.
        """
        if self._warehouse is None:
            raise RuntimeError(
                "No warehouse connection available. "
                "Construct the SemanticGraph with a warehouse to use get_filter_values()."
            )

        try:
            canonical = self._store.resolve_name(dimension_name, "dimension")
        except UnresolvedNameError:
            suggestions = self._store.suggest_name(dimension_name, "dimension")
            raise UnresolvedNameError(dimension_name, "dimension", suggestions=suggestions) from None

        dim = self._store.get_dimension(canonical)
        if dim is None or not dim.metric_views:
            return []

        view_fqn = dim.metric_views[0]
        sql = (
            f"SELECT {dim.sql_name} AS value, COUNT(*) AS count\n"
            f"FROM {view_fqn}\n"
            f"GROUP BY {dim.sql_name}\n"
            f"ORDER BY count DESC"
        )
        if limit is not None:
            sql += f"\nLIMIT {limit}"

        return self._warehouse.execute_query(sql)

    # ------------------------------------------------------------------
    # Graph traversal APIs (WS4)
    # ------------------------------------------------------------------

    def get_node(self, name_or_alias: str) -> NodeResult:
        """Look up a single node by name or alias and return its full description.

        Resolution strategy: try measure first, then dimension.

        Raises:
            UnresolvedNameError: If the name cannot be resolved as either type.
        """
        # Try measure first
        measure = None
        try:
            m_canonical = self._store.resolve_name(name_or_alias, "measure")
            measure = self._store.get_measure(m_canonical)
        except (UnresolvedNameError, AmbiguousNameError):
            pass

        if measure is not None:
            view_fqn = self._store.get_view_for_measure(measure.canonical_name)
            compat_dims = tuple(sorted(self._store.get_dimensions_for_view(view_fqn)))
            return NodeResult(
                kind="measure",
                canonical_name=measure.canonical_name,
                display_name=measure.display_name,
                description=measure.description,
                data_type=measure.data_type,
                synonyms=measure.synonyms,
                metric_view=view_fqn,
                compatible_dimensions=compat_dims,
            )

        # Try dimension
        try:
            d_canonical = self._store.resolve_name(name_or_alias, "dimension")
            dim = self._store.get_dimension(d_canonical)
        except (UnresolvedNameError, AmbiguousNameError):
            dim = None

        if dim is not None:
            compat_measures: list[str] = []
            for view_fqn in dim.metric_views:
                compat_measures.extend(self._store.get_measures_for_view(view_fqn))
            return NodeResult(
                kind="dimension",
                canonical_name=dim.canonical_name,
                display_name=dim.display_name,
                description=dim.description,
                data_type=dim.data_type,
                synonyms=dim.synonyms,
                metric_views=dim.metric_views,
                compatible_measures=tuple(sorted(set(compat_measures))),
            )

        # Neither resolved
        m_suggestions = self._store.suggest_name(name_or_alias, "measure")
        d_suggestions = self._store.suggest_name(name_or_alias, "dimension")
        raise UnresolvedNameError(
            name_or_alias, "measure or dimension", suggestions=m_suggestions + d_suggestions
        )

    def get_neighbors(self, canonical_name: str, edge_type: str | None = None) -> list[NeighborResult]:
        """Return the neighbors of a node in the graph.

        Args:
            canonical_name: Canonical name of a measure or dimension.
            edge_type: Optional filter -- "measure" or "dimension".

        Returns:
            List of NeighborResult objects.

        Raises:
            UnresolvedNameError: If the canonical name is not found.
        """
        measure = self._store.get_measure(canonical_name)
        if measure is not None:
            return self._measure_neighbors(measure, edge_type)

        dim = self._store.get_dimension(canonical_name)
        if dim is not None:
            return self._dimension_neighbors(dim, edge_type)

        raise UnresolvedNameError(canonical_name, "measure or dimension")

    def _measure_neighbors(self, measure: Measure, edge_type: str | None) -> list[NeighborResult]:
        view_fqn = self._store.get_view_for_measure(measure.canonical_name)
        results: list[NeighborResult] = []

        if edge_type is None or edge_type == "dimension":
            for dim_cn in self._store.get_dimensions_for_view(view_fqn):
                dim = self._store.get_dimension(dim_cn)
                if dim:
                    results.append(NeighborResult(dim.canonical_name, "dimension", dim.display_name))

        if edge_type is None or edge_type == "measure":
            for m_cn in self._store.get_measures_for_view(view_fqn):
                if m_cn == measure.canonical_name:
                    continue
                m = self._store.get_measure(m_cn)
                if m:
                    results.append(NeighborResult(m.canonical_name, "measure", m.display_name))

        return results

    def _dimension_neighbors(self, dim: Dimension, edge_type: str | None) -> list[NeighborResult]:
        results: list[NeighborResult] = []
        seen_measures: set[str] = set()
        seen_dims: set[str] = set()

        for view_fqn in dim.metric_views:
            if edge_type is None or edge_type == "measure":
                for m_cn in self._store.get_measures_for_view(view_fqn):
                    if m_cn not in seen_measures:
                        seen_measures.add(m_cn)
                        m = self._store.get_measure(m_cn)
                        if m:
                            results.append(NeighborResult(m.canonical_name, "measure", m.display_name))

            if edge_type is None or edge_type == "dimension":
                for d_cn in self._store.get_dimensions_for_view(view_fqn):
                    if d_cn == dim.canonical_name:
                        continue
                    if d_cn not in seen_dims:
                        seen_dims.add(d_cn)
                        other = self._store.get_dimension(d_cn)
                        if other:
                            results.append(
                                NeighborResult(other.canonical_name, "dimension", other.display_name)
                            )

        return results

    def find_path(self, node_a: str, node_b: str) -> PathResult:
        """Describe the relationship between two nodes.

        Resolution strategy: try measure first, then dimension for each node.
        """
        a_kind, a_canonical = self._resolve_node(node_a)
        b_kind, b_canonical = self._resolve_node(node_b)

        if a_kind == "measure" and b_kind == "measure":
            return self._path_measure_measure(a_canonical, b_canonical)
        if a_kind == "dimension" and b_kind == "dimension":
            return self._path_dimension_dimension(a_canonical, b_canonical)
        # One measure, one dimension (order doesn't matter for the check)
        m_cn = a_canonical if a_kind == "measure" else b_canonical
        d_cn = a_canonical if a_kind == "dimension" else b_canonical
        return self._path_measure_dimension(node_a, node_b, m_cn, d_cn)

    def _resolve_node(self, name: str) -> tuple[str, str]:
        """Resolve a name as measure or dimension. Returns (kind, canonical)."""
        try:
            return "measure", self._store.resolve_name(name, "measure")
        except (UnresolvedNameError, AmbiguousNameError):
            pass
        try:
            return "dimension", self._store.resolve_name(name, "dimension")
        except (UnresolvedNameError, AmbiguousNameError):
            pass
        raise UnresolvedNameError(name, "measure or dimension")

    def _path_measure_measure(self, a: str, b: str) -> PathResult:
        shared = self._store.get_compatible_dimensions([a, b])
        return PathResult(
            node_a=a,
            node_b=b,
            connected=bool(shared),
            relationship="joinable",
            shared_dimensions=tuple(sorted(shared)),
        )

    def _path_dimension_dimension(self, a: str, b: str) -> PathResult:
        dim_a = self._store.get_dimension(a)
        dim_b = self._store.get_dimension(b)
        views_a = set(dim_a.metric_views) if dim_a else set()
        views_b = set(dim_b.metric_views) if dim_b else set()
        co_occurring = views_a & views_b
        return PathResult(
            node_a=a,
            node_b=b,
            connected=bool(co_occurring),
            relationship="co_occurring",
            co_occurring_views=tuple(sorted(co_occurring)),
        )

    def _path_measure_dimension(self, node_a: str, node_b: str, m_cn: str, d_cn: str) -> PathResult:
        view_fqn = self._store.get_view_for_measure(m_cn)
        view_dims = set(self._store.get_dimensions_for_view(view_fqn))
        connected = d_cn in view_dims
        return PathResult(
            node_a=node_a,
            node_b=node_b,
            connected=connected,
            relationship="compatible" if connected else "none",
        )

    def validate_combination(self, names: list[str]) -> ValidationResult:
        """Pre-flight check: can these measures and dimensions be queried together?"""
        resolved_measures: list[str] = []
        resolved_dims: list[str] = []
        errors: list[str] = []

        for name in names:
            # Try measure
            try:
                cn = self._store.resolve_name(name, "measure")
                resolved_measures.append(cn)
                continue
            except (UnresolvedNameError, AmbiguousNameError):
                pass
            # Try dimension
            try:
                cn = self._store.resolve_name(name, "dimension")
                resolved_dims.append(cn)
                continue
            except (UnresolvedNameError, AmbiguousNameError):
                pass
            errors.append(f"Could not resolve: {name!r}")

        if not resolved_measures:
            if not errors:
                errors.append("No measures specified")
            return ValidationResult(
                valid=False,
                measures=tuple(resolved_measures),
                dimensions=tuple(resolved_dims),
                errors=tuple(errors),
            )

        compatible = self._store.get_compatible_dimensions(resolved_measures)
        incompatible = [d for d in resolved_dims if d not in compatible]

        valid = not incompatible and not errors
        return ValidationResult(
            valid=valid,
            measures=tuple(resolved_measures),
            dimensions=tuple(resolved_dims),
            compatible_dimensions=tuple(sorted(compatible)),
            incompatible=tuple(incompatible),
            errors=tuple(errors),
        )

    def list_entry_points(self, category: str | None = None) -> list[ViewSummary] | list[dict]:
        """List entry points into the graph.

        Args:
            category: None for view summaries, "measures" or "dimensions" for flat lists.
        """
        if category == "measures":
            return self.list_measures()
        if category == "dimensions":
            return self.list_dimensions()

        return [
            ViewSummary(
                view=view_fqn.rsplit(".", 1)[-1],
                view_fqn=view_fqn,
                measures=tuple(sorted(self._store.get_measures_for_view(view_fqn))),
                dimensions=tuple(sorted(self._store.get_dimensions_for_view(view_fqn))),
            )
            for view_fqn in self._store.get_views()
        ]
