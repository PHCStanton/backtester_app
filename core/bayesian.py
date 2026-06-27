from __future__ import annotations

import math
from typing import Any, Dict, Tuple
import numpy as np
from scipy.stats import beta as scipy_beta

class BayesianPocketState:
    """
    Represents the state of a single Spike Pocket × Expiry combination.
    Tracks success probability using a Beta-Binomial conjugate prior.
    """
    def __init__(self, alpha_prior: float = 2.0, beta_prior: float = 2.0) -> None:
        self.alpha = alpha_prior
        self.beta = beta_prior
        self.wins = 0
        self.losses = 0

    def update_outcome(self, outcome: str) -> None:
        if outcome == "win":
            self.wins += 1
            self.alpha += 1.0
        elif outcome == "loss":
            self.losses += 1
            self.beta += 1.0

    @property
    def expected_win_rate(self) -> float:
        """Expected value of the win rate (mean of the Beta distribution)."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def sample_size(self) -> int:
        return self.wins + self.losses

    def probability_above(self, threshold: float) -> float:
        """Calculate P(p >= threshold) using the Beta CDF."""
        if threshold <= 0.0:
            return 1.0
        if threshold >= 1.0:
            return 0.0
        # P(p >= threshold) = 1 - CDF(threshold)
        return float(1.0 - scipy_beta.cdf(threshold, self.alpha, self.beta))

    def get_credible_interval(self, confidence: float = 0.90) -> Tuple[float, float]:
        """Calculate the equal-tailed credible interval for win probability."""
        lower_tail = (1.0 - confidence) / 2.0
        upper_tail = 1.0 - lower_tail
        lower = scipy_beta.ppf(lower_tail, self.alpha, self.beta)
        upper = scipy_beta.ppf(upper_tail, self.alpha, self.beta)
        return float(lower), float(upper)


class BayesianUtilityEngine:
    """
    Manages Bayesian pocket states and handles Expected Utility sizing.
    """
    def __init__(self, alpha_prior: float = 2.0, beta_prior: float = 2.0) -> None:
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior
        # Maps pocket_state|expiry -> BayesianPocketState
        self.states: Dict[str, BayesianPocketState] = {}

    def get_or_create_state(self, pocket_state: str, expiry: int) -> BayesianPocketState:
        key = f"{pocket_state}|{expiry}"
        if key not in self.states:
            self.states[key] = BayesianPocketState(self.alpha_prior, self.beta_prior)
        return self.states[key]

    def update_trade(self, pocket_state: str, expiry: int, outcome: str) -> None:
        if outcome not in {"win", "loss"}:
            return
        state = self.get_or_create_state(pocket_state, expiry)
        state.update_outcome(outcome)

    def verify_credible_gate(
        self,
        pocket_state: str,
        expiry: int,
        threshold: float = 0.5208,
        confidence: float = 0.90
    ) -> bool:
        """
        Gating check: Veto if the posterior probability that our win rate is 
        above the breakeven threshold is lower than the target confidence.
        """
        state = self.get_or_create_state(pocket_state, expiry)
        p_above = state.probability_above(threshold)
        return p_above >= (1.0 - confidence)

    def calculate_optimal_sizing(
        self,
        pocket_state: str,
        expiry: int,
        payout_pct: float,
        w0: float = 100.0,
        risk_aversion: float = 2.0,
        max_fraction: float = 0.10
    ) -> Tuple[float, float]:
        """
        Compute optimal sizing fraction f using Power Utility maximization.
        Returns:
            - optimal_fraction: float (0.0 to max_fraction)
            - expected_utility: float
        """
        state = self.get_or_create_state(pocket_state, expiry)
        p_exp = state.expected_win_rate
        payout = payout_pct / 100.0

        # Define Power Utility Function
        def utility(w: float) -> float:
            if w <= 1e-6:
                return -1e10
            if abs(risk_aversion - 1.0) < 1e-6:
                return math.log(w)
            return (w ** (1.0 - risk_aversion)) / (1.0 - risk_aversion)

        # Discretize search space of fractions f in [0, max_fraction]
        fractions = np.linspace(0.0, max_fraction, 101)
        best_f = 0.0
        best_u = -1e10

        for f in fractions:
            w_win = w0 * (1.0 + f * payout)
            w_loss = w0 * (1.0 - f)
            
            # Expected utility
            exp_u = p_exp * utility(w_win) + (1.0 - p_exp) * utility(w_loss)
            if exp_u > best_u:
                best_u = exp_u
                best_f = f

        return float(best_f), float(best_u)
