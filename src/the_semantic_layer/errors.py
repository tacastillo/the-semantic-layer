"""Exception hierarchy for the Semantic Layer."""


class SemanticLayerError(Exception):
    """Base exception for all Semantic Layer errors."""


class UnresolvedNameError(SemanticLayerError):
    """A measure or dimension name could not be resolved."""

    def __init__(self, name: str, kind: str, *, suggestions: list[str] | None = None) -> None:
        self.name = name
        self.kind = kind
        self.suggestions = suggestions or []
        msg = f"Could not resolve {kind} name: {name!r}"
        if self.suggestions:
            msg += f". Did you mean: {', '.join(self.suggestions)}?"
        super().__init__(msg)


class AmbiguousNameError(SemanticLayerError):
    """A name resolves to multiple candidates."""

    def __init__(self, name: str, kind: str, candidates: list[str]) -> None:
        self.name = name
        self.kind = kind
        self.candidates = candidates
        super().__init__(
            f"Ambiguous {kind} name {name!r} resolves to multiple candidates: {', '.join(candidates)}"
        )


class IncompatibleDimensionError(SemanticLayerError):
    """A requested dimension is not compatible with the given measures."""

    def __init__(
        self,
        dimension: str,
        measures: list[str],
        *,
        compatible_dimensions: list[str] | None = None,
    ) -> None:
        self.dimension = dimension
        self.measures = measures
        self.compatible_dimensions = compatible_dimensions or []
        msg = f"Dimension {dimension!r} is not compatible with measures: {', '.join(measures)}"
        if self.compatible_dimensions:
            msg += f". Compatible dimensions: {', '.join(self.compatible_dimensions)}"
        super().__init__(msg)


class InvalidFilterError(SemanticLayerError):
    """A filter references a dimension that is not in the requested set."""

    def __init__(self, dimension: str, *, valid_dimensions: list[str] | None = None) -> None:
        self.dimension = dimension
        self.valid_dimensions = valid_dimensions or []
        msg = f"Filter references dimension {dimension!r} which is not in the requested dimension set"
        if self.valid_dimensions:
            msg += f". Valid filter dimensions: {', '.join(self.valid_dimensions)}"
        super().__init__(msg)


class CompilationError(SemanticLayerError):
    """An error occurred during warehouse introspection or compilation."""
