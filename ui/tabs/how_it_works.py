import sys
from pathlib import Path
import streamlit as st

# Adjust sys.path to REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def render_how_it_works_tab():
    st.header("📖 Quantitative Sandbox Guide")
    st.markdown(
        """
        Welcome to the **OTC SNIPER Quantitative Guide**. This page explains how the signal filters, 
        veto gates, and mathematical engines interact to secure and calibrate your trading strategy.
        """
    )

    # Gradient highlight banner
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #1f2937, #111827); padding: 20px; border-radius: 8px; border-left: 5px solid #58a6ff; margin-bottom: 25px;">
            <h4 style="color: #58a6ff; margin-top: 0;">🛡️ The Guard Rails Concept</h4>
            <p style="color: #c9d1d9; font-size: 14px; margin-bottom: 0;">
                The trading environment on Over-The-Counter (OTC) assets is prone to noise, swift momentum shifts, and pinning. 
                Instead of attempting to predict the exact path of prices, the Backtester stack acts as a <b>veto funnel</b>. 
                Its primary objective is not to find more trades, but to <i>eliminate high-risk, low-probability setups</i>.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Interactive selector for specific components
    st.subheader("🔍 Deep Dive: Filter & Gate Systems")
    gate_options = [
        "🌊 Overview: The Two-Stage Funnel",
        "🟢 Kalman Smoother (Noise Cancellation)",
        "📊 Hurst Exponent (Fractal Regimes)",
        "🌀 Ornstein-Uhlenbeck (Reversion Elasticity)",
        "🚨 Manipulation Gate (Anti-Pinning)",
        "🔮 Bayesian Credibility & Sizing"
    ]
    selected_gate = st.selectbox("Select a filter system to understand its inner workings:", gate_options)

    st.markdown("---")

    if selected_gate.startswith("🌊 Overview"):
        st.markdown("### 🌊 The Two-Stage Funnel Architecture")
        st.markdown(
            """
            Signals flow sequentially through two categories of gates:
            1. **Stage 1 (Pre-Signal Gates):** Decides if the general market context is tradable. If the regime is highly trending, extremely volatile, or manipulated, the signal is discarded instantly.
            2. **Stage 2 (Per-Expiry Gates):** Decides if a specific transaction length (e.g., 60s vs 300s expiry) is historically viable for the current Spike Pocket state using Bayesian probability updating.
            """
        )
        # Visual styling box
        st.info("💡 Tip: You can adjust which gates are active in the left pane of the **Switchboard Control** tab.")

    elif selected_gate.startswith("🟢 Kalman"):
        st.markdown("### 🟢 Kalman Smoother")
        st.markdown(
            """
            **What it is:** High-frequency noise cancellation. It computes the mathematical "true" price by filtering out tick fluctuations.
            
            **How it works:**
            It operates in a recursive loop: predicting the state, measuring the incoming tick price, and updating its estimate based on the ratio of system noise ($Q$) to measurement noise ($R$).
            
            **Parameters:**
            * **Process Noise ($Q$):** The rate of change in the underlying price trend. Lower values create a smoother, slower-reacting average.
            * **Measurement Noise ($R$):** The volatility of individual ticks. Higher values cause the smoother to ignore quick price spikes as noise.
            """
        )
        st.markdown(
            """
            🎨 **Nana Banana Prompt for Imagen:**
            `A digital price chart glowing green under a magnifying glass, separating a noisy jagged red line into a smooth glowing neon-green vector line, dark high-tech background.`
            """
        )

    elif selected_gate.startswith("📊 Hurst"):
        st.markdown("### 📊 Hurst Exponent")
        st.markdown(
            r"""
            **What it is:** Fractal persistence classifier. It determines the "personality" of the price action over a rolling window.
            
            **The Regimes:**
            * **Mean-Reverting ($H < 0.44$):** Prices act like a rubber band. Deviation from the average predicts a snapback. (Highly desirable for pockets)
            * **Random Walk ($0.44 \le H \le 0.58$):** Brownian motion. Direction is unpredictable.
            * **Trending ($H > 0.58$):** Strong momentum. Moves tend to continue, making mean-reversion trades highly dangerous.
            
            **Parameters:**
            * **Mean-Reverting & Trend Cutoffs:** Thresholds that dictate regime classification.
            * **Allowed Regimes:** A whitelist that vetoes any trade generated outside the checked regimes.
            """
        )
        st.markdown(
            """
            🎨 **Nana Banana Prompt for Imagen:**
            `A 3D render of a neon-blue ping-pong ball trapped in a smooth glass bowl, vibrating back and forth toward the center, representing mean reversion, dark theme.`
            """
        )

    elif selected_gate.startswith("🌀 Ornstein-Uhlenbeck"):
        st.markdown("### 🌀 Ornstein-Uhlenbeck (OU)")
        st.markdown(
            r"""
            **What it is:** Mean reversion speed and half-life estimator. 
            
            **How it works:**
            It fits price changes to a stochastic differential equation. If the fit indicates that price speed is moving *away* from the mean (OU Beta $\ge 0$), it classifies the process as explosive and blocks the trade. If it is mean-reverting, it estimates the half-life ($\tau$): the time required to close 50% of the price gap.
            
            **Parameters:**
            * **Mode (Kalman vs OLS):** Kalman tracks a dynamic, stateful beta coefficient; OLS performs a standard ordinary least squares linear regression over a fixed window.
            """
        )

    elif selected_gate.startswith("🚨 Manipulation"):
        st.markdown("### 🚨 Manipulation Gate")
        st.markdown(
            """
            **What it is:** Institutional spike and pinning detector.
            
            **How it works:**
            OTC brokers occasionally display artificial micro-trends or pinning behavior (holding price at a specific round number) near major expiries. The Manipulation detector tracks order book and tick anomalies to produce a severity rating ($0.0$ to $1.0$).
            
            **Parameters:**
            * **Severity Threshold:** If the severity exceeds this setting (e.g. $0.3$), all signals are vetoed.
            """
        )

    elif selected_gate.startswith("🔮 Bayesian"):
        st.markdown("### 🔮 Bayesian Credibility & Sizing")
        st.markdown(
            r"""
            **What it is:** A probability engine that updates trade win-rate expectations based on live results.
            
            **How it works:**
            For each market environment classification (Spike Pocket), we maintain a Beta distribution modeling the win rate $p$.
            As trades settle, we update the parameters:
            * **Win:** $\alpha \leftarrow \alpha + 1$ (shifts distribution right, higher probability)
            * **Loss:** $\beta \leftarrow \beta + 1$ (shifts distribution left, lower probability)
            
            **The Credible Gate:**
            We calculate the mathematical probability that the true win rate is above the break-even threshold (typically $52.08\%$ for a $92\%$ payout). If our confidence is below the setting (e.g. $90\%$), we veto the trade due to lack of historical proof.
            
            **Expected Utility Sizing:**
            Maximizes expected power utility to determine trade sizing. If risk is too high, the recommended size falls to $0$, vetoing the trade.
            """
        )
        st.latex(r"P(p \mid \alpha, \beta) = \frac{p^{\alpha-1}(1-p)^{\beta-1}}{\mathrm{B}(\alpha, \beta)}")
        st.markdown(
            """
            🎨 **Nana Banana Prompt for Imagen:**
            `A high-tech digital chalkboard rendering mathematical formulas, probability density bell-curves glowing purple, clean modern UI design.`
            """
        )

    st.markdown("---")
    st.subheader("📄 Read Full System Documentation")
    
    # Read and render the raw Dev_Docs/how_it_works.md file for users who want to print or read the full document
    doc_path = REPO_ROOT / "backtester_app/Dev_Docs/how_it_works.md"
    if doc_path.exists():
        with open(doc_path, "r", encoding="utf-8") as f:
            full_doc = f.read()
        with st.expander("Expand to read full technical documentation"):
            st.markdown(full_doc)
    else:
        st.warning("Technical documentation file not found.")
