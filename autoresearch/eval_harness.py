"""
eval_harness.py - Immutable evaluation script for autoresearch.
Loads tick logs, runs the candidate strategy using the correct OTEO/MarketContextEngine APIs, and outputs results.json.
"""
import sys
import json
import math
from pathlib import Path
from typing import Any

# Ensure project root is in path to import app modules
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Standard imports from OTC_SNIPER app
from app.backend.services.market_context import MarketContextEngine, apply_level2_policy, apply_level3_policy
from app.backend.services.oteo import OTEO
from app.backend.services.regime_classifier import RegimeClassifier

# Import candidate strategy
try:
    import strategy_candidate
except ImportError:
    # Fallback to local import if run from a different Cwd
    sys.path.append(str(Path(__file__).parent))
    import strategy_candidate

# Configuration
DEFAULT_TICK_FILE = REPO_ROOT / "app/data/tick_logs/CADCHF_otc/2026-06-15.jsonl"
PAYOUT_PCT = 92.0

class TickSchemaError(ValueError):
    pass

def load_ticks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Tick file not found: {path}")
    ticks = []
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                ticks.append({
                    "timestamp": float(row["t"]),
                    "price": float(row["p"]),
                    "asset": str(row["a"])
                })
            except Exception as e:
                raise TickSchemaError(f"Line {idx} invalid: {e}")
    return sorted(ticks, key=lambda t: t["timestamp"])

def evaluate_trade(ticks: list[dict[str, Any]], start_idx: int, direction: str, expiry_seconds: int) -> dict[str, Any]:
    entry_tick = ticks[start_idx]
    entry_time = entry_tick["timestamp"]
    entry_price = entry_tick["price"]
    target_time = entry_time + expiry_seconds
    
    # Binary search for exit tick
    low = start_idx
    high = len(ticks) - 1
    exit_idx = len(ticks)
    
    while low <= high:
        mid = (low + high) // 2
        if ticks[mid]["timestamp"] >= target_time:
            exit_idx = mid
            high = mid - 1
        else:
            low = mid + 1
            
    if exit_idx >= len(ticks):
        return {"outcome": "missing_exit", "pnl": 0.0}
        
    exit_tick = ticks[exit_idx]
    price_delta = exit_tick["price"] - entry_price
    
    if price_delta == 0:
        pnl = 0.0
    elif direction == "CALL":
        pnl = PAYOUT_PCT / 100.0 if price_delta > 0 else -1.0
    else:  # PUT
        pnl = PAYOUT_PCT / 100.0 if price_delta < 0 else -1.0
            
    return {"outcome": "win" if pnl > 0 else ("loss" if pnl < 0 else "draw"), "pnl": pnl}

def run_evaluation():
    print(f"Loading ticks from {DEFAULT_TICK_FILE.name}...")
    ticks = load_ticks(DEFAULT_TICK_FILE)
    print(f"Loaded {len(ticks)} ticks.")
    
    # Initialize engines
    oteo = OTEO()
    context_engine = MarketContextEngine()
    regime_classifier = RegimeClassifier()
    
    trades = []
    skipped_count = 0
    last_regime = None
    
    # Keep track of timestamps for binary search optimization in evaluate_trade
    # We will pass ticks list to evaluate_trade
    
    for idx, tick in enumerate(ticks):
        price = tick["price"]
        ts = tick["timestamp"]
        
        # Feed engines using the proper update_tick signature
        oteo_res = oteo.update_tick(price, timestamp=ts)
        context_res = context_engine.update_tick(price, timestamp=ts)
        
        if bool(context_res.get("candle_closed")) and bool(context_res.get("ready")):
            last_regime = regime_classifier.classify(context_res)
            
        if isinstance(oteo_res, dict):
            level1 = dict(oteo_res)
            level2 = apply_level2_policy(level1, context_res, enabled=True)
            level3 = None
            if last_regime is not None:
                level3 = apply_level3_policy(level2, context_res, last_regime)
                
            # Evaluate Level 3 signals (our main indicator target)
            if level3 is not None and bool(level3.get("actionable")):
                direction = str(level3.get("recommended") or "").upper()
                if direction not in {"CALL", "PUT"}:
                    continue
                    
                # Extract telemetry fields
                adx = float(context_res.get("adx") or 0.0)
                adx_slope = float(context_res.get("adx_slope") or 0.0)
                cci = float(context_res.get("cci") or 0.0)
                hurst_val = float(context_res.get("hurst") or 0.5)
                atr = float(context_res.get("atr") or 0.0001)
                
                # Query candidate strategy
                decision = strategy_candidate.evaluate_signal(
                    oteo_score=float(level3.get("oteo_score") or 50.0),
                    cci=cci,
                    adx=adx,
                    adx_slope=adx_slope,
                    hurst_val=hurst_val,
                    regime_label=last_regime or "UNKNOWN",
                    atr=atr
                )
                
                if decision.get("vetoed", False):
                    skipped_count += 1
                    continue
                    
                expiry = int(decision.get("expiry_seconds", 60))
                trade_res = evaluate_trade(ticks, idx, direction, expiry)
                
                if trade_res["outcome"] != "missing_exit":
                    trades.append(trade_res)
                
    # Calculate stats
    total_trades = len(trades)
    if total_trades == 0:
        win_rate = 0.0
        net_pnl = 0.0
        fitness = 0.0
    else:
        wins = sum(1 for t in trades if t["outcome"] == "win")
        win_rate = (wins / total_trades) * 100.0
        net_pnl = sum(t["pnl"] for t in trades)
        
        # Fitness objective function: penalizes too few trades or negative win rate
        if win_rate < 52.08:
            fitness = 0.0
        else:
            # win_rate * ln(trades)
            fitness = win_rate * math.log(total_trades)
            
    results = {
        "win_rate": round(win_rate, 4),
        "total_trades": total_trades,
        "skipped_trades": skipped_count,
        "net_pnl": round(net_pnl, 4),
        "fitness_score": round(fitness, 4)
    }
    
    output_path = Path(__file__).parent / "metrics.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
        
    print("\n--- Evaluation Summary ---")
    for k, v in results.items():
        print(f"{k:18}: {v}")
    print("--------------------------\n")

if __name__ == "__main__":
    run_evaluation()
