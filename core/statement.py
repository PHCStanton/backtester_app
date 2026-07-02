from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple
import pandas as pd
import numpy as np

# Adjust sys.path to REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtester_app.core.engine import (
    UnifiedBacktester,
    UnifiedBacktestConfig,
    GateContext,
    calculate_time_offsets,
    calculate_volatility_score,
    load_ticks_from_file,
    _net_pl_for_outcome
)
from app.backend.services.oteo import OTEO
from app.backend.services.market_context import MarketContextEngine, apply_level2_policy, apply_level3_policy
from app.backend.services.regime_classifier import RegimeClassifier

def normalize_asset(asset_name: str) -> str:
    if not isinstance(asset_name, str):
        return "UNKNOWN"
    name = asset_name.upper().strip()
    if name.startswith("#"):
        name = name[1:]
    if name.endswith("_OTC"):
        name = name[:-4]
    elif name.endswith("OTC"):
        name = name[:-3]
    name = name.strip()
    name = name.replace("-", "").replace("_", "").replace("/", "")
    return name

def detect_timezone_offset(df: pd.DataFrame, limit: int = 100) -> float:
    from collections import Counter
    offsets = []
    
    # Filter valid rows to sample
    sample_df = df.dropna(subset=["Asset", "Open time", "Open price", "Direction"])
    if len(sample_df) > limit:
        sample_df = sample_df.sample(n=limit, random_state=42)
        
    for _, row in sample_df.iterrows():
        asset = normalize_asset(row["Asset"])
        open_time = row["Open time"]
        open_price = float(row["Open price"])
        
        date_str = open_time.strftime("%Y-%m-%d")
        log_path = REPO_ROOT / f"app/data/tick_logs/{asset}_otc/{date_str}.jsonl"
        
        if not log_path.exists():
            continue
            
        excel_ts = open_time.replace(tzinfo=timezone.utc).timestamp()
        
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    tick = json.loads(line)
                    t_price = float(tick["p"])
                    t_time = float(tick["t"])
                    
                    # Look for tick within 4 hours with matching price
                    if abs(t_price - open_price) < 1e-7 and abs(t_time - excel_ts) < 14400:
                        diff = t_time - excel_ts
                        hour_diff = round(diff / 3600.0) * 3600
                        offsets.append(hour_diff)
                        break
        except Exception:
            continue
            
    if not offsets:
        return 0.0
        
    most_common = Counter(offsets).most_common(1)[0]
    return float(most_common[0])

