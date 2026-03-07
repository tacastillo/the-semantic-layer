"""Tests for the compiler with mocked warehouse."""

import json
from unittest.mock import MagicMock

from the_semantic_layer.compiler import compile_from_warehouse


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
