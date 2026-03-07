"""Tests for SQL query generation."""

from the_semantic_layer.models import Dimension, Measure
from the_semantic_layer.query_builder import build_query


def _make_measure(name, view, expression=None):
    return Measure(
        canonical_name=f"{view.rsplit('.', 1)[-1]}.{name}",
        column_name=name,
        metric_view=view,
        display_name=name.title(),
        description="",
        data_type="DOUBLE",
        expression=expression,
    )


def _make_dimension(name, views):
    return Dimension(
        canonical_name=name.lower(),
        column_name=name,
        display_name=name.title(),
        description="",
        data_type="STRING",
        metric_views=tuple(views),
    )


class TestSingleViewQuery:
    def test_basic_select(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, params = build_query(
            [m], [d], None, {"sales.revenue": "cat.sch.sales"}
        )
        assert "SELECT" in sql
        assert "date" in sql
        assert "revenue" in sql
        assert "FROM cat.sch.sales" in sql
        assert "GROUP BY 1" in sql
        assert params == []

    def test_with_filter(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("region", ["cat.sch.sales"])
        sql, params = build_query(
            [m], [d], {"region": "US"}, {"sales.revenue": "cat.sch.sales"}
        )
        assert "WHERE region = %s" in sql
        assert params == ["US"]

    def test_multiple_measures_same_view(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("order_count", "cat.sch.sales")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, params = build_query(
            [m1, m2], [d], None,
            {"sales.revenue": "cat.sch.sales", "sales.order_count": "cat.sch.sales"},
        )
        assert "revenue" in sql
        assert "order_count" in sql
        assert "GROUP BY 1" in sql

    def test_expression_measure(self):
        m = _make_measure("revenue", "cat.sch.sales", expression="SUM(amount)")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, _ = build_query(
            [m], [d], None, {"sales.revenue": "cat.sch.sales"}
        )
        assert "SUM(amount) AS revenue" in sql


class TestMultiViewQuery:
    def test_cte_structure(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d = _make_dimension("date", ["cat.sch.sales", "cat.sch.costs"])
        sql, params = build_query(
            [m1, m2], [d], None,
            {"sales.revenue": "cat.sch.sales", "costs.total_cost": "cat.sch.costs"},
        )
        assert "WITH" in sql
        assert "cte_sales" in sql
        assert "cte_costs" in sql
        assert "INNER JOIN" in sql
        assert "ON cte_sales.date = cte_costs.date" in sql

    def test_multi_view_with_filter(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d = _make_dimension("region", ["cat.sch.sales", "cat.sch.costs"])
        sql, params = build_query(
            [m1, m2], [d], {"region": "EU"},
            {"sales.revenue": "cat.sch.sales", "costs.total_cost": "cat.sch.costs"},
        )
        # Filter should appear in both CTEs
        assert sql.count("region = %s") == 2
        assert params == ["EU", "EU"]

    def test_multiple_dimensions_join(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d1 = _make_dimension("date", ["cat.sch.sales", "cat.sch.costs"])
        d2 = _make_dimension("region", ["cat.sch.sales", "cat.sch.costs"])
        sql, _ = build_query(
            [m1, m2], [d1, d2], None,
            {"sales.revenue": "cat.sch.sales", "costs.total_cost": "cat.sch.costs"},
        )
        assert "cte_sales.date = cte_costs.date" in sql
        assert "cte_sales.region = cte_costs.region" in sql
