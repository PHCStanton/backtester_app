import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as object_plots
from pathlib import Path
from scipy.stats import beta as scipy_beta

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_ROOT = REPO_ROOT / "app/backtesting/results/unified"

def render_ml_explorer_tab():
    st.header("🧬 Bayesian State & Machine Learning Feature Explorer")
    st.markdown("Explore the continuous quantitative features logged in `trades_raw.csv` and analyze the Bayesian PDF curves of Spike Pockets.")

    if not REPORT_ROOT.exists():
        st.warning("No backtest results directory found yet.")
        return

    assets_with_reports = sorted([d.name.replace("_unified", "") for d in REPORT_ROOT.iterdir() if d.is_dir()])
    if not assets_with_reports:
        st.info("No unified backtest reports found.")
        return

    selected_asset = st.selectbox("Select Asset to Explore", assets_with_reports, key="ml_asset_sel")
    report_dir = REPORT_ROOT / f"{selected_asset}_unified"
    csv_path = report_dir / "trades_raw.csv"

    if not csv_path.exists():
        st.error("Trades raw CSV log not found for the selected asset.")
        return

    # Load dataset
    # Safe optimized load of necessary columns only with sampling for large files
    try:
        file_size_mb = csv_path.stat().st_size / (1024 * 1024)
        first_row = pd.read_csv(csv_path, nrows=1)
        needed_cols = [
            "outcome", "pocket_state", "expiry_seconds", "hurst_value", 
            "volatility_score", "returns_std", "tick_frequency", "ou_beta", 
            "ou_half_life", "oteo_score", "z_score", "net_pl", "vetoed"
        ]
        cols_to_use = [c for c in needed_cols if c in first_row.columns]
        
        if file_size_mb > 30:
            st.warning(f"Trades log is large ({file_size_mb:.1f} MB). Sampling 10% of rows to optimize memory and speed...")
            df = pd.read_csv(csv_path, usecols=cols_to_use, skiprows=lambda i: i > 0 and i % 10 != 0)
        else:
            df = pd.read_csv(csv_path, usecols=cols_to_use)
    except Exception as e:
        st.error(f"Error loading trades log: {e}")
        df = pd.DataFrame()
    
    st.markdown("---")

    # 1. Bayesian PDF tab section
    st.subheader("🔮 Bayesian Probability Density Functions (Beta-Binomial Updates)")
    st.markdown("Visualize the probability distribution of success for specific pocket states. More trades shift the PDF curve to narrow uncertainty.")

    # Group trades by pocket_state and expiry to get counts of wins/losses
    pocket_stats = df[df["outcome"].isin(["win", "loss"])].groupby(["pocket_state", "expiry_seconds", "outcome"]).size().unstack(fill_value=0)
    
    if not pocket_stats.empty:
        # Re-index if wins/losses columns are missing
        if "win" not in pocket_stats.columns:
            pocket_stats["win"] = 0
        if "loss" not in pocket_stats.columns:
            pocket_stats["loss"] = 0
            
        pocket_keys = [f"{idx[0]} | Expiry: {idx[1]}s" for idx in pocket_stats.index]
        selected_key = st.selectbox("Select Spike Pocket State & Expiry for Bayesian curve", pocket_keys)
        
        # Parse selected key
        selected_state = selected_key.split(" | Expiry:")[0].strip()
        selected_exp = int(selected_key.split(" | Expiry:")[1].replace("s", "").strip())
        
        row = pocket_stats.loc[(selected_state, selected_exp)]
        wins = int(row["win"])
        losses = int(row["loss"])
        total = wins + losses
        
        # Bayesian prior
        alpha_prior = 2.0
        beta_prior = 2.0
        alpha_post = alpha_prior + wins
        beta_post = beta_prior + losses
        
        # Calculate expected win rate & credible intervals
        expected_wr = alpha_post / (alpha_post + beta_post)
        lower_90, upper_90 = scipy_beta.ppf(0.05, alpha_post, beta_post), scipy_beta.ppf(0.95, alpha_post, beta_post)
        prob_above_be = 1.0 - scipy_beta.cdf(0.5208, alpha_post, beta_post)

        # Plotly Beta PDF curve
        x = np.linspace(0.0, 1.0, 500)
        y_pdf = scipy_beta.pdf(x, alpha_post, beta_post)
        
        fig_pdf = object_plots.Figure()
        fig_pdf.add_trace(object_plots.Scatter(
            x=x, y=y_pdf,
            mode='lines',
            name='Posterior PDF',
            line=dict(color='#ff00cc', width=3),
            fill='tozeroy'
        ))
        
        # Add Breakeven Win-rate marker
        fig_pdf.add_shape(
            type="line",
            x0=0.5208, y0=0, x1=0.5208, y1=max(y_pdf) * 1.1,
            line=dict(color="Red", width=2, dash="dash")
        )
        
        fig_pdf.update_layout(
            title=f"Bayesian Win-Rate Probability Density Function<br>({selected_state} at {selected_exp}s)",
            xaxis_title="Win-Rate Probability",
            yaxis_title="Probability Density",
            template="plotly_dark"
        )
        
        st.plotly_chart(fig_pdf, use_container_width=True)
        
        # Render metrics row
        col_bayes1, col_bayes2, col_bayes3 = st.columns(3)
        with col_bayes1:
            st.metric("Raw Win-Rate (Wins/Total)", f"{(wins/total*100.0) if total else 0.0:.2f}% (n={total})")
        with col_bayes2:
            st.metric("Bayesian Expected Win-Rate", f"{expected_wr*100.0:.2f}%")
        with col_bayes3:
            st.metric("90% Credible Interval (Uncertainty Range)", f"[{lower_90*100.0:.1f}%, {upper_90*100.0:.1f}%]")
            
        st.markdown(f"Confidence that win-rate is above breakeven (52.08%): **{prob_above_be * 100.0:.2f}%**")
    else:
        st.info("No settled trade data available to compute Bayesian updates.")

    st.markdown("---")

    # 2. Correlation Matrix
    st.subheader("🔗 Continuous Feature Correlation Analysis")
    st.markdown("See how continuous mathematical parameters correlate with the binary trade outcome (win/loss).")
    
    # Filter executed settled trades
    df_executed = df[(df["vetoed"] == False) & (df["outcome"].isin(["win", "loss"]))].copy()
    if not df_executed.empty:
        df_executed["is_win"] = (df_executed["outcome"] == "win").astype(int)
        
        corr_cols = [
            "hurst_value", "volatility_score", "returns_std", 
            "tick_frequency", "ou_beta", "ou_half_life", 
            "oteo_score", "z_score", "is_win"
        ]
        
        # Filter existing columns
        existing_cols = [c for c in corr_cols if c in df_executed.columns]
        corr_matrix = df_executed[existing_cols].corr()
        
        # Clean labels
        clean_labels = [c.replace("_", " ").title() for c in existing_cols]
        
        fig_corr = px.imshow(
            corr_matrix.values,
            x=clean_labels,
            y=clean_labels,
            color_continuous_scale="RdBu",
            color_continuous_midpoint=0,
            title="Pearson Correlation Matrix Heatmap",
            labels=dict(color="Correlation"),
            template="plotly_dark",
            text_auto=".2f"
        )
        st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.info("No executed trades available to calculate correlation matrix.")

    st.markdown("---")

    # 3. Interactive Rule Tester
    st.subheader("🔬 Interactive Quantitative Rule Tester")
    st.markdown("Interactively test custom filter rules on the backtest dataset to see if they increase trade win expectancy.")
    
    col_rule1, col_rule2 = st.columns(2)
    with col_rule1:
        max_hurst = st.slider("Hurst Exponent Max (Strict MR filter)", 0.30, 0.60, 0.60, step=0.01)
        min_vol = st.slider("Volatility Score Min (Avoid flat chop)", 0.0, 0.20, 0.0, step=0.005)
    with col_rule2:
        max_ou_beta = st.slider("OU Kalman Beta Max (Explosive trend veto)", -1.0, 0.20, 0.20, step=0.01)
        has_oteo = "oteo_score" in df.columns
        if has_oteo:
            min_score = st.slider("Min OTEO score threshold", 50, 95, 55, step=5)
        else:
            st.info("OTEO score not available in this backtest run.")
            min_score = None

    # Filter dataframe based on user thresholds
    # We apply these on raw logs (even vetoed ones) to simulate the custom combination
    mask = (
        (df["hurst_value"] <= max_hurst) &
        (df["volatility_score"] >= min_vol) &
        ((df["ou_beta"].isna()) | (df["ou_beta"] <= max_ou_beta)) &
        (df["outcome"].isin(["win", "loss"]))
    )
    if has_oteo and min_score is not None:
        mask = mask & (df["oteo_score"] >= min_score)

    filtered_df = df[mask].copy()
    
    if not filtered_df.empty:
        f_wins = len(filtered_df[filtered_df["outcome"] == "win"])
        f_total = len(filtered_df)
        f_wr = (f_wins / f_total * 100.0) if f_total else 0.0
        f_pnl = filtered_df["net_pl"].sum()
        
        st.markdown(f"#### Results with custom rules applied:")
        col_res_r1, col_res_r2, col_res_r3 = st.columns(3)
        with col_res_r1:
            st.metric("Total Trades Passed", f"{f_total}")
        with col_res_r2:
            st.metric("Simulated Win-Rate", f"{f_wr:.2f}%")
        with col_res_r3:
            st.metric("Simulated Net P/L", f"{f_pnl:.2f}")
    else:
        st.warning("No trades match the selected filter combination.")
