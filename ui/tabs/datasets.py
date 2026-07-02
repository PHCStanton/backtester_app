import sys
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import streamlit as st
import pandas as pd
import numpy as np
import pytz

# Adjust sys.path to REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Paths
TICK_ROOT = REPO_ROOT / "app/data/tick_logs"
BACKUP_ROOT = REPO_ROOT / "app/data/backup_data"
STATEMENT_ROOT = REPO_ROOT / "app/data/PO_STATEMENTS"

# OHLCV Auto-Detection helper globals and functions
OHLCV_TIMESTAMP_ALIASES = {"time", "timestamp", "date", "datetime", "ts"}
OHLCV_CLOSE_ALIASES     = {"close", "c", "last", "price"}
OHLCV_OPEN_ALIASES      = {"open", "o"}
OHLCV_HIGH_ALIASES      = {"high", "h"}
OHLCV_LOW_ALIASES       = {"low", "l"}
OHLCV_VOLUME_ALIASES    = {"volume", "vol", "v"}

def _detect_ohlcv(columns: list[str]) -> dict | None:
    """Return detected column mapping if file looks like OHLCV, else None."""
    cols_lower = {c.lower(): c for c in columns}
    ts_col   = next((cols_lower[k] for k in OHLCV_TIMESTAMP_ALIASES if k in cols_lower), None)
    close_col = next((cols_lower[k] for k in OHLCV_CLOSE_ALIASES  if k in cols_lower), None)
    open_col  = next((cols_lower[k] for k in OHLCV_OPEN_ALIASES   if k in cols_lower), None)
    high_col  = next((cols_lower[k] for k in OHLCV_HIGH_ALIASES   if k in cols_lower), None)
    low_col   = next((cols_lower[k] for k in OHLCV_LOW_ALIASES    if k in cols_lower), None)
    vol_col   = next((cols_lower[k] for k in OHLCV_VOLUME_ALIASES if k in cols_lower), None)

    # Must have at least time + close to be considered OHLCV
    if ts_col and close_col:
        return {
            "ts": ts_col, "close": close_col,
            "open": open_col, "high": high_col,
            "low": low_col, "vol": vol_col,
        }
    return None

def _parse_timestamp(raw_t, ts_format: str, custom_format: str, source_tz) -> float:
    if ts_format == "Unix Seconds (float/int)":
        return float(raw_t)
    elif ts_format == "Unix Milliseconds (int)":
        return float(raw_t) / 1000.0
    else:
        val_str = str(raw_t).strip()
        if ts_format == "Custom Datetime Format String":
            dt = datetime.strptime(val_str, custom_format)
        else:
            dt = pd.to_datetime(val_str).to_pydatetime()
        if dt.tzinfo is None:
            dt = source_tz.localize(dt)
        return dt.astimezone(timezone.utc).timestamp()

