# Strategy Configurations Registry

This document lists the existing and proposed strategy configuration files used by the Standalone Backtester Application. All configuration profiles are stored in the [configs/](file:///c:/v3/OTC_SNIPER/configs/) directory.

---

## 1. Existing Configurations

### 1.1 Baseline Profile (`baseline_config.json`)
*   **Design Intent**: Serves as the raw, unfiltered baseline to measure core indicator edge. It runs sweeps across all static expiries without applying any regime veto gates.
*   **Active Features**:
    *   Hurst Veto: **Disabled**
    *   OU Veto: **Disabled**
    *   Pocket Veto: **Disabled**
    *   Timeframe Veto: **Disabled**
    *   Bayesian Engine: **Disabled**
    *   Expiry Mode: **Static Sweep** (`[15, 30, 60, 90, 120, 180, 300]` seconds)
*   **Best Used For**: Getting raw performance baselines and capturing raw signal occurrences across different volatility states.

### 1.2 Hurst-Only Profile (`hurst_only_config.json`)
*   **Design Intent**: Backtests performance when raw ticks are passed directly to the Hurst exponent R/S mean-reversion filter and Ornstein-Uhlenbeck tracking gate, completely bypassing Kalman pre-smoothing.
*   **Active Features**:
    *   Hurst Veto: **Enabled** (MR limit: `0.44`, Trend limit: `0.58`)
    *   OU Veto: **Enabled** (Kalman beta-tracking mode)
    *   Pocket Veto: **Disabled**
    *   Timeframe Veto: **Disabled**
    *   Bayesian Engine: **Disabled**
    *   Expiry Mode: **Static Sweep**
*   **Best Used For**: Benchmarking execution without the phase lag introduced by price-smoothing filters.

### 1.3 Hybrid Optimal Profile (`hybrid_optimal_config.json`)
*   **Design Intent**: Integrates indicator price pre-smoothing with active regime gators. Indicator calculations use Kalman-smoothed prices, while the Hurst R/S exponent is computed on raw prices to avoid dampening high-frequency mean-reverting microstructure noise.
*   **Active Features**:
    *   Kalman Smoothing on Indicators: **Enabled** ($Q = 10^{-9}, R = 10^{-7}$)
    *   Hurst Veto: **Enabled** (MR limit: `0.44`)
    *   OU Veto: **Enabled** (Kalman Beta tracking, $Q_\beta = 10^{-6}, R = 10^{-8}$)
    *   Pocket Veto: **Disabled**
    *   Timeframe Veto: **Disabled**
    *   Bayesian Engine: **Disabled**
    *   Expiry Mode: **Static Sweep**
*   **Best Used For**: Running low-noise indicator sweeps while preserving mean-reversion gator protections.

---

## 2. Proposed Configurations (To Be Created)

### 2.1 Bayesian expected utility Gated Profile (`bayesian_gated_config.json`)
*   **Design Intent**: Implements real-time walk-forward probability filtering and capital allocation using power expected utility (Kelly-style sizing).
*   **Key Parameters**:
    ```json
    "bayesian": {
      "enabled": true,
      "alpha_prior": 2.0,
      "beta_prior": 2.0,
      "confidence_threshold": 0.90,
      "breakeven_win_rate": 0.5208,
      "risk_aversion": 2.0,
      "max_fraction": 0.10
    }
    ```
*   **Veto Logic**: Suppresses entries if the 90% credible interval win probability falls below the breakeven win rate (52.08% at 92% payout), or if the optimal utility sizing fraction evaluates to zero (high uncertainty).

### 2.2 Volatility-Adaptive Expiries Profile (`vol_adaptive_expiry_config.json`)
*   **Design Intent**: Focuses on optimizing the volatility-adaptive contract duration formula:
    $$\text{Expiry} = C \cdot \frac{1 - H}{V}$$
    with specific scaling constants $C$, bypassing the standard static sweeps.
*   **Key Parameters**:
    ```json
    "expiry": {
      "mode": "adaptive",
      "adaptive_c": 10.0,
      "adaptive_bounds": [30, 60, 120, 300]
    }
    ```
*   **Veto Logic**: Minimizes gator vetoes to isolate the efficacy of dynamic contract durations.

### 2.3 Strict Mean-Reversion Pivot Profile (`strict_mr_pivot_config.json`)
*   **Design Intent**: Targets only high-probability, deep counter-trend micro-reversals by restricting trading to Level 3 Pivot signals under heavy mean-reverting regimes.
*   **Key Parameters**:
    ```json
    "hurst": {
      "veto_enabled": true,
      "mean_revert_limit": 0.40
    },
    "indicator": {
      "level_mode": "L3"
    }
    ```
*   **Veto Logic**: Vetoes any trade if the Hurst exponent exceeds `0.40`, restricting execution strictly to strong mean-reverting states.

### 2.4 Operational Guardrails Profile (`operational_guardrails_config.json`)
*   **Design Intent**: Applies structural blocklists on timeframes and market structure states derived from empirical drawdown analyses.
*   **Key Parameters**:
    ```json
    "timeframe": {
      "veto_enabled": true,
      "exclusion_blocks": [0, 4, 5]
    },
    "pocket": {
      "veto_enabled": true,
      "exclusion_list": [
        "Vol:LOW | Liq:HIGH | Manip:MEDIUM",
        "Vol:LOW | Liq:HIGH | Manip:LOW"
      ]
    }
    ```
*   **Veto Logic**: Vetoes trades during rollover hours (UTC 00:00, 04:00, 05:00) and low-volatility pockets where historical win expectancy is below breakeven.
