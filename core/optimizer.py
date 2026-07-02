from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List, Dict
import optuna

# Adjust sys.path to REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtester_app.core.engine import UnifiedBacktester, UnifiedBacktestConfig

# Default tick data directory
TICK_ROOT = REPO_ROOT / "app/data/tick_logs"

def objective_factory(
    dates: List[str],
    asset: str,
    target_metric: str = "pnl",
    min_trades: int = 15,
    payout_pct: float = 92.0,
) -> Any:
    """
    Creates the objective function for Optuna.
    """
    def objective(trial: optuna.Trial) -> float:
        # 1. Sample parameters from the defined search space
        
        # Kalman filters
        kalman_enabled = trial.suggest_categorical("kalman_enabled", [True, False])
        kalman_q = trial.suggest_float("kalman_q", 1e-11, 1e-7, log=True)
        kalman_r = trial.suggest_float("kalman_r", 1e-9, 1e-5, log=True)
        kalman_upstream = trial.suggest_categorical("kalman_upstream_of_hurst", [True, False])

        # Hurst exponent
        hurst_veto = trial.suggest_categorical("hurst_veto_enabled", [True, False])
        hurst_mean_revert_limit = trial.suggest_float("hurst_mean_revert_limit", 0.35, 0.48)
        hurst_trend_limit = trial.suggest_float("hurst_trend_limit", 0.52, 0.65)

        # OU parameters
        ou_veto = trial.suggest_categorical("ou_veto_enabled", [True, False])
        ou_q_beta = trial.suggest_float("ou_q_beta", 1e-8, 1e-4, log=True)
        ou_r = trial.suggest_float("ou_r", 1e-10, 1e-6, log=True)

        # Expiry config
        expiry_mode = trial.suggest_categorical("expiry_mode", ["static", "adaptive"])
        adaptive_c = trial.suggest_float("expiry_adaptive_c", 5.0, 50.0)

        # 2. Build configuration dictionary
        config_dict = {
            "payout_pct": payout_pct,
            "kalman": {
                "enabled": kalman_enabled,
                "q": kalman_q,
                "r": kalman_r,
                "upstream_of_hurst": kalman_upstream
            },
            "hurst": {
                "veto_enabled": hurst_veto,
                "window_size": 300,
                "mean_revert_limit": hurst_mean_revert_limit,
                "trend_limit": hurst_trend_limit
            },
            "ou": {
                "veto_enabled": ou_veto,
                "mode": "kalman",
                "window_size": 300,
                "q_c": 1e-10,
                "q_beta": ou_q_beta,
                "r": ou_r
            },
            "expiry": {
                "mode": expiry_mode,
                "static_seconds": [60, 120, 300],
                "adaptive_c": adaptive_c,
                "adaptive_bounds": [30, 60, 120, 300]
            },
            "indicator": {
                "level_mode": "L3",  # focus optimization on L3 pivots
                "cooldown_ticks": 30
            },
            "pocket": {
                "veto_enabled": True,
                # Always exclude unprofitable low volatility and manipulation structures
                "exclusion_list": [
                    "Vol:LOW | Liq:HIGH | Manip:MEDIUM",
                    "Vol:LOW | Liq:HIGH | Manip:LOW"
                ]
            },
            "timeframe": {
                "veto_enabled": True,
                "exclusion_blocks": [0, 4, 5]
            },
            "bayesian": {
                "enabled": False  # keep Bayesian off during standard parameter search
            }
        }

        # 3. Instantiate the engine and run backtests
        config = UnifiedBacktestConfig.from_dict(config_dict)
        tester = UnifiedBacktester(config)
        
        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_pnl = 0.0

        for date in dates:
            file_path = TICK_ROOT / asset / f"{date}.jsonl"
            if not file_path.exists():
                continue
            
            try:
                trade_rows = tester.run_file(file_path)
                for t in trade_rows:
                    if not t["vetoed"]:
                        total_trades += 1
                        if t["outcome"] == "win":
                            total_wins += 1
                        elif t["outcome"] == "loss":
                            total_losses += 1
                        total_pnl += t["net_pl"]
            except Exception:
                # Silently ignore individual file errors during optimization
                pass

        # 4. Check trade count constraints
        if total_trades < min_trades:
            # Heavily penalize trials with insufficient trade counts to avoid over-filtering
            return -9999.0 if target_metric == "pnl" else 0.0

        # 5. Return target metric value
        if target_metric == "winrate":
            win_rate = (total_wins / total_trades) * 100.0 if total_trades else 0.0
            return win_rate
        else:
            return total_pnl

    return objective


def run_optuna_study(
    dates: List[str],
    asset: str,
    n_trials: int = 50,
    target_metric: str = "pnl",
    db_path: Path | None = None,
    study_name: str = "backtest_opt",
    min_trades: int = 15,
    payout_pct: float = 92.0,
) -> Dict[str, Any]:
    """
    Creates and runs an Optuna study.
    """
    storage = None
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        storage = f"sqlite:///{db_path}"
        
    study = optuna.create_study(
        study_name=study_name,
        direction="maximize",
        storage=storage,
        load_if_exists=True
    )
    
    objective = objective_factory(dates, asset, target_metric, min_trades, payout_pct)
    study.optimize(objective, n_trials=n_trials)
    
    return {
        "best_value": study.best_value,
        "best_params": study.best_params,
        "total_trials": len(study.trials)
    }
