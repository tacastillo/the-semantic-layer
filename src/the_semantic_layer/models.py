"""Core data models for the Semantic Layer."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Measure:
    """A calculable metric belonging to exactly one metric view."""

    canonical_name: str
    column_name: str
    metric_view: str
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...] = ()
    expression: str | None = None


@dataclass(frozen=True)
class Dimension:
    """A way to slice, filter, or group measurements. Can span multiple metric views."""

    canonical_name: str
    column_name: str
    display_name: str
    description: str
    data_type: str
    synonyms: tuple[str, ...] = ()
    metric_views: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryResult:
    """The result of a query execution."""

    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    sql: str = ""
