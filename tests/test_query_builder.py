"""Tests for SQL query generation."""

from the_semantic_layer.graph.query_builder import build_query
from the_semantic_layer.models import Dimension, Measure
from the_semantic_layer.types import FilterClause, QueryPlan


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


def _plan(measures, dimensions, filters=None, measure_to_view=None, max_rows=None):
    if measure_to_view is None:
        measure_to_view = {m.canonical_name: m.metric_view for m in measures}
    return QueryPlan(
        measures=measures,
        dimensions=dimensions,
        filters=filters or [],
        measure_to_view=measure_to_view,
        max_rows=max_rows,
    )


class TestSingleViewQuery:
    def test_basic_select(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, params = build_query(_plan([m], [d]))
        assert "SELECT" in sql
        assert "date" in sql
        assert "revenue" in sql
        assert "FROM cat.sch.sales" in sql
        assert "GROUP BY 1" in sql
        assert params == []

    def test_with_filter(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("region", ["cat.sch.sales"])
        plan = _plan([m], [d], filters=[FilterClause(dimension="region", values=["US"])])
        sql, params = build_query(plan)
        assert "WHERE `region` = %s" in sql
        assert params == ["US"]

    def test_multiple_measures_same_view(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("order_count", "cat.sch.sales")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, _params = build_query(_plan([m1, m2], [d]))
        assert "revenue" in sql
        assert "order_count" in sql
        assert "GROUP BY 1" in sql

    def test_expression_field_not_emitted_in_sql(self):
        m = _make_measure("revenue", "cat.sch.sales", expression="SUM(amount)")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, _ = build_query(_plan([m], [d]))
        assert "SUM(amount)" not in sql
        assert "`revenue`" in sql

    def test_multi_value_filter_generates_in_clause(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("region", ["cat.sch.sales"])
        plan = _plan(
            [m],
            [d],
            filters=[FilterClause(dimension="region", values=["US", "EU", "APAC"])],
        )
        sql, params = build_query(plan)
        assert "`region` IN (%s, %s, %s)" in sql
        assert params == ["US", "EU", "APAC"]

    def test_single_value_filter_generates_equality(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("region", ["cat.sch.sales"])
        plan = _plan(
            [m],
            [d],
            filters=[FilterClause(dimension="region", values=["US"])],
        )
        sql, params = build_query(plan)
        assert "`region` = %s" in sql
        assert params == ["US"]

    def test_max_rows_generates_limit(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, _ = build_query(_plan([m], [d], max_rows=100))
        assert "LIMIT 100" in sql

    def test_no_max_rows_no_limit(self):
        m = _make_measure("revenue", "cat.sch.sales")
        d = _make_dimension("date", ["cat.sch.sales"])
        sql, _ = build_query(_plan([m], [d]))
        assert "LIMIT" not in sql


class TestMultiViewQuery:
    def test_cte_structure(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d = _make_dimension("date", ["cat.sch.sales", "cat.sch.costs"])
        sql, _params = build_query(_plan([m1, m2], [d]))
        assert "WITH" in sql
        assert "cte_sales" in sql
        assert "cte_costs" in sql
        assert "INNER JOIN" in sql
        assert "ON cte_sales.`date` = cte_costs.`date`" in sql

    def test_multi_view_with_filter(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d = _make_dimension("region", ["cat.sch.sales", "cat.sch.costs"])
        plan = _plan(
            [m1, m2],
            [d],
            filters=[FilterClause(dimension="region", values=["EU"])],
        )
        sql, params = build_query(plan)
        assert sql.count("`region` = %s") == 2
        assert params == ["EU", "EU"]

    def test_multiple_dimensions_join(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d1 = _make_dimension("date", ["cat.sch.sales", "cat.sch.costs"])
        d2 = _make_dimension("region", ["cat.sch.sales", "cat.sch.costs"])
        sql, _ = build_query(_plan([m1, m2], [d1, d2]))
        assert "cte_sales.`date` = cte_costs.`date`" in sql
        assert "cte_sales.`region` = cte_costs.`region`" in sql

    def test_multi_value_filter_in_multi_view(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d = _make_dimension("region", ["cat.sch.sales", "cat.sch.costs"])
        plan = _plan(
            [m1, m2],
            [d],
            filters=[FilterClause(dimension="region", values=["US", "EU"])],
        )
        sql, params = build_query(plan)
        assert sql.count("`region` IN (%s, %s)") == 2
        assert params == ["US", "EU", "US", "EU"]

    def test_max_rows_in_multi_view(self):
        m1 = _make_measure("revenue", "cat.sch.sales")
        m2 = _make_measure("total_cost", "cat.sch.costs")
        d = _make_dimension("date", ["cat.sch.sales", "cat.sch.costs"])
        sql, _ = build_query(_plan([m1, m2], [d], max_rows=50))
        assert sql.endswith("\nLIMIT 50")
