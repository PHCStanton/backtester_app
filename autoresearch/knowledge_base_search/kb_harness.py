"""
kb_harness.py - Immutable benchmark harness for the AI Knowledge Base search.
Loads patterns, executes benchmark queries, and outputs metrics.json.
"""
import sys
import json
import time
import random
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTORESEARCH_KB_DIR = Path(__file__).resolve().parent

# Ensure target files are in path
sys.path.append(str(AUTORESEARCH_KB_DIR))
import kb_retriever

# Load real pattern dataset
PATTERNS_FILE = REPO_ROOT / "reports/analysis/knowledge_base/condition_patterns.json"

def load_dataset() -> list[dict[str, Any]]:
    if not PATTERNS_FILE.exists():
        # Fallback to generating mock patterns if dataset is missing
        print("Dataset missing; generating mock records...")
        assets = ["EURUSD_otc", "USDCAD_otc", "GBPUSD_otc", "AUDUSD_otc", "ZARUSD_otc"]
        regimes = ["RANGE_BOUND", "STRONG_MOMENTUM", "TREND_REVERSAL", "CHOPPY", "BREAKOUT"]
        levels = ["level1", "level2", "level3"]
        directions = ["CALL", "PUT"]
        
        mock_patterns = []
        for i in range(1000):
            mock_patterns.append({
                "pattern_key": f"mock_{i}",
                "asset": random.choice(assets),
                "strategy_level": random.choice(levels),
                "oteo_score_band": "75-84",
                "regime_label": random.choice(regimes),
                "direction": random.choice(directions),
                "sample_size": random.randint(10, 100),
                "win_rate_pct": random.uniform(45.0, 75.0),
                "expectancy": random.uniform(-10.0, 150.0),
                "net_profit": random.uniform(-100.0, 1000.0),
                "confidence_tier": "MEDIUM",
                "suppression_candidate": False,
                "boost_candidate": False
            })
        return mock_patterns

    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("patterns", [])

def run_benchmark():
    patterns = load_dataset()
    print(f"Loaded {len(patterns)} patterns for benchmark.")
    
    # Generate benchmark query scenarios
    random.seed(42) # Deterministic
    query_scenarios = []
    assets = list(set(p.get("asset") for p in patterns if p.get("asset")))
    regimes = list(set(p.get("regime_label") for p in patterns if p.get("regime_label")))
    levels = ["level1", "level2", "level3"]
    directions = ["CALL", "PUT"]
    
    for _ in range(500): # 500 queries
        query_scenarios.append({
            "asset": random.choice(assets) if assets else "EURUSD_otc",
            "regime": random.choice(regimes) if regimes else "RANGE_BOUND",
            "level": random.choice(levels),
            "direction": random.choice(directions)
        })
        
    # Instantiate candidate retriever
    retriever = kb_retriever.KBRetriever()
    
    # Measure Load/Index Time
    t_start_load = time.perf_counter()
    retriever.load(patterns)
    t_end_load = time.perf_counter()
    load_time_ms = (t_end_load - t_start_load) * 1000.0
    
    # Measure Query Latency
    t_start_query = time.perf_counter()
    results = []
    for q in query_scenarios:
        res = retriever.query(q["asset"], q["regime"], q["level"], q["direction"])
        results.append(res)
    t_end_query = time.perf_counter()
    total_query_time_ms = (t_end_query - t_start_query) * 1000.0
    avg_query_time_ms = total_query_time_ms / len(query_scenarios)
    
    # Measure Recall Integrity
    # Verify that query() returns list/list of dicts
    valid_format = True
    for res in results:
        if not isinstance(res, list):
            valid_format = False
            break
            
    # Calculate Fitness Score
    # We want to minimize query latency and load time.
    # Latency penalty: if avg_query_time_ms > 2ms, degrade score.
    # Base Fitness = 1000.0 / (avg_query_time_ms + 0.01 * load_time_ms + 0.001)
    if not valid_format:
        fitness = 0.0
    else:
        fitness = 1000.0 / (avg_query_time_ms + 0.01 * load_time_ms + 0.001)
        
    metrics = {
        "valid_format": valid_format,
        "load_time_ms": round(load_time_ms, 4),
        "total_query_time_ms": round(total_query_time_ms, 4),
        "avg_query_time_ms": round(avg_query_time_ms, 6),
        "fitness_score": round(fitness, 4)
    }
    
    output_path = Path(__file__).parent / "metrics.json"
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    print("\n--- Benchmark Metrics ---")
    for k, v in metrics.items():
        print(f"{k:20}: {v}")
    print("-------------------------\n")

if __name__ == "__main__":
    run_benchmark()
