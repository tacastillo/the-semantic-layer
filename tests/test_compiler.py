"""Tests for the compiler with mocked warehouse."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from the_semantic_layer.compilation import compile_from_warehouse
from the_semantic_layer.compilation.compiler import _compile_view, _hydrate_store
from the_semantic_layer.graph.store import InMemoryGraphStore

FIXTURES = Path(__file__).parent / "fixtures"


def _make_metric_view_metadata(view_name, yaml_text, columns):
    """Build a mock DESCRIBE TABLE EXTENDED AS JSON response."""
    return {
        "language": "YAML",
        "view_text": yaml_text,
        "columns": columns,
    }


class TestCompiler:
    def test_compiles_single_metric_view(self):
        warehouse = MagicMock()
        warehouse.list_tables.return_value = ["cat.sch.sales"]
        warehouse.describe_view.return_value = _make_metric_view_metadata(
            "sales",
            yaml_text="""
measures:
  - name: revenue
    display_name: Revenue
    description: Total revenue
    synonyms:
      - rev
dimensions:
  - name: date
    display_name: Date
    description: Transaction date
  - name: region
    display_name: Region
""",
            columns=[
                {"name": "revenue", "type": "DOUBLE", "comment": "Total revenue"},
                {"name": "date", "type": "DATE", "comment": ""},
                {"name": "region", "type": "STRING", "comment": ""},
            ],
        )

        graph = compile_from_warehouse(warehouse)
        measures = graph.list_measures()
        assert len(measures) == 1
        assert measures[0]["canonical_name"] == "sales.revenue"
        assert measures[0]["display_name"] == "Revenue"

        dims = graph.get_dimensions_for_measures(["Revenue"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region"}

    def test_compiles_multiple_views_with_shared_dims(self):
        warehouse = MagicMock()
        warehouse.list_tables.return_value = ["cat.sch.sales", "cat.sch.costs"]

        sales_meta = _make_metric_view_metadata(
            "sales",
            yaml_text="""
measures:
  - name: revenue
    display_name: Revenue
dimensions:
  - name: date
  - name: region
  - name: product
""",
            columns=[
                {"name": "revenue", "type": "DOUBLE", "comment": ""},
                {"name": "date", "type": "DATE", "comment": ""},
                {"name": "region", "type": "STRING", "comment": ""},
                {"name": "product", "type": "STRING", "comment": ""},
            ],
        )
        costs_meta = _make_metric_view_metadata(
            "costs",
            yaml_text="""
measures:
  - name: total_cost
    display_name: Total Cost
dimensions:
  - name: date
  - name: region
  - name: channel
