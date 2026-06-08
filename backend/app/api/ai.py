"""
AI 群日报API：生成、列表、全局情报
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.services.ai_report_service import AIReportService

router = APIRouter(prefix="/ai", tags=["AI日报"])


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


@router.post("/daily-report/run", summary="生成今日(或指定日)AI群日报")
async def run_daily_report(
    background_tasks: BackgroundTasks,
    report_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    day = report_date or date.today()

    async def do_run():
        task_db = SessionLocal()
        try:
            await AIReportService(task_db).generate_all(cid, day)
        finally:
            task_db.close()

    background_tasks.add_task(do_run)
    return {"success": True, "message": "AI 日报生成中，稍后刷新查看", "date": str(day)}


@router.get("/summaries", summary="获取群日报列表")
async def get_summaries(
    report_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    day = report_date or date.today()
    return AIReportService(db).get_summaries(cid, day)


@router.get("/brief", summary="全局今日情报(驾驶舱用)")
async def get_brief(
    report_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    day = report_date or date.today()
    return AIReportService(db).global_brief(cid, day)
