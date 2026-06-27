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

# ─── OHLCV Auto-Detection ────────────────────────────────────────────────────
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


# ─── Main Tab Renderer ───────────────────────────────────────────────────────
def render_import_tab():
    st.header("📥 Import & Convert Backup Datasets")
    st.markdown(
        "Convert raw CSV files (OHLCV candle or tick format) from the backup directory "
        "into sorted `.jsonl` tick log files required by the `UnifiedBacktester`."
    )

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    TICK_ROOT.mkdir(parents=True, exist_ok=True)

    # ── 1. Source Selection ──────────────────────────────────────────────────
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
            return

        selected_file_name = st.selectbox("Select CSV File", csv_files)
        if selected_file_name:
            csv_file = BACKUP_ROOT / selected_file_name
            csv_filename = Path(selected_file_name).name
    else:
        uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
        if uploaded_file:
            csv_file = uploaded_file
            csv_filename = uploaded_file.name

    if csv_file is None:
        st.write("Waiting for a file selection...")
        return

    # ── 2. Parse Settings ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("⚙️ Parse & Mapping Settings")

    col1, col2 = st.columns(2)
    with col1:
        delimiter = st.selectbox("CSV Delimiter", [",", ";", "\\t"], index=0)
        if delimiter == "\\t":
            delimiter = "\t"
        header_row = st.number_input("Header Row (0-indexed)", min_value=0, value=0)

    # Load sample to get headers
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

    # ── Auto-detect OHLCV ────────────────────────────────────────────────────
    ohlcv_map = _detect_ohlcv(columns)
    is_ohlcv = ohlcv_map is not None

    if is_ohlcv:
        st.info(
            f"🔍 **OHLCV format auto-detected** — "
            f"Timestamp: `{ohlcv_map['ts']}` | "
            f"Price (close): `{ohlcv_map['close']}` | "
            f"Open: `{ohlcv_map['open']}` | "
            f"High: `{ohlcv_map['high']}` | "
            f"Low: `{ohlcv_map['low']}` | "
            f"Volume: `{ohlcv_map['vol']}`"
        )
        st.warning(
            "⚠️ **OHLCV → Tick conversion**: Each candle will be stored as a single tick "
            "using the **`close`** price. This is suitable for backtesting directional "
            "signals but does NOT provide true sub-minute tick resolution."
        )
        price_source_choice = st.selectbox(
            "Which OHLCV price to use as tick price?",
            ["close", "open", "high", "low", "(open+high+low+close)/4 (HLC4)"],
            index=0
        )
        # Resolve to column or formula
        ohlcv_price_mode = price_source_choice
    else:
        price_source_choice = None
        ohlcv_price_mode = None

    with col2:
        if is_ohlcv:
            ts_col    = ohlcv_map["ts"]
            price_col = ohlcv_map["close"]   # default, overridden below during parse
            st.markdown(f"**Timestamp column:** `{ts_col}` *(auto)*")
            st.markdown(f"**Price column:** `{price_col}` *(OHLCV close, configurable above)*")
        else:
            ts_col    = st.selectbox("Timestamp Column", columns, index=0)
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

    # ── 3. Data Quality Report (sampled) ────────────────────────────────────
    st.markdown("---")
    st.subheader("🔬 Data Quality Report")

    try:
        sample_df = raw_sample.copy()
        total_sample = len(sample_df)

        # Detect duplicates in sample
        dup_count = int(sample_df.duplicated(subset=[ts_col], keep="first").sum())
        unique_ts  = sample_df[ts_col].nunique()

        # Detect sort direction
        ts_vals = pd.to_numeric(sample_df[ts_col], errors="coerce").dropna().values
        if len(ts_vals) >= 2:
            diffs = np.diff(ts_vals)
            pct_desc = float((diffs < 0).mean())
            pct_asc  = float((diffs > 0).mean())
            if pct_desc > 0.6:
                sort_label = "🔽 Descending (newest-first)"
                sort_color = "orange"
            elif pct_asc > 0.6:
                sort_label = "🔼 Ascending (oldest-first)"
                sort_color = "green"
            else:
                sort_label = "⚠️ Mixed / Unordered"
                sort_color = "red"
            time_step = abs(float(np.median(diffs))) if len(diffs) > 0 else None
        else:
            sort_label = "N/A"
            sort_color = "grey"
            time_step = None

        # Candle interval label
        if time_step and is_ohlcv:
            if abs(time_step - 60) < 5:
                interval_label = "1-minute bars"
            elif abs(time_step - 300) < 10:
                interval_label = "5-minute bars"
            elif abs(time_step - 3600) < 60:
                interval_label = "1-hour bars"
            else:
                interval_label = f"{time_step:.0f}s bars"
        else:
            interval_label = "N/A"

        qc1, qc2, qc3, qc4 = st.columns(4)
        qc1.metric("Sample Rows", total_sample)
        qc2.metric("Unique Timestamps", unique_ts)
        qc3.metric("Duplicate Rows (sample)", dup_count,
                   delta=f"-{dup_count} will be removed" if dup_count else None,
                   delta_color="inverse")
        qc4.metric("Candle Interval", interval_label if is_ohlcv else "Tick data")

        st.markdown(f"**Sort Order (sample):** :{sort_color}[{sort_label}] — will be re-sorted ascending on import.")

        if dup_count > 0:
            st.warning(
                f"🔁 **{dup_count} duplicate timestamps detected** in the first {total_sample} rows. "
                f"These are a known artifact of the QuFLX-v2 logger (data appended in overlapping windows). "
                f"All duplicates will be **automatically removed** during import — only the first occurrence is kept."
            )

    except Exception as eq:
        st.warning(f"Could not run quality report: {eq}")

    # ── 4. Mapping Preview ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔍 Mapping Preview")

    preview_df = sample_df.head(10).copy()
    st.markdown("**First 5 rows of Raw CSV:**")
    st.dataframe(preview_df.head(5), use_container_width=True)

    # Resolve price column based on OHLCV mode
    def _resolve_price(row) -> float:
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

    parsed_rows = []
    preview_error = None
    for idx, row in preview_df.iterrows():
        try:
            p = _resolve_price(row)
            if not math.isfinite(p):
                raise ValueError("Price is not finite")

            t = _parse_timestamp(row[ts_col], ts_format, custom_format, source_tz)

            a = str(row[asset_col]).strip() if asset_source == "CSV Column" else asset_val
            if broker_source == "CSV Column":
                b = str(row[broker_col]).strip()
            else:
                b = broker_val

            parsed_rows.append({
                "t": round(t, 3),
                "p": p,
                "a": a,
                "b": b,
                "readable_utc": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception as ex:
            preview_error = f"Error parsing row {idx + 1}: {ex}"
            break

    if preview_error:
        st.error(preview_error)
        st.warning("Please check your mappings or format settings above.")
    else:
        st.markdown("**Mapped Output Preview (first 5 parsed ticks):**")
        st.dataframe(pd.DataFrame(parsed_rows).head(5), use_container_width=True)

    # ── 5. Save Options & Import ─────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💾 Target Settings & Import")

    default_target = asset_val if asset_source == "Static Value" else "IMPORTED_ASSET"
    target_asset = st.text_input("Target Asset Subfolder Name", value=default_target).strip()

    if not target_asset:
        st.error("Please enter a valid target folder name.")
        return

    target_dir = TICK_ROOT / target_asset

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        strategy = st.selectbox(
            "Conflict Resolution Strategy",
            ["Overwrite Existing Files", "Append and Merge (Remove Duplicates)"]
        )
    with col_s2:
        st.write("")
        st.write("")
        run_btn = st.button("🚀 Import and Convert Dataset", type="primary", use_container_width=True)

    if not run_btn:
        return

    # ── Full Import ──────────────────────────────────────────────────────────
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

    total_rows_raw = len(df_full)

    # Deduplicate on timestamp column — keep first occurrence
    before_dedup = len(df_full)
    df_full = df_full.drop_duplicates(subset=[ts_col], keep="first")
    after_dedup = len(df_full)
    dupes_removed = before_dedup - after_dedup

    if dupes_removed > 0:
        st.warning(
            f"🔁 **Removed {dupes_removed} duplicate rows** ({before_dedup} → {after_dedup} unique rows) "
            f"before import. This is normal for QuFLX-v2 backup files."
        )
    else:
        st.success(f"✅ No duplicate timestamps found. Processing {after_dedup} rows.")

    total_rows = len(df_full)
    st.write(f"Parsing **{total_rows}** unique rows...")

    progress_bar = st.progress(0)
    status_text  = st.empty()

    ticks_by_date  = {}
    parse_errors   = 0
    first_error_msg = None
    chunk_size = max(500, total_rows // 20)

    for i in range(total_rows):
        if i % chunk_size == 0 or i == total_rows - 1:
            progress_bar.progress((i + 1) / total_rows)
            status_text.text(f"Parsing: {i + 1} / {total_rows}")

        row = df_full.iloc[i]
        try:
            p = _resolve_price(row)
            if not math.isfinite(p):
                raise ValueError("Price is not finite")

            t = _parse_timestamp(row[ts_col], ts_format, custom_format, source_tz)

            a = str(row[asset_col]).strip() if asset_source == "CSV Column" else target_asset
            if broker_source == "CSV Column":
                b = str(row[broker_col]).strip()
            else:
                b = broker_val

            dt_utc   = datetime.fromtimestamp(t, tz=timezone.utc)
            date_str = dt_utc.strftime("%Y-%m-%d")

            if date_str not in ticks_by_date:
                ticks_by_date[date_str] = []
            ticks_by_date[date_str].append({"t": t, "p": p, "a": a, "b": b})

        except Exception as e:
            parse_errors += 1
            if first_error_msg is None:
                first_error_msg = f"Row {i + 1}: {e}"

    status_text.text("Writing tick log files...")

    if parse_errors > 0:
        st.warning(f"⚠️ {parse_errors} rows skipped due to parse errors. First: `{first_error_msg}`")

    target_dir.mkdir(parents=True, exist_ok=True)

    files_written      = []
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
                st.error(f"Failed to read existing `{file_path.name}`: {ex}. Overwriting.")

        combined = existing_ticks + ticks

        # Deduplicate by (t, p) and sort ascending
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
        st.success(
            f"🎉 Successfully imported **{ticks_written_count}** unique ticks "
            f"into asset folder **`{target_asset}`**!"
        )
        st.markdown("**Files Written:**")
        for f_info in files_written:
            st.markdown(f"- `{f_info}`")
        st.info(
            f"📁 Output directory: `app/data/tick_logs/{target_asset}/`  \n"
            f"These files are now ready for use in the backtester."
        )
    else:
        st.error("No tick log files were written. Check that the file is not empty and mappings are correct.")