""",
            columns=[
                {"name": "total_cost", "type": "DOUBLE", "comment": ""},
                {"name": "date", "type": "DATE", "comment": ""},
                {"name": "region", "type": "STRING", "comment": ""},
                {"name": "channel", "type": "STRING", "comment": ""},
            ],
        )

        warehouse.describe_view.side_effect = lambda fqn: {
            "cat.sch.sales": sales_meta,
            "cat.sch.costs": costs_meta,
        }[fqn]

        graph = compile_from_warehouse(warehouse)

        # Cross-view dimension intersection
        dims = graph.get_dimensions_for_measures(["Revenue", "Total Cost"])
        dim_names = {d["canonical_name"] for d in dims}
        assert dim_names == {"date", "region"}

    def test_skips_non_metric_views(self):
        warehouse = MagicMock()
        warehouse.list_tables.return_value = ["cat.sch.regular_table", "cat.sch.sales"]

        warehouse.describe_view.side_effect = lambda fqn: {
            "cat.sch.regular_table": {"columns": [{"name": "id", "type": "INT"}]},
            "cat.sch.sales": _make_metric_view_metadata(
                "sales",
                yaml_text="measures:\n  - name: revenue\ndimensions:\n  - name: date",
                columns=[
                    {"name": "revenue", "type": "DOUBLE", "comment": ""},
                    {"name": "date", "type": "DATE", "comment": ""},
                ],
            ),
        }[fqn]

        graph = compile_from_warehouse(warehouse)
        measures = graph.list_measures()
        assert len(measures) == 1
        assert measures[0]["canonical_name"] == "sales.revenue"

    def test_compiles_from_describe_table_fixture(self):
        """Compile from a realistic DESCRIBE TABLE EXTENDED AS JSON fixture."""
        metadata = json.loads((FIXTURES / "describe_orders_metric_view.json").read_text())
        warehouse = MagicMock()
        warehouse.list_tables.return_value = ["samples.tpch.orders_metric_view"]
        warehouse.describe_view.return_value = metadata

        graph = compile_from_warehouse(warehouse)
        measures = graph.list_measures()
        assert len(measures) == 3

        names = {m["canonical_name"] for m in measures}
        assert "orders_metric_view.order count" in names
        assert "orders_metric_view.total revenue" in names
        assert "orders_metric_view.total revenue per customer" in names

        dims = graph.get_dimensions_for_measures(["orders_metric_view.order count"])
        dim_names = {d["canonical_name"] for d in dims}
        assert "order month" in dim_names
        assert "order status" in dim_names
        assert "order priority" in dim_names

    def test_compiles_semantic_metadata_fixture(self):
        """Compile from a fixture with display_name, synonyms, and expr fields."""
        metadata = json.loads((FIXTURES / "describe_orders_semantic.json").read_text())
        warehouse = MagicMock()
        warehouse.list_tables.return_value = ["samples.tpch.orders_semantic"]
        warehouse.describe_view.return_value = metadata

        graph = compile_from_warehouse(warehouse)
        measures = graph.list_measures()

        rev = next(m for m in measures if "revenue" in m["canonical_name"])
        assert rev["display_name"] == "Total Revenue"
        assert "revenue" in rev["synonyms"]

        # Synonyms resolve correctly
        dims = graph.get_dimensions_for_measures(["revenue"])
        assert any(d["canonical_name"] == "order_date" for d in dims)

        # Dimension synonym resolution
        dims2 = graph.get_dimensions_for_measures(["order count"])
        assert any(d["canonical_name"] == "order_date" for d in dims2)

    def test_fallback_without_yaml(self):
        warehouse = MagicMock()
        warehouse.list_tables.return_value = ["cat.sch.metrics"]
        warehouse.describe_view.return_value = {
            "language": "YAML",
            "columns": [
                {"name": "amount", "type": "DOUBLE", "comment": ""},
                {"name": "month", "type": "STRING", "comment": ""},
            ],
        }

        graph = compile_from_warehouse(warehouse)
        measures = graph.list_measures()
        dims = graph.get_dimensions_for_measures([measures[0]["canonical_name"]])
        assert len(measures) == 1
        assert measures[0]["canonical_name"] == "metrics.amount"
        assert len(dims) == 1


class TestCompileView:
    def test_returns_view_definition(self):
        metadata = _make_metric_view_metadata(
            "sales",
            yaml_text="""
measures:
  - name: revenue
    display_name: Revenue
    synonyms:
      - rev
dimensions:
  - name: date
    display_name: Date
""",
            columns=[
                {"name": "revenue", "type": "DOUBLE", "comment": ""},
                {"name": "date", "type": "DATE", "comment": ""},
            ],
        )
        view_def = _compile_view("cat.sch.sales", metadata)
        assert view_def.name == "sales"
        assert view_def.fqn == "cat.sch.sales"
        assert len(view_def.measures) == 1
        assert view_def.measures[0].name == "revenue"
        assert view_def.measures[0].display_name == "Revenue"
        assert view_def.measures[0].synonyms == ("rev",)
        assert len(view_def.dimensions) == 1
        assert view_def.dimensions[0].name == "date"


class TestHydrateStore:
    def test_populates_store_from_view_definitions(self):
        metadata = _make_metric_view_metadata(
            "sales",
            yaml_text="""
measures:
  - name: revenue
    display_name: Revenue
dimensions:
  - name: date
  - name: region
""",
            columns=[
                {"name": "revenue", "type": "DOUBLE", "comment": ""},
                {"name": "date", "type": "DATE", "comment": ""},
                {"name": "region", "type": "STRING", "comment": ""},
            ],
        )
        view_def = _compile_view("cat.sch.sales", metadata)
        store = InMemoryGraphStore()
        _hydrate_store(store, [view_def])

        assert len(store.all_measures()) == 1
        assert store.get_measure("sales.revenue") is not None
        assert store.get_dimension("date") is not None
        assert store.get_dimension("region") is not None
        assert store.resolve_name("Revenue", "measure") == "sales.revenue"
