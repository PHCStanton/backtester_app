# Active Context — Backtester App

## Current Work
Implementing the Filter System Rectification and Config Alignment Plan:
- Deprecating the PO statement replayer module (`statement.py`) and all associated UI tabs/test references to eliminate duplicated tick looping logic.
- Rectifying the Hurst exponent veto logic to utilize a configurable regime whitelist instead of hardcoded vetoes.
- Introducing new filter gates for OTEO signal bounds (z-score, confidence/score) and ADX regime classification to align with Auto Ghost.
- Adding OTEO core parameters configuration and Optuna search space support.
- Building the Config Bridge to export calibrated parameters directly as Ghost Protocol JSON.

## Recent Changes
- Diagnostic review completed and saved to `backtester_app/Dev_Docs/reports/DIAG_2026-07-01_filter_system_rectification.md`.
- Implementation plan created and approved.
- Initialized Setup of the generic coding agent memory files in `.agent-memory-backtester/`.

## Next Steps
1. **Phase 1**: Delete `backtester_app/core/statement.py` and clean up dependencies.
2. **Phase 2**: Implement configurable Hurst allowed regimes inside `engine.py`.
3. **Phase 3**: Implement OTEOSignalGate, RegimeGate, Volatility/Liquidity threshold configurations, and Manipulation severity alignments inside `engine.py`.
4. **Phase 4**: Map core OTEO parameters to constructor inputs in `engine.py` and update the search space in `optimizer.py`.
5. **Phase 5**: Build `config_bridge.py`, integrate with Switchboard UI, clean up swallowed exceptions, and add unit test coverage.

## Blockers
- None.
