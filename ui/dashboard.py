import streamlit as st
from backtester_app.ui.tabs.run_sweep import render_run_sweep_tab
from backtester_app.ui.tabs.optimize import render_optimize_tab
from backtester_app.ui.tabs.results_viewer import render_results_viewer_tab
from backtester_app.ui.tabs.ml_explorer import render_ml_explorer_tab
from backtester_app.ui.tabs.import_data import render_import_tab

# Page configuration
st.set_page_config(
    page_title="OTC SNIPER — Standalone Backtester",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sleek premium dark theme overrides
st.markdown(
    """
    <style>
    .main {
        background-color: #0e1117;
        color: #c9d1d9;
    }
    h1, h2, h3 {
        color: #58a6ff;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #1f242e;
        border-radius: 4px 4px 0px 0px;
        color: #c9d1d9;
        padding-left: 16px;
        padding-right: 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #58a6ff !important;
        color: #0e1117 !important;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Sidebar layout
with st.sidebar:
    st.image("https://img.icons8.com/nolan/128/target.png", width=80)
    st.title("OTC SNIPER v3")
    st.subheader("Quantitative Sandbox")
    st.markdown("---")
    st.info("Environment: Conda `QuFLX-v2` active.")
    st.markdown(
        """
        **System Specs:**
        - Engine: `UnifiedBacktester`
        - Optimizer: `Optuna`
        - Probability Model: `Bayesian Beta`
        """
    )

# Main Page Header
st.title("🎯 OTC SNIPER — Standalone Backtesting & Calibration App")
st.markdown("---")

# Render Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Run Sweeps",
    "🧪 Parameter Calibration",
    "📊 Performance Metrics",
    "🧬 Bayesian & ML Explorer",
    "📥 Import Datasets"
])

with tab1:
    render_run_sweep_tab()

with tab2:
    render_optimize_tab()

with tab3:
    render_results_viewer_tab()

with tab4:
    render_ml_explorer_tab()

with tab5:
    render_import_tab()
