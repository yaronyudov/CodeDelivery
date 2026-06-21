"""Shared helpers for all agent nodes."""
from __future__ import annotations

from dataclasses import dataclass

from anthropic import Anthropic

_client = Anthropic()  # reads ANTHROPIC_API_KEY from environment


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
) -> tuple[str, Usage]:
    """Single-turn model call.  Returns (response_text, Usage)."""
    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    usage = Usage(
        in_=response.usage.input_tokens,
        out=response.usage.output_tokens,
    )
    text = response.content[0].text if response.content else ""
    return text, usage
