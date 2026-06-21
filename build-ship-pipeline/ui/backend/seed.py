"""Seed initial users and system skills from environment variables.

Usage:
    SEED_USERNAME=admin SEED_PASSWORD=changeme python -m ui.backend.seed

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from src.db.repo import PipelineRepo  # noqa: E402
from ui.backend.auth import hash_password  # noqa: E402

_SYSTEM_SKILLS = [
    {
        "id": "skip-docker",
        "name": "Skip Docker",
        "description": "Disable the Docker Compose agent for this run.",
        "kind": "agent_toggle",
        "target_agents": ["docker"],
        "prompt_addon": None,
        "is_default": False,
        "is_system": True,
    },
    {
        "id": "skip-observability",
        "name": "Skip Observability",
        "description": "Disable OTel instrumentation and dashboard generation.",
        "kind": "agent_toggle",
        "target_agents": ["observability"],
        "prompt_addon": None,
        "is_default": False,
        "is_system": True,
    },
    {
        "id": "skip-security",
        "name": "Skip Security Review",
        "description": "Disable the security auditor specialist.",
        "kind": "agent_toggle",
        "target_agents": ["security"],
        "prompt_addon": None,
        "is_default": False,
        "is_system": True,
    },
    {
        "id": "skip-perf",
        "name": "Skip Performance Review",
        "description": "Disable the performance analyst specialist.",
        "kind": "agent_toggle",
        "target_agents": ["perf"],
        "prompt_addon": None,
        "is_default": False,
        "is_system": True,
    },
    {
        "id": "skip-style",
        "name": "Skip Style Review",
        "description": "Disable the style checker specialist.",
        "kind": "agent_toggle",
        "target_agents": ["style"],
        "prompt_addon": None,
        "is_default": False,
        "is_system": True,
    },
    {
        "id": "skip-coverage",
        "name": "Skip Coverage Review",
        "description": "Disable the test coverage inspector.",
        "kind": "agent_toggle",
        "target_agents": ["coverage"],
        "prompt_addon": None,
        "is_default": False,
        "is_system": True,
    },
]


def seed_skills(db: PipelineRepo) -> None:
    """Insert built-in system skills. Idempotent — skips existing IDs."""
    for skill in _SYSTEM_SKILLS:
        existing = db.get_skill(skill["id"])
        if existing:
            print(f"Skill '{skill['id']}' already exists. Skipping.")
        else:
            db.create_skill(skill)
            print(f"Created system skill '{skill['id']}'.")


def seed() -> None:
    username = os.environ.get("SEED_USERNAME", "admin")
    password = os.environ.get("SEED_PASSWORD")
    if not password:
        print("ERROR: SEED_PASSWORD environment variable not set", file=sys.stderr)
        sys.exit(1)

    db = PipelineRepo()

    # Seed user
    existing = db.get_user_by_username(username)
    if existing:
        print(f"User '{username}' already exists (id={existing['id']}). Skipping.")
    else:
        hashed = hash_password(password)
        user_id = db.create_user(username, hashed)
        print(f"Created user '{username}' with id={user_id}.")

    # Seed system skills
    seed_skills(db)

    db.close()


if __name__ == "__main__":
    seed()
