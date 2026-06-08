"""
预警API：预警列表、标记已读
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import WxAlert

router = APIRouter(prefix="/alerts", tags=["预警"])

ALERT_TYPE_NAMES = {1: "沉默群", 2: "客户流失", 3: "投诉风险"}
ALERT_LEVEL_NAMES = {1: "严重", 2: "警告", 3: "提示"}


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


@router.get("", summary="获取预警列表")
@router.get("/", summary="获取预警列表", include_in_schema=False)
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_read: bool = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    query = db.query(WxAlert).filter(WxAlert.corp_id == cid)
    if is_read is not None:
        query = query.filter(WxAlert.is_read == is_read)
    query = query.order_by(WxAlert.created_at.desc())

    total = query.count()
    alerts = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": a.id, "chat_id": a.chat_id, "group_name": a.group_name,
                "alert_type": a.alert_type, "alert_type_name": ALERT_TYPE_NAMES.get(a.alert_type, ""),
                "alert_level": a.alert_level, "alert_level_name": ALERT_LEVEL_NAMES.get(a.alert_level, ""),
                "content": a.content, "is_read": a.is_read,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ],
    }


class ReadRequest(BaseModel):
    ids: list[int] = []
    all: bool = False


@router.post("/read", summary="标记预警已读")
async def mark_read(req: ReadRequest, db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    query = db.query(WxAlert).filter(WxAlert.corp_id == cid, WxAlert.is_read == False)
    if not req.all:
        query = query.filter(WxAlert.id.in_(req.ids or []))
    count = 0
    for a in query.all():
        a.is_read = True
        count += 1
    db.commit()
    return {"success": True, "marked": count}