def render_datasets_tab():
    st.header("📥 Dataset Manager")
    
    tab_import, tab_statements = st.tabs([
        "📥 Convert Tick & Candle Backups",
        "📄 Upload Pocket Option Statements"
    ])

    with tab_import:
        st.subheader("Convert Backup Datasets")
        st.markdown(
            "Convert raw CSV files (OHLCV candle or tick format) from the backup directory "
            "into sorted `.jsonl` tick log files required by the `UnifiedBacktester`."
        )

        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        TICK_ROOT.mkdir(parents=True, exist_ok=True)

        source_method = st.radio(
            "Select CSV Source Method",
            ["Scan Local backup_data Directory", "Drag & Drop Upload"],
            horizontal=True
        )

        csv_file = None
        csv_filename = ""

        if source_method == "Scan Local backup_data Directory":
            st.info(f"Scanning: `{BACKUP_ROOT.relative_to(REPO_ROOT)}`")
            csv_files = sorted([str(f.relative_to(BACKUP_ROOT)) for f in BACKUP_ROOT.rglob("*.csv")])

            if not csv_files:
                st.warning("No `.csv` files found in `app/data/backup_data/`. Place files there or use 'Drag & Drop'.")
            else:
                selected_file_name = st.selectbox("Select CSV File", csv_files)
                if selected_file_name:
                    csv_file = BACKUP_ROOT / selected_file_name
                    csv_filename = Path(selected_file_name).name
        else:
            uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
            if uploaded_file:
                csv_file = uploaded_file
                csv_filename = uploaded_file.name

        if csv_file is not None:
            # Render import fields
            delimiter = st.selectbox("CSV Delimiter", [",", ";", "\\t"], index=0)
            if delimiter == "\\t":
                delimiter = "\t"
            header_row = st.number_input("Header Row (0-indexed)", min_value=0, value=0)

            # Load sample
            try:
                if isinstance(csv_file, Path):
                    raw_sample = pd.read_csv(csv_file, sep=delimiter, header=header_row, nrows=200)
                else:
                    csv_file.seek(0)
                    raw_sample = pd.read_csv(csv_file, sep=delimiter, header=header_row, nrows=200)
                    csv_file.seek(0)
                columns = list(raw_sample.columns)
            except Exception as e:
                st.error(f"Failed to read CSV headers: {e}")
                return

            ohlcv_map = _detect_ohlcv(columns)
            is_ohlcv = ohlcv_map is not None

            if is_ohlcv:
                st.info(
                    f"🔍 **OHLCV format auto-detected** — "
                    f"Timestamp: `{ohlcv_map['ts']}` | Price (close): `{ohlcv_map['close']}`"
                )
                price_source_choice = st.selectbox(
                    "Which OHLCV price to use as tick price?",
                    ["close", "open", "high", "low", "(open+high+low+close)/4 (HLC4)"],
                    index=0
                )
                ohlcv_price_mode = price_source_choice
                ts_col = ohlcv_map["ts"]
                price_col = ohlcv_map["close"]
            else:
                price_source_choice = None
                ohlcv_price_mode = None
                ts_col = st.selectbox("Timestamp Column", columns, index=0)
                price_col = st.selectbox("Price Column", columns, index=1 if len(columns) > 1 else 0)

            col3, col4, col5 = st.columns(3)
            with col3:
                asset_source = st.radio("Asset Column Source", ["Static Value", "CSV Column"])
                if asset_source == "Static Value":
                    default_asset = csv_filename.replace(".csv", "").strip()
                    asset_val = st.text_input("Asset Name", value=default_asset)
                else:
                    asset_col = st.selectbox("Asset Column", columns)
                    asset_val = ""

            with col4:
                broker_source = st.radio("Broker", ["Default (pocket_option)", "Static Value", "CSV Column"])
                if broker_source == "Static Value":
                    broker_val = st.text_input("Broker Name", value="pocket_option")
                elif broker_source == "CSV Column":
                    broker_col = st.selectbox("Broker Column", columns)
                    broker_val = ""
                else:
                    broker_val = "pocket_option"

            with col5:
                ts_format = st.selectbox(
                    "Timestamp Format",
                    [
                        "Unix Seconds (float/int)",
                        "Unix Milliseconds (int)",
                        "Datetime String (ISO 8601 / Auto)",
                        "Custom Datetime Format String",
                    ]
                )
                custom_format = ""
                if ts_format == "Custom Datetime Format String":
                    custom_format = st.text_input("Format Pattern", value="%Y-%m-%d %H:%M:%S")

                tz_options = ["UTC"] + sorted(pytz.common_timezones)
                timezone_name = st.selectbox("Source Timezone", tz_options, index=0)
                source_tz = pytz.timezone(timezone_name)

            # Mapping preview & Target folder Settings
            st.markdown("---")
            default_target = asset_val if asset_source == "Static Value" else "IMPORTED_ASSET"
            target_asset = st.text_input("Target Asset Subfolder Name", value=default_target).strip()

            strategy = st.selectbox(
                "Conflict Resolution Strategy",
                ["Overwrite Existing Files", "Append and Merge (Remove Duplicates)"]
            )

            if st.button("🚀 Import and Convert Dataset", type="primary"):
                # Execute conversion
                st.info("Loading full CSV file...")
                try:
                    if isinstance(csv_file, Path):
                        df_full = pd.read_csv(csv_file, sep=delimiter, header=header_row)
                    else:
                        csv_file.seek(0)
                        df_full = pd.read_csv(csv_file, sep=delimiter, header=header_row)
                except Exception as e:
                    st.error(f"Failed to load CSV: {e}")
                    return

                total_rows = len(df_full)
                st.write(f"Parsing **{total_rows}** rows...")

                progress_bar = st.progress(0)
                status_text = st.empty()

                ticks_by_date = {}
                parse_errors = 0
                first_error_msg = None
                chunk_size = max(500, total_rows // 20)

                # Inner function to resolve price matching current ohlcv mode
                def _local_resolve_price(row) -> float:
                    if not is_ohlcv:
                        return float(row[price_col])
                    mode = ohlcv_price_mode
                    if mode == "close":
                        return float(row[ohlcv_map["close"]])
                    elif mode == "open":
                        return float(row[ohlcv_map["open"]])
                    elif mode == "high":
                        return float(row[ohlcv_map["high"]])
                    elif mode == "low":
                        return float(row[ohlcv_map["low"]])
                    else:  # HLC4
                        return (
                            float(row[ohlcv_map["open"]]) +
                            float(row[ohlcv_map["high"]]) +
                            float(row[ohlcv_map["low"]]) +
                            float(row[ohlcv_map["close"]])
                        ) / 4.0

                for i in range(total_rows):
                    if i % chunk_size == 0 or i == total_rows - 1:
                        progress_bar.progress((i + 1) / total_rows)
                        status_text.text(f"Parsing: {i + 1} / {total_rows}")

                    row = df_full.iloc[i]
                    try:
                        p = _local_resolve_price(row)
                        if not math.isfinite(p):
                            raise ValueError("Price is not finite")

                        t = _parse_timestamp(row[ts_col], ts_format, custom_format, source_tz)
                        a = str(row[asset_col]).strip() if asset_source == "CSV Column" else target_asset
                        if broker_source == "CSV Column":
                            b = str(row[broker_col]).strip()
                        else:
                            b = broker_val

                        dt_utc = datetime.fromtimestamp(t, tz=timezone.utc)
                        date_str = dt_utc.strftime("%Y-%m-%d")

                        if date_str not in ticks_by_date:
                            ticks_by_date[date_str] = []
                        ticks_by_date[date_str].append({"t": t, "p": p, "a": a, "b": b})

                    except Exception as e:
                        parse_errors += 1
                        if first_error_msg is None:
                            first_error_msg = f"Row {i + 1}: {e}"

                status_text.text("Writing tick log files...")
                target_dir = TICK_ROOT / target_asset
                target_dir.mkdir(parents=True, exist_ok=True)

                files_written = []
                ticks_written_count = 0

                for date_str, ticks in sorted(ticks_by_date.items()):
                    file_path = target_dir / f"{date_str}.jsonl"

                    existing_ticks = []
                    if file_path.exists() and strategy == "Append and Merge (Remove Duplicates)":
                        try:
                            with file_path.open("r", encoding="utf-8") as fh:
                                for line in fh:
                                    line = line.strip()
                                    if line:
                                        existing_ticks.append(json.loads(line))
                        except Exception as ex:
                            st.error(f"Failed to read existing `{file_path.name}`: {ex}")

                    combined = existing_ticks + ticks

                    seen = set()
                    unique_ticks = []
                    for tk in combined:
                        key = (round(tk["t"], 3), round(tk["p"], 8))
                        if key not in seen:
                            seen.add(key)
                            unique_ticks.append(tk)
                    unique_ticks.sort(key=lambda x: x["t"])

                    try:
                        with file_path.open("w", encoding="utf-8") as fh:
                            for tk in unique_ticks:
                                fh.write(json.dumps(tk) + "\n")
                        files_written.append(f"{file_path.name} ({len(unique_ticks)} ticks)")
                        ticks_written_count += len(unique_ticks)
                    except Exception as ex:
                        st.error(f"Failed to write `{file_path.name}`: {ex}")

                progress_bar.empty()
                status_text.empty()

                if files_written:
                    st.success(f"🎉 Successfully imported **{ticks_written_count}** unique ticks into **`{target_asset}`**!")
                    for f_info in files_written:
                        st.markdown(f"- `{f_info}`")
                else:
                    st.error("No tick log files were written. Check parameters.")

    with tab_statements:
        st.subheader("Upload and Manage Pocket Option Statements")
        st.markdown(
            "Upload Excel `.xlsx`/`.xls` or `.csv` files showing your real trade execution history "
            "so you can replay them in the switchboard replayer."
        )

        STATEMENT_ROOT.mkdir(parents=True, exist_ok=True)

        # File uploader
        uploaded_file = st.file_uploader("Choose Statement Excel/CSV File", type=["xlsx", "xls", "csv"], key="po_upload")
        if uploaded_file is not None:
            save_path = STATEMENT_ROOT / uploaded_file.name
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"Successfully uploaded and saved: `{uploaded_file.name}`")

        # List existing files
        st.markdown("---")
        st.markdown("### Existing Uploaded Statement Files")
        stmt_files = sorted([f for f in STATEMENT_ROOT.glob("*.*") if f.suffix.lower() in [".xlsx", ".xls", ".csv"]])
        if not stmt_files:
            st.info("No statement files found in `app/data/PO_STATEMENTS/` directory.")
        else:
            for idx, file in enumerate(stmt_files):
                col_fn, col_del = st.columns([5, 1])
                col_fn.markdown(f"📄 `{file.name}` ({file.stat().st_size / 1024:.1f} KB)")
                if col_del.button("🗑️ Delete", key=f"del_{idx}"):
                    file.unlink()
                    st.success(f"Deleted: `{file.name}`")
                    st.rerun()
