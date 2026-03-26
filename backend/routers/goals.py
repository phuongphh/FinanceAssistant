import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.goal import (
    GoalCreate,
    GoalProgressUpdate,
    GoalResponse,
    GoalUpdate,
    IncomeUpdate,
)
from backend.services import goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    data: GoalCreate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await goal_service.create_goal(db, user_id, data)


@router.get("", response_model=list[GoalResponse])
async def list_goals(
    user_id: uuid.UUID = Query(...),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    return await goal_service.list_goals(db, user_id, active_only=active_only)


@router.put("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: uuid.UUID,
    data: GoalUpdate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.update_goal(db, user_id, goal_id, data)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.put("/{goal_id}/progress", response_model=GoalResponse)
async def update_goal_progress(
    goal_id: uuid.UUID,
    data: GoalProgressUpdate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.update_goal_progress(db, user_id, goal_id, data)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    deleted = await goal_service.delete_goal(db, user_id, goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")


# Income endpoint — per CLAUDE.md: POST /users/income
income_router = APIRouter(prefix="/users", tags=["users"])


@income_router.post("/income")
async def set_income(
    data: IncomeUpdate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await goal_service.set_monthly_income(db, user_id, data.monthly_income)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": {"monthly_income": float(user.monthly_income)}, "error": None}
