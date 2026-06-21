"""Batch evaluation runner.

Submits each test case from a YAML file to a running pipeline server,
waits for the run to complete via polling, and collects full results
(artifacts, findings, budget, test results) into a JSON output file.

Usage
-----
    python -m eval.runner \\
        --cases eval/cases/sample_cases.yaml \\
        --url http://localhost:8000 \\
        --username admin --password secret \\
        --out results.json \\
        [--judge]          # also run LLM-as-judge scoring
        [--judge-model anthropic/claude-haiku-4-5-20251001]
        [--timeout 300]    # seconds per case (default 300)
        [--concurrency 1]  # parallel runs (default 1, sequential)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from eval.metrics import check_expectations, compute_all


def _login(base_url: str, username: str, password: str) -> requests.Session:
    session = requests.Session()
    resp = session.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return session


def _start_run(session: requests.Session, base_url: str, case: dict) -> str:
    payload: dict[str, Any] = {
        "feature_request": case["feature_request"].strip(),
        "require_approval": case.get("require_approval", False),
    }
    if override := case.get("model_override"):
        payload["model_config_"] = override

    resp = session.post(f"{base_url}/api/runs/start", json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["run_id"]


def _wait_for_run(
    session: requests.Session,
    base_url: str,
    run_id: str,
    timeout_s: int = 300,
    poll_interval_s: float = 5.0,
) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = session.get(f"{base_url}/api/runs/{run_id}", timeout=10)
        resp.raise_for_status()
        run = resp.json()
        if run.get("status") in {"done", "halted", "stopped"}:
            return run
        time.sleep(poll_interval_s)
    raise TimeoutError(f"run {run_id} did not finish within {timeout_s}s")


def _collect_run_detail(session: requests.Session, base_url: str, run_id: str) -> dict:
    """Fetch detailed run data: audit log + ledger summary."""
    detail: dict = {}
    for endpoint in ("audit", "ledger"):
        try:
            resp = session.get(f"{base_url}/api/runs/{run_id}/{endpoint}", timeout=10)
            if resp.ok:
                detail[endpoint] = resp.json()
        except Exception:
            pass
    return detail


def run_case(
    case: dict,
    base_url: str,
    session: requests.Session,
    timeout_s: int = 300,
    use_judge: bool = False,
    judge_model: str = "anthropic/claude-haiku-4-5-20251001",
) -> dict:
    """Execute one case and return its full result record."""
    case_id = case["id"]
    started_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "case_id": case_id,
        "description": case.get("description", ""),
        "started_at": started_at,
        "error": None,
    }

    try:
        run_id = _start_run(session, base_url, case)
        result["run_id"] = run_id
        run = _wait_for_run(session, base_url, run_id, timeout_s=timeout_s)
        result.update(run)
        detail = _collect_run_detail(session, base_url, run_id)
        result.update(detail)
    except Exception as exc:
        result["error"] = str(exc)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["metrics"] = compute_all(result)
    result["violations"] = check_expectations(result, case.get("expected", {}))

    if use_judge:
        try:
            from eval.judges.llm_judge import judge_run
            score, judgement = judge_run(case, result, model=judge_model)
            result["llm_judge"] = {"score": score, **judgement}
        except Exception as exc:
            result["llm_judge"] = {"error": str(exc)}

    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Batch evaluation runner")
    parser.add_argument("--cases", required=True, help="Path to YAML cases file")
    parser.add_argument("--url", default="http://localhost:8000", help="Pipeline server base URL")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--out", required=True, help="Output JSON file path")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait per case")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--judge", action="store_true", help="Run LLM-as-judge scoring")
    parser.add_argument("--judge-model", default="anthropic/claude-haiku-4-5-20251001")
    args = parser.parse_args(argv)

    cases = yaml.safe_load(Path(args.cases).read_text())["cases"]
    session = _login(args.url, args.username, args.password)

    results: list[dict] = []
    print(f"Running {len(cases)} cases (concurrency={args.concurrency}) …")

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(
                run_case, case, args.url, session,
                args.timeout, args.judge, args.judge_model,
            ): case["id"]
            for case in cases
        }
        for future in as_completed(futures):
            cid = futures[future]
            try:
                res = future.result()
            except Exception as exc:
                res = {"case_id": cid, "error": str(exc)}
            violations = res.get("violations", [])
            icon = "✓" if not violations and not res.get("error") else "✗"
            print(f"  {icon} {cid}: violations={len(violations)}, error={res.get('error')}")
            results.append(res)

    output = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "cases_file": args.cases,
        "server_url": args.url,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if not r.get("violations") and not r.get("error")),
            "failed": sum(1 for r in results if r.get("violations") or r.get("error")),
        },
    }
    Path(args.out).write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults written to {args.out}")
    total = output["summary"]["total"]
    passed = output["summary"]["passed"]
    print(f"Summary: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
