# API Reference

Complete reference for all public types, methods, and exceptions in `the_semantic_layer`.

## Entry Point

### `compile()`

```python
def compile(
    host: str,
    http_path: str,
    catalog: str,
    schema: str,
    access_token: str | None = None,
) -> SemanticGraph
```

Connect to a Databricks SQL warehouse, introspect all metric views in the given schema, and return a compiled `SemanticGraph`.

| Parameter | Type | Description |
|---|---|---|
| `host` | `str` | Databricks workspace hostname |
| `http_path` | `str` | SQL warehouse HTTP path |
| `catalog` | `str` | Unity Catalog name |
| `schema` | `str` | Schema containing metric views |
| `access_token` | `str \| None` | Databricks access token. If `None`, uses default auth. |

**Returns:** `SemanticGraph` ready for queries.

**Raises:** `CompilationError` if warehouse introspection fails.

---

## SemanticGraph

The main consumer API. Created by `compile()` or `compile_from_warehouse()`.

### Discovery Methods

#### `list_measures()`

```python
def list_measures(self) -> list[dict]
```

Returns all measures as dicts with keys: `canonical_name`, `display_name`, `description`, `synonyms`, `metric_view`, `data_type`.

#### `list_dimensions()`

```python
def list_dimensions(self) -> list[dict]
```

Returns all dimensions as dicts with keys: `canonical_name`, `display_name`, `description`, `synonyms`, `data_type`, `metric_views`.

#### `get_dimensions_for_measures()`

```python
def get_dimensions_for_measures(self, measure_names: list[str]) -> list[dict]
```

Returns dimensions compatible with *all* requested measures (set intersection across their views).

| Parameter | Type | Description |
|---|---|---|
| `measure_names` | `list[str]` | Measure names (canonical, display, or synonym) |

**Returns:** List of dimension dicts with keys: `canonical_name`, `display_name`, `description`, `synonyms`, `data_type`.

**Raises:** `UnresolvedNameError` (with suggestions) if any measure name doesn't resolve.

### Query Methods

#### `query()`

```python
def query(
    self,
    measure_names: list[str],
    dimension_names: list[str],
    filters: list[FilterClause] | None = None,
    max_rows: int | None = None,
) -> QueryResult
```

Execute a semantic query against the warehouse.

| Parameter | Type | Description |
|---|---|---|
| `measure_names` | `list[str]` | Measure names to include (resolved via synonyms) |
| `dimension_names` | `list[str]` | Dimension names to group/slice by |
| `filters` | `list[FilterClause] \| None` | Optional dimension filters |
| `max_rows` | `int \| None` | Optional row limit (appends `LIMIT` to SQL) |

**Returns:** `QueryResult` with `rows`, `row_count`, and `sql`.

**Raises:**
- `UnresolvedNameError` -- name not found (with suggestions)
- `IncompatibleDimensionError` -- dimension not in intersection (with compatible list)
- `InvalidFilterError` -- filter on non-requested dimension (with valid list)
- `RuntimeError` -- no warehouse connection

#### `get_filter_values()`

```python
def get_filter_values(
    self, dimension_name: str, limit: int | None = None
) -> list[dict[str, Any]]
```

Fetch distinct values for a dimension from the warehouse.

| Parameter | Type | Description |
|---|---|---|
| `dimension_name` | `str` | Dimension name (canonical, display, or synonym) |
| `limit` | `int \| None` | Max number of values to return |

**Returns:** List of dicts with `value` and `count` keys, ordered by count descending.

**Raises:** `UnresolvedNameError`, `RuntimeError` (no warehouse).

### Traversal Methods

#### `get_node()`

```python
def get_node(self, name_or_alias: str) -> NodeResult
```

Look up a node by name or alias. Tries measure first, then dimension.

**Returns:** `NodeResult` with full description and neighbors.

**Raises:** `UnresolvedNameError` with suggestions from both kinds.

**Example:**
```python
node = graph.get_node("Revenue")
# NodeResult(kind="measure", canonical_name="sales.revenue",
#            compatible_dimensions=("date", "product", "region"), ...)

node = graph.get_node("date")
# NodeResult(kind="dimension", canonical_name="date",
#            compatible_measures=("sales.revenue", "sales.order_count", ...), ...)
```

