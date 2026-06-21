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


class StartRunRequest(BaseModel):
    feature_request: str = Field(..., min_length=10)
    model_config_: ModelConfig = Field(default_factory=ModelConfig, alias="model_config")
    require_approval: bool = False
    budget_overrides: dict | None = None  # optional token/cost limit overrides

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
