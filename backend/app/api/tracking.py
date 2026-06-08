"""
查件 + 客户匹配 API（对接新智慧 NextSLS）
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.core import nextsls
from app.services.tracking_service import TrackingService
from app.services.customer_match_service import CustomerMatchService

router = APIRouter(prefix="/tracking", tags=["查件"])


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


@router.get("/status", summary="查件配置状态")
async def tracking_status(current_user: dict = Depends(get_current_user)):
    return {"nextsls_available": nextsls.is_available()}


@router.get("/by-number", summary="按单号查轨迹")
async def track_by_number(
    number: str = Query(..., description="系统运单号或客户单号"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _corp_id(current_user)
    return await TrackingService(db).track_by_number(number)


@router.get("/by-group", summary="按群查客户运单")
async def track_by_group(
    chat_id: str = Query(...),
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    return await TrackingService(db).track_by_group(cid, chat_id, limit)


# ---------- 客户匹配 ----------

@router.post("/match/run", summary="自动匹配群↔客户")
async def match_run(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    return await CustomerMatchService(db).match_all(cid)


@router.get("/match/list", summary="群↔客户映射列表")
async def match_list(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    return CustomerMatchService(db).list_mappings(cid)


class SetMappingRequest(BaseModel):
    chat_id: str
    user_number: str
    customer_name: str


@router.post("/match/set", summary="手动确认群↔客户")
async def match_set(
    req: SetMappingRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    CustomerMatchService(db).set_mapping(cid, req.chat_id, req.user_number, req.customer_name)
    return {"success": True}


# ---------- 群机器人轨迹推送 ----------

class SetWebhookRequest(BaseModel):
    chat_id: str
    webhook_url: str


@router.post("/webhook/set", summary="为群配置机器人webhook(配了才自动推轨迹)")
async def set_webhook(
    req: SetWebhookRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    from app.models.models import WxGroupCustomer
    row = db.query(WxGroupCustomer).filter(
        WxGroupCustomer.corp_id == cid, WxGroupCustomer.chat_id == req.chat_id
    ).first()
    if not row:
        row = WxGroupCustomer(corp_id=cid, chat_id=req.chat_id)
        db.add(row)
    row.webhook_url = req.webhook_url
    db.commit()
    return {"success": True}


@router.post("/push/run", summary="立即执行一次轨迹变化巡检推送")
async def push_run(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cid = _corp_id(current_user)
    from app.services.push_service import run_tracking_push
    return await run_tracking_push(db, cid)
