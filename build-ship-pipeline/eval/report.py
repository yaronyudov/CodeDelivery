"""Generate human-readable reports from batch evaluation results.

Supported output formats
------------------------
- html     Rich HTML table with color-coded pass/fail rows
- markdown GitHub-flavored Markdown table
- csv      Flat CSV with one metric row per case
- json     Pretty-printed JSON (passthrough of the result file)
- promptfoo
           YAML compatible with PromptFoo's --results flag for further analysis
- deepeval
           JSON compatible with DeepEval's TestResult schema

Usage
-----
    python -m eval.report results.json --format html --out report.html
    python -m eval.report results.json --format markdown
    python -m eval.report results.json --format csv --out results.csv
    python -m eval.report results.json --format promptfoo --out promptfoo_results.yaml
    python -m eval.report results.json --format deepeval --out deepeval_results.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _pass(result: dict) -> bool:
    return not result.get("violations") and not result.get("error")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Eval Report</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }
  h1 { font-size: 1.5rem; }
  table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
  th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }
  th { background: #f5f5f5; }
  tr.pass td:first-child { border-left: 4px solid #22c55e; }
  tr.fail td:first-child { border-left: 4px solid #ef4444; }
  .badge-pass { color: #16a34a; font-weight: bold; }
  .badge-fail { color: #dc2626; font-weight: bold; }
  .violations { color: #b91c1c; font-size: 0.8em; }
  .score { font-weight: bold; }
  .score-5 { color: #16a34a; }
  .score-4 { color: #65a30d; }
  .score-3 { color: #ca8a04; }
  .score-2 { color: #ea580c; }
  .score-1 { color: #dc2626; }
</style>
</head>
<body>
"""


