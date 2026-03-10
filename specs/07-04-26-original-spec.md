# The Semantic Layer

## What It Is

The Semantic Layer is a compiled graph of measures, dimensions, and their compatibility relationships. It gives any consumer a clear API for answering: what measures are available, what dimensions are compatible with a given set of measures, and give me the data for this combination.

The backing definitions today are Unity Catalog metric views. They're a good primitive. The Semantic Layer reads their definitions, compiles them into a unified graph, and exposes that graph through a consumer-agnostic API. If the backing primitive changes, only the compilation step changes. The API stays the same.

## Core Concepts

**Measures** are the things that can be calculated. Each measure has a canonical name, description, display name, synonyms, and belongs to exactly one metric view.

**Dimensions** are the ways measurements can be sliced, filtered, or grouped. A dimension can appear in multiple metric views. The Semantic Layer tracks which metric views carry each dimension.

**Compatibility** is the relationship between measures and dimensions. Not every dimension works with every measure. When a consumer requests measures that span multiple metric views, only the dimensions present in all involved metric views are valid. The Semantic Layer computes this intersection.

**Synonyms** are alternative names that resolve to canonical measure or dimension names. They come from the semantic metadata in metric view YAML definitions (display names, synonym lists) and are indexed at compilation time. Name resolution is case-insensitive and works transparently anywhere a measure or dimension name is accepted.

## API

The Semantic Layer exposes a structured API over the compiled graph, designed for programmatic consumers: agent tool calls, application code, notebooks. Three operations:

#### list_measures() → list of measures

Returns every measure the Semantic Layer knows about. Each entry includes the canonical name, description, display name, and synonyms. No arguments. No filtering. This is the "what can I ask about?" entry point.

### get_dimensions_for_measures(measure_names) → list of dimensions

Takes one or more measure names (canonical names, display names, or synonyms all accepted). Returns the dimensions that are valid for slicing across all of the requested measures. This is the intersection: only dimensions that appear in every metric view involved are returned. Each entry includes the canonical name, description, display name, and synonyms.

Raises an error if any measure name can't be resolved after synonym lookup. All names must resolve; partial resolution is not accepted.

### query(measure_names, dimension_names, filters?) → result set + generated SQL

Takes measure names, dimension names, and an optional set of filters (dimension name to value pairs). All names are resolved through the synonym index. The Semantic Layer validates that the combination is valid, composes the query (single metric view or CTE composition for multi-metric-view requests), executes it, and returns the rows along with the row count and the generated SQL.

This is the only way to get data out of the Semantic Layer. The consumer specifies what they want in logical terms; the Semantic Layer handles everything physical.

Raises an error if a measure or dimension name can't be resolved after synonym lookup.

## What It Does Not Do

It does not own metric definitions. Definitions live in the backing store (currently Unity Catalog metric views). The Semantic Layer reads them; it never writes them.

It does not interpret questions. It does not decide which measures or dimensions are relevant to a natural language question. That's the consumer's job.

It does not enforce access control. The backing store handles permissions. The Semantic Layer sees whatever the connection has access to.

## Compilation

Compilation is the process of reading the backing definitions and building the graph. This is the only component that is specific to the underlying primitive. Swapping the backing store means writing a new compilation step; everything else stays the same.

### Staleness and recompilation

The compiled graph is built once at startup and held in memory. There is no hot reloading. If metric view definitions change in Unity Catalog, the Semantic Layer must be restarted to pick up those changes. This is an acceptable tradeoff for this iteration: metric views change infrequently, and a future version will persist the compiled graph to durable state, enabling smarter invalidation and reload strategies without a full restart.

### Current implementation: Unity Catalog metric views

The Semantic Layer connects to a SQL warehouse and introspects all metric views in a given catalog and schema. For each metric view, it retrieves the JSON output from DESCRIBE TABLE EXTENDED AS JSON, which contains both the column metadata (names, types, is_measure flag) and the full YAML definition in the view_text field (expressions, comments, display names, synonyms, format specs, source, filters, joins).

It parses both, cross-references them, and builds the graph: measures, dimensions, synonym indexes, and compatibility mappings.

If the YAML is unavailable, it falls back to column metadata only (names, types, measure/dimension classification, but no synonyms or display names).

## Known Constraints

These are real-world cases we're acknowledging but not addressing in this iteration.

**Dimension name collisions.** When two metric views define a dimension with the same canonical name, the Semantic Layer treats them as the same logical dimension. This is correct when the definitions are well-governed. If two metric views use "Month" to mean different things, the Semantic Layer will incorrectly treat them as joinable. This is a governance problem that will surface here first.

**Inner join behavior on multi-metric-view queries.** CTEs are joined with INNER JOIN. If one metric view has data for 12 months and another has 10, the result contains 10 rows. No warning is surfaced automatically.

**Single-value equality filters only.** Filters are dimension-name-to-value string pairs. No range filters, no IN clauses, no inequality operators. Consumers needing these must handle post-retrieval filtering or the interface must be extended.

**Discovery round trips at compilation.** Identifying metric views requires describing each view in the schema to check for Language = YAML. For schemas with many non-metric views, this is slow.

## Evolution Path

The immediate implementation is dict-based. The natural next step is a proper graph structure where measures and dimensions are nodes, compatibility is edges, and graph traversal enables richer queries: what measures are reachable from this dimension, what's the shortest path between two measures through shared dimensions, what measure/dimension combinations are most commonly used together.

The consumer-facing API should remain stable through this evolution. The underlying data structure changes; the contract doesn't.