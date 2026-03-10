"""Abstract interface and in-memory implementation for semantic graph storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

from the_semantic_layer.graph.synonym_index import SynonymIndex
from the_semantic_layer.models import Dimension, Measure


class GraphStore(ABC):
    """Storage and query backend for the compiled semantic graph.

    The compiler writes into a store; SemanticGraph reads from it.
    Swap implementations to change persistence strategy without touching
    compilation or query logic.
    """

    # --- Write (called by compiler) ---

    @abstractmethod
    def add_measure(self, measure: Measure, view_fqn: str) -> None:
        """Register a measure and its source view."""

    @abstractmethod
    def add_or_merge_dimension(self, dimension: Dimension, view_fqn: str) -> None:
        """Register a dimension, merging with any existing entry of the same canonical name."""

    @abstractmethod
    def register_synonym(self, canonical_name: str, aliases: list[str], kind: str) -> None:
        """Register name aliases for a measure or dimension."""

    # --- Read (called by SemanticGraph) ---

    @abstractmethod
    def all_measures(self) -> list[Measure]:
        """Return all known measures."""

    @abstractmethod
    def get_measure(self, canonical_name: str) -> Measure | None:
        """Return a measure by canonical name."""

    @abstractmethod
    def get_dimension(self, canonical_name: str) -> Dimension | None:
        """Return a dimension by canonical name."""

    @abstractmethod
    def get_view_for_measure(self, canonical_name: str) -> str:
        """Return the metric view FQN that owns this measure."""

    @abstractmethod
    def get_compatible_dimensions(self, measure_canonical_names: list[str]) -> set[str]:
        """Return canonical dimension names present in every view of the given measures."""

    @abstractmethod
    def resolve_name(self, name: str, kind: str) -> str:
        """Resolve an alias to its canonical name. Raises on miss or ambiguity."""


class InMemoryGraphStore(GraphStore):
    """Dict-based graph store. Built once at startup, held in memory.

    This is the default backend. It can be serialized with pickle for
    faster cold starts, or replaced entirely with a graph database backend.
    """

    def __init__(self) -> None:
        self._measures: dict[str, Measure] = {}
        self._dimensions: dict[str, Dimension] = {}
        self._measure_to_view: dict[str, str] = {}
        self._view_measures: dict[str, list[str]] = {}
        self._view_dimensions: dict[str, list[str]] = {}
        self._synonym_index = SynonymIndex()

    def add_measure(self, measure: Measure, view_fqn: str) -> None:
        self._measures[measure.canonical_name] = measure
        self._measure_to_view[measure.canonical_name] = view_fqn
        self._view_measures.setdefault(view_fqn, []).append(measure.canonical_name)

    def add_or_merge_dimension(self, dimension: Dimension, view_fqn: str) -> None:
        canonical = dimension.canonical_name
        if canonical in self._dimensions:
            existing = self._dimensions[canonical]
            dimension = Dimension(
                canonical_name=canonical,
                column_name=existing.column_name,
                display_name=existing.display_name,
                description=existing.description or dimension.description,
                data_type=existing.data_type or dimension.data_type,
                synonyms=tuple(set(existing.synonyms) | set(dimension.synonyms)),
                metric_views=tuple(set(existing.metric_views) | {view_fqn}),
            )
        self._dimensions[canonical] = dimension
        self._view_dimensions.setdefault(view_fqn, []).append(canonical)
        # Always re-register so synonyms from later views are indexed (additive, idempotent).
        self._synonym_index.register(
            canonical,
            [dimension.display_name, dimension.column_name, *dimension.synonyms],
            "dimension",
        )

    def register_synonym(self, canonical_name: str, aliases: list[str], kind: str) -> None:
        self._synonym_index.register(canonical_name, aliases, kind)

    def all_measures(self) -> list[Measure]:
        return list(self._measures.values())

    def get_measure(self, canonical_name: str) -> Measure | None:
        return self._measures.get(canonical_name)

    def get_dimension(self, canonical_name: str) -> Dimension | None:
        return self._dimensions.get(canonical_name)

    def get_view_for_measure(self, canonical_name: str) -> str:
        return self._measure_to_view[canonical_name]

    def get_compatible_dimensions(self, measure_canonical_names: list[str]) -> set[str]:
        involved_views = {self._measure_to_view[cn] for cn in measure_canonical_names}
        dim_sets = [set(self._view_dimensions.get(view_fqn, [])) for view_fqn in involved_views]
        return set.intersection(*dim_sets) if dim_sets else set()

    def resolve_name(self, name: str, kind: str) -> str:
        return self._synonym_index.resolve(name, kind)
