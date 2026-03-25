"""Tests for typed intermediate representations."""

import pytest

from the_semantic_layer.types import (
    DimensionDefinition,
    FilterClause,
    MeasureDefinition,
    NeighborResult,
    NodeResult,
    PathResult,
    QueryPlan,
    ValidationResult,
    ViewDefinition,
    ViewSummary,
)


class TestMeasureDefinition:
    def test_construction(self):
        md = MeasureDefinition(
            name="revenue",
            display_name="Revenue",
            description="Total revenue",
            data_type="DOUBLE",
            synonyms=("rev",),
        )
        assert md.name == "revenue"
        assert md.expression is None

    def test_frozen(self):
        md = MeasureDefinition("revenue", "Revenue", "", "DOUBLE", ())
        with pytest.raises(AttributeError):
            md.name = "other"


class TestDimensionDefinition:
    def test_construction(self):
        dd = DimensionDefinition(
            name="date",
            display_name="Date",
            description="Transaction date",
            data_type="DATE",
            synonyms=(),
        )
        assert dd.name == "date"

    def test_frozen(self):
        dd = DimensionDefinition("date", "Date", "", "DATE", ())
        with pytest.raises(AttributeError):
            dd.name = "other"


class TestViewDefinition:
    def test_construction(self):
        vd = ViewDefinition(
            name="sales",
            fqn="catalog.schema.sales",
            description="Sales metrics",
            measures=[MeasureDefinition("revenue", "Revenue", "", "DOUBLE", ())],
            dimensions=[DimensionDefinition("date", "Date", "", "DATE", ())],
        )
        assert vd.name == "sales"
        assert len(vd.measures) == 1
        assert len(vd.dimensions) == 1


class TestFilterClause:
    def test_single_value(self):
        fc = FilterClause(dimension="region", values=["US"])
        assert fc.dimension == "region"
        assert fc.values == ["US"]

    def test_multiple_values(self):
        fc = FilterClause(dimension="region", values=["US", "EU", "APAC"])
        assert len(fc.values) == 3

    def test_frozen(self):
        fc = FilterClause(dimension="region", values=["US"])
        with pytest.raises(AttributeError):
            fc.dimension = "date"


class TestQueryPlan:
    def test_construction(self):
        from the_semantic_layer.models import Dimension, Measure

        m = Measure("sales.rev", "rev", "v", "Revenue", "", "DOUBLE")
        d = Dimension("date", "date", "Date", "", "DATE")
        plan = QueryPlan(
            measures=[m],
            dimensions=[d],
            filters=[FilterClause("date", ["2024-01-01"])],
            measure_to_view={"sales.rev": "v"},
            max_rows=100,
        )
        assert plan.max_rows == 100
        assert len(plan.filters) == 1

    def test_default_max_rows(self):
        plan = QueryPlan(measures=[], dimensions=[], filters=[], measure_to_view={})
        assert plan.max_rows is None


class TestNodeResult:
    def test_measure_node(self):
        nr = NodeResult(
            kind="measure",
            canonical_name="sales.revenue",
            display_name="Revenue",
            description="Total revenue",
            data_type="DOUBLE",
            synonyms=("rev",),
            metric_view="catalog.schema.sales",
            compatible_dimensions=("date", "region"),
        )
        assert nr.kind == "measure"
        assert nr.metric_view == "catalog.schema.sales"

    def test_dimension_node(self):
        nr = NodeResult(
            kind="dimension",
            canonical_name="date",
            display_name="Date",
            description="",
            data_type="DATE",
            synonyms=(),
            metric_views=("catalog.schema.sales",),
            compatible_measures=("sales.revenue",),
        )
        assert nr.kind == "dimension"


class TestNeighborResult:
    def test_construction(self):
        nr = NeighborResult("sales.revenue", "measure", "Revenue")
        assert nr.canonical_name == "sales.revenue"


class TestPathResult:
    def test_joinable(self):
        pr = PathResult("a", "b", True, "joinable", shared_dimensions=("date",))
        assert pr.connected is True
        assert pr.shared_dimensions == ("date",)

    def test_not_connected(self):
        pr = PathResult("a", "b", False, "none")
        assert pr.connected is False


class TestValidationResult:
    def test_valid(self):
        vr = ValidationResult(valid=True, measures=("m1",), dimensions=("d1",))
        assert vr.valid is True

    def test_invalid(self):
        vr = ValidationResult(valid=False, errors=("bad",))
        assert not vr.valid


class TestViewSummary:
    def test_construction(self):
        vs = ViewSummary(
            view="sales",
            view_fqn="cat.sch.sales",
            measures=("sales.revenue",),
            dimensions=("date",),
        )
        assert vs.view == "sales"
