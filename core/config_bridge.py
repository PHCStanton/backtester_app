from __future__ import annotations

from typing import Any
from backtester_app.core.engine import UnifiedBacktestConfig

def backtester_to_ghost_protocol(config: UnifiedBacktestConfig) -> dict[str, Any]:
    """
    Maps a UnifiedBacktestConfig instance to the AutoGhostConfig JSON schema format.
    """
    return {
        "minimum_payout_pct": config.payout_pct,
        "per_asset_cooldown_seconds": config.indicator.cooldown_ticks,  # Conceptual match (seconds vs ticks)
        "block_on_manipulation": config.manipulation.veto_enabled,
        "manipulation_severity_threshold": config.manipulation.severity_threshold,
        "blacklist_assets": config.pocket.blacklist_assets,
        
        # Hurst
        "hurst_filter_enabled": config.hurst.veto_enabled,
        "hurst_filter_threshold": config.hurst.filter_threshold if config.hurst.filter_threshold is not None else 0.48,
        "hurst_mean_revert_threshold": config.hurst.mean_revert_limit,
        "hurst_trend_threshold": config.hurst.trend_limit,
        "hurst_min_scale_cutoff": config.hurst.min_scale_cutoff,

        # OTEO Gate (z-score and score bounds)
        "min_zscore_enabled": config.oteo_gate.min_zscore_enabled,
        "min_zscore": config.oteo_gate.min_zscore,
        "max_zscore_enabled": config.oteo_gate.max_zscore_enabled,
        "max_zscore": config.oteo_gate.max_zscore,
        "min_confidence_enabled": config.oteo_gate.min_score_enabled,
        "min_confidence": config.oteo_gate.min_score,
        "max_confidence_enabled": config.oteo_gate.max_score_enabled,
        "max_confidence": config.oteo_gate.max_score,

        # Regime Gate
        "regime_gate_enabled": config.regime.enabled,
        "allowed_regimes": config.regime.allowed_regimes,
        "require_regime_stable": config.regime.require_stable,

        # OTEO Core Parameters (note: live app does not necessarily expose these 
        # in AutoGhostConfig directly, but we export them so they are preserved)
        "oteo_min_abs_z_score": config.oteo_params.min_abs_z_score,
        "oteo_min_pressure_pct": config.oteo_params.min_pressure_pct,
        "oteo_score_center": config.oteo_params.score_center,
        "oteo_score_slope": config.oteo_params.score_slope,
        "oteo_cooldown_ticks": config.oteo_params.cooldown_ticks,
        "oteo_buffer_size": config.oteo_params.buffer_size,
        "oteo_pressure_window": config.oteo_params.pressure_window,
        "oteo_macro_window": config.oteo_params.macro_window,
    }

def ghost_protocol_to_backtester(data: dict[str, Any]) -> dict[str, Any]:
    """
    Maps an AutoGhostConfig JSON dict to a UnifiedBacktestConfig dict structure.
    """
    return {
        "payout_pct": float(data.get("minimum_payout_pct", 92.0)),
        "kalman": {
            "enabled": False,
            "q": 1e-9,
            "r": 1e-7,
            "upstream_of_hurst": False,
        },
        "hurst": {
            "veto_enabled": bool(data.get("hurst_filter_enabled", False)),
            "window_size": 300,
            "mean_revert_limit": float(data.get("hurst_mean_revert_threshold", 0.44)),
            "trend_limit": float(data.get("hurst_trend_threshold", 0.58)),
            "allowed_regimes": ["mean_reverting", "random_walk", "trending"],
            "filter_threshold": float(data["hurst_filter_threshold"]) if data.get("hurst_filter_threshold") is not None else None,
            "min_scale_cutoff": int(data.get("hurst_min_scale_cutoff", 12)),
        },
        "ou": {
            "veto_enabled": False,
            "mode": "kalman",
            "window_size": 300,
            "q_c": 1e-10,
            "q_beta": 1e-6,
            "r": 1e-8,
        },
        "expiry": {
            "mode": "static",
            "static_seconds": [60, 120, 300],
            "adaptive_c": 10.0,
            "adaptive_bounds": [30, 60, 120, 300],
        },
        "indicator": {
            "level_mode": "all",
            "cooldown_ticks": int(data.get("per_asset_cooldown_seconds", 30)),
        },
        "pocket": {
            "veto_enabled": False,
            "exclusion_list": [],
            "blacklist_assets": list(data.get("blacklist_assets", []) or []),
        },
        "timeframe": {
            "veto_enabled": False,
            "exclusion_blocks": [],
        },
        "bayesian": {
            "enabled": False,
            "alpha_prior": 2.0,
            "beta_prior": 2.0,
            "confidence_threshold": 0.90,
            "breakeven_win_rate": 0.5208,
            "risk_aversion": 2.0,
            "max_fraction": 0.10,
        },
        "manipulation": {
            "veto_enabled": bool(data.get("block_on_manipulation", False)),
            "severity_threshold": float(data.get("manipulation_severity_threshold", 0.3)),
        },
        "oteo_gate": {
            "min_zscore_enabled": bool(data.get("min_zscore_enabled", False)),
            "min_zscore": float(data.get("min_zscore", 0.0)),
            "max_zscore_enabled": bool(data.get("max_zscore_enabled", False)),
            "max_zscore": float(data.get("max_zscore", 10.0)),
            "min_score_enabled": bool(data.get("min_confidence_enabled", False)),
            "min_score": float(data.get("min_confidence", 0.0) or 0.0),
            "max_score_enabled": bool(data.get("max_confidence_enabled", False)),
            "max_score": float(data.get("max_confidence", 100.0) or 100.0),
        },
        "regime": {
            "enabled": bool(data.get("regime_gate_enabled", False)),
            "allowed_regimes": list(data.get("allowed_regimes", []) or []),
            "require_stable": bool(data.get("require_stable", False)),
        },
        "oteo_params": {
            "min_abs_z_score": float(data.get("oteo_min_abs_z_score", 0.35)),
            "min_pressure_pct": float(data.get("oteo_min_pressure_pct", 12.0)),
            "score_center": float(data.get("oteo_score_center", 0.85)),
            "score_slope": float(data.get("oteo_score_slope", 3.5)),
            "cooldown_ticks": int(data.get("oteo_cooldown_ticks", 30)),
            "buffer_size": int(data.get("oteo_buffer_size", 300)),
            "pressure_window": int(data.get("oteo_pressure_window", 24)),
            "macro_window": int(data.get("oteo_macro_window", 120)),
        },
        "volatility": {
            "high_ratio": 2.0,
            "medium_ratio": 1.2,
        },
        "liquidity": {
            "high_freq": 40.0,
            "medium_freq": 15.0,
        }
    }
