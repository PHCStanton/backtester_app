# Project Roadmap: Standalone Quantitative Backtester App

This roadmap outlines the milestones, phases, and task checklist for developing the Standalone Backtester Application in the [backtester_app](file:///c:/v3/OTC_SNIPER/backtester_app) directory.

---

## Phased Development Schedule

### Phase 1: Foundations & Structure (Milestone 1)
*   **Goal**: Set up directories, dependencies, and verify Streamlit runtime.
*   **Tasks**:
    *   Create directories: `core/`, `ui/`, `ui/tabs/`, `configs/`.
    *   Write `requirements.txt` containing dependencies.
    *   Write `ui/dashboard.py` (basic structure).
    *   Create helper script `run.ps1` to start Streamlit.
    *   *Verification*: Launch Streamlit server and verify UI runs on localhost.

### Phase 2: Core Estimators & Optuna Integration (Milestone 2)
*   **Goal**: Port core backtesting engine, implement Optuna optimizations, and write the Bayesian utility calculator.
*   **Tasks**:
    *   Implement `core/engine.py` (modular tick replay engine with config-driven vetoes).
    *   Implement `core/bayesian.py` (Beta-Binomial conjugate update, 95% Credible Interval calculation, and Power Utility sizing).
    *   Implement `core/optimizer.py` (Optuna trials runner mapping Kalman, Hurst, OU, and pockets search space).
    *   *Verification*: Run a CLI-based Optuna study over a 3-day tick sample.

### Phase 3: Visual Reporting & Sweep Tabs (Milestone 3)
*   **Goal**: Implement the Config Constructor, Subprocess Sweeper, and Plotly charts.
*   **Tasks**:
    *   Implement `ui/tabs/run_sweep.py` (config selectors, subprocess executor, progress tracking).
    *   Implement `ui/tabs/results_viewer.py` (equity curves, timezone blocks bar charts, veto gate distributions).
    *   *Verification*: Run a full 74-day sweep from the UI and verify reports render.

### Phase 4: Pattern Explorer & Calibration Tabs (Milestone 4)
*   **Goal**: Implement the Optuna monitor and Bayesian ML explorer pages.
*   **Tasks**:
    *   Implement `ui/tabs/optimize.py` (Optuna configuration inputs, real-time trials table, optimization plots).
    *   Implement `ui/tabs/ml_explorer.py` (PDF curves of Bayesian states, Pearson correlation matrix, rule generator).
    *   *Verification*: Run an interactive rule check on `trades_raw.csv` using the UI.

---

## Detailed Task Checklist

- [ ] **Phase 1: Foundations**
  - [ ] Initialize `backtester_app/` structure
  - [ ] Write `requirements.txt`
  - [ ] Implement `run.ps1` helper script
  - [ ] Verify Streamlit server starts up cleanly
- [ ] **Phase 2: Core Estimators**
  - [ ] Port backtesting loop to `core/engine.py`
  - [ ] Add Beta-Binomial update state tracking to `core/bayesian.py`
  - [ ] Add credible interval and expected utility sizing to `core/bayesian.py`
  - [ ] Create search space definition in `core/optimizer.py`
- [ ] **Phase 3: Visual Reporting**
  - [ ] Build interactive config builder inputs
  - [ ] Build bulk run script subprocess wrapper
  - [ ] Add Plotly charts for P/L and Veto reasons
  - [ ] Render pocket heatmap matrix
- [ ] **Phase 4: Optimization & Exploration**
  - [ ] Connect Optuna trials output to UI
  - [ ] Add correlation matrix plotting
  - [ ] Implement Bayesian Beta PDF curve visualizer
