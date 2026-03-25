"""Tests for the SemanticGraph API."""

import pytest

from the_semantic_layer.errors import (
    IncompatibleDimensionError,
    InvalidFilterError,
    UnresolvedNameError,
)
from the_semantic_layer.models import QueryResult
from the_semantic_layer.types import FilterClause, NodeResult, PathResult, ValidationResult, ViewSummary


class TestListMeasures:
    def test_returns_all_measures(self, sample_graph):
        result = sample_graph.list_measures()
        names = {m["canonical_name"] for m in result}
        assert names == {"sales.revenue", "sales.order_count", "costs.total_cost"}

    def test_measure_fields(self, sample_graph):
        result = sample_graph.list_measures()
        revenue = next(m for m in result if m["canonical_name"] == "sales.revenue")
        assert revenue["display_name"] == "Revenue"
        assert revenue["description"] == "Total revenue"
        assert "rev" in revenue["synonyms"]
        assert revenue["metric_view"] == "catalog.schema.sales"


class TestListDimensions:
    def test_returns_all_dimensions(self, sample_graph):
        result = sample_graph.list_dimensions()
        names = {d["canonical_name"] for d in result}
        assert names == {"date", "region", "product", "channel"}

    def test_dimension_fields(self, sample_graph):
        result = sample_graph.list_dimensions()
        date = next(d for d in result if d["canonical_name"] == "date")
        assert date["display_name"] == "Date"
        assert date["description"] == "Transaction date"
        assert "catalog.schema.sales" in date["metric_views"]
        assert "catalog.schema.costs" in date["metric_views"]


