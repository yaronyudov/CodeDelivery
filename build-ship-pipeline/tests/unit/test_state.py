"""Tests for PipelineState structure and initial_state()."""
import pytest

from src.state import initial_state


def test_initial_state_structure():
    s = initial_state("run-1", "Build a todo API")
    assert s["run_id"] == "run-1"
    assert s["feature_request"] == "Build a todo API"
    assert s["phase"] == "dev"
    assert s["artifacts"] == []
    assert s["findings"] == []
    assert s["verdict"] is None
    assert s["halt_reason"] is None
    assert s["debug_attempts"] == 0


def test_initial_budget_counters_are_zero():
    s = initial_state("run-2", "Feature")
    b = s["budget"]
    assert b["tokens_used"] == 0
    assert b["cost_used_usd"] == 0.0
    assert b["steps_taken"] == 0


def test_initial_budget_limits_from_config():
    from src.config import BUDGET_CFG
    s = initial_state("run-3", "Feature")
    b = s["budget"]
    assert b["tokens_limit"] == BUDGET_CFG.tokens_limit
    assert b["cost_limit_usd"] == BUDGET_CFG.cost_limit_usd
    assert b["steps_limit"] == BUDGET_CFG.steps_limit
