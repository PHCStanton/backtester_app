# Technical Context — Backtester App

## Technologies Used
- **Python (3.10+)**: Primary language.
- **Streamlit**: Web dashboard framework.
- **Optuna**: Bayesian optimization and hyperparameter tuning.
- **NumPy / SciPy**: Vectorized math, regression algorithms, and Beta distribution modeling.
- **Pandas**: Data transformation, parsing, and dataframe exports.
- **Plotly**: Dynamic equity curves and parameters search visualization.

## Development Setup
- **Conda Environment**: `QuFLX-v2` (`conda activate QuFLX-v2`).
- **Dashboard Command**: `conda run --no-capture-output -n QuFLX-v2 streamlit run backtester_app/ui/dashboard.py`.
- **PowerShell Launcher**: `run.ps1` runs the dashboard on Windows using conda run directly.

## Technical Constraints
- **PowerShell Syntax**: Do not chain commands with `&&` as it can fail on default Windows shells. Use separate command lines or `;`.
- **Workspace Isolation**: Save and load configuration files exclusively from the root `/configs/` folder.
- **Memory Optimization**: Use vectorized pandas calculations where possible to prevent UI thread blocking in Streamlit when loading large tick files.

## Coding Standards
- Mandatory type-hinting on class fields and function parameters.
- Absolute paths resolved relative to `REPO_ROOT` to avoid execution environment path mismatches.
- Strict error handling: Empty `except: pass` blocks are prohibited. Log warnings or raise explicit exceptions.

## Testing Requirements
- **Framework**: `pytest`.
- **Execution**: `conda run -n QuFLX-v2 pytest test_backtester_engine.py`.
- **Target Coverage**: Core configurations, config bridge symmetry, filter gates correctness, Optuna TRIAL execution, and filter independence.
