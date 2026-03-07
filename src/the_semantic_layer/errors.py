"""Exception hierarchy for the Semantic Layer."""


class SemanticLayerError(Exception):
    """Base exception for all Semantic Layer errors."""


class UnresolvedNameError(SemanticLayerError):
    """A measure or dimension name could not be resolved."""

    def __init__(self, name: str, kind: str) -> None:
        self.name = name
        self.kind = kind
        super().__init__(f"Could not resolve {kind} name: {name!r}")


class AmbiguousNameError(SemanticLayerError):
    """A name resolves to multiple candidates."""

    def __init__(self, name: str, kind: str, candidates: list[str]) -> None:
        self.name = name
        self.kind = kind
        self.candidates = candidates
        super().__init__(
            f"Ambiguous {kind} name {name!r} resolves to multiple candidates: "
            f"{', '.join(candidates)}"
        )


class IncompatibleDimensionError(SemanticLayerError):
    """A requested dimension is not compatible with the given measures."""

    def __init__(self, dimension: str, measures: list[str]) -> None:
        self.dimension = dimension
        self.measures = measures
        super().__init__(
            f"Dimension {dimension!r} is not compatible with measures: "
            f"{', '.join(measures)}"
        )


class InvalidFilterError(SemanticLayerError):
    """A filter references a dimension that is not in the requested set."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(
            f"Filter references dimension {dimension!r} which is not in the "
            f"requested dimension set"
        )


class CompilationError(SemanticLayerError):
    """An error occurred during warehouse introspection or compilation."""
