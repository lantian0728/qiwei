"""
驾驶舱API：今日必须处理（聚合各模块的待办/风险）
随后续模块（流失预警、投诉雷达）接入会持续扩充。
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import WxAlert
from app.services.staff_service import StaffPerformanceService

router = APIRouter(prefix="/dashboard", tags=["驾驶舱"])


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


@router.get("/today-actions", summary="今日必须处理")
async def today_actions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    actions = []

    # 1) 今日超时/未响应（客服效能模块）
    today = date.today()
    timeouts = StaffPerformanceService(db).timeout_list(cid, today, today, limit=10)
    for t in timeouts:
        actions.append({
            "level": "high" if not t["answered"] else "medium",
            "type": "客服超时",
            "group_name": t["group_name"],
            "chat_id": t["chat_id"],
            "text": f"{t['group_name']}：客户消息{t['status']}" +
                    (f"（等待{t['wait_min']}分钟）" if t["wait_min"] else ""),
        })

    # 2) 未读预警（沉默群 / 后续的流失、投诉预警都会进这里）
    alerts = db.query(WxAlert).filter(
        WxAlert.corp_id == cid, WxAlert.is_read == False,
    ).order_by(WxAlert.created_at.desc()).limit(10).all()
    for a in alerts:
        actions.append({
            "level": "high" if a.alert_level == 1 else "medium" if a.alert_level == 2 else "low",
            "type": {1: "沉默群", 2: "活跃度下降", 3: "风险"}.get(a.alert_type, "预警"),
            "group_name": a.group_name,
            "chat_id": a.chat_id,
            "text": a.content,
        })

    # 高优先级排前
    order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda x: order.get(x["level"], 9))
    return {"total": len(actions), "actions": actions}
