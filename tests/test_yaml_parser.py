"""Tests for YAML definition parsing."""

from pathlib import Path

from the_semantic_layer.compilation.yaml_parser import (
    parse_from_columns_only,
    parse_metric_view_yaml,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseMetricViewYaml:
    def test_explicit_measures_and_dimensions(self):
        # Uses real Databricks YAML field names: expr (not expression), comment (not description)
        yaml_text = """
measures:
  - name: revenue
    display_name: Revenue
    comment: Total revenue in dollars
    synonyms:
      - rev
      - total revenue
    expr: SUM(amount)
  - name: order_count
    display_name: Order Count
    comment: Number of orders
dimensions:
  - name: date
    display_name: Date
    comment: Transaction date
  - name: region
    display_name: Region
source: catalog.schema.raw_sales
"""
        columns = [
            {"name": "revenue", "type": "DOUBLE", "comment": ""},
            {"name": "order_count", "type": "BIGINT", "comment": ""},
            {"name": "date", "type": "DATE", "comment": ""},
            {"name": "region", "type": "STRING", "comment": ""},
        ]
        result = parse_metric_view_yaml(yaml_text, columns)
        assert len(result["measures"]) == 2
        assert len(result["dimensions"]) == 2
        assert result["source"] == "catalog.schema.raw_sales"

        rev = result["measures"][0]
        assert rev["name"] == "revenue"
        assert rev["display_name"] == "Revenue"
        assert rev["synonyms"] == ("rev", "total revenue")
        assert rev["expression"] == "SUM(amount)"
        assert rev["data_type"] == "DOUBLE"

    def test_orders_metric_view_fixture(self):
        """Parse the real-world orders fixture (names with spaces, no semantic metadata)."""
        yaml_text = (FIXTURES / "orders_metric_view.yaml").read_text()
        columns = [
            {"name": "Order Month", "type": "DATE", "nullable": True, "comment": ""},
            {"name": "Order Status", "type": "STRING", "nullable": True, "comment": ""},
            {"name": "Order Priority", "type": "STRING", "nullable": True, "comment": ""},
            {"name": "Order Count", "type": "BIGINT", "nullable": True, "comment": ""},
            {"name": "Total Revenue", "type": "DOUBLE", "nullable": True, "comment": ""},
            {"name": "Total Revenue per Customer", "type": "DOUBLE", "nullable": True, "comment": ""},
        ]
        result = parse_metric_view_yaml(yaml_text, columns)
        assert len(result["measures"]) == 3
        assert len(result["dimensions"]) == 3
        assert result["source"] == "samples.tpch.orders"

        names = {m["name"] for m in result["measures"]}
        assert names == {"Order Count", "Total Revenue", "Total Revenue per Customer"}

        dim_names = {d["name"] for d in result["dimensions"]}
        assert dim_names == {"Order Month", "Order Status", "Order Priority"}

        # expr is parsed correctly
        total_rev = next(m for m in result["measures"] if m["name"] == "Total Revenue")
        assert total_rev["expression"] == "SUM(o_totalprice)"

    def test_orders_semantic_metadata_fixture(self):
        """Parse the semantic metadata fixture (display_name, synonyms, comment, expr)."""
        yaml_text = (FIXTURES / "orders_semantic_metadata.yaml").read_text()
        columns = [
            {"name": "order_date", "type": "DATE", "comment": "Date when the order was placed"},
            {"name": "customer_segment", "type": "STRING", "comment": "Customer classification"},
            {"name": "total_revenue", "type": "DOUBLE", "comment": "Total revenue from all orders"},
            {"name": "order_count", "type": "BIGINT", "comment": "Total number of orders"},
        ]
        result = parse_metric_view_yaml(yaml_text, columns)
        assert len(result["measures"]) == 2
        assert len(result["dimensions"]) == 2

        rev = next(m for m in result["measures"] if m["name"] == "total_revenue")
        assert rev["display_name"] == "Total Revenue"
        assert rev["description"] == "Total revenue from all orders"
        assert rev["expression"] == "SUM(o_totalprice)"
        assert "revenue" in rev["synonyms"]
        assert "total sales" in rev["synonyms"]

        date_dim = next(d for d in result["dimensions"] if d["name"] == "order_date")
        assert date_dim["display_name"] == "Order Date"
        assert "order time" in date_dim["synonyms"]

    def test_string_measures(self):
        """Measures listed as plain strings (just column names)."""
        yaml_text = """
measures:
  - revenue
  - order_count
dimensions:
  - date
"""
        columns = [
            {"name": "revenue", "type": "DOUBLE", "comment": ""},
            {"name": "order_count", "type": "BIGINT", "comment": ""},
            {"name": "date", "type": "DATE", "comment": ""},
        ]
        result = parse_metric_view_yaml(yaml_text, columns)
        assert len(result["measures"]) == 2
        assert result["measures"][0]["name"] == "revenue"

    def test_invalid_yaml_falls_back(self):
        result = parse_metric_view_yaml(
            "{{invalid yaml",
            [{"name": "amount", "type": "DOUBLE", "comment": ""}],
        )
        assert len(result["measures"]) == 1
        assert result["measures"][0]["name"] == "amount"

    def test_non_dict_yaml_falls_back(self):
        result = parse_metric_view_yaml(
            "- just a list",
            [{"name": "amount", "type": "DOUBLE", "comment": ""}],
        )
        assert len(result["measures"]) == 1

    def test_synonym_as_string(self):
        yaml_text = """
measures:
  - name: revenue
    expr: SUM(amount)
    synonyms: rev
dimensions: []
"""
        columns = [{"name": "revenue", "type": "DOUBLE", "comment": ""}]
        result = parse_metric_view_yaml(yaml_text, columns)
        assert result["measures"][0]["synonyms"] == ("rev",)


class TestFallbackFromColumns:
    def test_numeric_columns_become_measures(self):
        columns = [
            {"name": "revenue", "type": "DOUBLE", "comment": ""},
            {"name": "cost", "type": "DECIMAL(10,2)", "comment": ""},
            {"name": "date", "type": "DATE", "comment": ""},
            {"name": "region", "type": "STRING", "comment": ""},
        ]
        result = parse_from_columns_only(columns)
        measure_names = {m["name"] for m in result["measures"]}
        dim_names = {d["name"] for d in result["dimensions"]}
        assert measure_names == {"revenue", "cost"}
        assert dim_names == {"date", "region"}

    def test_id_columns_are_dimensions(self):
        columns = [
            {"name": "customer_id", "type": "BIGINT", "comment": ""},
            {"name": "amount", "type": "DOUBLE", "comment": ""},
        ]
        result = parse_from_columns_only(columns)
        assert result["dimensions"][0]["name"] == "customer_id"
        assert result["measures"][0]["name"] == "amount"

    def test_timestamp_columns_are_dimensions(self):
        columns = [
            {"name": "created_timestamp", "type": "BIGINT", "comment": ""},
            {"name": "value", "type": "INT", "comment": ""},
        ]
        result = parse_from_columns_only(columns)
        dim_names = {d["name"] for d in result["dimensions"]}
        assert "created_timestamp" in dim_names
