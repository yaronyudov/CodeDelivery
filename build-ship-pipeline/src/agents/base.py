"""Shared helpers for all agent nodes — model calls via LiteLLM."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Usage:
    in_: int
    out: int

    @property
    def total(self) -> int:
        return self.in_ + self.out


def call_model(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    api_base: str | None = None,
    api_key: str | None = None,
) -> tuple[str, Usage]:
    """Single-turn model call via LiteLLM.

    Supports any LiteLLM model string:
      anthropic/claude-sonnet-4-6
      openai/gpt-4o
      groq/llama-3.1-70b-versatile
      ollama/llama3              (needs api_base=http://localhost:11434)
      openai/<name>              (needs api_base=<custom endpoint>)
    """
    import litellm  # lazy import — avoid loading at module level in tests
    litellm.suppress_debug_info = True

    kwargs: dict = dict(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key

    response = litellm.completion(**kwargs)
    usage = Usage(
        in_=response.usage.prompt_tokens,
        out=response.usage.completion_tokens,
    )
    text = response.choices[0].message.content or ""
    return text, usage


def inject_skills(system: str, state: dict) -> str:
    """Append active skill instructions to an agent's system prompt."""
    ctx = state.get("_skill_ctx", "")
    if not ctx:
        return system
    return f"{system}\n\n## Active skill instructions:\n{ctx}"


def model_kwargs_from_state(state: dict) -> dict:
    """Extract model call kwargs from state['model_config']."""
    cfg = state.get("model_config") or {}
    out: dict = {}
    if cfg.get("api_base"):
        out["api_base"] = cfg["api_base"]
    if cfg.get("api_key"):
        out["api_key"] = cfg["api_key"]
    return out
