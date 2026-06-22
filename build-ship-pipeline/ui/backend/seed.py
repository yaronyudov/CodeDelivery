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
from pydantic import ValidationError  # noqa: E402

from src.db.repo import PipelineRepo  # noqa: E402
from ui.backend.auth import hash_password  # noqa: E402
from ui.backend.models import SkillCreate  # noqa: E402

_SKILLS_DIR = Path(__file__).parent.parent.parent / "agents" / "skills"


def _load_skill_definitions() -> list[dict]:
    """Load and validate every skill definition in agents/skills/*.yml.

    Each file is validated through the same ``SkillCreate`` schema the API uses,
    so a malformed definition fails fast with a clear error instead of inserting
    bad data. The server-controlled ``is_system`` flag (default ``True``) is
    re-attached after validation, since the API model never accepts it from input.
    """
    skills: list[dict] = []
    for path in sorted(_SKILLS_DIR.glob("*.yml")):
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError(f"{path.name}: expected a YAML mapping, got {type(raw).__name__}")
        is_system = raw.pop("is_system", True)
        try:
            validated = SkillCreate.model_validate(raw).model_dump()
        except ValidationError as exc:
            raise ValueError(f"{path.name}: invalid skill definition\n{exc}") from exc
        validated["is_system"] = is_system
        skills.append(validated)
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
