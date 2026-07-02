# Product Context — Backtester App

## Project Purpose
The Backtester App is a standalone quantitative simulation, visualization, and calibration tool designed for the OTC SNIPER v3 system. It enables developers and traders to test trading ideas, optimize filter parameters, and validate OTEO indicator policies on historical tick data before deploying them to the live Auto Ghost trading engine.

## Problem Statement
Prior to this system:
1. **Disconnected execution environments**: Live trading (Auto Ghost) and backtesting used different configuration structures and slightly different indicator behaviors.
2. **Hardcoded heuristics**: Critical filters (like the Hurst exponent regime veto) were hardcoded, making it impossible to experimentally calibrate them.
3. **Lack of calibration parameters**: Core indicator settings (like OTEO z-score bounds and confidence centers) were fixed in code, preventing algorithmic search (Optuna) from finding optimal sensitivity parameters.
4. **Maintenance overhead**: Legacy features like the PO statement replayer duplicated massive chunks of the tick processing loop, introducing logic drift and bugs.

## Intended Users
- Algorithmic and Quantitative Traders.
- System developers optimizing trading strategies.
- Risk managers calibrating veto gates.

## Core Functionality
- **Switchboard Dashboard**: A Streamlit interface to configure stack presets, activate/deactivate individual filter gates, and visualize results side-by-side.
- **Sequential Tick Backtesting**: A deterministic, pure-Python simulation engine that runs on raw tick logs (JSONL format) and records trade metrics (win rates, net P&L).
- **Optuna Parametric Search**: Optimizes configuration combinations (Kalman, Hurst, OU, OTEO, Bayesian) to maximize P&L or Win Rate.
- **Multi-Gate Pipeline**: Sequentially applies pre-signal filters (Kalman, Hurst, OU, OTEO, ADX, manipulation, timeframe) and per-cell filters (pocket, Bayesian utility).
- **Config Bridge**: Seamlessly exports backtest parameters to the live Auto Ghost trading engine in Ghost Protocol JSON format.

## Success Metrics
- **Zero Drift**: Simulated backtest outcomes perfectly match live dry-run strategy decisions under identical market conditions.
- **Seamless Deployability**: Calibrated parameters can be exported and imported into Auto Ghost with zero manual translation.
- **Improved Risk-Adjusted Returns**: Optimized filter parameters successfully identify and block unprofitable market regimes (like high trend or manipulation).