#### `get_neighbors()`

```python
def get_neighbors(
    self, canonical_name: str, edge_type: str | None = None
) -> list[NeighborResult]
```

Return adjacent nodes in the graph.

| Parameter | Type | Description |
|---|---|---|
| `canonical_name` | `str` | Canonical name of a measure or dimension |
| `edge_type` | `str \| None` | Filter to `"measure"` or `"dimension"` only |

For a **measure** node: neighbors are its view's dimensions and other measures in the same view.
For a **dimension** node: neighbors are measures from all views containing this dimension, plus other dimensions in those views.

**Returns:** List of `NeighborResult`.

**Raises:** `UnresolvedNameError` if canonical name not found.

#### `find_path()`

```python
def find_path(self, node_a: str, node_b: str) -> PathResult
```

Describe the relationship between two nodes.

| Node types | `relationship` | `connected` when |
|---|---|---|
| measure + measure | `"joinable"` | Views share dimensions (`shared_dimensions` populated) |
| measure + dimension | `"compatible"` or `"none"` | Dimension is in the measure's view |
| dimension + dimension | `"co_occurring"` | Both appear in at least one common view (`co_occurring_views` populated) |

**Returns:** `PathResult`.

**Raises:** `UnresolvedNameError` if either name doesn't resolve.

#### `validate_combination()`

```python
def validate_combination(self, names: list[str]) -> ValidationResult
```

Pre-flight check: can these measures and dimensions be queried together?

Each name is resolved as a measure first, then dimension. Unresolvable names go into `errors`. Dimensions not in the compatible set go into `incompatible`.

**Returns:** `ValidationResult` with `valid`, `measures`, `dimensions`, `compatible_dimensions`, `incompatible`, `errors`.

**Example:**
```python
result = graph.validate_combination(["Revenue", "Total Cost", "date", "product"])
# ValidationResult(valid=False, incompatible=("product",),
#                  compatible_dimensions=("date", "region"), ...)
```

#### `list_entry_points()`

```python
def list_entry_points(
    self, category: str | None = None
) -> list[ViewSummary] | list[dict]
```

| `category` | Returns |
|---|---|
| `None` | `list[ViewSummary]` with each view's measures and dimensions |
| `"measures"` | `list[dict]` same as `list_measures()` |
| `"dimensions"` | `list[dict]` same as `list_dimensions()` |

---

## Types (`types.py`)

All types are frozen dataclasses.

### ViewDefinition

Compiler output representing a parsed metric view.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Short name (e.g., `"sales"`) |
| `fqn` | `str` | Fully qualified name (e.g., `"catalog.schema.sales"`) |
| `description` | `str` | View description |
| `measures` | `list[MeasureDefinition]` | Parsed measures |
| `dimensions` | `list[DimensionDefinition]` | Parsed dimensions |

### MeasureDefinition

A measure as extracted from YAML, before graph hydration.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Column/YAML name |
| `display_name` | `str` | Human-readable label |
| `description` | `str` | Description text |
| `data_type` | `str` | SQL data type |
| `synonyms` | `tuple[str, ...]` | Alternative names |
| `expression` | `str \| None` | YAML `expr`, introspection only |

### DimensionDefinition

A dimension as extracted from YAML, before graph hydration.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Column/YAML name |
| `display_name` | `str` | Human-readable label |
| `description` | `str` | Description text |
| `data_type` | `str` | SQL data type |
| `synonyms` | `tuple[str, ...]` | Alternative names |

### FilterClause

A resolved filter on a dimension.

| Field | Type | Description |
|---|---|---|
| `dimension` | `str` | Canonical dimension name |
| `values` | `list[str]` | Filter values. 1 = equality, N = IN clause |

### QueryPlan

Everything the query builder needs to generate SQL. Built internally by `SemanticGraph.query()`.

