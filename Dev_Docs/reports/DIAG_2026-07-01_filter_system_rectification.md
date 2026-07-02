# Backtester Filter System — Diagnostic Report & Proposed Changes

**Report ID:** DIAG-2026-07-01  
**Author:** Antigravity Agent (System Architect)  
**Status:** Approved for Implementation  
**Scope:** `backtester_app/core/` filter system only (live app deferred)

---

## 1. Executive Summary

A full diagnostic review of the backtester filter system identified **2 critical bugs**, **1 major duplication**, **8 missing filter parameters**, and **several error handling violations**. This report documents each finding, its root cause, and the approved fix for any collaborator or coding agent to execute.

**Overall Health Rating:** 🟡 YELLOW — gate pipeline architecture is sound, but contains logic errors and config gaps that prevent the backtester from accurately simulating the live Auto Ghost trading environment.

---

## 2. Architecture Context

The backtester uses a **two-stage gate pipeline** to evaluate trade signals:

```
Tick Stream → OTEO Signal → Pre-Signal Gates (veto?) → Per-Expiry Gates (veto?) → Trade Record
```

**Key files:**
- Engine: [engine.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py) — 1012 lines, contains all configs, gates, and main loop
- Bayesian: [bayesian.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/bayesian.py) — 134 lines, Beta-Binomial utility engine
- Optimizer: [optimizer.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/optimizer.py) — 178 lines, Optuna integration
- Statement: [statement.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/statement.py) — 414 lines, **marked for deletion**

