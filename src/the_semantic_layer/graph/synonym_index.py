"""Case-insensitive name resolution for measures and dimensions."""

from the_semantic_layer.errors import AmbiguousNameError, UnresolvedNameError


class SynonymIndex:
    """Maps aliases (display names, synonyms, canonical names) to canonical names.

    Lookups are case-insensitive. Each alias is tagged with a kind
    ("measure" or "dimension") to prevent cross-type collisions.
    """

    def __init__(self) -> None:
        # (normalized_alias, kind) -> set of canonical names
        self._index: dict[tuple[str, str], set[str]] = {}

    def register(
        self,
        canonical_name: str,
        aliases: list[str],
        kind: str,
    ) -> None:
        """Register a canonical name and its aliases.

        Args:
            canonical_name: The authoritative name.
            aliases: Alternative names (display name, synonyms, bare column name).
            kind: Either "measure" or "dimension".
        """
        all_names = [canonical_name, *aliases]
        for name in all_names:
            if not name:
                continue
            key = (name.lower().strip(), kind)
            if key not in self._index:
                self._index[key] = set()
            self._index[key].add(canonical_name)

    def resolve(self, name: str, kind: str) -> str:
        """Resolve a name to its canonical form.

        Args:
            name: The name to resolve (case-insensitive).
            kind: Either "measure" or "dimension".

        Returns:
            The canonical name.

        Raises:
            UnresolvedNameError: If the name is not found.
            AmbiguousNameError: If the name maps to multiple canonical names.
        """
        key = (name.lower().strip(), kind)
        candidates = self._index.get(key)

        if not candidates:
            raise UnresolvedNameError(name, kind)

        if len(candidates) == 1:
            return next(iter(candidates))

        raise AmbiguousNameError(name, kind, sorted(candidates))

    def suggest(self, name: str, kind: str, max_results: int = 5) -> list[str]:
        """Suggest canonical names for a near-miss lookup.

        Uses a simple tiered approach:
        1. Exact prefix match (highest priority)
        2. Substring match (medium priority)
        3. Character overlap ratio > 0.5 (lowest priority)

        Args:
            name: The name that failed to resolve.
            kind: Either "measure" or "dimension".
            max_results: Maximum suggestions to return.

        Returns:
            List of canonical names, best matches first.
        """
        normalized = name.lower().strip()
        if not normalized:
            return []

        prefix_matches: set[str] = set()
        substring_matches: set[str] = set()
        overlap_matches: set[str] = set()

        norm_chars = set(normalized)

        for (alias, alias_kind), canonicals in self._index.items():
            if alias_kind != kind:
                continue

            if alias.startswith(normalized) or normalized.startswith(alias):
                prefix_matches.update(canonicals)
            elif normalized in alias or alias in normalized:
                substring_matches.update(canonicals)
            else:
                alias_chars = set(alias)
                union = norm_chars | alias_chars
                if union:
                    overlap = len(norm_chars & alias_chars) / len(union)
                    if overlap > 0.5:
                        overlap_matches.update(canonicals)

        # Deduplicate across tiers (higher tier wins)
        substring_matches -= prefix_matches
        overlap_matches -= prefix_matches | substring_matches

        result = sorted(prefix_matches) + sorted(substring_matches) + sorted(overlap_matches)
        return result[:max_results]
