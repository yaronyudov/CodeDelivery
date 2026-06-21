"""LangGraph state schema for the Build & Ship Pipeline."""
from __future__ import annotations

from operator import add
from typing import Annotated, Literal

from typing_extensions import TypedDict

from src.config import BUDGET_CFG


class Budget(TypedDict):
    # Global ceilings (set at run start from config)
    tokens_limit: int
    cost_limit_usd: float
    steps_limit: int
    # Live counters (mutated only by BudgetGuard)
    tokens_used: int
    cost_used_usd: float
    steps_taken: int
    # Dynamic per-action caps (recomputed each step inside guard)
    per_action_token_cap: int
    per_action_cost_cap_usd: float


class Artifact(TypedDict):
    path: str
    kind: Literal["code", "config", "compose", "dashboard", "test"]
    content_ref: str  # pointer into DB artifacts table, not inline content
    version: int


class Finding(TypedDict):
    agent: str
    severity: Literal["critical", "major", "minor", "info"]
    message: str
    location: str


class PipelineState(TypedDict):
    run_id: str
    feature_request: str
    phase: Literal["dev", "review", "done", "halted"]

    plan: dict
    tech_stack: list[str]
    # Reducers accumulate across nodes; agents append, never replace
    artifacts: Annotated[list[Artifact], add]

    test_results: dict
    debug_attempts: int

    findings: Annotated[list[Finding], add]
    verdict: Literal["clean", "minor", "critical"] | None

    budget: Budget
    # Every routing decision is appended here for the audit log
    audit: Annotated[list[dict], add]
    halt_reason: str | None

    # UI additions
    require_approval: bool  # pause between planner and coder for human review
    approval_status: Literal["pending", "approved", "rejected"] | None
    model_config: dict  # {provider, model, api_base, api_key} — passed to call_model

    # Skill system — computed once at run start from DB defaults + session overrides
    skill_context: dict   # {agent_name: combined prompt injection text}
    enabled_agents: list  # agent names that should run (all agents minus toggles)


_ALL_AGENTS = [
    "planner", "coder", "docker", "observability", "tester",
    "debugger", "reviewer", "review_supervisor", "security",
    "perf", "style", "coverage",
]


def initial_state(
    run_id: str,
    feature_request: str,
    require_approval: bool = False,
    model_config: dict | None = None,
    skill_context: dict | None = None,
    enabled_agents: list | None = None,
) -> PipelineState:
    """Build the starting state for a new pipeline run."""
    return PipelineState(
        run_id=run_id,
        feature_request=feature_request,
        phase="dev",
        plan={},
        tech_stack=[],
        artifacts=[],
        test_results={},
        debug_attempts=0,
        findings=[],
        verdict=None,
        budget=Budget(
            tokens_limit=BUDGET_CFG.tokens_limit,
            cost_limit_usd=BUDGET_CFG.cost_limit_usd,
            steps_limit=BUDGET_CFG.steps_limit,
            tokens_used=0,
            cost_used_usd=0.0,
            steps_taken=0,
            per_action_token_cap=0,
            per_action_cost_cap_usd=0.0,
        ),
        audit=[],
        halt_reason=None,
        require_approval=require_approval,
        approval_status=None,
        model_config=model_config or {},
        skill_context=skill_context or {},
        enabled_agents=enabled_agents if enabled_agents is not None else list(_ALL_AGENTS),
    )
