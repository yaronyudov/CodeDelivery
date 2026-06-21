"""Pydantic schemas for the UI backend API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    api_base: str | None = None   # for Ollama / Azure / custom
    api_key: str | None = None    # override (if not set, uses env var)


class RunSkillOverride(BaseModel):
    """Per-agent skill additions/removals for a single run."""
    add: list[str] = []      # skill IDs to add for this agent
    remove: list[str] = []   # skill IDs to remove for this agent


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
    id: str = Field(..., pattern=r"^[a-z0-9-]+$", description="URL-safe slug")
    name: str
    description: str = ""
    kind: Literal["prompt_injection", "agent_toggle"]
    target_agents: list[str] = []   # empty = all agents
    prompt_addon: str | None = None
    is_default: bool = False


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target_agents: list[str] | None = None
    prompt_addon: str | None = None
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