| Field | Type | Description |
|---|---|---|
| `measures` | `list[Measure]` | Resolved Measure objects |
| `dimensions` | `list[Dimension]` | Resolved Dimension objects |
| `filters` | `list[FilterClause]` | Resolved filters |
| `measure_to_view` | `dict[str, str]` | Measure canonical name to view FQN |
| `max_rows` | `int \| None` | Optional row limit |

### NodeResult

Full description of a graph node, returned by `get_node()`.

| Field | Type | Description |
|---|---|---|
| `kind` | `str` | `"measure"` or `"dimension"` |
| `canonical_name` | `str` | Canonical name |
| `display_name` | `str` | Human-readable label |
| `description` | `str` | Description text |
| `data_type` | `str` | SQL data type |
| `synonyms` | `tuple[str, ...]` | Alternative names |
| `metric_view` | `str \| None` | Owning view FQN (measures only) |
| `metric_views` | `tuple[str, ...]` | All containing views (dimensions only) |
| `compatible_measures` | `tuple[str, ...]` | For dimensions: measures in those views |
| `compatible_dimensions` | `tuple[str, ...]` | For measures: dims in the owning view |

### NeighborResult

Compact node reference, returned by `get_neighbors()`.

| Field | Type | Description |
|---|---|---|
| `canonical_name` | `str` | Canonical name |
| `kind` | `str` | `"measure"` or `"dimension"` |
| `display_name` | `str` | Human-readable label |

### PathResult

Relationship description, returned by `find_path()`.

| Field | Type | Description |
|---|---|---|
| `node_a` | `str` | First node name (as passed in) |
| `node_b` | `str` | Second node name (as passed in) |
| `connected` | `bool` | Whether the nodes are related |
| `relationship` | `str` | `"joinable"`, `"compatible"`, `"co_occurring"`, or `"none"` |
| `shared_dimensions` | `tuple[str, ...]` | For measure-measure: shared dims |
| `co_occurring_views` | `tuple[str, ...]` | For dimension-dimension: shared views |

### ValidationResult

Pre-flight query validation, returned by `validate_combination()`.

| Field | Type | Description |
|---|---|---|
| `valid` | `bool` | `True` if the combination can be queried |
| `measures` | `tuple[str, ...]` | Resolved measure canonical names |
| `dimensions` | `tuple[str, ...]` | Resolved dimension canonical names |
| `compatible_dimensions` | `tuple[str, ...]` | All compatible dimensions for the measures |
| `incompatible` | `tuple[str, ...]` | Dimensions that aren't compatible |
| `errors` | `tuple[str, ...]` | Unresolvable names |

### ViewSummary

View overview, returned by `list_entry_points()`.

| Field | Type | Description |
|---|---|---|
| `view` | `str` | Short view name |
| `view_fqn` | `str` | Fully qualified view name |
| `measures` | `tuple[str, ...]` | Measure canonical names in this view |
| `dimensions` | `tuple[str, ...]` | Dimension canonical names in this view |

### SemanticBackend (Protocol)

Documented contract for the compilation/execution boundary.

```python
class SemanticBackend(Protocol):
    def discover(self) -> list[ViewDefinition]: ...
    def execute(self, plan: QueryPlan) -> list[dict[str, Any]]: ...
```

---

## Models (`models.py`)

### Measure

Frozen dataclass representing a calculable metric belonging to exactly one view.

| Field | Type | Description |
|---|---|---|
| `canonical_name` | `str` | `"{view}.{column}"` lowercased |
| `column_name` | `str` | YAML `name` field (may have spaces) |
| `metric_view` | `str` | Owning view FQN |
| `display_name` | `str` | Human-readable label |
| `description` | `str` | Description text |
| `data_type` | `str` | SQL data type |
| `synonyms` | `tuple[str, ...]` | Alternative names (default `()`) |
| `expression` | `str \| None` | YAML `expr`, introspection only (default `None`) |

**Property:** `sql_name` returns backtick-quoted `column_name` for use in SQL.

### Dimension

Frozen dataclass representing a grouping/filtering column that can span multiple views.

| Field | Type | Description |
|---|---|---|
| `canonical_name` | `str` | `"{column}"` lowercased |
| `column_name` | `str` | YAML `name` field |
| `display_name` | `str` | Human-readable label |
| `description` | `str` | Description text |
| `data_type` | `str` | SQL data type |
| `synonyms` | `tuple[str, ...]` | Alternative names (default `()`) |
| `metric_views` | `tuple[str, ...]` | All views containing this dimension (default `()`) |

