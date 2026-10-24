"""개선 조치
GET   /api/tasks              — 목록 (쿼리: product_id · status)
POST  /api/tasks              — 만들기 → 201
PATCH /api/tasks/{task_id}    — 수정 (status · assignee · due_date · title)
"""
from fastapi import APIRouter, Depends

from app.database import get_db
from app.schemas import TaskCreate, TaskUpdate
from app.services import tasks as svc

router = APIRouter(prefix="/api/tasks", tags=["개선 조치"])


@router.get("")
def list_tasks(product_id: str | None = None, status: str | None = None, conn=Depends(get_db)):
    return svc.list_tasks(conn, product_id, status)


@router.post("", status_code=201)
def create_task(body: TaskCreate, conn=Depends(get_db)):
    return svc.create_task(conn, body.model_dump())


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskUpdate, conn=Depends(get_db)):
    return svc.update_task(conn, task_id, body.model_dump(exclude_unset=True))
