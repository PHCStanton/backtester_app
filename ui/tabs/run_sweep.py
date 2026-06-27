import streamlit as st
import subprocess
import sys
import json
from pathlib import Path

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
TICK_ROOT = REPO_ROOT / "app/data/tick_logs"
CONFIG_ROOT = REPO_ROOT / "configs"

def render_run_sweep_tab():
    st.header("🎯 Single & Bulk Backtest Sweeps")
    st.markdown("Configure parameters and launch parallel sweeps over historical daily tick files.")

    # 1. Discover assets and dates
    if not TICK_ROOT.exists():
        st.error(f"Tick log directory not found at {TICK_ROOT}. Please make sure you have data files.")
        return

    assets = sorted([d.name for d in TICK_ROOT.iterdir() if d.is_dir()])
    if not assets:
        st.warning("No asset folders found in tick logs.")
        return

    col1, col2 = st.columns(2)
    with col1:
        selected_asset = st.selectbox("Select Asset", assets)
    
    asset_dir = TICK_ROOT / selected_asset
    available_dates = sorted([f.stem for f in asset_dir.glob("*.jsonl")])

    with col2:
        date_selection_mode = st.radio("Date Mode", ["All Available Ticks", "Custom Date List"], horizontal=True)

    if date_selection_mode == "Custom Date List":
        selected_dates = st.multiselect("Select Dates", available_dates, default=available_dates[-3:] if len(available_dates) >= 3 else available_dates)
    else:
        selected_dates = available_dates

    st.markdown("---")

    # 2. Strategy Config Selector
    st.subheader("⚙️ Strategy Configuration Profile")
    
    # Load local configurations
    available_configs = sorted([f.name for f in CONFIG_ROOT.glob("*.json")])
    if available_configs:
        selected_config_file = st.selectbox("Select Strategy Config File", available_configs)
        config_path = CONFIG_ROOT / selected_config_file
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # Display config preview
        with st.expander("🔍 Preview Configuration Parameters"):
            st.json(config_data)
    else:
        st.warning("No config files found in configs/ directory.")
        return

    # 3. Execution parameters
    st.subheader("🚀 Execution Settings")
    col_w, col_p = st.columns(2)
    with col_w:
        workers = st.slider("Logical Worker Processes (Parallel cores)", 1, 16, 4)
    with col_p:
        payout_override = st.slider("Payout Percentage Override", 10.0, 100.0, float(config_data.get("payout_pct", 92.0)), step=1.0)

    # 4. Trigger Backtest
    if st.button("🔥 Launch Backtest Sweep", type="primary"):
        if not selected_dates:
            st.error("Please select at least one date file to test.")
            return

        st.markdown("### Run Progress")
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_box = st.empty()

        # Build execution arguments
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts/run_bulk_unified.py"),
            "--config-json", str(config_path),
            "--assets", selected_asset,
            "--workers", str(workers),
        ]
        
        if date_selection_mode == "Custom Date List":
            cmd.append("--dates")
            cmd.extend(selected_dates)
        else:
            cmd.append("--all-dates")

        # Run process and stream logs
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(REPO_ROOT)
            )

            stdout_lines = []
            total_steps = len(selected_dates)
            completed_steps = 0

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    stripped = line.strip()
                    stdout_lines.append(stripped)
                    log_box.code("\n".join(stdout_lines[-10:])) # display last 10 lines of console output

                    # Parse progress output e.g. [5/74]
                    if stripped.startswith("[") and "/" in stripped and "]" in stripped:
                        try:
                            progress_part = stripped.split("]")[0][1:] # e.g. "5/74"
                            done, total = map(int, progress_part.split("/"))
                            progress_val = min(1.0, done / total)
                            progress_bar.progress(progress_val)
                            status_text.text(f"Processed {done} of {total} dates...")
                        except Exception:
                            pass

            rc = process.poll()
            if rc == 0:
                progress_bar.progress(1.0)
                st.success("✅ Backtest Sweep Completed Successfully!")
                status_text.text("Ready. Results have been compiled.")
                
                # Store paths in session state for the other tabs to load
                st.session_state["last_run_asset"] = selected_asset
                st.session_state["last_run_completed"] = True
            else:
                st.error(f"❌ Sweep process failed with exit code: {rc}")

        except Exception as e:
            st.error(f"Failed to start subprocess: {e}")
