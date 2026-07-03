import json
import os
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Adjust sys.path to REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtester_app.core.engine import UnifiedBacktester, UnifiedBacktestConfig
from backtester_app.core.optimizer import run_optuna_study

CONFIG_ROOT = REPO_ROOT / "configs"
TICK_ROOT = REPO_ROOT / "app/data/tick_logs"

def load_presets() -> dict[str, Path]:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    presets = {}
    for f in CONFIG_ROOT.glob("*.json"):
        presets[f.stem.replace("_", " ").title()] = f
    return presets

def render_switchboard_tab():
    st.header("🎯 Switchboard Control Center")
    st.markdown("Configure quantitative parameters, select veto gates, and launch backtest/statement sweeps.")

    # Discover assets and dates
    if not TICK_ROOT.exists():
        st.error(f"Tick log directory not found at {TICK_ROOT}.")
        return

    assets = sorted([d.name for d in TICK_ROOT.iterdir() if d.is_dir()])
    if not assets:
        st.warning("No asset folders found in tick logs.")
        return

    presets = load_presets()

    # Initialize session state for config
    if "switchboard_config" not in st.session_state:
        # Default starting config is L3 Baseline
        st.session_state["switchboard_config"] = {
            "payout_pct": 92.0,
            "kalman": {"enabled": False, "q": 1e-9, "r": 1e-7, "upstream_of_hurst": False},
            "hurst": {"veto_enabled": False, "window_size": 300, "mean_revert_limit": 0.44, "trend_limit": 0.58, "allowed_regimes": ["mean_reverting", "random_walk", "trending"], "filter_threshold": None, "min_scale_cutoff": 12},
            "ou": {"veto_enabled": False, "mode": "kalman", "window_size": 300, "q_c": 1e-10, "q_beta": 1e-6, "r": 1e-8},
            "expiry": {"mode": "static", "static_seconds": [60, 120, 300], "adaptive_c": 10.0, "adaptive_bounds": [30, 60, 120, 300]},
            "indicator": {"level_mode": "L3", "cooldown_ticks": 30},
            "pocket": {"veto_enabled": False, "exclusion_list": [], "blacklist_assets": []},
            "timeframe": {"veto_enabled": False, "exclusion_blocks": []},
            "bayesian": {"enabled": False, "alpha_prior": 2.0, "beta_prior": 2.0, "confidence_threshold": 0.90, "breakeven_win_rate": 0.5208, "risk_aversion": 2.0, "max_fraction": 0.10},
            "manipulation": {"veto_enabled": False, "severity_threshold": 0.3},
            "oteo_gate": {"min_zscore_enabled": False, "min_zscore": 0.0, "max_zscore_enabled": False, "max_zscore": 10.0, "min_score_enabled": False, "min_score": 0.0, "max_score_enabled": False, "max_score": 100.0},
            "regime": {"enabled": False, "allowed_regimes": [], "require_stable": False},
            "oteo_params": {"min_abs_z_score": 0.35, "min_pressure_pct": 12.0, "score_center": 0.85, "score_slope": 3.5, "cooldown_ticks": 30, "buffer_size": 300, "pressure_window": 24, "macro_window": 120},
            "volatility": {"high_ratio": 2.0, "medium_ratio": 1.2},
            "liquidity": {"high_freq": 40.0, "medium_freq": 15.0}
        }

    # Preset dropdown selector
    col_pre, col_act = st.columns([2, 2])
    with col_pre:
        preset_options = ["Custom (Modified)"] + list(presets.keys())
        selected_preset = st.selectbox("Apply Preset Profile", preset_options)
        if selected_preset != "Custom (Modified)" and st.button("Load Selected Preset"):
            preset_path = presets[selected_preset]
            with open(preset_path, "r", encoding="utf-8") as f:
                loaded_cfg = json.load(f)
                # Parse to ensure all fields exist
                temp_cfg = UnifiedBacktestConfig.from_dict(loaded_cfg)
                st.session_state["switchboard_config"] = temp_cfg.to_dict()
                st.success(f"Preset '{selected_preset}' loaded successfully.")
                st.rerun()

    # Split-pane layout
    left_pane, right_pane = st.columns([1, 1])

    with left_pane:
        st.subheader("⚙️ Filter & Parameter Matrix")
        cfg = st.session_state["switchboard_config"]

        # Payout percentage
        cfg["payout_pct"] = st.slider("Payout Percentage %", 10.0, 100.0, float(cfg.get("payout_pct", 92.0)), step=1.0)

        # Kalman Filter
        with st.expander("🟢 Kalman Smoother", expanded=cfg["kalman"]["enabled"]):
            cfg["kalman"]["enabled"] = st.checkbox("Enable Kalman Smoothing", value=cfg["kalman"]["enabled"], key="kf_enable")
            cfg["kalman"]["q"] = st.number_input("Process Noise Q", value=float(cfg["kalman"]["q"]), format="%.2e")
            cfg["kalman"]["r"] = st.number_input("Measurement Noise R", value=float(cfg["kalman"]["r"]), format="%.2e")
            cfg["kalman"]["upstream_of_hurst"] = st.checkbox("Feed Smoothed Prices to Hurst Estimator", value=cfg["kalman"]["upstream_of_hurst"])

        # Hurst Exponent
        with st.expander("📊 Hurst Exponent Veto", expanded=cfg["hurst"]["veto_enabled"]):
            cfg["hurst"]["veto_enabled"] = st.checkbox("Enable Hurst Veto", value=cfg["hurst"]["veto_enabled"], key="hurst_enable")
            cfg["hurst"]["window_size"] = st.number_input("Rolling Window Size", value=int(cfg["hurst"]["window_size"]), min_value=50, max_value=2000, step=50)
            cfg["hurst"]["mean_revert_limit"] = st.slider("Mean-Reverting Threshold (< H)", 0.20, 0.50, float(cfg["hurst"]["mean_revert_limit"]), step=0.01)
            cfg["hurst"]["trend_limit"] = st.slider("Trending Threshold (> H)", 0.50, 0.80, float(cfg["hurst"]["trend_limit"]), step=0.01)
            
            st.markdown("**Allowed Regimes (Whitelist)**")
            allow_mr = st.checkbox("Allow Mean-Reverting (< MR Threshold)", value="mean_reverting" in cfg["hurst"].get("allowed_regimes", ["mean_reverting", "random_walk", "trending"]))
            allow_rw = st.checkbox("Allow Random Walk (MR to Trend Threshold)", value="random_walk" in cfg["hurst"].get("allowed_regimes", ["mean_reverting", "random_walk", "trending"]))
            allow_tr = st.checkbox("Allow Trending (> Trend Threshold)", value="trending" in cfg["hurst"].get("allowed_regimes", ["mean_reverting", "random_walk", "trending"]))
            
            allowed = []
            if allow_mr: allowed.append("mean_reverting")
            if allow_rw: allowed.append("random_walk")
            if allow_tr: allowed.append("trending")
            cfg["hurst"]["allowed_regimes"] = allowed

            thresh_enabled = st.checkbox("Enable Raw Hurst Threshold Veto", value=cfg["hurst"].get("filter_threshold") is not None)
            if thresh_enabled:
                cfg["hurst"]["filter_threshold"] = st.slider("Veto if Raw H >= Threshold", 0.20, 0.90, float(cfg["hurst"].get("filter_threshold") or 0.48), step=0.01)
            else:
                cfg["hurst"]["filter_threshold"] = None
                
            cfg["hurst"]["min_scale_cutoff"] = st.number_input("Hurst Min Scale Cutoff", value=int(cfg["hurst"].get("min_scale_cutoff", 12)), min_value=4, max_value=30, step=1)

        # OU Veto
        with st.expander("🌀 Ornstein-Uhlenbeck Veto", expanded=cfg["ou"]["veto_enabled"]):
            cfg["ou"]["veto_enabled"] = st.checkbox("Enable OU Veto", value=cfg["ou"]["veto_enabled"], key="ou_enable")
            cfg["ou"]["mode"] = st.selectbox("OU Estimator Mode", ["kalman", "ols"], index=0 if cfg["ou"]["mode"] == "kalman" else 1)
            cfg["ou"]["window_size"] = st.number_input("OU OLS Window Size", value=int(cfg["ou"]["window_size"]), min_value=50, max_value=2000, step=50)
            cfg["ou"]["q_beta"] = st.number_input("OU Kalman Q Beta", value=float(cfg["ou"]["q_beta"]), format="%.2e")
            cfg["ou"]["r"] = st.number_input("OU Kalman R", value=float(cfg["ou"]["r"]), format="%.2e")

        # Expiry config
        with st.expander("⏳ Expiry Settings", expanded=True):
            cfg["expiry"]["mode"] = st.selectbox("Expiry Mode", ["static", "adaptive"], index=0 if cfg["expiry"]["mode"] == "static" else 1)
            if cfg["expiry"]["mode"] == "static":
                static_str = st.text_input("Static Expiries (comma separated seconds)", value=",".join(map(str, cfg["expiry"]["static_seconds"])))
                cfg["expiry"]["static_seconds"] = sorted([int(x.strip()) for x in static_str.split(",") if x.strip().isdigit()])
            else:
                cfg["expiry"]["adaptive_c"] = st.slider("Adaptive Scaling C", 1.0, 100.0, float(cfg["expiry"]["adaptive_c"]), step=0.5)
                bounds_str = st.text_input("Adaptive Bound Options (seconds)", value=",".join(map(str, cfg["expiry"]["adaptive_bounds"])))
                cfg["expiry"]["adaptive_bounds"] = sorted([int(x.strip()) for x in bounds_str.split(",") if x.strip().isdigit()])

        # Bayesian Gate
        with st.expander("🔮 Bayesian Credible Gate", expanded=cfg["bayesian"]["enabled"]):
            cfg["bayesian"]["enabled"] = st.checkbox("Enable Bayesian Utility Sizing & Gating", value=cfg["bayesian"]["enabled"], key="bayes_enable")
            cfg["bayesian"]["confidence_threshold"] = st.slider("Confidence Threshold", 0.50, 0.99, float(cfg["bayesian"]["confidence_threshold"]), step=0.01)
            cfg["bayesian"]["breakeven_win_rate"] = st.slider("Breakeven win rate", 0.40, 0.65, float(cfg["bayesian"]["breakeven_win_rate"]), step=0.005)
            cfg["bayesian"]["risk_aversion"] = st.slider("Risk Aversion Level (gamma)", 1.0, 5.0, float(cfg["bayesian"]["risk_aversion"]), step=0.5)
            cfg["bayesian"]["max_fraction"] = st.slider("Max Kelly Sizing Fraction", 0.01, 0.50, float(cfg["bayesian"]["max_fraction"]), step=0.01)

        # Timeframe Veto
        with st.expander("🕰️ Timeframe Exclusion blocks", expanded=cfg["timeframe"]["veto_enabled"]):
            cfg["timeframe"]["veto_enabled"] = st.checkbox("Enable Timeframe Veto", value=cfg["timeframe"]["veto_enabled"], key="tf_enable")
            tf_str = st.text_input("Excluded 4-Hour UTC blocks (comma separated 0-5)", value=",".join(map(str, cfg["timeframe"]["exclusion_blocks"])))
            cfg["timeframe"]["exclusion_blocks"] = sorted([int(x.strip()) for x in tf_str.split(",") if x.strip().isdigit() and 0 <= int(x) <= 5])

        # Pockets Veto
        with st.expander("🕳️ Spike Pocket Exclusions", expanded=cfg["pocket"]["veto_enabled"]):
            cfg["pocket"]["veto_enabled"] = st.checkbox("Enable Pocket Veto", value=cfg["pocket"]["veto_enabled"], key="pocket_enable")
            pockets_str = st.text_area("Exclusion States / Expiry Cells (one per line)", value="\n".join(cfg["pocket"]["exclusion_list"]))
            cfg["pocket"]["exclusion_list"] = [x.strip() for x in pockets_str.split("\n") if x.strip()]
            blacklist_str = st.text_input("Asset Blacklist (comma separated)", value=",".join(cfg["pocket"].get("blacklist_assets", [])))
            cfg["pocket"]["blacklist_assets"] = [x.strip() for x in blacklist_str.split(",") if x.strip()]

        # Manipulation Veto
        with st.expander("🚨 Manipulation Gate", expanded=cfg["manipulation"]["veto_enabled"]):
            cfg["manipulation"]["veto_enabled"] = st.checkbox("Enable Manipulation Veto", value=cfg["manipulation"]["veto_enabled"], key="manip_enable")
            cfg["manipulation"]["severity_threshold"] = st.slider("Severity Threshold Veto (>= value)", 0.0, 1.0, float(cfg["manipulation"].get("severity_threshold", 0.3)), step=0.05)

        # OTEO Signal Gate
        with st.expander("🎯 OTEO Signal Gate", expanded=cfg["oteo_gate"]["min_zscore_enabled"] or cfg["oteo_gate"]["min_score_enabled"]):
            cfg["oteo_gate"]["min_zscore_enabled"] = st.checkbox("Enable Min Z-Score Veto", value=cfg["oteo_gate"]["min_zscore_enabled"])
            if cfg["oteo_gate"]["min_zscore_enabled"]:
                cfg["oteo_gate"]["min_zscore"] = st.number_input("Min Z-Score", value=float(cfg["oteo_gate"]["min_zscore"]), step=0.1)
            cfg["oteo_gate"]["max_zscore_enabled"] = st.checkbox("Enable Max Z-Score Veto", value=cfg["oteo_gate"]["max_zscore_enabled"])
            if cfg["oteo_gate"]["max_zscore_enabled"]:
                cfg["oteo_gate"]["max_zscore"] = st.number_input("Max Z-Score", value=float(cfg["oteo_gate"]["max_zscore"]), step=0.1)
            cfg["oteo_gate"]["min_score_enabled"] = st.checkbox("Enable Min Score Veto", value=cfg["oteo_gate"]["min_score_enabled"])
            if cfg["oteo_gate"]["min_score_enabled"]:
                cfg["oteo_gate"]["min_score"] = st.slider("Min OTEO Score", 0.0, 100.0, float(cfg["oteo_gate"]["min_score"]), step=5.0)
            cfg["oteo_gate"]["max_score_enabled"] = st.checkbox("Enable Max Score Veto", value=cfg["oteo_gate"]["max_score_enabled"])
            if cfg["oteo_gate"]["max_score_enabled"]:
                cfg["oteo_gate"]["max_score"] = st.slider("Max OTEO Score", 0.0, 100.0, float(cfg["oteo_gate"]["max_score"]), step=5.0)

        # Regime Classifier Gate
        with st.expander("📈 ADX/CCI Market Regime Gate", expanded=cfg["regime"]["enabled"]):
            cfg["regime"]["enabled"] = st.checkbox("Enable Regime Gate", value=cfg["regime"]["enabled"])
            cfg["regime"]["require_stable"] = st.checkbox("Require Stable Regime (persistence >= 3)", value=cfg["regime"]["require_stable"])
            regimes_str = st.text_input("Allowed Regimes (comma separated, e.g. RANGE_BOUND,TREND_PULLBACK)", value=",".join(cfg["regime"].get("allowed_regimes", [])))
            cfg["regime"]["allowed_regimes"] = [x.strip() for x in regimes_str.split(",") if x.strip()]

        # OTEO Core Parameters Calibration
        with st.expander("🎛️ OTEO Core Parameters", expanded=False):
            cfg["oteo_params"]["min_abs_z_score"] = st.slider("OTEO Min Abs Z-Score", 0.1, 1.0, float(cfg["oteo_params"]["min_abs_z_score"]), step=0.05)
            cfg["oteo_params"]["min_pressure_pct"] = st.slider("OTEO Min Pressure Pct", 1.0, 50.0, float(cfg["oteo_params"]["min_pressure_pct"]), step=1.0)
            cfg["oteo_params"]["score_center"] = st.slider("OTEO Score Center (sigmoid offset)", 0.3, 2.0, float(cfg["oteo_params"]["score_center"]), step=0.05)
            cfg["oteo_params"]["score_slope"] = st.slider("OTEO Score Slope", 1.0, 10.0, float(cfg["oteo_params"]["score_slope"]), step=0.1)
            cfg["oteo_params"]["cooldown_ticks"] = st.number_input("OTEO Cooldown Ticks", value=int(cfg["oteo_params"]["cooldown_ticks"]), min_value=0, max_value=500, step=5)
            cfg["oteo_params"]["buffer_size"] = st.number_input("OTEO Buffer Size", value=int(cfg["oteo_params"]["buffer_size"]), min_value=50, max_value=1000, step=50)
            cfg["oteo_params"]["pressure_window"] = st.number_input("OTEO Pressure Window", value=int(cfg["oteo_params"]["pressure_window"]), min_value=5, max_value=100, step=5)
            cfg["oteo_params"]["macro_window"] = st.number_input("OTEO Macro Window", value=int(cfg["oteo_params"]["macro_window"]), min_value=20, max_value=500, step=10)

        # Volatility & Liquidity Thresholds
        with st.expander("🌊 Volatility & Liquidity Thresholds", expanded=False):
            st.markdown("**Volatility (Fast / Slow Standard Deviation ratio)**")
            cfg["volatility"]["high_ratio"] = st.number_input("High Volatility Ratio Threshold", value=float(cfg["volatility"]["high_ratio"]), step=0.1)
            cfg["volatility"]["medium_ratio"] = st.number_input("Medium Volatility Ratio Threshold", value=float(cfg["volatility"]["medium_ratio"]), step=0.1)
            st.markdown("**Liquidity (Ticks per minute frequency)**")
            cfg["liquidity"]["high_freq"] = st.number_input("High Liquidity Freq Threshold", value=float(cfg["liquidity"]["high_freq"]), step=1.0)
            cfg["liquidity"]["medium_freq"] = st.number_input("Medium Liquidity Freq Threshold", value=float(cfg["liquidity"]["medium_freq"]), step=1.0)

        # Save & Export configurations
        st.markdown("---")
        save_col1, save_col2 = st.columns(2)
        with save_col1:
            save_name = st.text_input("Export Config Name", "my_custom_preset")
        with save_col2:
            st.write("")
            st.write("")
            if st.button("💾 Save Config Profile"):
                target_path = CONFIG_ROOT / f"{save_name}.json"
                with open(target_path, "w", encoding="utf-8") as out:
                    json.dump(cfg, out, indent=2)
                st.success(f"Saved: {target_path.name}")
                st.rerun()

        export_col1, export_col2 = st.columns(2)
        with export_col1:
            ghost_name = st.text_input("Auto Ghost Export Name", "auto_ghost_preset")
        with export_col2:
            st.write("")
            st.write("")
            if st.button("🚀 Export to Ghost Protocol"):
                from backtester_app.core.config_bridge import backtester_to_ghost_protocol
                temp_cfg = UnifiedBacktestConfig.from_dict(cfg)
                ghost_dict = backtester_to_ghost_protocol(temp_cfg)
                target_path = CONFIG_ROOT / f"{ghost_name}.json"
                with open(target_path, "w", encoding="utf-8") as out:
                    json.dump(ghost_dict, out, indent=2)
                st.success(f"Exported: {target_path.name}")
                st.rerun()

    with right_pane:
        st.subheader("🚀 Execution Stack")

        # Select Asset
        selected_asset = st.selectbox("Asset Target", assets)
        asset_dir = TICK_ROOT / selected_asset
        available_dates = sorted([f.stem for f in asset_dir.glob("*.jsonl")])

        # Date selectors
        date_mode = st.radio("Date Selection Range", ["Last 3 days", "Custom Date Selection", "All Available Dates"], horizontal=True)
        if date_mode == "Last 3 days":
            selected_dates = available_dates[-3:] if len(available_dates) >= 3 else available_dates
        elif date_mode == "Custom Date Selection":
            selected_dates = st.multiselect("Select Target Dates", available_dates, default=available_dates[-3:] if len(available_dates) >= 3 else available_dates)
        else:
            selected_dates = available_dates

        # Execution Mode
        exec_mode = st.selectbox("Execution Mode", ["Single Backtest Sweep", "Optuna Hyperparameter Calibration"])
        
        data_source = "Tick Logs (Simulation)"
        selected_stmt = None

        if exec_mode == "Optuna Hyperparameter Calibration":
            st.subheader("⚙️ Calibration Settings")
            col_t, col_m = st.columns(2)
            with col_t:
                trials = st.number_input("Number of Optimization Trials", min_value=10, max_value=200, value=30, step=10)
            with col_m:
                metric = st.selectbox("Target Calibration Metric", ["pnl", "winrate"])
            min_trades = st.number_input("Minimum Trial Trade Count Constraint", min_value=1, max_value=200, value=15, step=5)

        st.markdown("---")
        
        if st.button("🔥 Run Execution Stack", type="primary", use_container_width=True):
            if not selected_dates and data_source == "Tick Logs (Simulation)":
                st.error("Please select at least one target date.")
                return

            status_placeholder = st.empty()
            progress_bar = st.progress(0)
            results_area = st.container()

            if exec_mode == "Single Backtest Sweep":
                # SINGLE BACKTEST RUN (In-process execution with real-time updates)
                if data_source == "Tick Logs (Simulation)":
                    status_placeholder.info("⚙️ Initializing backtest engine...")
                    engine_config = UnifiedBacktestConfig.from_dict(cfg)
                    tester = UnifiedBacktester(engine_config)
                    
                    all_rows = []
                    total_dates = len(selected_dates)
                    
                    for idx, dt in enumerate(selected_dates):
                        status_placeholder.text(f"Running simulation for {dt} ({idx+1}/{total_dates})...")
                        file_path = TICK_ROOT / selected_asset / f"{dt}.jsonl"
                        try:
                            day_rows = tester.run_file(file_path)
                            all_rows.extend(day_rows)
                        except Exception as e:
                            st.warning(f"Failed to process {dt}: {e}")
                        progress_bar.progress((idx + 1) / total_dates)

                    progress_bar.empty()
                    status_placeholder.empty()

                    if not all_rows:
                        st.warning("Simulation completed but no trade entries were generated.")
                    else:
                        st.success(f"✅ Simulation complete. Generated {len(all_rows)} signals/entries.")
                        df_res = pd.DataFrame(all_rows)
                        
                        # Store in session state for results tab
                        st.session_state["last_run_df"] = df_res
                        st.session_state["last_run_asset"] = selected_asset
                        st.session_state["last_run_completed"] = True
                        st.session_state["last_run_summary"] = {
                            "overall_stats": {
                                "settled": len(df_res[(df_res["vetoed"] == False) & (df_res["outcome"].isin(["win", "loss"]))]),
                                "wins": len(df_res[(df_res["vetoed"] == False) & (df_res["outcome"] == "win")]),
                                "net_pl": df_res[df_res["vetoed"] == False]["net_pl"].sum(),
                                "total_signals": len(df_res),
                                "total_vetoed": len(df_res[df_res["vetoed"] == True])
                            }
                        }
                        
                        # Render metrics inside Right Pane directly
                        st.markdown("### Performance Output")
                        stats = st.session_state["last_run_summary"]["overall_stats"]
                        col_r1, col_r2, col_r3 = st.columns(3)
                        col_r1.metric("Settled Trades", stats["settled"])
                        wr = (stats["wins"] / stats["settled"] * 100.0) if stats["settled"] else 0.0
                        col_r2.metric("Win-Rate", f"{wr:.2f}%")
                        col_r3.metric("Net P/L", f"{stats['net_pl']:.2f}")
                        
                        # Render simple Plotly equity curve
                        df_executed = df_res[(df_res["vetoed"] == False) & (df_res["outcome"].isin(["win", "loss"]))].copy()
                        if not df_executed.empty:
                            df_executed = df_executed.sort_values("entry_time")
                            df_executed["cum_pnl"] = df_executed["net_pl"].cumsum()
                            fig = px.line(df_executed, x="entry_time", y="cum_pnl", title="Cumulative Equity Curve", template="plotly_dark")
                            st.plotly_chart(fig, use_container_width=True)



            else:
                # OPTUNA CALIBRATION
                status_placeholder.info("🧬 Running hyperparameter calibration. Please check console outputs...")
                db_path = REPO_ROOT / "configs/optuna_studies.db"
                study_name = f"opt_{selected_asset}_{metric}"
                
                with st.spinner("Calibrating parameters... this will take a while..."):
                    try:
                        results = run_optuna_study(
                            dates=selected_dates,
                            asset=selected_asset,
                            n_trials=int(trials),
                            target_metric=metric,
                            db_path=db_path,
                            study_name=study_name,
                            min_trades=int(min_trades),
                            payout_pct=float(cfg["payout_pct"])
                        )
                        progress_bar.progress(1.0)
                        status_placeholder.empty()
                        
                        st.success("✅ Calibration study complete.")
                        st.metric(label=f"Best Calibration {metric.upper()}", value=f"{results['best_value']:.2f}")
                        st.subheader("Optimal Configuration Settings")
                        st.json(results["best_params"])
                    except Exception as e:
                        st.error(f"Optuna Calibration Study Failed: {e}")
