"""LangGraph StateGraph wiring for the Build & Ship Pipeline."""
from __future__ import annotations

import os
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from src.agents.dev.coder import coder_node
from src.agents.dev.debugger import debugger_node
from src.agents.dev.docker import docker_node
from src.agents.dev.observability import observability_node
from src.agents.dev.planner import planner_node
from src.agents.dev.reviewer import reviewer_node
from src.agents.dev.tester import tester_node
from src.agents.review.coverage import coverage_node
from src.agents.review.perf import perf_node
from src.agents.review.security import security_node
from src.agents.review.style import style_node
from src.agents.review.supervisor import review_supervisor_node
from src.config import BUDGET_CFG
from src.governance.governed import governed
from src.nodes.approval import approval_gate_node
from src.nodes.halt import halt_node
from src.nodes.report import report_node
from src.state import PipelineState


def _after_approval(state: PipelineState) -> str:
    if state["phase"] == "halted":
        return "halt"
    return "coder"


def _after_tester(state: PipelineState) -> str:
    if state["phase"] == "halted":
        return "halt"
    if state.get("test_results", {}).get("passed", False):
        return "reviewer"
    if state.get("debug_attempts", 0) >= BUDGET_CFG.debug_max_attempts:
        return "planner"
    return "debugger"


def _after_reviewer(state: PipelineState) -> str:
    return "halt" if state["phase"] == "halted" else "review_supervisor"


def _verdict_router(state: PipelineState) -> str:
    if state["phase"] == "halted":
        return "halt"
    if state.get("verdict") == "critical":
        return "planner"
    return "report"


def build_graph(db: Any = None) -> Any:
    """Build and compile the pipeline StateGraph."""
    g = StateGraph(PipelineState)

    # ── Dev phase nodes ────────────────────────────────────────────────
    g.add_node("planner", governed("planner", db)(planner_node))
    g.add_node("approval_gate", approval_gate_node)  # zero-cost; no LLM
    g.add_node("coder", governed("coder", db)(
        lambda s, m: coder_node(s, m, db)
    ))
    g.add_node("docker", governed("docker", db)(
        lambda s, m: docker_node(s, m, db)
    ))
    g.add_node("observability", governed("observability", db)(
        lambda s, m: observability_node(s, m, db)
    ))
    g.add_node("tester", governed("tester", db)(
        lambda s, m: tester_node(s, m, db)
    ))
    g.add_node("debugger", governed("debugger", db)(debugger_node))
    g.add_node("reviewer", governed("reviewer", db)(reviewer_node))

    # ── Review phase nodes ────────────────────────────────────────────
    g.add_node("review_supervisor", governed("review_sup", db)(review_supervisor_node))
    g.add_node("review_verdict", governed("review_sup", db)(review_supervisor_node))
    g.add_node("security", governed("security", db)(security_node))
    g.add_node("perf", governed("perf", db)(perf_node))
    g.add_node("style", governed("style", db)(style_node))
    g.add_node("coverage", governed("coverage", db)(coverage_node))

    # ── Terminal nodes ─────────────────────────────────────────────────
    g.add_node("halt", halt_node)
    g.add_node("report", report_node)

    # ── Dev phase edges ────────────────────────────────────────────────
    g.add_edge(START, "planner")
    g.add_edge("planner", "approval_gate")  # gate between planner and coder
    g.add_conditional_edges(
        "approval_gate",
        _after_approval,
        {"halt": "halt", "coder": "coder"},
    )
    g.add_edge("coder", "docker")
    g.add_edge("docker", "observability")
    g.add_edge("observability", "tester")

    g.add_conditional_edges(
        "tester",
        _after_tester,
        {"halt": "halt", "reviewer": "reviewer", "planner": "planner", "debugger": "debugger"},
    )
    g.add_edge("debugger", "coder")

    g.add_conditional_edges(
        "reviewer",
        _after_reviewer,
        {"halt": "halt", "review_supervisor": "review_supervisor"},
    )

    # ── Review phase: sequential specialist chain then verdict ─────────
    g.add_edge("review_supervisor", "security")
    g.add_edge("security", "perf")
    g.add_edge("perf", "style")
    g.add_edge("style", "coverage")
    g.add_edge("coverage", "review_verdict")

    g.add_conditional_edges(
        "review_verdict",
        _verdict_router,
        {"halt": "halt", "planner": "planner", "report": "report"},
    )

    g.add_edge("report", END)
    g.add_edge("halt", END)

    checkpointer = _make_checkpointer()
    return g.compile(checkpointer=checkpointer)


def _make_checkpointer():
    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None
    try:
        conn_str = (
            f"postgresql://{os.getenv('POSTGRES_USER', 'pipeline')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'pipeline_secret')}@"
            f"{host}:{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'build_ship')}"
        )
        conn = psycopg.connect(conn_str)
        saver = PostgresSaver(conn)
        saver.setup()
        return saver
    except Exception:
        return None
