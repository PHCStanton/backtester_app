"""
strategy_candidate.py - Mutable target for autoresearch experiments.
The AI agent is allowed to edit this file to optimize trading logic.

It must implement:
    evaluate_signal(oteo_score: float, cci: float, adx: float, adx_slope: float, 
                    hurst_val: float, regime_label: str, atr: float) -> dict[str, Any]

Returned dictionary keys:
    - vetoed (bool): True if the trade should be skipped
    - veto_reason (str): Reason for the veto (logged in results)
    - expiry_seconds (int): Duration of the trade contract in seconds
"""
from typing import Any

def evaluate_signal(
    oteo_score: float,
    cci: float,
    adx: float,
    adx_slope: float,
    hurst_val: float,
    regime_label: str,
    atr: float
) -> dict[str, Any]:
    # Default baseline strategy
    vetoed = False
    veto_reason = ""
    
    # 1. Default static expiry
    expiry_seconds = 60
    
    # 2. Basic Hurst mean-reversion veto
    if regime_label == "RANGE_BOUND" and hurst_val > 0.44:
        vetoed = True
        veto_reason = "Hurst mean-reversion threshold exceeded in Range Bound regime"
        
    # 3. Basic Momentum veto
    if regime_label == "STRONG_MOMENTUM" and adx > 35:
        vetoed = True
        veto_reason = "High ADX momentum veto"
        
    return {
        "vetoed": vetoed,
        "veto_reason": veto_reason,
        "expiry_seconds": expiry_seconds
    }
