"""
kb_retriever.py - Mutable target for knowledge base memory autoresearch.
The AI agent edits this file to optimize data structure indexing and retrieval math.
"""
from typing import Any

class KBRetriever:
    def __init__(self) -> None:
        self.index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        self._cache: dict[str, str] = {}

    def _normalize(self, x: str | None) -> str:
        if not x:
            return ""
        if x in self._cache:
            return self._cache[x]
        norm = x.lower().replace("_otc", "").strip()
        self._cache[x] = norm
        return norm

    def load(self, raw_patterns_list: list[dict[str, Any]]) -> None:
        """
        Ingests the flat list of patterns.
        Optimizations (e.g. SQLite database creation, index building, 
        hash map indexing, or Obsidian folder structure generation) should occur here.
        """
        idx: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        cache = self._cache
        for p in raw_patterns_list:
            a = p.get("asset")
            if a in cache:
                na = cache[a]
            else:
                na = a.lower().replace("_otc", "").strip() if a else ""
                cache[a] = na
            r = p.get("regime_label", "").upper().strip()
            l = p.get("strategy_level", "").lower().strip()
            d = p.get("direction", "").upper().strip()
            key = (na, r, l, d)
            if key in idx:
                idx[key].append(p)
            else:
                idx[key] = [p]
        self.index = idx

    def query(
        self,
        asset: str,
        regime: str,
        level: str,
        direction: str
    ) -> list[dict[str, Any]]:
        """
        Retrieves matching patterns.
        Matches by asset normalizations, regime, and level.
        Returns top matches.
        """
        cache = self._cache
        if asset in cache:
            clean_asset = cache[asset]
        else:
            clean_asset = asset.lower().replace("_otc", "").strip() if asset else ""
            cache[asset] = clean_asset
        r = regime.upper().strip()
        l = level.lower().strip()
        d = direction.upper().strip()
        key = (clean_asset, r, l, d)
        matches = self.index.get(key, [])
        return matches[:5]