"""Pydantic schemas for the UI backend API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Agents that must always run — disabling them produces an empty/broken pipeline.
_ESSENTIAL_AGENTS = {"planner", "coder"}


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenData(BaseModel):
    user_id: int
    username: str


class ModelConfig(BaseModel):
    """Model selection and endpoint configuration."""

    provider: Literal["anthropic", "openai", "groq", "ollama", "custom"] = "anthropic"
    model: str = "anthropic/claude-sonnet-4-6"
    api_base: str | None = None  # for Ollama / Azure / custom
    api_key: str | None = None  # override (if not set, uses env var)


class RunSkillOverride(BaseModel):
    """Per-agent skill additions/removals for a single run."""

    add: list[str] = []  # skill IDs to add for this agent
    remove: list[str] = []  # skill IDs to remove for this agent


class StartRunRequest(BaseModel):
    feature_request: str = Field(..., min_length=10)
    model_config_: ModelConfig = Field(default_factory=ModelConfig, alias="model_config")
    require_approval: bool = False
    budget_overrides: dict | None = None
    # key = agent_name (e.g. "coder") or "*" for all agents
    skill_overrides: dict[str, RunSkillOverride] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class RunSummary(BaseModel):
    run_id: str
    feature_request: str
    status: str
    verdict: str | None
    require_approval: bool
    created_at: str
    finished_at: str | None


class RunDetail(RunSummary):
    model_config_: dict | None = None


class ApproveRequest(BaseModel):
    approved: bool


# ── Skill schemas ──────────────────────────────────────────────────────────────


class SkillCreate(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9-]+$", max_length=64, description="URL-safe slug")
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=500)
    kind: Literal["prompt_injection", "agent_toggle"]
    target_agents: list[str] = Field(default_factory=list, max_length=32)  # empty = all agents
    prompt_addon: str | None = Field(None, max_length=8000)
    is_default: bool = False

    @field_validator("target_agents")
    @classmethod
    def _no_essential_toggle(cls, v: list[str], info) -> list[str]:
        if info.data.get("kind") == "agent_toggle" and _ESSENTIAL_AGENTS.intersection(v):
            raise ValueError(
                f"agent_toggle skills cannot disable essential agents: {sorted(_ESSENTIAL_AGENTS)}"
            )
        return v


class SkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)
    target_agents: list[str] | None = Field(None, max_length=32)
    prompt_addon: str | None = Field(None, max_length=8000)
    is_default: bool | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    kind: str
    target_agents: list[str]
    prompt_addon: str | None
    is_default: bool
    is_system: bool
    created_at: str
