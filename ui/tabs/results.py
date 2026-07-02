import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

def render_results_tab():
    st.header("📊 Comparative Performance Results")
    st.markdown("Compare the equity curves and metrics of your current switchboard stack configurations with cached reference stacks.")

    # Fetch last run from session state
    has_last_run = "last_run_df" in st.session_state and st.session_state["last_run_completed"]
    
    if not has_last_run:
        st.info("No active sweep has been executed yet in the session. Go to the Switchboard tab and launch a run first.")
        return

    df_current = st.session_state["last_run_df"]
    asset_current = st.session_state["last_run_asset"]
    
    # Initialize cache list in session state if not existing
    if "cached_stacks" not in st.session_state:
        st.session_state["cached_stacks"] = {}

    # Check if this is PO Statement or normal simulation
    is_po_replay = asset_current == "PO_Statement"

    # Compute stats for current run
    if not is_po_replay:
        # Standard backtest rows
        df_exec = df_current[(df_current["vetoed"] == False) & (df_current["outcome"].isin(["win", "loss"]))].copy()
        total_trades = len(df_exec)
        wins = len(df_exec[df_exec["outcome"] == "win"])
        win_rate = (wins / total_trades * 100.0) if total_trades else 0.0
        net_pl = df_current[df_current["vetoed"] == False]["net_pl"].sum()
        total_signals = len(df_current)
        total_vetoed = len(df_current[df_current["vetoed"] == True])
        suppression_rate = (total_vetoed / total_signals * 100.0) if total_signals else 0.0
    else:
        # PO Statement Replay results
        df_exec = df_current[df_current["outcome"] != "draw"].copy()
        total_trades = len(df_exec)
        wins = len(df_exec[df_exec["outcome"] == "win"])
        win_rate = (wins / total_trades * 100.0) if total_trades else 0.0
        
        # Net P/L calculation
        net_pl = 0.0
        for _, row in df_current.iterrows():
            if row["stack_aligned"]:
                if row["outcome"] == "win":
                    net_pl += row["profit"]
                elif row["outcome"] == "loss":
                    net_pl -= row["amount"]
        suppression_rate = 100.0 - (len(df_current[df_current["stack_aligned"] == True]) / len(df_current) * 100.0) if len(df_current) else 0.0

    current_stats = {
        "Name": "Current Run",
        "Asset": asset_current,
        "Trades": total_trades,
        "Win Rate": f"{win_rate:.2f}%",
        "Net P/L": round(net_pl, 2),
        "Suppression Rate": f"{suppression_rate:.2f}%",
        "raw_win_rate_val": win_rate,
        "raw_pnl_val": net_pl,
        "df": df_exec
    }

    # Action buttons for caching
    st.subheader("💾 Session Caching Reference Center")
    col_c1, col_c2 = st.columns([3, 1])
    with col_c1:
        cache_name = st.text_input("Name this cache reference slot (e.g. 'Kalman Only')", "Reference Stack A")
    with col_c2:
        st.write("")
        st.write("")
        if st.button("🔥 Cache Current Stack"):
            st.session_state["cached_stacks"][cache_name] = current_stats
            st.success(f"Successfully cached run into slot: '{cache_name}'")
            st.rerun()

    # Comparative Grid Metrics Table
    st.subheader("📈 Performance Metrics Grid Comparison")
    
    # Build list of rows to display
    display_rows = [current_stats]
    for name, cached_stats in st.session_state["cached_stacks"].items():
        row_copy = dict(cached_stats)
        row_copy["Name"] = name
        display_rows.append(row_copy)
        
    df_metrics = pd.DataFrame([{
        "Stack Configuration": r["Name"],
        "Target Asset": r["Asset"],
        "Settled Trades": r["Trades"],
        "Win Rate %": r["Win Rate"],
        "Net P/L": r["Net P/L"],
        "Suppression Rate": r["Suppression Rate"]
    } for r in display_rows])
    
    st.table(df_metrics)

    # Plot comparative equity curves
    st.subheader("📊 Comparative Cumulative Equity Curves")
    
    fig = go.Figure()
    
    # 1. Add current run line
    if not df_exec.empty:
        df_sorted = df_exec.sort_values(by="entry_time" if "entry_time" in df_exec.columns else "adjusted_ts")
        if not is_po_replay:
            cum_pnl = df_sorted["net_pl"].cumsum()
            x_vals = df_sorted["entry_time"]
        else:
            # Reconstruct statement aligned cumulative profits
            pnl_accum = []
            running_pnl = 0.0
            for _, row in df_sorted.iterrows():
                if row["stack_aligned"]:
                    if row["outcome"] == "win":
                        running_pnl += row["profit"]
                    elif row["outcome"] == "loss":
                        running_pnl -= row["amount"]
                pnl_accum.append(running_pnl)
            cum_pnl = pnl_accum
            x_vals = df_sorted["adjusted_ts"]
            
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=cum_pnl,
            mode="lines",
            name="Current Run (Active Stack)",
            line=dict(color="#00ff66", width=3)
        ))

    # 2. Add cached references lines
    colors = ["#ff00cc", "#58a6ff", "#ffcc00", "#ff3333", "#00ffff"]
    for idx, (name, r) in enumerate(st.session_state["cached_stacks"].items()):
        df_cached = r["df"]
        if df_cached.empty: continue
        
        df_cached_sorted = df_cached.sort_values(by="entry_time" if "entry_time" in df_cached.columns else "adjusted_ts")
        if r["Asset"] != "PO_Statement":
            cum_pnl_c = df_cached_sorted["net_pl"].cumsum()
            x_vals_c = df_cached_sorted["entry_time"]
        else:
            pnl_accum_c = []
            running_pnl_c = 0.0
            for _, row in df_cached_sorted.iterrows():
                if row["stack_aligned"]:
                    if row["outcome"] == "win":
                        running_pnl_c += row["profit"]
                    elif row["outcome"] == "loss":
                        running_pnl_c -= row["amount"]
                pnl_accum_c.append(running_pnl_c)
            cum_pnl_c = pnl_accum_c
            x_vals_c = df_cached_sorted["adjusted_ts"]

        color = colors[idx % len(colors)]
        fig.add_trace(go.Scatter(
            x=x_vals_c,
            y=cum_pnl_c,
            mode="lines",
            name=name,
            line=dict(color=color, width=2, dash="dash")
        ))
        
    fig.update_layout(
        title="Comparative Walk-Forward Equity Growth Curves",
        xaxis_title="Execution time (timestamp)",
        yaxis_title="Accumulated P/L units / profit",
        template="plotly_dark"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # Veto Reason distribution analysis for current run
    if not is_po_replay:
        st.subheader("🔍 Current Veto Gate Suppression Analysis")
        # Extract veto reason counts from running session
        # Read from backtester counts if we run a single backtest
        if "last_run_summary" in st.session_state:
            # We can reconstruct it from the dataframe's veto_reason counts
            reasons = df_current[df_current["vetoed"] == True]["veto_reason"].value_counts()
            if not reasons.empty:
                fig_veto = px.bar(
                    x=reasons.values,
                    y=[str(x).replace("_", " ").title() for x in reasons.index],
                    orientation="h",
                    labels={"x": "Veto Count", "y": "Gate Filter"},
                    title="Veto Distribution by Gate Reason",
                    template="plotly_dark",
                    color=reasons.values,
                    color_continuous_scale="Reds"
                )
                fig_veto.update_layout(yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig_veto, use_container_width=True)
            else:
                st.info("No vetoes were triggered in this run configuration.")
    else:
        # Replay vetoes
        st.subheader("🔍 Replay Veto Gate Suppression Analysis")
        reasons = df_current[df_current["stack_aligned"] == False]["veto_reason"].value_counts()
        if not reasons.empty:
            fig_veto = px.bar(
                x=reasons.values,
                y=[str(x).replace("_", " ").title() for x in reasons.index],
                orientation="h",
                labels={"x": "Veto Count", "y": "Gate Filter"},
                title="Veto Distribution by Gate Reason",
                template="plotly_dark",
                color=reasons.values,
                color_continuous_scale="Reds"
            )
            fig_veto.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_veto, use_container_width=True)
        else:
            st.info("No vetoes were triggered during Statement Replay.")