class TestGetDimensionsForMeasures:
    def test_single_measure_returns_all_view_dims(self, sample_graph):
        dims = sample_graph.get_dimensions_for_measures(["sales.revenue"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region", "product"}

    def test_cross_view_returns_intersection(self, sample_graph):
        """Measures from sales + costs -> only shared dimensions (date, region)."""
        dims = sample_graph.get_dimensions_for_measures(["Revenue", "Total Cost"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region"}

    def test_synonym_resolution(self, sample_graph):
        dims = sample_graph.get_dimensions_for_measures(["rev"])
        dim_names = {d["canonical_name"] for d in dims}
        assert "date" in dim_names

    def test_unresolved_measure_raises(self, sample_graph):
        with pytest.raises(UnresolvedNameError):
            sample_graph.get_dimensions_for_measures(["nonexistent"])

    def test_same_view_measures_returns_full_dims(self, sample_graph):
        """Two measures from the same view -> all dims of that view."""
        dims = sample_graph.get_dimensions_for_measures(["Revenue", "Order Count"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region", "product"}

    def test_unresolved_measure_includes_suggestions(self, sample_graph):
        with pytest.raises(UnresolvedNameError) as exc_info:
            sample_graph.get_dimensions_for_measures(["revnue"])
        assert len(exc_info.value.suggestions) > 0


class TestQuery:
    def test_no_warehouse_raises(self, sample_graph):
        with pytest.raises(RuntimeError, match="No warehouse connection"):
            sample_graph.query(["Revenue"], ["date"])

    def test_incompatible_dimension_raises(self, graph_with_warehouse):
        """Requesting a dimension not in the intersection should raise."""
        with pytest.raises(IncompatibleDimensionError) as exc_info:
            graph_with_warehouse.query(["Revenue", "Total Cost"], ["product"])
        assert len(exc_info.value.compatible_dimensions) > 0

    def test_invalid_filter_raises(self, graph_with_warehouse):
        with pytest.raises(InvalidFilterError) as exc_info:
            graph_with_warehouse.query(
                ["Revenue"],
                ["date"],
                filters=[FilterClause(dimension="region", values=["US"])],
            )
        assert len(exc_info.value.valid_dimensions) > 0

    def test_query_executes_and_returns_result(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse

        graph_with_warehouse._warehouse = FakeWarehouse(rows=[{"date": "2024-01-01", "revenue": 100.0}])
        result = graph_with_warehouse.query(["Revenue"], ["date"])
        assert isinstance(result, QueryResult)
        assert result.row_count == 1
        assert result.rows[0]["revenue"] == 100.0
        assert "SELECT" in result.sql

    def test_query_with_multi_value_filter(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse

        graph_with_warehouse._warehouse = FakeWarehouse(rows=[])
        result = graph_with_warehouse.query(
            ["Revenue"],
            ["region"],
            filters=[FilterClause(dimension="region", values=["US", "EU"])],
        )
        assert "IN (%s, %s)" in result.sql

    def test_query_with_max_rows(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse

        graph_with_warehouse._warehouse = FakeWarehouse(rows=[])
        result = graph_with_warehouse.query(["Revenue"], ["date"], max_rows=10)
        assert "LIMIT 10" in result.sql


class TestGetFilterValues:
    def test_returns_values_from_warehouse(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse

        graph_with_warehouse._warehouse = FakeWarehouse(
            rows=[{"value": "US", "count": 100}, {"value": "EU", "count": 50}]
        )
        result = graph_with_warehouse.get_filter_values("date")
        assert len(result) == 2

    def test_unresolved_dimension_raises(self, graph_with_warehouse):
        with pytest.raises(UnresolvedNameError):
            graph_with_warehouse.get_filter_values("nonexistent")

    def test_limit_appears_in_sql(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse

        captured = {}

        class CapturingWarehouse(FakeWarehouse):
            def execute_query(self, sql, params=None):
                captured["sql"] = sql
                return []

        graph_with_warehouse._warehouse = CapturingWarehouse()
        graph_with_warehouse.get_filter_values("date", limit=10)
        assert "LIMIT 10" in captured["sql"]

    def test_no_warehouse_raises(self, sample_graph):
        with pytest.raises(RuntimeError, match="No warehouse connection"):
            sample_graph.get_filter_values("date")

    def test_builds_correct_sql(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse

        captured = {}

        class CapturingWarehouse(FakeWarehouse):
            def execute_query(self, sql, params=None):
                captured["sql"] = sql
                return []

        graph_with_warehouse._warehouse = CapturingWarehouse()
        graph_with_warehouse.get_filter_values("date")
        sql = captured["sql"]
        assert "SELECT `date` AS value" in sql
        assert "COUNT(*) AS count" in sql
        assert "GROUP BY" in sql
        assert "ORDER BY count DESC" in sql


class TestGetNode:
    def test_resolve_measure(self, sample_graph):
        node = sample_graph.get_node("Revenue")
        assert isinstance(node, NodeResult)
        assert node.kind == "measure"
        assert node.canonical_name == "sales.revenue"
        assert node.metric_view == "catalog.schema.sales"
        assert len(node.compatible_dimensions) > 0

    def test_resolve_dimension(self, sample_graph):
        node = sample_graph.get_node("date")
        assert node.kind == "dimension"
        assert node.canonical_name == "date"
        assert len(node.metric_views) > 0
        assert len(node.compatible_measures) > 0

    def test_unresolved_raises(self, sample_graph):
        with pytest.raises(UnresolvedNameError):
            sample_graph.get_node("totally_fake")


class TestGetNeighbors:
    def test_measure_neighbors_include_dimensions(self, sample_graph):
        neighbors = sample_graph.get_neighbors("sales.revenue")
        kinds = {n.kind for n in neighbors}
        assert "dimension" in kinds

    def test_dimension_neighbors_include_measures(self, sample_graph):
        neighbors = sample_graph.get_neighbors("date")
        kinds = {n.kind for n in neighbors}
        assert "measure" in kinds

    def test_edge_type_filtering(self, sample_graph):
        dim_only = sample_graph.get_neighbors("sales.revenue", edge_type="dimension")
        assert all(n.kind == "dimension" for n in dim_only)

        measure_only = sample_graph.get_neighbors("date", edge_type="measure")
        assert all(n.kind == "measure" for n in measure_only)

    def test_unknown_raises(self, sample_graph):
        with pytest.raises(UnresolvedNameError):
            sample_graph.get_neighbors("nonexistent")


class TestFindPath:
    def test_measures_with_shared_dims_are_joinable(self, sample_graph):
        result = sample_graph.find_path("sales.revenue", "costs.total_cost")
        assert isinstance(result, PathResult)
        assert result.connected is True
        assert result.relationship == "joinable"
        assert len(result.shared_dimensions) > 0
        assert "date" in result.shared_dimensions

    def test_measure_and_compatible_dimension(self, sample_graph):
        result = sample_graph.find_path("sales.revenue", "date")
        assert result.connected is True
        assert result.relationship == "compatible"

    def test_measure_and_incompatible_dimension(self, sample_graph):
        result = sample_graph.find_path("sales.revenue", "channel")
        assert result.connected is False
        assert result.relationship == "none"

    def test_dimensions_in_same_view(self, sample_graph):
        result = sample_graph.find_path("date", "region")
        assert result.connected is True
        assert result.relationship == "co_occurring"
        assert len(result.co_occurring_views) > 0


class TestValidateCombination:
    def test_all_compatible(self, sample_graph):
        result = sample_graph.validate_combination(["sales.revenue", "date", "region"])
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert len(result.incompatible) == 0

    def test_incompatible_dimension(self, sample_graph):
        result = sample_graph.validate_combination(["sales.revenue", "costs.total_cost", "product"])
        assert result.valid is False
        assert "product" in result.incompatible

    def test_unresolved_name(self, sample_graph):
        result = sample_graph.validate_combination(["sales.revenue", "nonexistent"])
        assert result.valid is False
        assert len(result.errors) > 0

    def test_cross_view_measures(self, sample_graph):
        result = sample_graph.validate_combination(["sales.revenue", "costs.total_cost", "date"])
        assert result.valid is True
        assert "date" in result.compatible_dimensions


class TestListEntryPoints:
    def test_returns_view_summaries(self, sample_graph):
        result = sample_graph.list_entry_points()
        assert all(isinstance(v, ViewSummary) for v in result)
        views = {v.view for v in result}
        assert "sales" in views
        assert "costs" in views

    def test_category_measures(self, sample_graph):
        result = sample_graph.list_entry_points(category="measures")
        assert all(isinstance(m, dict) for m in result)
        names = {m["canonical_name"] for m in result}
        assert "sales.revenue" in names

    def test_category_dimensions(self, sample_graph):
        result = sample_graph.list_entry_points(category="dimensions")
        assert all(isinstance(d, dict) for d in result)
        names = {d["canonical_name"] for d in result}
        assert "date" in names


class TestStoreViewMethods:
    """Test the new store methods added for traversal APIs."""

    def test_all_dimensions(self, sample_graph):
        dims = sample_graph._store.all_dimensions()
        names = {d.canonical_name for d in dims}
        assert names == {"date", "region", "product", "channel"}

    def test_get_views(self, sample_graph):
        views = sample_graph._store.get_views()
        assert set(views) == {"catalog.schema.sales", "catalog.schema.costs"}

    def test_get_measures_for_view(self, sample_graph):
        measures = sample_graph._store.get_measures_for_view("catalog.schema.sales")
        assert set(measures) == {"sales.revenue", "sales.order_count"}

    def test_get_dimensions_for_view(self, sample_graph):
        dims = sample_graph._store.get_dimensions_for_view("catalog.schema.sales")
        assert set(dims) == {"date", "region", "product"}
