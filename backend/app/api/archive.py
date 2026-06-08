"""
会话存档 API：状态 + 手动触发同步
（仅服务器 Linux + SDK 可真正运行；本地返回不可用）
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.core import wework_finance

router = APIRouter(prefix="/archive", tags=["会话存档"])


@router.get("/status", summary="会话存档配置状态")
async def archive_status(current_user: dict = Depends(get_current_user)):
    return {"available": wework_finance.is_available()}


@router.post("/sync", summary="手动触发会话存档同步")
async def archive_sync(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    if not wework_finance.is_available():
        return {"success": False, "message": "未配置会话存档(SDK/Secret/私钥)，仅服务器可用"}

    def do_sync():
        db = SessionLocal()
        try:
            from app.services.chat_archive_service import ChatArchiveService
            ChatArchiveService(db).sync()
        finally:
            db.close()

    background_tasks.add_task(do_sync)
    return {"success": True, "message": "会话存档同步已触发"}