**Live app counterpart:** [auto_ghost.py](file:///c:/v3/OTC_SNIPER/app/backend/services/auto_ghost.py) — the production Auto Ghost controller whose `AutoGhostConfig` should be parameter-compatible with the backtester's `UnifiedBacktestConfig`.

---

## 3. Findings & Approved Changes

### 3.1 CRITICAL: Hurst Veto Logic Inversion

**Location:** [engine.py L569-L581](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L569-L581) — `HurstFilterGate.evaluate()`

**What it does now:**
```python
if context.hurst_regime == "trending":     return True   # VETO trending
elif context.hurst_regime == "random_walk": return True  # VETO random_walk
return False  # ONLY allows mean_reverting
```

**Why this is wrong:** The Hurst regime state machine produces three states: `mean_reverting` (H < 0.44), `random_walk` (0.44 ≤ H ≤ 0.58), and `trending` (H > 0.58). The current code blocks 2 of 3 regimes, which discards ~80-90% of signals since `random_walk` is the dominant state.

**Same bug exists in live app:** [hurst_adaptive_expiry.py L176-L188](file:///c:/v3/OTC_SNIPER/app/backend/services/extensions/hurst_adaptive_expiry.py#L176-L188) has identical inverted logic. Live app fix is deferred to a follow-up task.

**Approved fix:** Replace hardcoded veto logic with a **configurable regime whitelist**. Add `allowed_regimes: list[str]` to `HurstConfig` with default `["mean_reverting", "random_walk", "trending"]` (all allowed). The switchboard UI exposes checkboxes so the user can experimentally determine which regime combinations produce optimal results. The gate vetoes any regime NOT in the allowed list.

**Also add:** A numeric `filter_threshold: float | None` matching the Auto Ghost's `hurst_filter_threshold` (L1 gate that vetoes when raw H value ≥ threshold).

---

### 3.2 DELETE: Statement Replayer (Dead Code)

**Location:** [statement.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/statement.py) — entire file (414 lines)

**Why delete:** 
1. User confirmed they will use CLI for statement analysis; this code will not be used
2. The file contains a **190-line reimplementation** of the engine's tick processing loop ([L196-L384](file:///c:/v3/OTC_SNIPER/backtester_app/core/statement.py#L196-L384)) — the exact anti-pattern the original refactoring eliminated from `optimizer.py`
3. Contains a **verbatim copy** of `calculate_rolling_ou()` ([L386-L413](file:///c:/v3/OTC_SNIPER/backtester_app/core/statement.py#L386-L413)) that already exists in [engine.py L495-L522](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L495-L522)
4. Ignores the `upstream_of_hurst` config flag — [L251](file:///c:/v3/OTC_SNIPER/backtester_app/core/statement.py#L251) always feeds smoothed price to Hurst, unlike engine.py which has routing logic at [L793-L798](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L793-L798)

**Impact:** Removes 414 lines and eliminates all code duplication risk.

**Also clean up:** Remove `POStatementReplayer` imports from [switchboard.py](file:///c:/v3/OTC_SNIPER/backtester_app/ui/tabs/switchboard.py), [datasets.py](file:///c:/v3/OTC_SNIPER/backtester_app/ui/tabs/datasets.py), and delete `test_statement_replayer_mock_run` from [test_backtester_engine.py](file:///c:/v3/OTC_SNIPER/test_backtester_engine.py).

---

### 3.3 MISSING: OTEO Signal Gate (Z-Score & Confidence Bounds)

**Context:** The Auto Ghost has configurable z-score bounds ([auto_ghost.py L559-L581](file:///c:/v3/OTC_SNIPER/app/backend/services/auto_ghost.py#L559-L581)) and confidence/score bounds ([L518-L537](file:///c:/v3/OTC_SNIPER/app/backend/services/auto_ghost.py#L518-L537)). The backtester has **no equivalent** — it accepts all OTEO signals regardless of z-score or score value.

**Approved fix:** Add a new `OTEOGateConfig` dataclass and `OTEOSignalGate` class to `engine.py`. Fields:
- `min_zscore_enabled`, `min_zscore` — minimum z-score bound
- `max_zscore_enabled`, `max_zscore` — maximum z-score bound
- `min_score_enabled`, `min_score` — minimum OTEO score bound
- `max_score_enabled`, `max_score` — maximum OTEO score bound

Requires adding `oteo_score` and `z_score` to the `GateContext` class.

---

### 3.4 MISSING: ADX Regime Gate

**Context:** The Auto Ghost has `regime_gate_enabled`, `allowed_regimes`, and `require_regime_stable` ([auto_ghost.py L585-L598](file:///c:/v3/OTC_SNIPER/app/backend/services/auto_ghost.py#L585-L598)). These filter on the ADX-based `RegimeClassifier` output (RANGE_BOUND, TREND_REVERSAL, TREND_PULLBACK, STRONG_MOMENTUM, BREAKOUT, CHOPPY). The backtester has **no equivalent**.

**Approved fix:** Add `RegimeGateConfig` and `RegimeGate`. This is separate from the Hurst regime gate — Hurst measures fractal persistence, the regime classifier uses ADX/CCI/structure.

Requires adding `regime_label` and `regime_stable` to `GateContext`. The regime data is already computed in the engine loop ([engine.py L805](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L805)) but not currently exposed to the gate context.

---

### 3.5 MISSING: OTEO Core Parameter Passthrough

**Context:** The OTEO indicator in [oteo.py](file:///c:/v3/OTC_SNIPER/app/backend/services/oteo.py) has an `OTEOConfig` with 12 tunable parameters (buffer_size, min_abs_z_score, score_center, score_slope, min_pressure_pct, etc.). The backtester instantiates OTEO with **hardcoded defaults** at [engine.py L690](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L690):

```python
self.oteo = OTEO()  # No config passed!
```

**Why this matters:** If the backtester can't tune these parameters, Optuna can never find optimal OTEO sensitivity settings. The user specifically wants OTEO core params to be Optuna-calibratable.

**Approved fix:** Add `OTEOParamsConfig` to `UnifiedBacktestConfig` containing the key tunable OTEO parameters. In `UnifiedBacktester.__init__()`, construct `OTEOConfig` from these values and pass to `OTEO(config=...)`.

Add OTEO parameters to the Optuna search space in [optimizer.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/optimizer.py).

---

### 3.6 ALIGNMENT: Volatility & Liquidity Thresholds

**Context:** The `PocketTracker` ([engine.py L372-L424](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L372-L424)) uses hardcoded thresholds to classify volatility and liquidity:
- Volatility: `ratio > 2.0` → HIGH, `ratio > 1.2` → MEDIUM, else LOW
- Liquidity: `freq >= 40.0` → HIGH, `freq >= 15.0` → MEDIUM, else LOW

These thresholds are not configurable. The pocket state string (`Vol:HIGH | Liq:LOW | Manip:MEDIUM`) drives the Bayesian cell keying, so we can't change the categorical format.

**Approved fix:** Keep LOW/MEDIUM/HIGH categories but make the numeric thresholds configurable via new `VolatilityConfig` and `LiquidityConfig` dataclasses. This preserves the Bayesian cell architecture while allowing threshold tuning.

**Design rationale:** The Bayesian engine uses pocket state strings as dictionary keys for its Beta-Binomial state tracking. Changing to numeric values would break the state machine. Configurable thresholds give numeric tunability without architectural disruption.

---

### 3.7 ALIGNMENT: Manipulation Severity Scale

**Context:** The Auto Ghost uses a 0.0–1.0 float for `manipulation_severity_threshold` ([auto_ghost.py L36](file:///c:/v3/OTC_SNIPER/app/backend/services/auto_ghost.py#L36)), comparing directly against raw `push_snap`/`pinning` severity floats. The backtester uses string-based "HIGH"/"MEDIUM"/"LOW" comparison ([engine.py L624-L637](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L624-L637)).

**Approved fix:** Change `ManipulationConfig` to use numeric `severity_threshold: float` (0.0-1.0). Update `ManipulationFilterGate` to compare raw severity floats from `PocketTracker`. Add raw `manip_push_snap` and `manip_pinning` floats to `GateContext`.

---

### 3.8 NEW: Config Bridge for Auto Ghost Export

**Context:** The user wants to calibrate filter parameters in the backtester and export them as a JSON config that the Auto Ghost can import. Currently no mapping exists between the two config schemas.

**Approved fix:** Create [config_bridge.py](file:///c:/v3/OTC_SNIPER/backtester_app/core/config_bridge.py) with two functions:
- `backtester_to_ghost_protocol(config) -> dict` — maps `UnifiedBacktestConfig` fields to `AutoGhostConfig` field names
- `ghost_protocol_to_backtester(data) -> dict` — reverse mapping

Add "Export to Ghost Protocol" button to the switchboard UI.

---

### 3.9 ERROR HANDLING: Silent Exception Swallowing

**Locations:**
| File | Line | Issue |
|---|---|---|
| [optimizer.py L126-L128](file:///c:/v3/OTC_SNIPER/backtester_app/core/optimizer.py#L126-L128) | `except Exception: pass` | Silently ignores ALL errors during optimization |
| [engine.py L354](file:///c:/v3/OTC_SNIPER/backtester_app/core/engine.py#L354) | `except Exception: return self.last_h` | Returns stale Hurst on polyfit failure |

**Approved fix:** Replace all bare `except Exception: pass` with `except Exception as e: logger.warning(...)`. Add `import logging` and `logger = logging.getLogger(__name__)` to all core modules. This complies with Core Principle #8 (Zero Silent Failures).

---

## 4. Files Changed Summary

| File | Action | Lines Changed (est.) |
|---|---|---|
| `backtester_app/core/statement.py` | **DELETE** | -414 |
| `backtester_app/core/engine.py` | **MODIFY** | +180 / -30 |
| `backtester_app/core/optimizer.py` | **MODIFY** | +25 / -5 |
| `backtester_app/core/config_bridge.py` | **NEW** | +80 |
| `backtester_app/ui/tabs/switchboard.py` | **MODIFY** | +60 / -20 |
| `backtester_app/ui/tabs/datasets.py` | **MODIFY** | -15 |
| `test_backtester_engine.py` | **MODIFY** | +60 / -20 |

**Net effect:** ~-130 lines (deletion of statement.py outweighs additions)

---

## 5. Parameter Mapping Reference

Complete mapping between `AutoGhostConfig` and `UnifiedBacktestConfig` after implementation:

| Auto Ghost Field | Backtester Field | Status |
|---|---|---|
| `hurst_filter_enabled` | `hurst.veto_enabled` | ✅ Exists |
| `hurst_filter_threshold` | `hurst.filter_threshold` | 🆕 Adding |
| `hurst_mean_revert_threshold` | `hurst.mean_revert_limit` | ✅ Exists |
| `hurst_trend_threshold` | `hurst.trend_limit` | ✅ Exists |
| `hurst_min_scale_cutoff` | `hurst.min_scale_cutoff` | 🆕 Adding |
| `min_zscore_enabled` / `min_zscore` | `oteo_gate.min_zscore_enabled/min_zscore` | 🆕 Adding |
| `max_zscore_enabled` / `max_zscore` | `oteo_gate.max_zscore_enabled/max_zscore` | 🆕 Adding |
| `min_confidence` / `min_confidence_enabled` | `oteo_gate.min_score_enabled/min_score` | 🆕 Adding |
| `max_confidence` / `max_confidence_enabled` | `oteo_gate.max_score_enabled/max_score` | 🆕 Adding |
| `regime_gate_enabled` | `regime.enabled` | 🆕 Adding |
| `allowed_regimes` | `regime.allowed_regimes` | 🆕 Adding |
| `require_regime_stable` | `regime.require_stable` | 🆕 Adding |
| `block_on_manipulation` | `manipulation.veto_enabled` | ✅ Exists |
| `manipulation_severity_threshold` | `manipulation.severity_threshold` | 🔄 Aligning (string→float) |
| `blacklist_assets` | `pocket.blacklist_assets` | 🆕 Adding |
| `minimum_payout_pct` | `payout_pct` (used as both value and minimum) | ✅ Exists |
| `per_asset_cooldown_seconds` | `indicator.cooldown_ticks` | ✅ Conceptual match |
| OTEO `min_abs_z_score` | `oteo_params.min_abs_z_score` | 🆕 Adding |
| OTEO `score_center` | `oteo_params.score_center` | 🆕 Adding |
| OTEO `score_slope` | `oteo_params.score_slope` | 🆕 Adding |
| OTEO `min_pressure_pct` | `oteo_params.min_pressure_pct` | 🆕 Adding |

**Not applicable to backtester** (live-only concerns):
`max_concurrent_trades`, `max_session_trades`, `max_drawdown_amount`, `drawdown_cooldown_seconds`, `oteo_ai_enabled`, `ai_pulse_enabled`, `ai_trade_interval`

---

## 6. Deferred Work (Follow-up Tasks)

1. **Fix `hurst_adaptive_expiry.py`** in the live app — same Hurst veto inversion bug
2. **Live app config import** — add API endpoint to ingest Ghost Protocol JSON from backtester
3. **Bayesian per-cell state export** — allow backtester to export learned Bayesian priors for use in live trading

---

*End of report.*
