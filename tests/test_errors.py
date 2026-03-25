"""Tests for the error hierarchy with suggestion fields."""

from the_semantic_layer.errors import (
    IncompatibleDimensionError,
    InvalidFilterError,
    UnresolvedNameError,
)


class TestUnresolvedNameError:
    def test_basic_construction(self):
        err = UnresolvedNameError("revnue", "measure")
        assert err.name == "revnue"
        assert err.kind == "measure"
        assert err.suggestions == []
        assert "revnue" in str(err)
        assert "Did you mean" not in str(err)

    def test_with_suggestions(self):
        err = UnresolvedNameError(
            "revnue",
            "measure",
            suggestions=["sales.revenue", "costs.revenue"],
        )
        assert err.suggestions == ["sales.revenue", "costs.revenue"]
        assert "Did you mean" in str(err)
        assert "sales.revenue" in str(err)

    def test_empty_suggestions(self):
        err = UnresolvedNameError("x", "measure", suggestions=[])
        assert "Did you mean" not in str(err)


class TestIncompatibleDimensionError:
    def test_basic_construction(self):
        err = IncompatibleDimensionError("channel", ["sales.revenue"])
        assert err.dimension == "channel"
        assert err.measures == ["sales.revenue"]
        assert err.compatible_dimensions == []
        assert "Compatible dimensions" not in str(err)

    def test_with_compatible_dimensions(self):
        err = IncompatibleDimensionError(
            "channel",
            ["sales.revenue"],
            compatible_dimensions=["date", "region"],
        )
        assert err.compatible_dimensions == ["date", "region"]
        assert "Compatible dimensions" in str(err)
        assert "date" in str(err)

    def test_empty_compatible(self):
        err = IncompatibleDimensionError("x", ["m"], compatible_dimensions=[])
        assert "Compatible dimensions" not in str(err)


class TestInvalidFilterError:
    def test_basic_construction(self):
        err = InvalidFilterError("product")
        assert err.dimension == "product"
        assert err.valid_dimensions == []
        assert "Valid filter dimensions" not in str(err)

    def test_with_valid_dimensions(self):
        err = InvalidFilterError(
            "product",
            valid_dimensions=["date", "region"],
        )
        assert err.valid_dimensions == ["date", "region"]
        assert "Valid filter dimensions" in str(err)
        assert "date" in str(err)

    def test_empty_valid(self):
        err = InvalidFilterError("x", valid_dimensions=[])
        assert "Valid filter dimensions" not in str(err)
