"""
客户流失预警API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.churn_service import ChurnService

router = APIRouter(prefix="/churn", tags=["客户流失预警"])


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


@router.get("/list", summary="客户流失风险列表")
async def churn_list(db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    return ChurnService(db).list_at_risk(cid)


@router.post("/scan", summary="扫描并生成流失预警")
async def churn_scan(db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    n = ChurnService(db).generate_alerts(cid)
    return {"success": True, "new_alerts": n}
