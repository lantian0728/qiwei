"""
客服效能API：概览、排名榜、超时/未响应清单
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import WxSystemConfig
from app.services.staff_service import StaffPerformanceService, STAFF_NAMES_KEY

router = APIRouter(prefix="/staff", tags=["客服效能"])


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


def _range(start_date: Optional[date], end_date: Optional[date]):
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=7))
    return start, end


@router.get("/overview", summary="客服效能概览")
async def staff_overview(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    start, end = _range(start_date, end_date)
    return StaffPerformanceService(db).overview(cid, start, end)


@router.get("/ranking", summary="客服首响排名榜")
async def staff_ranking(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    start, end = _range(start_date, end_date)
    return StaffPerformanceService(db).staff_ranking(cid, start, end)


@router.get("/timeouts", summary="超时/未响应清单")
async def staff_timeouts(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    start, end = _range(start_date, end_date)
    return StaffPerformanceService(db).timeout_list(cid, start, end, limit)


@router.get("/staff-names", summary="获取客服名单")
async def get_staff_names(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    return {"names": sorted(StaffPerformanceService(db).staff_names(cid))}


class StaffNamesReq(BaseModel):
    names: list[str]


@router.post("/staff-names", summary="设置客服名单(只统计这些人的客服效能/发言)")
async def set_staff_names(
    req: StaffNamesReq,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    clean = [n.strip() for n in req.names if n.strip()]
    row = db.query(WxSystemConfig).filter(
        WxSystemConfig.corp_id == cid, WxSystemConfig.config_key == STAFF_NAMES_KEY
    ).first()
    if not row:
        row = WxSystemConfig(corp_id=cid, config_key=STAFF_NAMES_KEY)
        db.add(row)
    row.config_value = ",".join(clean)
    db.commit()
    return {"success": True, "names": clean}
