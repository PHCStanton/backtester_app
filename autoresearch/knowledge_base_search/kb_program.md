# Autoresearch AI Knowledge Base Memory Search

The goal is to design the most efficient and accurate memory recall system for the `OTC_SNIPER` AI Knowledge Base (where the AI retrieves past statistical patterns for active market contexts).

Currently, patterns are stored in a monolithic `condition_patterns.json` file. If this file grows to millions of entries, scanning it with O(N) iteration in Python will introduce event-loop lag.

---

## The Optimization Targets

We are seeking a retrieval implementation that minimizes:
1. **Query Latency (ms):** Crucial for real-time streaming operations where ticks arrive in milliseconds.
2. **Memory Footprint (MB):** Keeping the engine lightweight.

While maximizing:
3. **Recall Relevance (F1-Score):** Finding the exact or most similar patterns (e.g. normalizations for symbols, matching regimes, and score bands).

---

## Ideas to Propose

*   **SQLite Indexing:** Moving from flat JSON to SQLite with indexed columns for `asset`, `regime_label`, `strategy_level`, etc.
*   **Obsidian-Style Markdown Vault:** A folder-structured markdown wiki (e.g. `vault/USDCAD_otc/RANGE_BOUND_level3.md`) with frontmatter metadata. Python can query files dynamically using filename matching rather than scanning a whole database.
*   **Divided JSON files:** Splitting the monolithic database into asset-specific or regime-specific sub-files.
*   **Hash Maps / Dictionary indexing:** Pre-computing multi-key hash lookups:
    `self.index[asset][regime][level][direction] = list_of_patterns`
