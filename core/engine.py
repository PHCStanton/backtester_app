from __future__ import annotations

import csv
import json
import math
import sys
from collections import deque, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, Tuple, Dict, Protocol
import numpy as np

# Adjust sys.path to REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.backend.services.market_context import MarketContextEngine, apply_level2_policy, apply_level3_policy
from app.backend.services.oteo import OTEO
from app.backend.services.regime_classifier import RegimeClassifier
from app.backend.services.manipulation import ManipulationDetector

from backtester_app.core.bayesian import BayesianUtilityEngine

# --- Config Dataclasses ---

@dataclass
class KalmanConfig:
    enabled: bool = False
    q: float = 1e-9
    r: float = 1e-7
    upstream_of_hurst: bool = False

@dataclass
class HurstConfig:
    veto_enabled: bool = False
    window_size: int = 300
    mean_revert_limit: float = 0.44
    trend_limit: float = 0.58

@dataclass
class OUConfig:
    veto_enabled: bool = False
    mode: str = "kalman"  # "ols" or "kalman"
    window_size: int = 300
    q_c: float = 1e-10
    q_beta: float = 1e-6
    r: float = 1e-8

@dataclass
class ExpiryConfig:
    mode: str = "static"  # "static" or "adaptive"
    static_seconds: list[int] = field(default_factory=lambda: [15, 30, 60, 90, 120, 180, 300])
    adaptive_c: float = 10.0
    adaptive_bounds: list[int] = field(default_factory=lambda: [30, 60, 120, 300])

@dataclass
class IndicatorConfig:
    level_mode: str = "all"  # "L1", "L2", "L3", or "all"
    cooldown_ticks: int = 30

@dataclass
class PocketConfig:
    veto_enabled: bool = False
    exclusion_list: list[str] = field(default_factory=list)

@dataclass
class TimeframeConfig:
    veto_enabled: bool = False
    exclusion_blocks: list[int] = field(default_factory=list)

@dataclass
class BayesianConfig:
    enabled: bool = False
    alpha_prior: float = 2.0
    beta_prior: float = 2.0
    confidence_threshold: float = 0.90
    breakeven_win_rate: float = 0.5208
    risk_aversion: float = 2.0
    max_fraction: float = 0.10

@dataclass
class ManipulationConfig:
    veto_enabled: bool = False
    min_severity_level: str = "HIGH"  # "HIGH", "MEDIUM", or "LOW"

