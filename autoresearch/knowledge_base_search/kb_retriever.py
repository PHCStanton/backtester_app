"""
kb_retriever.py - Mutable target for knowledge base memory autoresearch.
The AI agent edits this file to optimize data structure indexing and retrieval math.
"""
from typing import Any
from collections import defaultdict

class KBRetriever:
    def __init__(self) -> None:
        self.index = {}
        self._normalize = lambda x: x.lower().replace("_otc", "").strip() if x else ""

    def load(self, raw_patterns_list: list[dict[str, Any]]) -> None:
        """
        Ingests the flat list of patterns.
        Optimizations (e.g. SQLite database creation, index building, 
        hash map indexing, or Obsidian folder structure generation) should occur here.
        """
        tmp = defaultdict(list)
        for p in raw_patterns_list:
            a = self._normalize(p.get("asset", ""))
            r = p.get("regime_label", "").upper().strip()
            l = p.get("strategy_level", "").lower().strip()
            d = p.get("direction", "").upper().strip()
            key = (a, r, l, d)
            tmp[key].append(p)
        self.index = {}
        for key, lst in tmp.items():
            lst.sort(key=lambda x: x.get("expectancy", 0.0), reverse=True)
            self.index[key] = lst

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
        clean_asset = self._normalize(asset)
        r = regime.upper().strip()
        l = level.lower().strip()
        d = direction.upper().strip()
        key = (clean_asset, r, l, d)
        matches = self.index.get(key, [])
        return matches[:5]