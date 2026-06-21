"""Compare two batch evaluation result files and print a delta table.

Usage
-----
    python -m eval.compare results_v1.json results_v2.json
    python -m eval.compare results_v1.json results_v2.json --format json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_NUMERIC_METRICS = [
    "artifact_count",
    "test_artifact_count",
    "findings_critical",
    "findings_major",
    "findings_minor",
    "findings_info",
    "budget_efficiency",
    "total_cost_usd",
]
_BOOL_METRICS = ["tests_passed"]
_STR_METRICS = ["verdict", "status"]

_LOWER_BETTER = {"findings_critical", "findings_major", "findings_minor", "budget_efficiency", "total_cost_usd"}


def _load(path: str) -> dict[str, dict]:
    data = json.loads(Path(path).read_text())
    return {r["case_id"]: r for r in data["results"]}


def _direction(metric: str, delta: float) -> str:
    if delta == 0:
        return "="
    if metric in _LOWER_BETTER:
        return "↑ worse" if delta > 0 else "↓ better"
    return "↑ better" if delta > 0 else "↓ worse"


def compare(path_a: str, path_b: str) -> list[dict[str, Any]]:
    """Return a list of per-case delta records."""
    by_id_a = _load(path_a)
    by_id_b = _load(path_b)

    all_ids = sorted(set(by_id_a) | set(by_id_b))
    rows = []
    for cid in all_ids:
        a = by_id_a.get(cid, {})
        b = by_id_b.get(cid, {})
        ma: dict = a.get("metrics", {})
        mb: dict = b.get("metrics", {})

        row: dict[str, Any] = {
            "case_id": cid,
            "only_in": "a" if cid not in by_id_b else ("b" if cid not in by_id_a else None),
        }

        for metric in _NUMERIC_METRICS:
            va = ma.get(metric)
            vb = mb.get(metric)
            if va is not None and vb is not None:
                delta = round(float(vb) - float(va), 6)
                row[metric] = {"a": va, "b": vb, "delta": delta, "direction": _direction(metric, delta)}
            else:
                row[metric] = {"a": va, "b": vb, "delta": None, "direction": "?"}

        for metric in _BOOL_METRICS:
            va = ma.get(metric)
            vb = mb.get(metric)
            row[metric] = {"a": va, "b": vb, "changed": va != vb}

        for metric in _STR_METRICS:
            va = ma.get(metric)
            vb = mb.get(metric)
            row[metric] = {"a": va, "b": vb, "changed": va != vb}

        # LLM judge scores
        if "llm_judge" in a or "llm_judge" in b:
            sa = (a.get("llm_judge") or {}).get("score")
            sb = (b.get("llm_judge") or {}).get("score")
            row["llm_score"] = {
                "a": sa, "b": sb,
                "delta": (sb - sa) if (sa is not None and sb is not None) else None,
            }

        rows.append(row)
    return rows


def _print_table(rows: list[dict]) -> None:
    header = f"{'Case':<30} {'metric':<25} {'A':>8} {'B':>8} {'Delta':>10} {'Dir':<12}"
    print(header)
    print("-" * len(header))
    for row in rows:
        cid = row["case_id"]
        if row.get("only_in"):
            print(f"{cid:<30} (only in run {row['only_in']})")
            continue
        for metric in _NUMERIC_METRICS:
            d = row.get(metric, {})
            if d.get("delta") is not None:
                print(
                    f"{cid:<30} {metric:<25} {str(d['a']):>8} {str(d['b']):>8} "
                    f"{d['delta']:>+10.4f} {d['direction']:<12}"
                )
        for metric in _BOOL_METRICS + _STR_METRICS:
            d = row.get(metric, {})
            if d.get("changed"):
                print(f"{cid:<30} {metric:<25} {str(d['a']):>8} → {str(d['b']):<8} CHANGED")
        if "llm_score" in row:
            ls = row["llm_score"]
            delta_str = f"{ls['delta']:+d}" if ls["delta"] is not None else "?"
            print(f"{cid:<30} {'llm_judge_score':<25} {str(ls['a']):>8} {str(ls['b']):>8} {delta_str:>10}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare two eval result files")
    parser.add_argument("a", help="First result file (baseline)")
    parser.add_argument("b", help="Second result file (candidate)")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    args = parser.parse_args(argv)

    rows = compare(args.a, args.b)
    if args.format == "json":
        print(json.dumps(rows, indent=2, default=str))
    else:
        _print_table(rows)


if __name__ == "__main__":
    main()
