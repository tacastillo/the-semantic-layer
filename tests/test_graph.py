"""Tests for the SemanticGraph API."""

import pytest

from the_semantic_layer.errors import (
    IncompatibleDimensionError,
    InvalidFilterError,
    UnresolvedNameError,
)
from the_semantic_layer.models import QueryResult


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


class TestGetDimensionsForMeasures:
    def test_single_measure_returns_all_view_dims(self, sample_graph):
        dims = sample_graph.get_dimensions_for_measures(["sales.revenue"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region", "product"}

    def test_cross_view_returns_intersection(self, sample_graph):
        """Measures from sales + costs → only shared dimensions (date, region)."""
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
        """Two measures from the same view → all dims of that view."""
        dims = sample_graph.get_dimensions_for_measures(["Revenue", "Order Count"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region", "product"}


class TestQuery:
    def test_no_warehouse_raises(self, sample_graph):
        with pytest.raises(RuntimeError, match="No warehouse connection"):
            sample_graph.query(["Revenue"], ["date"])

    def test_incompatible_dimension_raises(self, graph_with_warehouse):
        """Requesting a dimension not in the intersection should raise."""
        # "product" is only in sales, not in costs
        with pytest.raises(IncompatibleDimensionError):
            graph_with_warehouse.query(["Revenue", "Total Cost"], ["product"])

    def test_invalid_filter_raises(self, graph_with_warehouse):
        # Filter on "region" but only requesting dimension "date"
        with pytest.raises(InvalidFilterError):
            graph_with_warehouse.query(["Revenue"], ["date"], filters={"region": "US"})

    def test_query_executes_and_returns_result(self, graph_with_warehouse):
        from tests.conftest import FakeWarehouse
        graph_with_warehouse._warehouse = FakeWarehouse(
            rows=[{"date": "2024-01-01", "revenue": 100.0}]
        )
        result = graph_with_warehouse.query(["Revenue"], ["date"])
        assert isinstance(result, QueryResult)
        assert result.row_count == 1
        assert result.rows[0]["revenue"] == 100.0
        assert "SELECT" in result.sql
