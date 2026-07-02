# System Patterns — Backtester App

## Architecture Overview
The Backtester application uses a clean, decoupled architecture:
- **Core Simulation Engines (`core/`)**: Pure Python modules containing deterministic logic, state management, and parameter optimization.
- **Frontend Presentation (`ui/`)**: Declarative Streamlit interface for configuration, real-time logging, and interactive Plotly charting.
- **Unified Settings (`configs/`)**: Central directory at the repository root storing configuration presets and study databases.

```
+--------------------------------------------+
|                Streamlit UI                |
|  (Switchboard, Results, Explorer, Dataset)  |
+--------------------------------------------+
                      |
                      v
+--------------------------------------------+
|             UnifiedBacktester              |
|        (Core Execution Engine Loop)        |
+--------------------------------------------+
        |                      |
        v                      v
+---------------+      +---------------------+
|  Filter Gates |      |   Analysis Engine   |
|  (Protocol)   |      |  (Bayesian Utility) |
+---------------+      +---------------------+
```

## Key Design Patterns

### FilterGate Protocol
Every filter gate implements a simple protocol to evaluate trades:
```python
class FilterGate(Protocol):
    enabled: bool
    def evaluate(self, context: GateContext) -> Tuple[bool, str | None]:
        ...
```
- If a filter is disabled (`enabled=False`), it immediately returns `False, None` to bypass execution with zero CPU overhead.
- This protocol guarantees that filters are completely independent and can be composed in any sequence.

### Walk-Forward Bayesian Learning
Simulates real-time, online learning by postponing outcome updates until the trade's exit time:
- Active trades are added to a `pending_trades` list.
- On each tick, the engine checks if the current timestamp exceeds the exit time of any pending trades.
- Once exited, the outcome (win/loss) is updated in the `BayesianUtilityEngine` prior to evaluating subsequent trade signals.

## Data Flow
1. **Tick Ingestion**: Loads tick files (JSONL) and validates timestamps and prices.
2. **Context Tracker Updates**: Iterates sequentially over ticks to feed core estimators (Kalman Filter, Hurst Tracker, OU Parameter Tracker, Pocket Tracker).
3. **Signal Generation**: Evaluates Level 1, 2, and 3 policies via OTEO and MarketContextEngine.
4. **Veto Gates Pipelines**: Evaluates Pre-Signal Gates. If allowed, iterates through target expiries and evaluates Per-Cell Gates.
5. **Execution Simulation**: Simulates contract outcome using the nearest available exit tick.
6. **Walk-Forward Feedback**: Commits outcomes back to the Bayesian engine.

## Significant Technical Decisions
- **Decoupled Business Logic**: No Streamlit UI component performs mathematical calculations; all metrics (volatility score, returns std, win rate, utility fraction) are computed in the `core/` modules.
- **Configurable Categorical Gates**: Volatility/Liquidity classification outputs LOW/MEDIUM/HIGH categories to preserve Bayesian dictionary keys, but their underlying numeric thresholds are fully configurable.
- **Defensive Error Handling**: Replaces bare try-except blocks with explicit warnings to maintain codebase health and prevent silent failures during Optuna optimization runs.
