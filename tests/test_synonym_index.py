"""Tests for the SynonymIndex."""

import pytest

from the_semantic_layer.errors import AmbiguousNameError, UnresolvedNameError
from the_semantic_layer.graph.synonym_index import SynonymIndex


class TestSynonymIndex:
    def test_resolve_canonical_name(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["Revenue"], "measure")
        assert idx.resolve("sales.revenue", "measure") == "sales.revenue"

    def test_resolve_alias(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["Revenue", "rev"], "measure")
        assert idx.resolve("Revenue", "measure") == "sales.revenue"
        assert idx.resolve("rev", "measure") == "sales.revenue"

    def test_case_insensitive(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["Revenue"], "measure")
        assert idx.resolve("REVENUE", "measure") == "sales.revenue"
        assert idx.resolve("revenue", "measure") == "sales.revenue"
        assert idx.resolve("SALES.REVENUE", "measure") == "sales.revenue"

    def test_whitespace_stripped(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["Revenue"], "measure")
        assert idx.resolve("  Revenue  ", "measure") == "sales.revenue"

    def test_unresolved_raises(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["Revenue"], "measure")
        with pytest.raises(UnresolvedNameError) as exc_info:
            idx.resolve("nonexistent", "measure")
        assert exc_info.value.name == "nonexistent"
        assert exc_info.value.kind == "measure"

    def test_ambiguous_raises(self):
        idx = SynonymIndex()
        # Two measures with the same bare column name
        idx.register("view_a.revenue", ["revenue"], "measure")
        idx.register("view_b.revenue", ["revenue"], "measure")
        with pytest.raises(AmbiguousNameError) as exc_info:
            idx.resolve("revenue", "measure")
        assert set(exc_info.value.candidates) == {"view_a.revenue", "view_b.revenue"}

    def test_kind_separation(self):
        """Same alias for different kinds should not collide."""
        idx = SynonymIndex()
        idx.register("sales.date", ["date"], "measure")
        idx.register("date", ["date"], "dimension")
        assert idx.resolve("date", "measure") == "sales.date"
        assert idx.resolve("date", "dimension") == "date"

    def test_empty_alias_skipped(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["", "Revenue"], "measure")
        assert idx.resolve("Revenue", "measure") == "sales.revenue"

    def test_unresolved_wrong_kind(self):
        idx = SynonymIndex()
        idx.register("sales.revenue", ["Revenue"], "measure")
        with pytest.raises(UnresolvedNameError):
            idx.resolve("Revenue", "dimension")
