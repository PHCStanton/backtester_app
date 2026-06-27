# Standalone Backtester Autoresearch Guide

This folder contains a custom implementation of Andrej Karpathy's `autoresearch` agentic loop, adapted specifically for the `Backtest_App` quantitative strategy search.

The agent loop autonomously updates trading logic in `strategy_candidate.py`, runs the backtester on tick logs, parses results, and commits or discards changes using Git based on a mathematical objective fitness score.

---

## Folder Structure

*   [`run_backtest_loop.py`](file:///c:/v3/OTC_SNIPER/backtester_app/autoresearch/run_backtest_loop.py): The main orchestrator script that queries the xAI API, manages execution, and handles Git branches.
*   [`strategy_candidate.py`](file:///c:/v3/OTC_SNIPER/backtester_app/autoresearch/strategy_candidate.py): The **mutable target script** containing the strategy vetoes and expiry logic. The LLM edits this file.
*   [`eval_harness.py`](file:///c:/v3/OTC_SNIPER/backtester_app/autoresearch/eval_harness.py): The **immutable evaluation harness** that loads ticks, runs the strategy, and outputs validation metrics.
*   [`program.md`](file:///c:/v3/OTC_SNIPER/backtester_app/autoresearch/program.md): Natural language instructions for the agent (editable by the human researcher).
*   `results.tsv`: Experiment logs containing Git hashes, metrics, and description logs (untracked by Git).

---

## Setup & Execution

### 1. Requirements
Ensure you are in the `QuFLX-v2` Conda environment and have your xAI API key set in the `app/.env` file:
```ini
GROK_API_KEY=xai-your-api-key-here
```

### 2. Launch the Loop
To start the autonomous search:
```powershell
conda activate QuFLX-v2
cd c:\v3\OTC_SNIPER\backtester_app\autoresearch
python run_backtest_loop.py
```

### 3. Customize Model Choice
By default, the loop uses `"grok-4.3"`. If you want to use the flagship reasoning model `"grok-4.20"`, run:
```powershell
$env:GROK_MODEL="grok-4.20"
python run_backtest_loop.py
```

---

## Customizing the Optimization Target

The harness computes a composite **Fitness Score**:
$$\text{Fitness} = \text{Win Rate} \times \ln(\text{Total Trades})$$
*Condition:* If $\text{Win Rate} < 52.08\%$, the fitness drops to `0.0` (breakeven gate).

You can modify the evaluation dataset, indicators, or fitness function inside [`eval_harness.py`](file:///c:/v3/OTC_SNIPER/backtester_app/autoresearch/eval_harness.py) to target different assets or risk constraints (like maximum drawdowns or profit factors).
