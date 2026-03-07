"""Shared test fixtures for the Semantic Layer."""

import pytest

from the_semantic_layer.graph import SemanticGraph
from the_semantic_layer.models import Dimension, Measure
from the_semantic_layer.synonym_index import SynonymIndex


@pytest.fixture
def synonym_index():
    """A pre-populated synonym index."""
    idx = SynonymIndex()
    # Measures
    idx.register("sales.revenue", ["Revenue", "rev", "total revenue", "revenue"], "measure")
    idx.register("sales.order_count", ["Order Count", "orders", "order_count"], "measure")
    idx.register("costs.total_cost", ["Total Cost", "cost", "total_cost"], "measure")
    # Dimensions
    idx.register("date", ["Date", "date"], "dimension")
    idx.register("region", ["Region", "region"], "dimension")
    idx.register("product", ["Product", "product"], "dimension")
    idx.register("channel", ["Channel", "channel"], "dimension")
    return idx


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
def sample_graph(sample_measures, sample_dimensions, synonym_index):
    """A SemanticGraph built from fixtures (no warehouse)."""
    return SemanticGraph(
        measures=sample_measures,
        dimensions=sample_dimensions,
        view_measures={
            "catalog.schema.sales": ["sales.revenue", "sales.order_count"],
            "catalog.schema.costs": ["costs.total_cost"],
        },
        view_dimensions={
            "catalog.schema.sales": ["date", "region", "product"],
            "catalog.schema.costs": ["date", "region", "channel"],
        },
        measure_to_view={
            "sales.revenue": "catalog.schema.sales",
            "sales.order_count": "catalog.schema.sales",
            "costs.total_cost": "catalog.schema.costs",
        },
        synonym_index=synonym_index,
        warehouse=None,
    )
