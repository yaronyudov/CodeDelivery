"""Skill management endpoints — CRUD for skill definitions and defaults."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ui.backend.dependencies import get_current_user, get_db
from ui.backend.models import SkillCreate, SkillResponse, SkillUpdate, TokenData

router = APIRouter(tags=["skills"])


@router.get("", response_model=list[SkillResponse])
async def list_skills(user: TokenData = Depends(get_current_user)):
    db = get_db()
    rows = db.list_skills()
    return [_to_response(r) for r in rows]


@router.get("/defaults", response_model=list[SkillResponse])
async def list_default_skills(user: TokenData = Depends(get_current_user)):
    db = get_db()
    rows = db.get_default_skills()
    return [_to_response(r) for r in rows]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    row = db.get_skill(skill_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _to_response(row)


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(body: SkillCreate, user: TokenData = Depends(get_current_user)):
    db = get_db()
    if db.get_skill(body.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill ID already exists")
    db.create_skill(body.model_dump())
    return _to_response(db.get_skill(body.id))


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    body: SkillUpdate,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    row = db.get_skill(skill_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if row["is_system"] and body.model_dump(exclude_none=True).keys() - {
        "prompt_addon",
        "is_default",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System skills can only have prompt_addon and is_default changed",
        )
    db.update_skill(skill_id, body.model_dump(exclude_none=True))
    return _to_response(db.get_skill(skill_id))


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    row = db.get_skill(skill_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if row["is_system"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete system skills"
        )
    db.delete_skill(skill_id)


@router.patch("/{skill_id}/default", response_model=SkillResponse)
async def toggle_default(skill_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    result = db.toggle_skill_default(skill_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _to_response(db.get_skill(skill_id))


def _to_response(row: dict) -> SkillResponse:
    return SkillResponse(
        id=row["id"],
        name=row["name"],
        description=row.get("description", ""),
        kind=row["kind"],
        target_agents=row.get("target_agents") or [],
        prompt_addon=row.get("prompt_addon"),
        is_default=row.get("is_default", False),
        is_system=row.get("is_system", False),
        created_at=str(row.get("created_at", "")),
    )
