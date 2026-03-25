# The Semantic Layer

A Python library that compiles Databricks Unity Catalog metric views into a queryable semantic graph. It resolves measures and dimensions by name (canonical, display name, or synonym), validates compatibility across views, generates SQL, and executes queries.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd the-semantic-layer
uv venv
uv sync
```

Runtime dependencies: `databricks-sql-connector>=3.0.0`, `PyYAML>=6.0`.

## Quickstart

### Compile from a warehouse

```python
from the_semantic_layer import compile

graph = compile(
    host="your-workspace.cloud.databricks.com",
    http_path="/sql/1.0/warehouses/abc123",
    catalog="analytics",
    schema="gold",
    access_token="dapi...",
)
```

This connects to Databricks, introspects all metric views in the schema, and builds a `SemanticGraph`.

### Explore what's available

```python
# All measures
for m in graph.list_measures():
    print(f"{m['canonical_name']} ({m['display_name']})")

# All dimensions
for d in graph.list_dimensions():
    print(f"{d['canonical_name']} - views: {d['metric_views']}")

# Dimensions compatible with specific measures
dims = graph.get_dimensions_for_measures(["Revenue", "Total Cost"])
```

### Query

```python
from the_semantic_layer import FilterClause

result = graph.query(
    measure_names=["Revenue", "Order Count"],
    dimension_names=["date", "region"],
    filters=[
        FilterClause(dimension="region", values=["US", "EU"]),
    ],
    max_rows=1000,
)

print(result.sql)        # generated SQL
print(result.row_count)  # number of rows
for row in result.rows:
    print(row)
```

Names are resolved through synonyms. `"Revenue"`, `"rev"`, `"total revenue"`, and `"sales.revenue"` all resolve to the same measure.

### Explore the graph

```python
# Full node description with neighbors
node = graph.get_node("Revenue")
print(node.kind)                   # "measure"
print(node.compatible_dimensions)  # ("date", "product", "region")

# Check if two nodes can be queried together
path = graph.find_path("sales.revenue", "costs.total_cost")
print(path.connected)          # True
print(path.shared_dimensions)  # ("date", "region")

# Pre-flight validation
result = graph.validate_combination(["Revenue", "Total Cost", "date", "product"])
print(result.valid)         # False
print(result.incompatible)  # ("product",) -- not shared across both views
```

### Handle errors gracefully

```python
from the_semantic_layer import UnresolvedNameError

try:
    graph.get_dimensions_for_measures(["revnue"])  # typo
except UnresolvedNameError as e:
    print(e.suggestions)  # ["sales.revenue"]
    print(e)  # "Could not resolve measure name: 'revnue'. Did you mean: sales.revenue?"
```

## Key Concepts

### Canonical names

Every measure and dimension has a canonical name used as its unique identifier.

- **Measures**: `{view_short_name}.{column_name}` lowercased. Example: `"sales.revenue"`, `"orders.total revenue"`.
- **Dimensions**: `{column_name}` lowercased. Example: `"date"`, `"order month"`. Dimensions are shared across views by name identity.

### Dimension compatibility

When querying measures from multiple views, only dimensions present in *all* involved views are valid. The library computes this as a set intersection and raises `IncompatibleDimensionError` (with the compatible set attached) if you request an incompatible dimension.

### FilterClause

Filters use `FilterClause` objects:

```python
# Single value -> generates: WHERE `region` = %s
FilterClause(dimension="region", values=["US"])

# Multiple values -> generates: WHERE `region` IN (%s, %s, %s)
FilterClause(dimension="region", values=["US", "EU", "APAC"])
```

All filter values use bind parameters for safety.

### Multi-view queries

When measures span multiple views, the library generates CTE-based SQL with INNER JOINs on shared dimensions. This is transparent to the caller.

## Project Structure

```
src/the_semantic_layer/
├── __init__.py          # public API and compile() entry point
├── models.py            # Measure, Dimension, QueryResult
├── types.py             # ViewDefinition, QueryPlan, FilterClause, traversal types
├── errors.py            # exception hierarchy with suggestion fields
├── compilation/
│   ├── compiler.py      # warehouse introspection, ViewDefinition, store hydration
│   ├── warehouse.py     # Databricks SQL connector (sole I/O boundary)
│   └── yaml_parser.py   # metric view YAML parsing with column fallback
└── graph/
    ├── store.py          # GraphStore ABC + InMemoryGraphStore
    ├── synonym_index.py  # name resolution + fuzzy suggestion
    ├── semantic_graph.py # SemanticGraph (query, traversal, filter values)
    └── query_builder.py  # SQL generation from QueryPlan
```

For architecture details, see [docs/architecture.md](docs/architecture.md).
For the complete API reference, see [docs/api-reference.md](docs/api-reference.md).

## Development

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run ty check src/
```

Tests mock the Databricks connection entirely via `FakeWarehouse` in `conftest.py`. No live warehouse needed.
