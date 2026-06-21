"""Seed initial users from environment variables.

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

from src.db.repo import PipelineRepo
from ui.backend.auth import hash_password


def seed() -> None:
    username = os.environ.get("SEED_USERNAME", "admin")
    password = os.environ.get("SEED_PASSWORD")
    if not password:
        print("ERROR: SEED_PASSWORD environment variable not set", file=sys.stderr)
        sys.exit(1)

    db = PipelineRepo()
    existing = db.get_user_by_username(username)
    if existing:
        print(f"User '{username}' already exists (id={existing['id']}). Skipping.")
        return

    hashed = hash_password(password)
    user_id = db.create_user(username, hashed)
    print(f"Created user '{username}' with id={user_id}.")
    db.close()


if __name__ == "__main__":
    seed()
