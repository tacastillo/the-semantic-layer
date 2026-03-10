"""Core data models for the Semantic Layer."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Measure:
    """A calculable metric belonging to exactly one metric view."""

    canonical_name: str
    column_name: str  # YAML `name` field — the column name in the metric view
    metric_view: str
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...] = ()
    expression: str | None = None  # YAML `expr` — informational only, not used in SQL

    @property
    def sql_name(self) -> str:
        """Backtick-quoted column name for safe use in Databricks SQL."""
        return f"`{self.column_name}`"


@dataclass(frozen=True)
class Dimension:
    """A way to slice, filter, or group measurements. Can span multiple metric views."""

    canonical_name: str
    column_name: str  # YAML `name` field — the column name in the metric view
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...] = ()
    metric_views: tuple[str, ...] = ()

    @property
    def sql_name(self) -> str:
        """Backtick-quoted column name for safe use in Databricks SQL."""
        return f"`{self.column_name}`"


@dataclass(frozen=True)
class QueryResult:
    """The result of a query execution."""

    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    sql: str = ""
