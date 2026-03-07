"""Tests for YAML definition parsing."""

from the_semantic_layer.yaml_parser import (
    parse_from_columns_only,
    parse_metric_view_yaml,
)


class TestParseMetricViewYaml:
    def test_explicit_measures_and_dimensions(self):
        yaml_text = """
measures:
  - name: revenue
    display_name: Revenue
    description: Total revenue in dollars
    synonyms:
      - rev
      - total revenue
    expression: SUM(amount)
  - name: order_count
    display_name: Order Count
    description: Number of orders
dimensions:
  - name: date
    display_name: Date
    description: Transaction date
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
