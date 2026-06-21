"""Loads budget.yaml and prices.yaml at import time; exposes typed dataclasses."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_CONFIG_DIR = _ROOT / "config"


def _load(name: str) -> dict:
    path = _CONFIG_DIR / name
    with path.open() as f:
        return yaml.safe_load(f)


@dataclass
class BudgetConfig:
    tokens_limit: int
    cost_limit_usd: float
    steps_limit: int
    hard_action_token_ceil: int
    hard_action_cost_ceil_usd: float
    debug_max_attempts: int

    @classmethod
    def from_yaml(cls) -> "BudgetConfig":
        raw = _load("budget.yaml")["budget"]
        return cls(
            tokens_limit=int(str(raw["tokens_limit"]).replace("_", "")),
            cost_limit_usd=float(raw["cost_limit_usd"]),
            steps_limit=int(str(raw["steps_limit"]).replace("_", "")),
            hard_action_token_ceil=int(str(raw["hard_action_token_ceil"]).replace("_", "")),
            hard_action_cost_ceil_usd=float(raw["hard_action_cost_ceil_usd"]),
            debug_max_attempts=int(raw["debug_max_attempts"]),
        )


@dataclass
class PricesConfig:
    prices: dict[str, dict[str, float]]
    agent_models: dict[str, str]
    expected_output_tokens: dict[str, int]

    @classmethod
    def from_yaml(cls) -> "PricesConfig":
        raw = _load("prices.yaml")
        return cls(
            prices=raw["prices"],
            agent_models=raw["agent_models"],
            expected_output_tokens=raw["expected_output_tokens"],
        )

    def price_per_1k(self, model: str) -> tuple[float, float]:
        """Returns (input_price, output_price) per 1K tokens."""
        p = self.prices[model]
        return p["in"], p["out"]

    def model_for(self, agent: str) -> str:
        return self.agent_models.get(agent, "claude-haiku-4-5-20251001")

    def expected_out(self, agent: str) -> int:
        return self.expected_output_tokens.get(agent, 500)


# Singletons loaded at import time
BUDGET_CFG = BudgetConfig.from_yaml()
PRICES_CFG = PricesConfig.from_yaml()
