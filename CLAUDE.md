# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Uses [uv](https://docs.astral.sh/uv/) for environment management. Install uv first: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Dev dependencies use PEP 735 dependency groups — `uv run` installs them automatically, no `--extra` needed.

Run all tests:
```bash
uv run pytest
```

Run a single test file or test:
```bash
uv run pytest tests/test_graph.py
uv run pytest tests/test_query_builder.py::TestSingleViewQuery::test_basic_select
```

Lint (ruff) and type-check (ty):
```bash
uv run ruff check src/
uv run ty check src/
```

Format:
```bash
uv run ruff format src/ tests/
```

## Architecture

This library compiles Unity Catalog metric views from a Databricks SQL warehouse into a graph, then lets callers query measures and dimensions using resolved names (canonical, display name, or synonym).

### Package structure

```
src/the_semantic_layer/
├── __init__.py          # public API: compile(), SemanticGraph, GraphStore, models, errors
├── models.py            # Measure, Dimension, QueryResult (frozen dataclasses)
├── errors.py            # exception hierarchy
├── compilation/         # Databricks → graph  (swap this layer to change backing store)
│   ├── compiler.py      # orchestrates introspection and populates the graph store
│   ├── warehouse.py     # Databricks SQL connector (sole I/O boundary)
│   └── yaml_parser.py   # parses metric view YAML; heuristic fallback on columns only
└── graph/               # runtime graph + query  (backing-store-agnostic)
    ├── store.py          # GraphStore ABC + InMemoryGraphStore
    ├── synonym_index.py  # case-insensitive alias → canonical name registry
    ├── semantic_graph.py # SemanticGraph consumer API
    └── query_builder.py  # SQL generation (single-view and multi-view CTE)
```

### Data flow

1. **`compile()`** (`__init__.py`) — entry point. Creates a `WarehouseConnection` and calls `compile_from_warehouse()`.
2. **`compilation/compiler.py`** — lists tables, filters to metric views (`language=YAML`), parses each view into the `GraphStore`.
3. **`compilation/yaml_parser.py`** — parses each view's YAML (`expr`, `comment`, `display_name`, `synonyms`). Falls back to column type heuristics when YAML is unavailable.
4. **`graph/store.py`** — `GraphStore` ABC with `InMemoryGraphStore` as the default. Handles dimension merging across views. Swap for pickle or graph DB backends.
5. **`graph/semantic_graph.py`** — consumer-facing API: `list_measures()`, `get_dimensions_for_measures()`, `query()`.

### Key design decisions

**Canonical names** for measures: `{view_short_name}.{yaml_name}`.lower() (e.g., `orders.total revenue`). For dimensions: `{yaml_name}`.lower() — dimensions are shared across views by name identity.

**`Measure.column_name` / `Dimension.column_name`** stores the YAML `name` field (may contain spaces, e.g. `"Order Month"`). Use `.sql_name` property for backtick-quoted SQL identifiers.

**`Measure.expression`** stores the YAML `expr` for introspection only — never emitted in SQL. Metric views pre-define aggregation; querying just selects by column name.

**Dimension compatibility** is set intersection across all views involved. Multi-view queries use CTE + INNER JOIN on shared dimension columns.

**`GraphStore`** is injectable — `compile_from_warehouse(warehouse, store=MyStore())` accepts any backend. Default is `InMemoryGraphStore` (dict-based). Pickle it for faster cold starts; implement `GraphStore` ABC for Neo4j/PuppyGraph.

**`WarehouseConnection`** is the sole I/O boundary. Tests mock it entirely — no Databricks connection needed to run tests.

### Databricks metric view YAML field names (spec v1.1)

- `expr` — SQL expression (NOT `expression`)
- `comment` — description text (NOT `description`)
- `display_name`, `synonyms`, `format` — semantic metadata
- Top-level: `source`, `filter`, `joins`, `version`