class POStatementReplayer:
    def __init__(self, config: UnifiedBacktestConfig) -> None:
        self.config = config
        self.tester = UnifiedBacktester(config)

    def load_statement_trades(self, file_path: Path, offset: float) -> List[Dict[str, Any]]:
        if file_path.suffix.lower() == ".csv":
            # Guess delimiter
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        df["Open time"] = pd.to_datetime(df["Open time"])
        df["Close time"] = pd.to_datetime(df["Close time"])
        
        trades = []
        for _, row in df.iterrows():
            asset = normalize_asset(row["Asset"])
            open_time = row["Open time"]
            direction = str(row["Direction"]).upper().strip()
            amount = float(row["Trade amount"])
            profit = float(row["Profit"])
            open_price = float(row["Open price"])
            close_price = float(row["Close price"])
            
            outcome = "loss"
            if open_price == close_price:
                outcome = "draw"
            elif direction == "CALL":
                outcome = "win" if close_price > open_price else "loss"
            elif direction == "PUT":
                outcome = "win" if close_price < open_price else "loss"
                
            excel_ts = open_time.replace(tzinfo=timezone.utc).timestamp()
            adjusted_ts = excel_ts + offset
            
            # Extract duration in seconds
            duration_delta = row["Close time"] - row["Open time"]
            duration_sec = int(duration_delta.total_seconds())
            if duration_sec <= 0:
                duration_sec = 60 # fallback default
            
            trades.append({
                "asset": asset,
                "open_time": open_time,
                "day_of_week": open_time.strftime("%A"),
                "hour_of_day": open_time.hour,
                "date_str": open_time.strftime("%Y-%m-%d"),
                "adjusted_ts": adjusted_ts,
                "direction": direction,
                "amount": amount,
                "profit": profit,
                "outcome": outcome,
                "duration_seconds": duration_sec
            })
        return trades

    def replay(self, statement_path: Path, offset_override: float | None = None) -> List[Dict[str, Any]]:
        if not statement_path.exists():
            raise FileNotFoundError(f"PO statement file not found: {statement_path}")
            
        if statement_path.suffix.lower() == ".csv":
            df = pd.read_csv(statement_path)
        else:
            df = pd.read_excel(statement_path)

        df["Open time"] = pd.to_datetime(df["Open time"])
        
        if offset_override is not None:
            offset = offset_override
        else:
            offset = detect_timezone_offset(df)
            
        all_trades = self.load_statement_trades(statement_path, offset)
        trades_by_key = defaultdict(list)
        for t in all_trades:
            key = (t["date_str"], t["asset"])
            trades_by_key[key].append(t)
            
        keys_to_process = sorted(trades_by_key.keys())
        results = []
        
        # Clear/reset backtester engines/bayesian states
        self.tester.bayesian_engine.states.clear()
        
        for date_str, asset in keys_to_process:
            log_path = REPO_ROOT / f"app/data/tick_logs/{asset}_otc/{date_str}.jsonl"
            if not log_path.exists():
                continue
                
            trades = sorted(trades_by_key[(date_str, asset)], key=lambda x: x["adjusted_ts"])
            
            # Load ticks
            ticks = []
            try:
                raw_ticks = load_ticks_from_file(log_path)
                for tk in raw_ticks:
                    ticks.append((tk.timestamp, tk.price))
            except Exception:
                continue
                
            if not ticks:
                continue
                
            # Reset backtester trackers for this file segment
            self.tester.reset_trackers()
            
            # Instantiations matching baseline
            oteo_base = OTEO()
            context_base = MarketContextEngine()
            regime_base = RegimeClassifier()
            last_regime_base = None
            
            # Buffers for rolling OLS OU calculation
            ols_prices: deque[float] = deque(maxlen=self.config.ou.window_size + 10)
            ols_ts: deque[float] = deque(maxlen=self.config.ou.window_size + 10)
            
            trade_idx = 0
            num_trades = len(trades)
            
            recent_tick_times = deque()
            
            for t_time, t_price in ticks:
                self.tester._price_buffer.append(t_price)
                ols_prices.append(t_price)
                ols_ts.append(t_time)
                
                # Resolve Pending Trades (Walk-Forward Bayesian Learning)
                resolved_pt = []
                for pt in self.tester.pending_trades:
                    if t_time >= pt["exit_time"]:
                        self.tester.bayesian_engine.update_trade(pt["pocket_state"], pt["expiry_seconds"], pt["outcome"])
                        resolved_pt.append(pt)
                for pt in resolved_pt:
                    self.tester.pending_trades.remove(pt)
                
                # Tick frequency calculation
                recent_tick_times.append(t_time)
                while recent_tick_times and recent_tick_times[0] < t_time - 60:
                    recent_tick_times.popleft()
                tick_freq = len(recent_tick_times)
                
                # Kalman price pre-filtering for engine stack
                if self.config.kalman.enabled:
                    smoothed_price = self.tester.kalman_filter.update(t_price)
                else:
                    smoothed_price = t_price
                    
                # Update baseline policy
                oteo_res_base = oteo_base.update_tick(t_price, timestamp=t_time)
                context_res_base = context_base.update_tick(t_price, timestamp=t_time)
                if bool(context_res_base.get("candle_closed")) and bool(context_res_base.get("ready")):
                    last_regime_base = regime_base.classify(context_res_base)
                    
                # Update main stack components
                oteo_res_kf = self.tester.oteo.update_tick(smoothed_price, timestamp=t_time)
                context_res_kf = self.tester.context.update_tick(smoothed_price, timestamp=t_time)
                
                if bool(context_res_kf.get("candle_closed")) and bool(context_res_kf.get("ready")):
                    self.tester.hurst_tracker.update_regime()
                    self.tester.regime_classifier.classify(context_res_kf)
                    
                self.tester.hurst_tracker.add_price(smoothed_price)
                
                # Calculate features
                h_val = self.tester.hurst_tracker.last_h
                h_regime = self.tester.hurst_tracker.regime
                
                atr = context_res_kf.get("atr")
                if len(self.tester._price_buffer) >= 2:
                    returns = np.diff(np.log(self.tester._price_buffer))
                    returns_std = float(np.std(returns)) if len(returns) > 0 else 0.0
                else:
                    returns_std = 0.0
                v_score = calculate_volatility_score(atr, t_price, returns_std, tick_freq)
                
                # OU Parameter Tracking
                tau_ou = None
                ou_beta = None
                if self.config.ou.mode == "ols":
                    if len(ols_prices) >= self.config.ou.window_size:
                        tau_ou = calculate_rolling_ou(np.array(ols_prices), np.array(ols_ts), self.config.ou.window_size)
                else:  # mode == "kalman"
                    if self.tester._ou_last_price is not None:
                        dt_raw = t_time - self.tester._ou_last_price[1]
                        if dt_raw > 0:
                            self.tester._ou_dt_buffer.append(dt_raw)
                        _, ou_beta = self.tester.ou_kalman_tracker.update(self.tester._ou_last_price[0], t_price)
                        dt_stable = np.mean(self.tester._ou_dt_buffer) if self.tester._ou_dt_buffer else 1.0
                        if ou_beta < 0 and (1.0 + ou_beta) > 1e-5:
                            theta_ou = -math.log(1.0 + ou_beta) / dt_stable
                            if theta_ou > 0:
                                tau_ou = math.log(2) / theta_ou
                    self.tester._ou_last_price = (t_price, t_time)
                    
                # Spike Pocket Classification
                vol_lvl, liq_lvl, manip_lvl, pocket_state = self.tester.pocket_tracker.update(t_time, t_price)
                hour_offset, four_hour_offset = calculate_time_offsets(t_time)
                
                # Check if statement trades match this timestamp
                while trade_idx < num_trades and trades[trade_idx]["adjusted_ts"] <= t_time:
                    trade = trades[trade_idx]
                    trade_idx += 1
                    
                    # 1. Baseline Level 3 Validation
                    baseline_aligned = False
                    if isinstance(oteo_res_base, dict) and "recommended" in oteo_res_base:
                        level1 = dict(oteo_res_base)
                        level2 = apply_level2_policy(level1, context_res_base, enabled=True)
                        level3 = None
                        if last_regime_base is not None:
                            level3 = apply_level3_policy(level2, context_res_base, last_regime_base)
                            if isinstance(level3, dict):
                                baseline_aligned = bool(level3.get("actionable", False)) and (str(level3.get("recommended")).upper() == trade["direction"])

                    # 2. Main Stack Validation using Gate pipelines
                    stack_aligned = False
                    veto_reason = None
                    
                    if isinstance(oteo_res_kf, dict) and "recommended" in oteo_res_kf:
                        level1_kf = dict(oteo_res_kf)
                        level2_kf = apply_level2_policy(level1_kf, context_res_kf, enabled=True)
                        level3_kf = None
                        # Use engine classifier result
                        last_regime_kf = self.tester.regime_classifier.classify(context_res_kf) if bool(context_res_kf.get("ready")) else None
                        
                        if last_regime_kf is not None:
                            level3_kf = apply_level3_policy(level2_kf, context_res_kf, last_regime_kf)
                            
                        if isinstance(level3_kf, dict) and bool(level3_kf.get("actionable", False)) and (str(level3_kf.get("recommended")).upper() == trade["direction"]):
                            # Reconstruct GateContext
                            gate_context = GateContext(
                                timestamp=t_time,
                                price=t_price,
                                direction=trade["direction"],
                                hurst_value=h_val,
                                hurst_regime=h_regime,
                                ou_beta=ou_beta,
                                tau_ou=tau_ou,
                                pocket_state=pocket_state,
                                vol_level=vol_lvl,
                                liq_level=liq_lvl,
                                manip_level=manip_lvl,
                                hour_offset=hour_offset,
                                four_hour_offset=four_hour_offset,
                                volatility_score=v_score,
                                payout_pct=self.config.payout_pct,
                                expiry_seconds=trade["duration_seconds"]
                            )
                            
                            # Evaluate Pre-Signal Gates
                            vetoed = False
                            for gate in self.tester.pre_signal_gates:
                                gate_vetoed, gate_reason = gate.evaluate(gate_context)
                                if gate_vetoed:
                                    vetoed = True
                                    veto_reason = gate_reason
                                    break
                                    
                            if not vetoed:
                                # Evaluate Per-Cell Gates
                                for gate in self.tester.per_cell_gates:
                                    gate_vetoed, gate_reason = gate.evaluate(gate_context)
                                    if gate_vetoed:
                                        vetoed = True
                                        veto_reason = gate_reason
                                        break
                                        
                            stack_aligned = not vetoed

                    # Record outcome to walk-forward Bayesian learning if stack allowed it
                    if stack_aligned and trade["outcome"] in {"win", "loss"}:
                        self.tester.pending_trades.append({
                            "exit_time": t_time + trade["duration_seconds"],
                            "pocket_state": pocket_state,
                            "expiry_seconds": trade["duration_seconds"],
                            "outcome": trade["outcome"]
                        })
                        
                    results.append({
                        "asset": trade["asset"],
                        "day_of_week": trade["day_of_week"],
                        "hour_of_day": trade["hour_of_day"],
                        "outcome": trade["outcome"],
                        "amount": trade["amount"],
                        "profit": trade["profit"],
                        "baseline_aligned": baseline_aligned,
                        "stack_aligned": stack_aligned,
                        "veto_reason": veto_reason,
                        "tick_freq": tick_freq,
                        "atr": atr,
                        "pocket_state": pocket_state,
                        "manip_penalty": oteo_res_kf.get("manipulation_penalty", 0.0) if isinstance(oteo_res_kf, dict) else 0.0
                    })
                    
        return results

def calculate_rolling_ou(prices: np.ndarray, timestamps: np.ndarray, window_size: int) -> float | None:
    if len(prices) < window_size:
        return None
    w_prices = prices[-window_size:]
    w_ts = timestamps[-window_size:]
    y = np.diff(w_prices)
    x_lag = w_prices[:-1]
    n = len(y)
    if n < 50:
        return None
    dt = (w_ts[-1] - w_ts[0]) / n
    if dt <= 0:
        return None
    sum_x = np.sum(x_lag)
    sum_y = np.sum(y)
    sum_xx = np.sum(x_lag**2)
    sum_xy = np.sum(x_lag * y)
    denom = n * sum_xx - sum_x**2
    if abs(denom) < 1e-12:
        return None
    beta = (n * sum_xy - sum_x * sum_y) / denom
    if beta >= 0 or (1.0 + beta) <= 0:
        return None
    theta = -math.log(1.0 + beta) / dt
    if theta <= 0:
        return None
    tau = math.log(2) / theta
    return float(tau)
