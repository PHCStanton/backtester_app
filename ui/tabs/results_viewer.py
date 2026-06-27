import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as object_plots
from pathlib import Path

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_ROOT = REPO_ROOT / "app/backtesting/results/unified"

def render_results_viewer_tab():
    st.header("📊 Backtest Results & Visualizations")
    
    if not REPORT_ROOT.exists():
        st.warning("No backtest results directory found yet. Please run a sweep first.")
        return

    # 1. Select Asset report
    assets_with_reports = sorted([d.name.replace("_unified", "") for d in REPORT_ROOT.iterdir() if d.is_dir()])
    if not assets_with_reports:
        st.info("No unified backtest reports found. Run a sweep on Tab 1 to generate data.")
        return

    selected_asset = st.selectbox("Select Asset Report to Load", assets_with_reports)
    report_dir = REPORT_ROOT / f"{selected_asset}_unified"
    
    summary_path = report_dir / "unified_bulk_report_summary.json"
    csv_path = report_dir / "trades_raw.csv"

    if not summary_path.exists():
        st.error("Summary JSON report not found for the selected asset.")
        return

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    # 2. Key Metrics Rows
    stats = summary["overall_stats"]
    st.subheader("📈 Overall Performance Summary")
    
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    with col_stat1:
        st.metric("Total Trades", f"{stats['settled']}")
    with col_stat2:
        wr = (stats["wins"] / stats["settled"] * 100.0) if stats["settled"] else 0.0
        st.metric("Win-Rate", f"{wr:.2f}%")
    with col_stat3:
        st.metric("Net P/L (Units)", f"{stats['net_pl']:.2f}")
    with col_stat4:
        suppression = (stats["total_vetoed"] / stats["total_signals"] * 100.0) if stats["total_signals"] else 0.0
        st.metric("Suppression Rate", f"{suppression:.2f}%")

    st.markdown("---")

    # 3. Equity Curve and Performance plots
    st.subheader("📊 Visual Breakdown")
    
    col_plot1, col_plot2 = st.columns(2)
    
    # Render Cumulative Equity Curve if CSV exists
    with col_plot1:
        if csv_path.exists():
            st.markdown("### Cumulative Equity Curve")
            # Safe optimized load of necessary columns only
            try:
                file_size_mb = csv_path.stat().st_size / (1024 * 1024)
                if file_size_mb > 30:
                    st.warning(f"Trades log is large ({file_size_mb:.1f} MB). Loading optimized columns...")
                
                first_row = pd.read_csv(csv_path, nrows=1)
                cols_to_use = [c for c in ["vetoed", "outcome", "entry_time", "net_pl"] if c in first_row.columns]
                df = pd.read_csv(csv_path, usecols=cols_to_use)
            except Exception as e:
                st.error(f"Error loading trades log: {e}")
                df = pd.DataFrame()
            
            # Filter non-vetoed settled trades
            df_executed = df[(df["vetoed"] == False) & (df["outcome"].isin(["win", "loss"]))].copy()
            if not df_executed.empty:
                # Sort by entry time
                df_executed = df_executed.sort_values("entry_time")
                df_executed["cumulative_pnl"] = df_executed["net_pl"].cumsum()
                
                # Plotly line chart
                fig_equity = px.line(
                    df_executed,
                    x="entry_time",
                    y="cumulative_pnl",
                    labels={"entry_time": "Tick Entry Time (unix)", "cumulative_pnl": "Cumulative Net P/L (units)"},
                    title=f"Walk-Forward P/L Growth Curve ({selected_asset})",
                    template="plotly_dark"
                )
                fig_equity.update_traces(line=dict(color="#00ff66", width=2))
                st.plotly_chart(fig_equity, use_container_width=True)
            else:
                st.info("No executed trades to plot equity curve.")
        else:
            st.info("Raw trades log CSV not found. Run a new backtest sweep to generate details.")

    # Render Veto Reason Breakdown
    with col_plot2:
        st.markdown("### Veto Gate Reason Analysis")
        veto_data = summary["veto_totals"]
        if veto_data:
            # Sort veto reasons by count
            sorted_vetos = sorted(veto_data.items(), key=lambda x: x[1], reverse=True)
            reasons = [v[0].replace("_", " ").title() for v in sorted_vetos]
            counts = [v[1] for v in sorted_vetos]
            
            fig_veto = px.bar(
                x=counts,
                y=reasons,
                orientation="h",
                labels={"x": "Veto Count", "y": "Gate Filter"},
                title="Veto Distribution by Gate Reason",
                template="plotly_dark",
                color=counts,
                color_continuous_scale="Reds"
            )
            fig_veto.update_layout(yaxis=dict(autorange="reversed")) # top reason first
            st.plotly_chart(fig_veto, use_container_width=True)
        else:
            st.info("No signals were vetoed.")

    st.markdown("---")

    # 4. Timeframe Blocks Performance
    st.subheader("🕰️ Timeframe Blocks Performance")
    block_data = summary["block_totals"]
    if block_data:
        blocks = list(block_data.keys())
        pnl_values = [block_data[b]["net_pl"] for b in blocks]
        
        # Color coding: green for profit, red for loss
        colors = ["#00ff66" if p >= 0 else "#ff3333" for p in pnl_values]
        
        fig_blocks = object_plots.Figure(
            data=[
                object_plots.Bar(
                    x=[f"Block {b} (UTC)" for b in blocks],
                    y=pnl_values,
                    marker_color=colors
                )
            ]
        )
        fig_blocks.update_layout(
            title="Net P/L by 4-Hour Timeframe Blocks",
            xaxis_title="Time block interval",
            yaxis_title="Net P/L",
            template="plotly_dark"
        )
        st.plotly_chart(fig_blocks, use_container_width=True)
    
    st.markdown("---")

    # 5. Pockets Performance Heatmap Matrix
    st.subheader("🕳️ Spike Pocket win-rate matrix")
    matrix_data = summary["matrix_pool"]
    if matrix_data:
        # Extract unique states and expiries
        expiries = sorted(list({int(k.split("|")[-1]) for k in matrix_data.keys()}))
        states = sorted(list({"|".join(k.split("|")[:-1]) for k in matrix_data.keys()}))
        
        # Build 2D matrix
        z_win_rates = []
        hover_texts = []
        
        for state in states:
            wr_row = []
            txt_row = []
            for exp in expiries:
                key = f"{state}|{exp}"
                cell = matrix_data.get(key)
                if cell:
                    wins = cell["wins"]
                    losses = cell["losses"]
                    total = wins + losses
                    wr = (wins / total * 100.0) if total else 0.0
                    wr_row.append(wr)
                    txt_row.append(f"State: {state}<br>Expiry: {exp}s<br>Win-Rate: {wr:.2f}% (n={total})")
                else:
                    wr_row.append(None)
                    txt_row.append("No Data")
            z_win_rates.append(wr_row)
            hover_texts.append(txt_row)

        fig_matrix = object_plots.Figure(
            data=object_plots.Heatmap(
                z=z_win_rates,
                x=[f"{exp}s" for exp in expiries],
                y=states,
                hovertext=hover_texts,
                hoverinfo="text",
                colorscale="Viridis",
                colorbar=dict(title="Win-Rate %")
            )
        )
        fig_matrix.update_layout(
            title="Win-Rate Heatmap per Spike Pocket State × Expiry duration",
            xaxis_title="Expiry Duration",
            yaxis_title="Spike Pocket State (Vol | Liq | Manip)",
            template="plotly_dark",
            height=400
        )
        st.plotly_chart(fig_matrix, use_container_width=True)
    else:
        st.info("No pocket matrix data generated.")
