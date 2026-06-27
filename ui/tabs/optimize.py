import streamlit as st
import json
from pathlib import Path
from backtester_app.core.optimizer import run_optuna_study

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
TICK_ROOT = REPO_ROOT / "app/data/tick_logs"
CONFIG_ROOT = REPO_ROOT / "configs"
OPTUNA_DB_DIR = REPO_ROOT / "backtester_app/configs"

def render_optimize_tab():
    st.header("🧪 Optuna Strategy Parameter Calibration")
    st.markdown("Run automated hyperparameter searches to optimize thresholds for the Kalman Filter, Hurst exponent limits, and OU tracking gains.")

    if not TICK_ROOT.exists():
        st.error(f"Tick log directory not found at {TICK_ROOT}.")
        return

    assets = sorted([d.name for d in TICK_ROOT.iterdir() if d.is_dir()])
    if not assets:
        st.warning("No asset folders found.")
        return

    col1, col2 = st.columns(2)
    with col1:
        selected_asset = st.selectbox("Select Asset to Optimize", assets)
    
    asset_dir = TICK_ROOT / selected_asset
    available_dates = sorted([f.stem for f in asset_dir.glob("*.jsonl")])

    with col2:
        selected_dates = st.multiselect(
            "Select Training Date Range (Recommend 3-5 days for optimization speed)",
            available_dates,
            default=available_dates[-3:] if len(available_dates) >= 3 else available_dates
        )

    st.markdown("---")

    # 1. Optuna configuration
    st.subheader("⚙️ Optimizer Settings")
    
    col_t, col_m, col_c = st.columns(3)
    with col_t:
        trials = st.number_input("Number of Optimization Trials", min_value=10, max_value=500, value=50, step=10)
    with col_m:
        metric = st.selectbox("Target Objective Metric", ["pnl", "winrate"])
    with col_c:
        min_trades = st.number_input("Minimum Trade Count Constraint", min_value=1, max_value=200, value=15, step=5)

    st.markdown("---")

    # 2. Trigger optimization
    if st.button("🧬 Launch Parameter Optimization Study", type="primary"):
        if not selected_dates:
            st.error("Please select at least one training date.")
            return

        status_placeholder = st.empty()
        status_placeholder.info("🧬 Initializing Optuna study and launching parallel workers...")
        
        db_path = OPTUNA_DB_DIR / "optuna_studies.db"
        study_name = f"opt_{selected_asset}_{metric}"

        with st.spinner("Crunching numbers... this may take a few minutes depending on trials and days..."):
            try:
                results = run_optuna_study(
                    dates=selected_dates,
                    asset=selected_asset,
                    n_trials=int(trials),
                    target_metric=metric,
                    db_path=db_path,
                    study_name=study_name,
                    min_trades=int(min_trades)
                )

                status_placeholder.empty()
                st.success("✅ Optuna Optimization Study Completed!")

                # 3. Render Results
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric(
                        label=f"Best Found Objective ({metric.upper()})",
                        value=f"{results['best_value']:.2f}" if metric == "pnl" else f"{results['best_value']:.2f}%"
                    )
                    st.write(f"Total Trials run: `{results['total_trials']}`")

                with col_res2:
                    st.subheader("Optimal Parameter Profile")
                    st.json(results["best_params"])

                st.markdown("---")
                
                # 4. Save optimized config
                st.subheader("💾 Export Strategy Profile")
                profile_name = st.text_input("Profile Name", f"opt_{selected_asset}_{metric}").strip()
                
                if st.button("Save Profile to configs/"):
                    if not profile_name:
                        st.error("Profile name cannot be empty.")
                    else:
                        # Build full configuration using optimal parameters
                        bp = results["best_params"]
                        full_config = {
                            "payout_pct": 92.0,
                            "kalman": {
                                "enabled": bp.get("kalman_enabled", False),
                                "q": bp.get("kalman_q", 1e-9),
                                "r": bp.get("kalman_r", 1e-7),
                                "upstream_of_hurst": bp.get("kalman_upstream_of_hurst", False)
                            },
                            "hurst": {
                                "veto_enabled": bp.get("hurst_veto_enabled", False),
                                "window_size": 300,
                                "mean_revert_limit": bp.get("hurst_mean_revert_limit", 0.44),
                                "trend_limit": bp.get("hurst_trend_limit", 0.58)
                            },
                            "ou": {
                                "veto_enabled": bp.get("ou_veto_enabled", False),
                                "mode": "kalman",
                                "window_size": 300,
                                "q_c": 1e-10,
                                "q_beta": bp.get("ou_q_beta", 1e-6),
                                "r": bp.get("ou_r", 1e-8)
                            },
                            "expiry": {
                                "mode": bp.get("expiry_mode", "static"),
                                "static_seconds": [60, 120, 300],
                                "adaptive_c": bp.get("expiry_adaptive_c", 10.0),
                                "adaptive_bounds": [30, 60, 120, 300]
                            },
                            "indicator": {
                                "level_mode": "L3",
                                "cooldown_ticks": 30
                            },
                            "pocket": {
                                "veto_enabled": True,
                                "exclusion_list": [
                                    "Vol:LOW | Liq:HIGH | Manip:MEDIUM",
                                    "Vol:LOW | Liq:HIGH | Manip:LOW"
                                ]
                            },
                            "timeframe": {
                                "veto_enabled": True,
                                "exclusion_blocks": [0, 4, 5]
                            },
                            "bayesian": {
                                "enabled": False  # defaults to disabled for raw parameters
                            }
                        }

                        export_path = CONFIG_ROOT / f"{profile_name}.json"
                        with open(export_path, "w", encoding="utf-8") as out:
                            json.dump(full_config, out, indent=2)
                        st.success(f"💾 Profile saved successfully to {export_path.name}!")

            except Exception as e:
                status_placeholder.empty()
                st.error(f"Failed to run Optuna study: {e}")
                import traceback
                st.code(traceback.format_exc())

# Dummy wrapper so streamlit doesn't crash on layout imports
if __name__ == "__main__":
    pass
