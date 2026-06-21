"""Pydantic output schemas for every LLM-facing agent node.

Each schema covers exactly what the agent's system prompt asks for, so
parse errors are caught early and callers always receive a typed default
rather than a bare dict or empty list.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class PlanTask(BaseModel):
    id: str = ""
    title: str = ""
    description: str = ""
    owner: str = ""


class PlannerOutput(BaseModel):
    summary: str = ""
    tasks: list[PlanTask] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    complexity: float = 1.0
    acceptance_criteria: list[str] = Field(default_factory=list)

    @field_validator("complexity")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.5, min(3.0, v))


# ---------------------------------------------------------------------------
# Coder / Observability / Docker — they all produce file arrays
# ---------------------------------------------------------------------------

class FileOutput(BaseModel):
    path: str
    content: str
    kind: str = "code"

    @field_validator("path")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("path must not be empty")
        return v


class FilesOutput(BaseModel):
    """Wrapper for agents that return a JSON array of FileOutput."""
    files: list[FileOutput] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------

class TestResults(BaseModel):
    passed: bool = False
    summary: str = ""
    failures: list[str] = Field(default_factory=list)


class TesterOutput(BaseModel):
    files: list[FileOutput] = Field(default_factory=list)
    results: TestResults = Field(default_factory=TestResults)


# ---------------------------------------------------------------------------
# Debugger
# ---------------------------------------------------------------------------

class DebuggerOutput(BaseModel):
    diagnosis: str = ""
    fix_targets: list[str] = Field(default_factory=list)
    fix_instructions: str = ""
    escalate_to_planner: bool = False


# ---------------------------------------------------------------------------
# Reviewer (internal dev-phase sign-off)
# ---------------------------------------------------------------------------

class ReviewerOutput(BaseModel):
    approved: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Review specialists — security / perf / style / coverage all return findings
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"critical", "major", "minor", "info"}


class ReviewFinding(BaseModel):
    severity: Literal["critical", "major", "minor", "info"] = "info"
    message: str = ""
    location: str = "unknown"

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v: object) -> str:
        s = str(v).lower()
        return s if s in _VALID_SEVERITIES else "info"


class FindingsOutput(BaseModel):
    """Wrapper for review agents that return a JSON array of findings."""
    findings: list[ReviewFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Review Supervisor
# ---------------------------------------------------------------------------

class SupervisorOutput(BaseModel):
    verdict: Literal["clean", "minor", "critical"] = "clean"
    summary: str = ""
    action_required: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v: object) -> str:
        s = str(v).lower()
        return s if s in {"clean", "minor", "critical"} else "clean"