@dataclass
class UnifiedBacktestConfig:
    payout_pct: float = 92.0
    kalman: KalmanConfig = field(default_factory=KalmanConfig)
    hurst: HurstConfig = field(default_factory=HurstConfig)
    ou: OUConfig = field(default_factory=OUConfig)
    expiry: ExpiryConfig = field(default_factory=ExpiryConfig)
    indicator: IndicatorConfig = field(default_factory=IndicatorConfig)
    pocket: PocketConfig = field(default_factory=PocketConfig)
    timeframe: TimeframeConfig = field(default_factory=TimeframeConfig)
    bayesian: BayesianConfig = field(default_factory=BayesianConfig)
    manipulation: ManipulationConfig = field(default_factory=ManipulationConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedBacktestConfig:
        kalman_data = data.get("kalman", {})
        hurst_data = data.get("hurst", {})
        ou_data = data.get("ou", {})
        expiry_data = data.get("expiry", {})
        indicator_data = data.get("indicator", {})
        pocket_data = data.get("pocket", {})
        timeframe_data = data.get("timeframe", {})
        bayesian_data = data.get("bayesian", {})
        manipulation_data = data.get("manipulation", {})

        return cls(
            payout_pct=float(data.get("payout_pct", 92.0)),
            kalman=KalmanConfig(
                enabled=bool(kalman_data.get("enabled", False)),
                q=float(kalman_data.get("q", 1e-9)),
                r=float(kalman_data.get("r", 1e-7)),
                upstream_of_hurst=bool(kalman_data.get("upstream_of_hurst", False)),
            ),
            hurst=HurstConfig(
                veto_enabled=bool(hurst_data.get("veto_enabled", False)),
                window_size=int(hurst_data.get("window_size", 300)),
                mean_revert_limit=float(hurst_data.get("mean_revert_limit", 0.44)),
                trend_limit=float(hurst_data.get("trend_limit", 0.58)),
            ),
            ou=OUConfig(
                veto_enabled=bool(ou_data.get("veto_enabled", False)),
                mode=str(ou_data.get("mode", "kalman")),
                window_size=int(ou_data.get("window_size", 300)),
                q_c=float(ou_data.get("q_c", 1e-10)),
                q_beta=float(ou_data.get("q_beta", 1e-6)),
                r=float(ou_data.get("r", 1e-8)),
            ),
            expiry=ExpiryConfig(
                mode=str(expiry_data.get("mode", "static")),
                static_seconds=list(expiry_data.get("static_seconds", [15, 30, 60, 90, 120, 180, 300])),
                adaptive_c=float(expiry_data.get("adaptive_c", 10.0)),
                adaptive_bounds=list(expiry_data.get("adaptive_bounds", [30, 60, 120, 300])),
            ),
            indicator=IndicatorConfig(
                level_mode=str(indicator_data.get("level_mode", "all")),
                cooldown_ticks=int(indicator_data.get("cooldown_ticks", 30)),
            ),
            pocket=PocketConfig(
                veto_enabled=bool(pocket_data.get("veto_enabled", False)),
                exclusion_list=list(pocket_data.get("exclusion_list", [])),
            ),
            timeframe=TimeframeConfig(
                veto_enabled=bool(timeframe_data.get("veto_enabled", False)),
                exclusion_blocks=list(timeframe_data.get("exclusion_blocks", [])),
            ),
            bayesian=BayesianConfig(
                enabled=bool(bayesian_data.get("enabled", False)),
                alpha_prior=float(bayesian_data.get("alpha_prior", 2.0)),
                beta_prior=float(bayesian_data.get("beta_prior", 2.0)),
                confidence_threshold=float(bayesian_data.get("confidence_threshold", 0.90)),
                breakeven_win_rate=float(bayesian_data.get("breakeven_win_rate", 0.5208)),
                risk_aversion=float(bayesian_data.get("risk_aversion", 2.0)),
                max_fraction=float(bayesian_data.get("max_fraction", 0.10)),
            ),
            manipulation=ManipulationConfig(
                veto_enabled=bool(manipulation_data.get("veto_enabled", False)),
                min_severity_level=str(manipulation_data.get("min_severity_level", "HIGH")),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "payout_pct": self.payout_pct,
            "kalman": {
                "enabled": self.kalman.enabled,
                "q": self.kalman.q,
                "r": self.kalman.r,
                "upstream_of_hurst": self.kalman.upstream_of_hurst,
            },
            "hurst": {
                "veto_enabled": self.hurst.veto_enabled,
                "window_size": self.hurst.window_size,
                "mean_revert_limit": self.hurst.mean_revert_limit,
                "trend_limit": self.hurst.trend_limit,
            },
            "ou": {
                "veto_enabled": self.ou.veto_enabled,
                "mode": self.ou.mode,
                "window_size": self.ou.window_size,
                "q_c": self.ou.q_c,
                "q_beta": self.ou.q_beta,
                "r": self.ou.r,
            },
            "expiry": {
                "mode": self.expiry.mode,
                "static_seconds": self.expiry.static_seconds,
                "adaptive_c": self.expiry.adaptive_c,
                "adaptive_bounds": self.expiry.adaptive_bounds,
            },
            "indicator": {
                "level_mode": self.indicator.level_mode,
                "cooldown_ticks": self.indicator.cooldown_ticks,
            },
            "pocket": {
                "veto_enabled": self.pocket.veto_enabled,
                "exclusion_list": self.pocket.exclusion_list,
            },
            "timeframe": {
                "veto_enabled": self.timeframe.veto_enabled,
                "exclusion_blocks": self.timeframe.exclusion_blocks,
            },
            "bayesian": {
                "enabled": self.bayesian.enabled,
                "alpha_prior": self.bayesian.alpha_prior,
                "beta_prior": self.bayesian.beta_prior,
                "confidence_threshold": self.bayesian.confidence_threshold,
                "breakeven_win_rate": self.bayesian.breakeven_win_rate,
                "risk_aversion": self.bayesian.risk_aversion,
                "max_fraction": self.bayesian.max_fraction,
            },
            "manipulation": {
                "veto_enabled": self.manipulation.veto_enabled,
                "min_severity_level": self.manipulation.min_severity_level,
            }
        }


# --- Base Estimator Helpers ---

class TickSchemaError(ValueError):
    """Raised when a tick JSONL row does not match the required backtest schema."""

@dataclass(frozen=True)
class Tick:
    timestamp: float
    price: float
    asset: str

def _require_finite_number(value: Any, *, field_name: str, path: Path, line_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TickSchemaError(f"{path}:{line_number} field '{field_name}' must be numeric, got {value!r}") from exc
    if not math.isfinite(number):
        raise TickSchemaError(f"{path}:{line_number} field '{field_name}' must be finite, got {value!r}")
    return number

def _validate_tick_row(row: Any, *, path: Path, line_number: int) -> Tick:
    if not isinstance(row, dict):
        raise TickSchemaError(f"{path}:{line_number} tick row must be a JSON object")
    for required in ("t", "p", "a"):
        if required not in row:
            raise TickSchemaError(f"{path}:{line_number} missing required field '{required}'")
    timestamp = _require_finite_number(row["t"], field_name="t", path=path, line_number=line_number)
    price = _require_finite_number(row["p"], field_name="p", path=path, line_number=line_number)
    asset = str(row["a"]).strip()
    if not asset:
        raise TickSchemaError(f"{path}:{line_number} field 'a' must be a non-empty asset string")
    return Tick(timestamp=timestamp, price=price, asset=asset)

def load_ticks_from_file(path: Path) -> list[Tick]:
    if not path.exists():
        raise FileNotFoundError(f"Tick file not found: {path}")
    ticks: list[Tick] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TickSchemaError(f"{path}:{line_number} invalid JSON: {exc.msg}") from exc
            ticks.append(_validate_tick_row(row, path=path, line_number=line_number))
    return sorted(ticks, key=lambda tick: tick.timestamp)

class KalmanFilter:
    def __init__(self, q: float, r: float) -> None:
        self.q = q
        self.r = r
        self.x = None
        self.p = 1.0

    def update(self, z: float) -> float:
        if self.x is None:
            self.x = z
            return self.x
        x_pred = self.x
        p_pred = self.p + self.q
        y = z - x_pred
        s = p_pred + self.r
        k = p_pred / s
        self.x = x_pred + k * y
        self.p = (1.0 - k) * p_pred
        return self.x

class ParameterKalmanTracker:
    def __init__(self, q_beta: float, r: float) -> None:
        self.q = q_beta
        self.r = r
        self.beta = -0.05
        self.p = 1.0
        self.prices = deque(maxlen=300)

    def update(self, x_prev: float, x_curr: float) -> tuple[float, float]:
        self.prices.append(x_prev)
        mu = np.mean(self.prices)
        h = x_prev - mu
        y = x_curr - x_prev
        p_pred = self.p + self.q
        s = (h ** 2) * p_pred + self.r
        k = (p_pred * h) / s
        residual = y - h * self.beta
        self.beta = self.beta + k * residual
        self.p = (1.0 - k * h) * p_pred
        self.beta = max(-0.999, min(0.999, self.beta))
        return 0.0, float(self.beta)

class UnifiedHurstTracker:
    def __init__(self, window_size: int, mean_revert_limit: float, trend_limit: float) -> None:
        self.mean_revert_limit = mean_revert_limit
        self.trend_limit = trend_limit
        self.prices = deque(maxlen=window_size)
        self.regime = "random_walk"
        self.last_h = 0.5

    def add_price(self, price: float) -> None:
        self.prices.append(price)

    def calculate_vectorized_hurst(self) -> float:
        prices_arr = np.array(self.prices)
        if len(prices_arr) < 50:
            return 0.5
        returns = np.diff(np.log(prices_arr))
        N = len(returns)
        scales = [16, 32, 64, 128, 256]
        rs_list = []
        for scale in scales:
            if N < scale:
                continue
            num_segments = N // scale
            segments = returns[:num_segments * scale].reshape((num_segments, scale))
            means = np.mean(segments, axis=1, keepdims=True)
            cum_dev = np.cumsum(segments - means, axis=1)
            ranges = np.max(cum_dev, axis=1) - np.min(cum_dev, axis=1)
            stds = np.std(segments, axis=1, ddof=1)
            valid = stds > 0
            if np.any(valid):
                rs_list.append(np.mean(ranges[valid] / stds[valid]))
            else:
                rs_list.append(1.0)
        if len(rs_list) < 2:
            return 0.5
        try:
            h, _ = np.polyfit(np.log(scales[:len(rs_list)]), np.log(rs_list), 1)
            self.last_h = float(np.clip(h, 0.0, 1.0))
            return self.last_h
        except Exception:
            return self.last_h

    def update_regime(self) -> str:
        current_h = self.calculate_vectorized_hurst()
        if self.regime == "mean_reverting":
            if current_h > 0.48:
                self.regime = "random_walk"
        elif self.regime == "trending":
            if current_h < 0.52:
                self.regime = "random_walk"
        else:
            if current_h < self.mean_revert_limit:
                self.regime = "mean_reverting"
            elif current_h > self.trend_limit:
                self.regime = "trending"
        return self.regime

class PocketTracker:
    def __init__(self) -> None:
        self.log_returns: deque[float] = deque(maxlen=1000)
        self.last_price: float | None = None
        self.tick_timestamps: deque[float] = deque(maxlen=60)
        self.manip_detector = ManipulationDetector()

    def update(self, timestamp: float, price: float) -> tuple[str, str, str, str]:
        vol_level = "LOW"
        if self.last_price is not None and self.last_price > 0 and price > 0:
            log_ret = math.log(price / self.last_price)
            self.log_returns.append(log_ret)
            if len(self.log_returns) >= 100:
                fast_returns = list(self.log_returns)[-100:]
                std_fast = np.std(fast_returns)
                std_slow = np.std(self.log_returns)
                ratio = std_fast / max(std_slow, 1e-8)
                if ratio > 2.0:
                    vol_level = "HIGH"
                elif ratio > 1.2:
                    vol_level = "MEDIUM"
                else:
                    vol_level = "LOW"
        self.last_price = price

        self.tick_timestamps.append(timestamp)
        liq_level = "LOW"
        freq = 0.0
        if len(self.tick_timestamps) >= 2:
            dt = self.tick_timestamps[-1] - self.tick_timestamps[0]
            if dt > 0:
                freq = ((len(self.tick_timestamps) - 1) / dt) * 60.0
            if freq >= 40.0:
                liq_level = "HIGH"
            elif freq >= 15.0:
                liq_level = "MEDIUM"
            else:
                liq_level = "LOW"

        manip_flags = self.manip_detector.update(timestamp, price)
        push_snap = manip_flags.get("push_snap", 0.0)
        pinning = manip_flags.get("pinning", 0.0)
        
        manip_level = "LOW"
        if push_snap >= 0.7 or pinning >= 0.7:
            manip_level = "HIGH"
        elif push_snap >= 0.3 or pinning >= 0.3:
            manip_level = "MEDIUM"
        else:
            manip_level = "LOW"
            
        pocket_state = f"Vol:{vol_level} | Liq:{liq_level} | Manip:{manip_level}"
        return vol_level, liq_level, manip_level, pocket_state

def calculate_time_offsets(timestamp: float) -> tuple[int, int]:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    mins_today = dt.hour * 60 + dt.minute
    offset_mins = (mins_today - 1320) % (24 * 60)
    offset_hour = offset_mins // 60
    offset_4hour = offset_hour // 4
    return int(offset_hour), int(offset_4hour)

def evaluate_expiry(
    ticks: list[Tick],
    timestamps: list[float],
    entry_time: float,
    entry_price: float,
    direction: str,
    expiry_seconds: int,
) -> dict[str, Any]:
    if not ticks:
        return {"outcome": "insufficient_data", "exit_time": None, "exit_price": None, "price_delta": None}
    target_time = entry_time + expiry_seconds
    
    from bisect import bisect_left
    exit_index = bisect_left(timestamps, target_time)
    if exit_index >= len(ticks):
        return {"outcome": "missing_exit", "exit_time": None, "exit_price": None, "price_delta": None}
        
    exit_tick = ticks[exit_index]
    exit_time = exit_tick.timestamp
    exit_price = exit_tick.price
    price_delta = exit_price - entry_price
    
    if price_delta == 0:
        outcome = "draw"
    elif direction == "CALL":
        outcome = "win" if price_delta > 0 else "loss"
    else:
        outcome = "win" if price_delta < 0 else "loss"
        
    return {
        "outcome": outcome,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "price_delta": round(price_delta, 8),
    }

def _net_pl_for_outcome(outcome: str, payout_pct: float) -> float:
    if outcome == "win":
        return round(payout_pct / 100.0, 6)
    if outcome == "loss":
        return -1.0
    return 0.0

def calculate_volatility_score(
    atr: float | None,
    price: float,
    returns_std: float,
    tick_frequency: float,
    max_atr_ratio: float = 0.005,
    max_returns_std: float = 0.002
) -> float:
    if price <= 0 or atr is None or atr <= 0:
        return 0.0
    atr_ratio = atr / price
    norm_atr = min(1.0, atr_ratio / max_atr_ratio)
    norm_std = min(1.0, returns_std / max_returns_std)
    frequency_multiplier = min(1.0, tick_frequency / 30.0)
    composite = (norm_atr * 0.5) + (norm_std * 0.5)
    return float(np.clip(composite * frequency_multiplier, 0.0, 1.0))

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

# --- Veto Gates and Pipeline ---

class GateContext:
    """All runtime state needed by any gate to make a veto decision."""
    def __init__(
        self,
        timestamp: float,
        price: float,
        direction: str,
        hurst_value: float,
        hurst_regime: str,
        ou_beta: float | None,
        tau_ou: float | None,
        pocket_state: str,
        vol_level: str,
        liq_level: str,
        manip_level: str,
        hour_offset: int,
        four_hour_offset: int,
        volatility_score: float,
        payout_pct: float,
        expiry_seconds: int = 0
    ) -> None:
        self.timestamp = timestamp
        self.price = price
        self.direction = direction
        self.hurst_value = hurst_value
        self.hurst_regime = hurst_regime
        self.ou_beta = ou_beta
        self.tau_ou = tau_ou
        self.pocket_state = pocket_state
        self.vol_level = vol_level
        self.liq_level = liq_level
        self.manip_level = manip_level
        self.hour_offset = hour_offset
        self.four_hour_offset = four_hour_offset
        self.volatility_score = volatility_score
        self.payout_pct = payout_pct
        self.expiry_seconds = expiry_seconds

class FilterGate(Protocol):
    enabled: bool
    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        ...

class HurstFilterGate:
    def __init__(self, config: HurstConfig) -> None:
        self.config = config
        self.enabled = config.veto_enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        if context.hurst_regime == "trending":
            return True, "hurst_veto_trend"
        elif context.hurst_regime == "random_walk":
            return True, "hurst_veto_chop"
        return False, None

class OUFilterGate:
    def __init__(self, config: OUConfig) -> None:
        self.config = config
        self.enabled = config.veto_enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        if self.config.mode == "kalman":
            if context.ou_beta is not None and context.ou_beta >= 0:
                return True, "ou_veto_explosive"
        else:  # ols
            if context.tau_ou is None:
                return True, "ou_veto_non_reverting"
        return False, None

class PocketPreSignalGate:
    def __init__(self, config: PocketConfig) -> None:
        self.config = config
        self.enabled = config.veto_enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        if context.pocket_state in self.config.exclusion_list:
            reason = f"pocket_veto_{context.pocket_state.replace(' ', '').replace('|', '_')}"
            return True, reason
        return False, None

class TimeframeFilterGate:
    def __init__(self, config: TimeframeConfig) -> None:
        self.config = config
        self.enabled = config.veto_enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        if context.four_hour_offset in self.config.exclusion_blocks:
            return True, f"timeframe_veto_block_{context.four_hour_offset}"
        return False, None

class ManipulationFilterGate:
    def __init__(self, config: ManipulationConfig) -> None:
        self.config = config
        self.enabled = config.veto_enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        severity_mapping = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        current_val = severity_mapping.get(context.manip_level, 0)
        limit_val = severity_mapping.get(self.config.min_severity_level, 3)
        if current_val >= limit_val:
            return True, f"manipulation_veto_{context.manip_level}"
        return False, None

class PocketPerCellGate:
    def __init__(self, config: PocketConfig) -> None:
        self.config = config
        self.enabled = config.veto_enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        cell_key = f"{context.pocket_state}|{context.expiry_seconds}"
        if cell_key in self.config.exclusion_list:
            return True, "pocket_expiry_veto"
        return False, None

class BayesianPerCellGate:
    def __init__(self, config: BayesianConfig, engine: BayesianUtilityEngine) -> None:
        self.config = config
        self.engine = engine
        self.enabled = config.enabled

    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        
        # 1. Credible Gate Check
        credible_ok = self.engine.verify_credible_gate(
            context.pocket_state,
            context.expiry_seconds,
            threshold=self.config.breakeven_win_rate,
            confidence=self.config.confidence_threshold
        )
        if not credible_ok:
            return True, "bayesian_veto_credible"
        
        # 2. Sizing Sizer Check
        opt_fraction, _ = self.engine.calculate_optimal_sizing(
            context.pocket_state,
            context.expiry_seconds,
            payout_pct=context.payout_pct,
            risk_aversion=self.config.risk_aversion,
            max_fraction=self.config.max_fraction
        )
        if opt_fraction <= 0.005:
            return True, "bayesian_veto_utility"
            
        return False, None

# --- Unified Backtester ---

class UnifiedBacktester:
    def __init__(self, config: UnifiedBacktestConfig) -> None:
        self.config = config
        self.oteo = OTEO()
        self.context = MarketContextEngine()
        self.regime_classifier = RegimeClassifier()
        self.pocket_tracker = PocketTracker()
        
        # Pre-filters and parameters trackers
        self.kalman_filter = KalmanFilter(config.kalman.q, config.kalman.r)
        self.hurst_tracker = UnifiedHurstTracker(
            window_size=config.hurst.window_size,
            mean_revert_limit=config.hurst.mean_revert_limit,
            trend_limit=config.hurst.trend_limit
        )
        self.ou_kalman_tracker = ParameterKalmanTracker(config.ou.q_beta, config.ou.r)
        
        # Bayesian Utility Engine
        self.bayesian_engine = BayesianUtilityEngine(
            alpha_prior=config.bayesian.alpha_prior,
            beta_prior=config.bayesian.beta_prior
        )
        
        # Veto gate pipelines
        self.pre_signal_gates = [
            HurstFilterGate(config.hurst),
            OUFilterGate(config.ou),
            PocketPreSignalGate(config.pocket),
            TimeframeFilterGate(config.timeframe),
            ManipulationFilterGate(config.manipulation),
        ]
        
        self.per_cell_gates = [
            PocketPerCellGate(config.pocket),
            BayesianPerCellGate(config.bayesian, self.bayesian_engine),
        ]
        
        # Pending trades list for walk-forward updates: list[dict]
        self.pending_trades: list[dict[str, Any]] = []
        
        # Buffer for returns std calculation (adaptive expiry)
        self._price_buffer: deque[float] = deque(maxlen=100)
        self._ou_last_price: float | None = None
        self._ou_dt_buffer: deque[float] = deque(maxlen=100)
        
        # Stats tracking
        self.veto_counts = defaultdict(int)

    def reset_trackers(self) -> None:
        self.kalman_filter = KalmanFilter(self.config.kalman.q, self.config.kalman.r)
        self.hurst_tracker = UnifiedHurstTracker(
            window_size=self.config.hurst.window_size,
            mean_revert_limit=self.config.hurst.mean_revert_limit,
            trend_limit=self.config.hurst.trend_limit
        )
        self.ou_kalman_tracker = ParameterKalmanTracker(self.config.ou.q_beta, self.config.ou.r)
        self.pending_trades.clear()
        self._price_buffer.clear()
        self._ou_last_price = None
        self._ou_dt_buffer.clear()
        self.veto_counts.clear()

    def run_file(self, path: Path) -> list[dict[str, Any]]:
        self.reset_trackers()
        ticks = load_ticks_from_file(path)
        if not ticks:
            return []
        
        asset = ticks[0].asset
        date = path.stem
        
        rows: list[dict[str, Any]] = []
        last_regime: dict[str, Any] | None = None
        timestamps = [t.timestamp for t in ticks]
        
        # Buffers for rolling OLS OU calculation
        ols_prices: deque[float] = deque(maxlen=self.config.ou.window_size + 10)
        ols_ts: deque[float] = deque(maxlen=self.config.ou.window_size + 10)

        # Clear pending trades at start of file
        self.pending_trades.clear()

        for tick in ticks:
            raw_price = tick.price
            self._price_buffer.append(raw_price)
            ols_prices.append(raw_price)
            ols_ts.append(tick.timestamp)
            
            # A. Resolve Pending Trades (Walk-Forward Bayesian Learning)
            resolved_pt = []
            for pt in self.pending_trades:
                if tick.timestamp >= pt["exit_time"]:
                    self.bayesian_engine.update_trade(pt["pocket_state"], pt["expiry_seconds"], pt["outcome"])
                    resolved_pt.append(pt)
            for pt in resolved_pt:
                self.pending_trades.remove(pt)

            # 1. Price Pre-Filtering
            if self.config.kalman.enabled:
                kalman_price = self.kalman_filter.update(raw_price)
            else:
                kalman_price = raw_price
                
            # Determine which price to feed to estimators and indicator engines
            indicator_price = kalman_price
            
            # Hurst pre-smoothing bypass logic
            if self.config.kalman.enabled and not self.config.kalman.upstream_of_hurst:
                hurst_price = raw_price
            else:
                hurst_price = kalman_price

            # 2. Update Context and Engines
            oteo_res = self.oteo.update_tick(indicator_price, timestamp=tick.timestamp)
            context_res = self.context.update_tick(indicator_price, timestamp=tick.timestamp)
            
            if bool(context_res.get("candle_closed")) and bool(context_res.get("ready")):
                self.hurst_tracker.update_regime()
                last_regime = self.regime_classifier.classify(context_res)

            # Update Hurst price buffer
            self.hurst_tracker.add_price(hurst_price)
            
            # Calculate continuous features
            h_val = self.hurst_tracker.last_h
            h_regime = self.hurst_tracker.regime
            
            # Volatility features
            atr = context_res.get("atr")
            tick_frequency = context_res.get("tick_frequency", 0.0)
            if len(self._price_buffer) >= 2:
                returns = np.diff(np.log(self._price_buffer))
                returns_std = float(np.std(returns)) if len(returns) > 0 else 0.0
            else:
                returns_std = 0.0
            v_score = calculate_volatility_score(atr, raw_price, returns_std, tick_frequency)
            
            # OU Parameter Tracking
            tau_ou = None
            ou_beta = None
            if self.config.ou.mode == "ols":
                if len(ols_prices) >= self.config.ou.window_size:
                    tau_ou = calculate_rolling_ou(np.array(ols_prices), np.array(ols_ts), self.config.ou.window_size)
            else:  # mode == "kalman"
                if self._ou_last_price is not None:
                    dt_raw = tick.timestamp - self._ou_last_price[1]
                    if dt_raw > 0:
                        self._ou_dt_buffer.append(dt_raw)
                    _, ou_beta = self.ou_kalman_tracker.update(self._ou_last_price[0], raw_price)
                    
                    dt_stable = np.mean(self._ou_dt_buffer) if self._ou_dt_buffer else 1.0
                    if ou_beta < 0 and (1.0 + ou_beta) > 1e-5:
                        theta_ou = -math.log(1.0 + ou_beta) / dt_stable
                        if theta_ou > 0:
                            tau_ou = math.log(2) / theta_ou
                self._ou_last_price = (raw_price, tick.timestamp)

            # Spike Pocket Classification
            vol_lvl, liq_lvl, manip_lvl, pocket_state = self.pocket_tracker.update(tick.timestamp, raw_price)
            hour_offset, four_hour_offset = calculate_time_offsets(tick.timestamp)

            # Create GateContext (with direction/expiry to be filled)
            gate_context = GateContext(
                timestamp=tick.timestamp,
                price=tick.price,
                direction="",
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
                expiry_seconds=0
            )

            # 3. Evaluate Policies and Signals
            if isinstance(oteo_res, dict):
                level1 = dict(oteo_res)
                level2 = apply_level2_policy(level1, context_res, enabled=True)
                level3 = None
                if last_regime is not None:
                    level3 = apply_level3_policy(level2, context_res, last_regime)
                
                # Determine which levels to backtest
                levels_to_test = []
                if self.config.indicator.level_mode == "all":
                    levels_to_test = [("L1", level1), ("L2", level2), ("L3", level3)]
                elif self.config.indicator.level_mode == "L1":
                    levels_to_test = [("L1", level1)]
                elif self.config.indicator.level_mode == "L2":
                    levels_to_test = [("L2", level2)]
                elif self.config.indicator.level_mode == "L3":
                    levels_to_test = [("L3", level3)]

                for level_name, level_signal in levels_to_test:
                    if level_signal is None or not bool(level_signal.get("actionable")):
                        continue
                    
                    direction = str(level_signal.get("recommended") or "").upper()
                    if direction not in {"CALL", "PUT"}:
                        continue

                    # Update context direction
                    gate_context.direction = direction

                    # 4. Evaluate Pre-Signal Veto Gates
                    vetoed = False
                    veto_reason = None
                    for gate in self.pre_signal_gates:
                        gate_vetoed, gate_reason = gate.evaluate(gate_context)
                        if gate_vetoed:
                            vetoed = True
                            veto_reason = gate_reason
                            break

                    # Update veto metrics
                    if vetoed:
                        self.veto_counts[veto_reason] += 1

                    # 5. Expiries & Order execution simulation
                    expiries_to_run = []
                    if self.config.expiry.mode == "static":
                        expiries_to_run = self.config.expiry.static_seconds
                    else:  # mode == "adaptive"
                        continuous_exp = self.config.expiry.adaptive_c * (1.0 - h_val) / max(v_score, 0.001)
                        # map to nearest allowed adaptive bounds
                        chosen_exp = min(self.config.expiry.adaptive_bounds, key=lambda x: abs(x - continuous_exp))
                        expiries_to_run = [int(chosen_exp)]

                    for exp in expiries_to_run:
                        cell_vetoed = vetoed
                        cell_veto_reason = veto_reason
                        
                        # Update context expiry
                        gate_context.expiry_seconds = exp

                        # Evaluate Per-Cell Veto Gates if not already vetoed upstream
                        if not cell_vetoed:
                            for gate in self.per_cell_gates:
                                gate_vetoed, gate_reason = gate.evaluate(gate_context)
                                if gate_vetoed:
                                    cell_vetoed = True
                                    cell_veto_reason = gate_reason
                                    break
                            if cell_vetoed:
                                self.veto_counts[cell_veto_reason] += 1

                        # Bayesian Utility Sizing & Logs
                        bayesian_exp_wr = 0.5
                        bayesian_lower = 0.1
                        bayesian_upper = 0.9
                        opt_fraction = 0.0
                        
                        if self.config.bayesian.enabled:
                            bayes_state = self.bayesian_engine.get_or_create_state(pocket_state, exp)
                            bayesian_exp_wr = bayes_state.expected_win_rate
                            bayesian_lower, bayesian_upper = bayes_state.get_credible_interval(
                                self.config.bayesian.confidence_threshold
                            )
                            opt_fraction, _ = self.bayesian_engine.calculate_optimal_sizing(
                                pocket_state,
                                exp,
                                payout_pct=self.config.payout_pct,
                                risk_aversion=self.config.bayesian.risk_aversion,
                                max_fraction=self.config.bayesian.max_fraction
                            )

                        expiry_res = evaluate_expiry(ticks, timestamps, tick.timestamp, tick.price, direction, exp)
                        
                        net_pl = 0.0
                        if not cell_vetoed:
                            net_pl = _net_pl_for_outcome(expiry_res["outcome"], self.config.payout_pct)
                            # Add to pending trades list for future walk-forward learning
                            self.pending_trades.append({
                                "exit_time": expiry_res["exit_time"] or (tick.timestamp + exp),
                                "pocket_state": pocket_state,
                                "expiry_seconds": exp,
                                "outcome": expiry_res["outcome"]
                            })

                        rows.append({
                            "date": date,
                            "asset": asset,
                            "level": level_name,
                            "entry_time": tick.timestamp,
                            "entry_price": tick.price,
                            "direction": direction,
                            "expiry_seconds": exp,
                            "exit_time": expiry_res["exit_time"],
                            "exit_price": expiry_res["exit_price"],
                            "price_delta": expiry_res["price_delta"],
                            "outcome": expiry_res["outcome"],
                            "net_pl": net_pl,
                            "payout_pct": self.config.payout_pct,
                            "vetoed": cell_vetoed,
                            "veto_reason": cell_veto_reason,
                            "pocket_state": pocket_state,
                            "vol_level": vol_lvl,
                            "liq_level": liq_lvl,
                            "manip_level": manip_lvl,
                            "utc_hour_offset": hour_offset,
                            "utc_4hour_offset": four_hour_offset,
                            "hurst_value": round(h_val, 3),
                            "hurst_regime": h_regime,
                            "volatility_score": round(v_score, 4),
                            "returns_std": round(returns_std, 6),
                            "tick_frequency": round(tick_frequency, 2),
                            "ou_beta": round(ou_beta, 6) if ou_beta is not None else None,
                            "ou_half_life": round(tau_ou, 1) if tau_ou is not None else None,
                            "adx_regime": context_res.get("adx_regime"),
                            "trend_direction": context_res.get("trend_direction"),
                            # Bayesian features
                            "bayesian_expected_wr": round(bayesian_exp_wr, 4),
                            "bayesian_credible_lower": round(bayesian_lower, 4),
                            "bayesian_credible_upper": round(bayesian_upper, 4),
                            "bayesian_optimal_fraction": round(opt_fraction, 4),
                        })

        return rows