**Property:** `sql_name` returns backtick-quoted `column_name` for use in SQL.

### QueryResult

Frozen dataclass returned by `query()`.

| Field | Type | Default | Description |
|---|---|---|---|
| `rows` | `list[dict]` | `[]` | Query result rows |
| `row_count` | `int` | `0` | Number of rows |
| `sql` | `str` | `""` | Generated SQL (for introspection/debugging) |

---

## Errors (`errors.py`)

All exceptions inherit from `SemanticLayerError`. New fields have defaults, so existing error handling code doesn't break.

### SemanticLayerError

Base exception. No extra fields.

### UnresolvedNameError

```python
UnresolvedNameError(name: str, kind: str, *, suggestions: list[str] | None = None)
```

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | The name that failed to resolve |
| `kind` | `str` | `"measure"`, `"dimension"`, or `"measure or dimension"` |
| `suggestions` | `list[str]` | Fuzzy matches from the synonym index (default `[]`) |

**`str()` output:** `"Could not resolve measure name: 'revnue'. Did you mean: sales.revenue?"` (omits "Did you mean" if suggestions is empty).

### AmbiguousNameError

```python
AmbiguousNameError(name: str, kind: str, candidates: list[str])
```

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | The ambiguous name |
| `kind` | `str` | `"measure"` or `"dimension"` |
| `candidates` | `list[str]` | All canonical names this alias maps to |

### IncompatibleDimensionError

```python
IncompatibleDimensionError(
    dimension: str, measures: list[str],
    *, compatible_dimensions: list[str] | None = None,
)
```

| Attribute | Type | Description |
|---|---|---|
| `dimension` | `str` | The incompatible dimension |
| `measures` | `list[str]` | The requested measures |
| `compatible_dimensions` | `list[str]` | Dimensions that *are* compatible (default `[]`) |

### InvalidFilterError

```python
InvalidFilterError(dimension: str, *, valid_dimensions: list[str] | None = None)
```

| Attribute | Type | Description |
|---|---|---|
| `dimension` | `str` | The invalid filter dimension |
| `valid_dimensions` | `list[str]` | Dimensions the filter could target (default `[]`) |

### CompilationError

Raised when warehouse introspection fails. No extra fields beyond the message.

---

## GraphStore (ABC)

Abstract base class for graph storage backends. Subclass to implement a custom backend.

### Write methods (called by compiler)

```python
def add_measure(self, measure: Measure, view_fqn: str) -> None
def add_or_merge_dimension(self, dimension: Dimension, view_fqn: str) -> None
def register_synonym(self, canonical_name: str, aliases: list[str], kind: str) -> None
```

### Core read methods

```python
def all_measures(self) -> list[Measure]
def all_dimensions(self) -> list[Dimension]
def get_measure(self, canonical_name: str) -> Measure | None
def get_dimension(self, canonical_name: str) -> Dimension | None
def get_view_for_measure(self, canonical_name: str) -> str
def get_compatible_dimensions(self, measure_canonical_names: list[str]) -> set[str]
def resolve_name(self, name: str, kind: str) -> str
```

### Extended read methods

```python
def suggest_name(self, name: str, kind: str, max_results: int = 5) -> list[str]
def get_views(self) -> list[str]
def get_measures_for_view(self, view_fqn: str) -> list[str]
def get_dimensions_for_view(self, view_fqn: str) -> list[str]
```

---

## SynonymIndex

Internal name resolution engine. Not part of the public API, but useful context.

### `resolve(name, kind) -> str`

Case-insensitive, whitespace-stripped lookup. Returns canonical name.
Raises `UnresolvedNameError` or `AmbiguousNameError`.

### `suggest(name, kind, max_results=5) -> list[str]`

Fuzzy matching for near-miss lookups. Three tiers:
1. Prefix match (highest priority)
2. Substring match
3. Character set overlap > 50%

Returns deduplicated canonical names, best matches first.
