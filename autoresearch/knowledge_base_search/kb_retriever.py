"""
kb_retriever.py - Mutable target for knowledge base memory autoresearch.
The AI agent edits this file to optimize data structure indexing and retrieval math.
"""
from typing import Any

class KBRetriever:
    def __init__(self) -> None:
        self.patterns = []

    def load(self, raw_patterns_list: list[dict[str, Any]]) -> None:
        """
        Ingests the flat list of patterns.
        Optimizations (e.g. SQLite database creation, index building, 
        hash map indexing, or Obsidian folder structure generation) should occur here.
        """
        # Default baseline: Keep as flat list
        self.patterns = raw_patterns_list

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
        # Default baseline: O(N) linear scan
        matches = []
        clean_asset = asset.lower().replace("_otc", "").strip()
        
        for p in self.patterns:
            p_asset = p.get("asset", "").lower().replace("_otc", "").strip()
            p_regime = p.get("regime_label", "").upper().strip()
            p_level = p.get("strategy_level", "").lower().strip()
            p_dir = p.get("direction", "").upper().strip()
            
            # Simple similarity scoring
            score = 0
            if clean_asset == p_asset:
                score += 10
            if regime.upper().strip() == p_regime:
                score += 5
            if level.lower().strip() == p_level:
                score += 5
            if direction.upper().strip() == p_dir:
                score += 2
                
            if score >= 15: # Similarity threshold
                matches.append((score, p))
                
        # Sort by similarity score and expectancy
        matches.sort(key=lambda x: (x[0], x[1].get("expectancy", 0.0)), reverse=True)
        return [m[1] for m in matches[:5]]
