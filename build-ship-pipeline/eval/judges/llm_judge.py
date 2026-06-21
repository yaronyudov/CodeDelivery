"""LLM-as-Judge evaluator.

Uses the same LiteLLM call interface as the pipeline agents so no extra
API keys are needed — just reuse whatever model is configured in the env.

Score meaning
-------------
5  Excellent: artifacts are complete, tests pass, no significant issues.
4  Good: minor gaps but overall solid.
3  Acceptable: notable gaps or issues present.
2  Poor: significant problems; would need rework before production.
1  Unacceptable: the output does not address the feature request.

Usage
-----
    from eval.judges.llm_judge import judge_run
    score, rationale = judge_run(case, result, model="anthropic/claude-haiku-4-5-20251001")
"""
from __future__ import annotations

import json

_JUDGE_SYSTEM = """You are an independent code quality judge evaluating the output of an AI software build pipeline.

You will be given:
1. The original feature request
2. A summary of what the pipeline produced (artifact paths, test results, review findings)

Score the output on a scale of 1–5 using these criteria:
- Completeness: Does the output address all aspects of the feature request?
- Correctness: Are the artifacts likely to work (tests passed, no critical findings)?
- Security: Are there critical or major security findings?
- Quality: Is the code organized, tested, and follows best practices?

Respond with a JSON object:
{
  "score": <integer 1-5>,
  "rationale": "<one paragraph explaining the score>",
  "strengths": ["<brief strength>", ...],
  "weaknesses": ["<brief weakness>", ...]
}

Be concise and objective.  Respond ONLY with valid JSON."""


def judge_run(
    case: dict,
    result: dict,
    model: str = "anthropic/claude-haiku-4-5-20251001",
    api_base: str | None = None,
    api_key: str | None = None,
) -> tuple[int, dict]:
    """Judge a single pipeline result.

    Returns (score: int, full_response: dict).
    On LLM/parse failure returns (0, {"error": "..."}).
    """
    summary = {
        "feature_request": case.get("feature_request", ""),
        "artifact_paths": [a.get("path") for a in result.get("artifacts", [])],
        "test_results": result.get("test_results", {}),
        "findings": result.get("findings", []),
        "verdict": result.get("verdict"),
        "status": result.get("status"),
    }

    user_msg = (
        f"Feature request:\n{case['feature_request'].strip()}\n\n"
        f"Pipeline output summary:\n{json.dumps(summary, indent=2)}"
    )

    try:
        import litellm
        litellm.suppress_debug_info = True
        kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 1024,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key

        response = litellm.completion(**kwargs)
        text = response.choices[0].message.content or ""
    except Exception as exc:
        return 0, {"error": str(exc)}

    try:
        parsed = json.loads(text.strip().strip("`").strip())
    except json.JSONDecodeError:
        return 0, {"error": "json_parse_failed", "raw": text[:500]}

    score = int(parsed.get("score", 0))
    return score, parsed
