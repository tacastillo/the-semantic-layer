"""Shared test fixtures for the Semantic Layer."""

import pytest

from the_semantic_layer.graph import InMemoryGraphStore, SemanticGraph
from the_semantic_layer.models import Dimension, Measure


@pytest.fixture
def sample_measures():
    return {
        "sales.revenue": Measure(
            canonical_name="sales.revenue",
            column_name="revenue",
            metric_view="catalog.schema.sales",
            display_name="Revenue",
            description="Total revenue",
            data_type="DOUBLE",
            synonyms=("rev", "total revenue"),
        ),
        "sales.order_count": Measure(
            canonical_name="sales.order_count",
            column_name="order_count",
            metric_view="catalog.schema.sales",
            display_name="Order Count",
            description="Number of orders",
            data_type="BIGINT",
            synonyms=("orders",),
        ),
        "costs.total_cost": Measure(
            canonical_name="costs.total_cost",
            column_name="total_cost",
            metric_view="catalog.schema.costs",
            display_name="Total Cost",
            description="Total cost",
            data_type="DOUBLE",
            synonyms=("cost",),
        ),
    }


@pytest.fixture
def sample_dimensions():
    return {
        "date": Dimension(
            canonical_name="date",
            column_name="date",
            display_name="Date",
            description="Transaction date",
            data_type="DATE",
            synonyms=(),
            metric_views=("catalog.schema.sales", "catalog.schema.costs"),
        ),
        "region": Dimension(
            canonical_name="region",
            column_name="region",
            display_name="Region",
            description="Geographic region",
            data_type="STRING",
            synonyms=(),
            metric_views=("catalog.schema.sales", "catalog.schema.costs"),
        ),
        "product": Dimension(
            canonical_name="product",
            column_name="product",
            display_name="Product",
            description="Product name",
            data_type="STRING",
            synonyms=(),
            metric_views=("catalog.schema.sales",),
        ),
        "channel": Dimension(
            canonical_name="channel",
            column_name="channel",
            display_name="Channel",
            description="Sales channel",
            data_type="STRING",
            synonyms=(),
            metric_views=("catalog.schema.costs",),
        ),
    }


@pytest.fixture
def sample_graph(sample_measures, sample_dimensions):
    """A SemanticGraph built from fixtures (no warehouse)."""
    store = InMemoryGraphStore()

    for canonical, measure in sample_measures.items():
        store.add_measure(measure, measure.metric_view)
        store.register_synonym(
            canonical,
            [measure.display_name, measure.column_name, *measure.synonyms],
            "measure",
        )

    for canonical, dim in sample_dimensions.items():
        for view_fqn in dim.metric_views:
            # Use add_or_merge_dimension so shared dims (date, region) register correctly
            store.add_or_merge_dimension(
                Dimension(
                    canonical_name=canonical,
                    column_name=dim.column_name,
                    display_name=dim.display_name,
                    description=dim.description,
                    data_type=dim.data_type,
                    synonyms=dim.synonyms,
                    metric_views=(view_fqn,),
                ),
                view_fqn,
            )

    return SemanticGraph(store=store, warehouse=None)


class FakeWarehouse:
    """Minimal warehouse stub for tests that need query execution."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def execute_query(self, sql, params=None):
        return self.rows


@pytest.fixture
def graph_with_warehouse(sample_measures, sample_dimensions):
    """A SemanticGraph with a fake warehouse, for testing query() paths."""
    store = InMemoryGraphStore()

    for canonical, measure in sample_measures.items():
        store.add_measure(measure, measure.metric_view)
        store.register_synonym(
            canonical,
            [measure.display_name, measure.column_name, *measure.synonyms],
            "measure",
        )

    for canonical, dim in sample_dimensions.items():
        for view_fqn in dim.metric_views:
            store.add_or_merge_dimension(
                Dimension(
                    canonical_name=canonical,
                    column_name=dim.column_name,
                    display_name=dim.display_name,
                    description=dim.description,
                    data_type=dim.data_type,
                    synonyms=dim.synonyms,
                    metric_views=(view_fqn,),
                ),
                view_fqn,
            )

    return SemanticGraph(store=store, warehouse=FakeWarehouse())