def _html_report(data: dict) -> str:
    run_at = data.get("run_at", "")
    summary = data.get("summary", {})
    results = data.get("results", [])

    buf = io.StringIO()
    buf.write(_HTML_HEAD)
    buf.write(f"<h1>Evaluation Report</h1>\n")
    buf.write(f"<p>Generated: {run_at} &nbsp;|&nbsp; Server: {data.get('server_url', '')} &nbsp;|&nbsp; "
              f"Cases: {data.get('cases_file', '')}</p>\n")
    buf.write(f"<p><strong>Summary:</strong> {summary.get('passed', 0)}/{summary.get('total', 0)} passed</p>\n")
    buf.write("<table>\n<thead><tr>")
    for col in ["Case", "Status", "Artifacts", "Tests↑", "Cost $", "Critical", "Verdict", "LLM Score", "Violations"]:
        buf.write(f"<th>{col}</th>")
    buf.write("</tr></thead>\n<tbody>\n")

    for r in results:
        m = r.get("metrics", {})
        passed = _pass(r)
        cls = "pass" if passed else "fail"
        badge = '<span class="badge-pass">PASS</span>' if passed else '<span class="badge-fail">FAIL</span>'
        violations_html = ""
        if r.get("violations"):
            items = "".join(f"<li>{v}</li>" for v in r["violations"])
            violations_html = f'<ul class="violations">{items}</ul>'
        elif r.get("error"):
            violations_html = f'<span class="violations">ERROR: {r["error"]}</span>'

        score_html = ""
        if judge := r.get("llm_judge"):
            s = judge.get("score", 0)
            score_html = f'<span class="score score-{s}">{s}/5</span>'

        buf.write(
            f'<tr class="{cls}">'
            f'<td><strong>{r["case_id"]}</strong><br><small>{r.get("description","")}</small></td>'
            f'<td>{badge}</td>'
            f'<td>{m.get("artifact_count","")}</td>'
            f'<td>{"✓" if m.get("tests_passed") else "✗"}</td>'
            f'<td>{m.get("total_cost_usd", "")}</td>'
            f'<td>{m.get("findings_critical","")}</td>'
            f'<td>{m.get("verdict","")}</td>'
            f'<td>{score_html}</td>'
            f'<td>{violations_html}</td>'
            f'</tr>\n'
        )

    buf.write("</tbody></table>\n</body></html>")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _md_report(data: dict) -> str:
    results = data.get("results", [])
    lines = [
        f"# Eval Report — {data.get('run_at','')}",
        f"**Server:** {data.get('server_url','')}  |  **Cases:** {data.get('cases_file','')}",
        "",
        "| Case | Pass? | Artifacts | Tests | Cost | Critical | Verdict | LLM Score | Violations |",
        "|------|-------|-----------|-------|------|----------|---------|-----------|------------|",
    ]
    for r in results:
        m = r.get("metrics", {})
        passed = "✓" if _pass(r) else "✗"
        tests = "✓" if m.get("tests_passed") else "✗"
        score = (r.get("llm_judge") or {}).get("score", "")
        viols = "; ".join(r.get("violations", [])) or (r.get("error") or "")
        lines.append(
            f"| {r['case_id']} | {passed} | {m.get('artifact_count','')} | {tests} "
            f"| {m.get('total_cost_usd','')} | {m.get('findings_critical','')} "
            f"| {m.get('verdict','')} | {score} | {viols} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _csv_report(data: dict) -> str:
    results = data.get("results", [])
    buf = io.StringIO()
    fields = [
        "case_id", "pass", "error",
        "artifact_count", "test_artifact_count", "tests_passed",
        "findings_critical", "findings_major", "findings_minor", "findings_info",
        "budget_efficiency", "total_cost_usd", "verdict", "status",
        "llm_score", "violations",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        m = r.get("metrics", {})
        row = {**m}
        row["case_id"] = r["case_id"]
        row["pass"] = _pass(r)
        row["error"] = r.get("error", "")
        row["llm_score"] = (r.get("llm_judge") or {}).get("score", "")
        row["violations"] = " | ".join(r.get("violations", []))
        writer.writerow(row)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PromptFoo export
# ---------------------------------------------------------------------------

def _promptfoo_report(data: dict) -> str:
    results = data.get("results", [])
    pf_results = []
    for r in results:
        m = r.get("metrics", {})
        pf_results.append({
            "prompt": {"raw": r.get("feature_request", "")},
            "vars": {"case_id": r["case_id"]},
            "response": {"output": json.dumps(m)},
            "success": _pass(r),
            "score": (r.get("llm_judge") or {}).get("score", 0) / 5.0,
        })
    return yaml.dump({"results": pf_results}, allow_unicode=True)


# ---------------------------------------------------------------------------
# DeepEval export
# ---------------------------------------------------------------------------

def _deepeval_report(data: dict) -> str:
    results = data.get("results", [])
    de_cases = []
    for r in results:
        m = r.get("metrics", {})
        de_cases.append({
            "name": r["case_id"],
            "input": r.get("feature_request", ""),
            "actual_output": json.dumps(m),
            "expected_output": "",
            "success": _pass(r),
            "metrics_data": [
                {"name": "artifact_count", "score": m.get("artifact_count", 0), "success": True},
                {"name": "tests_passed", "score": 1.0 if m.get("tests_passed") else 0.0, "success": True},
                {"name": "llm_judge", "score": (r.get("llm_judge") or {}).get("score", 0) / 5.0, "success": True},
            ],
        })
    return json.dumps({"test_cases": de_cases}, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate eval report")
    parser.add_argument("results", help="Path to results JSON file")
    parser.add_argument("--format", choices=["html", "markdown", "csv", "json", "promptfoo", "deepeval"],
                        default="html")
    parser.add_argument("--out", help="Output file path (default: stdout)")
    args = parser.parse_args(argv)

    data = _load(args.results)

    dispatch = {
        "html": _html_report,
        "markdown": _md_report,
        "csv": _csv_report,
        "json": lambda d: json.dumps(d, indent=2, default=str),
        "promptfoo": _promptfoo_report,
        "deepeval": _deepeval_report,
    }
    output = dispatch[args.format](data)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Report written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
