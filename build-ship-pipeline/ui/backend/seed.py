"""Seed initial users and system skills from environment variables.

Usage:
    SEED_USERNAME=admin SEED_PASSWORD=changeme python -m ui.backend.seed

Idempotent — safe to run multiple times.
Skills are loaded from agents/skills/*.yml at the repo root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

import yaml  # noqa: E402

from src.db.repo import PipelineRepo  # noqa: E402
from ui.backend.auth import hash_password  # noqa: E402

_SKILLS_DIR = Path(__file__).parent.parent.parent / "agents" / "skills"


def _load_skill_definitions() -> list[dict]:
    skills = []
    for path in sorted(_SKILLS_DIR.glob("*.yml")):
        with path.open() as f:
            skill = yaml.safe_load(f)
        if skill.get("prompt_addon") == "null":
            skill["prompt_addon"] = None
        skill.setdefault("is_system", True)
        skills.append(skill)
    return skills


def seed_skills(db: PipelineRepo) -> None:
    """Insert built-in system skills from agents/skills/*.yml. Idempotent — skips existing IDs."""
    skills = _load_skill_definitions()
    if not skills:
        print(f"WARNING: No skill YAML files found in {_SKILLS_DIR}")
        return
    for skill in skills:
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
