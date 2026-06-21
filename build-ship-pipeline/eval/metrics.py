"""Deterministic (non-LLM) evaluation metrics.

These metrics run against the raw pipeline result dict (as stored by the runner).
They are cheap, reproducible, and always available — no model calls needed.
"""
from __future__ import annotations

from typing import Any


def artifact_count(result: dict[str, Any]) -> int:
    """Total number of artifacts produced by the run."""
    return len(result.get("artifacts", []))


def test_artifact_count(result: dict[str, Any]) -> int:
    """Number of artifacts with kind == 'test'."""
    return sum(1 for a in result.get("artifacts", []) if a.get("kind") == "test")


def tests_passed(result: dict[str, Any]) -> bool:
    """True if the tester agent reported all tests passing."""
    return bool(result.get("test_results", {}).get("passed", False))


def finding_counts(result: dict[str, Any]) -> dict[str, int]:
    """Return a dict of {severity: count} across all findings."""
    counts: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for f in result.get("findings", []):
        sev = f.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def budget_efficiency(result: dict[str, Any]) -> float:
    """Fraction of the token budget consumed.  0.0 = none used, 1.0 = full."""
    budget = result.get("budget", {})
    limit = budget.get("tokens_limit", 0)
    used = budget.get("tokens_used", 0)
    if limit == 0:
        return 0.0
    return round(min(used / limit, 1.0), 4)


def total_cost_usd(result: dict[str, Any]) -> float:
    """Actual total cost in USD from the budget ledger summary."""
    return float(result.get("ledger_summary", {}).get("total_cost_usd") or 0.0)


def verdict(result: dict[str, Any]) -> str | None:
    """Final pipeline verdict: 'clean' | 'minor' | 'critical' | None."""
    return result.get("verdict")


def status(result: dict[str, Any]) -> str:
    """Pipeline run status: 'done' | 'halted' | 'stopped' | 'running'."""
    return result.get("status", "unknown")


def compute_all(result: dict[str, Any]) -> dict[str, Any]:
    """Compute all deterministic metrics and return them as a flat dict."""
    fc = finding_counts(result)
    return {
        "artifact_count": artifact_count(result),
        "test_artifact_count": test_artifact_count(result),
        "tests_passed": tests_passed(result),
        "findings_critical": fc["critical"],
        "findings_major": fc["major"],
        "findings_minor": fc["minor"],
        "findings_info": fc["info"],
        "budget_efficiency": budget_efficiency(result),
        "total_cost_usd": total_cost_usd(result),
        "verdict": verdict(result),
        "status": status(result),
    }


def check_expectations(result: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Return a list of violation strings (empty = all expectations met)."""
    violations: list[str] = []
    metrics = compute_all(result)

    if "min_artifacts" in expected and metrics["artifact_count"] < expected["min_artifacts"]:
        violations.append(
            f"artifact_count={metrics['artifact_count']} < min_artifacts={expected['min_artifacts']}"
        )
    if "min_tests" in expected and metrics["test_artifact_count"] < expected["min_tests"]:
        violations.append(
            f"test_artifact_count={metrics['test_artifact_count']} < min_tests={expected['min_tests']}"
        )
    if expected.get("test_passed") and not metrics["tests_passed"]:
        violations.append("tests_passed=False (expected True)")
    if "max_cost_usd" in expected and metrics["total_cost_usd"] > expected["max_cost_usd"]:
        violations.append(
            f"total_cost_usd={metrics['total_cost_usd']:.4f} > max_cost_usd={expected['max_cost_usd']}"
        )
    if "verdict" in expected and expected["verdict"] is not None:
        if metrics["verdict"] != expected["verdict"]:
            violations.append(
                f"verdict={metrics['verdict']!r} != expected={expected['verdict']!r}"
            )
    # Forbidden finding substrings
    for substring in expected.get("forbidden_findings", []):
        for f in result.get("findings", []):
            if substring.lower() in f.get("message", "").lower():
                violations.append(f"forbidden finding matched: {substring!r} in {f!r}")
                break

    return violations
