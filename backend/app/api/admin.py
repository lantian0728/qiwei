"""
后台配置API：企业微信配置、系统参数、用户权限、同步日志
"""
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.wxwork_client import WxWorkClient, WxWorkAPIError
from app.models.models import WxCorpConfig, WxSystemConfig, SysUser, WxSyncLog

router = APIRouter(prefix="/admin", tags=["后台配置"])

SYNC_STATUS_NAMES = {1: "进行中", 2: "成功", 3: "失败"}


def _corp_id(current_user: dict) -> str:
    cid = current_user.get("corp_id")
    if not cid:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return cid


# ========== 企业微信配置 ==========

class CorpConfigRequest(BaseModel):
    corp_id: str
    corp_name: Optional[str] = ""
    agent_id: Optional[str] = ""
    corp_secret: Optional[str] = ""
    token: Optional[str] = ""
    encoding_aes_key: Optional[str] = ""
    webhook_url: Optional[str] = ""


@router.get("/corp-config", summary="获取企业微信配置")
async def get_corp_config(db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    config = db.query(WxCorpConfig).filter(WxCorpConfig.corp_id == cid).first()
    if not config:
        return {"configured": False}
    # 不回传明文 Secret，仅标记是否已设置
    return {
        "configured": True,
        "corp_id": config.corp_id,
        "corp_name": config.corp_name,
        "agent_id": config.agent_id,
        "corp_secret": "******" if config.corp_secret else "",
        "token": config.token,
        "encoding_aes_key": config.encoding_aes_key,
        "webhook_url": config.webhook_url,
        "is_active": config.is_active,
    }


@router.post("/corp-config", summary="保存企业微信配置")
async def save_corp_config(req: CorpConfigRequest, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    config = db.query(WxCorpConfig).filter(WxCorpConfig.corp_id == req.corp_id).first()
    if not config:
        config = WxCorpConfig(corp_id=req.corp_id)
        db.add(config)
    config.corp_name = req.corp_name or ""
    config.agent_id = req.agent_id or ""
    # 仅当传入了非掩码值时才更新 Secret
    if req.corp_secret and req.corp_secret != "******":
        config.corp_secret = req.corp_secret
    config.token = req.token or ""
    config.encoding_aes_key = req.encoding_aes_key or ""
    config.webhook_url = req.webhook_url or ""
    config.is_active = True
    db.commit()
    return {"success": True, "message": "保存成功"}


@router.post("/test-connection", summary="测试企业微信连接")
async def test_connection(db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    config = db.query(WxCorpConfig).filter(WxCorpConfig.corp_id == cid).first()
    if not config or not config.corp_secret:
        return {"success": False, "message": "未配置 Secret，无法测试"}
    try:
        client = WxWorkClient(corp_id=config.corp_id, corp_secret=config.corp_secret)
        await client.test_connection()
        return {"success": True, "message": "连接成功，凭证有效"}
    except WxWorkAPIError as e:
        return {"success": False, "message": f"连接失败：{e.errmsg}"}


# ========== 系统参数 ==========

@router.get("/system-config", summary="获取系统参数")
async def get_system_config(db: Session = Depends(get_db),
                            current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    rows = db.query(WxSystemConfig).filter(WxSystemConfig.corp_id == cid).all()
    return {r.config_key: r.config_value for r in rows}


@router.post("/system-config", summary="保存系统参数")
async def save_system_config(configs: Dict[str, Any], db: Session = Depends(get_db),
                             current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    for key, value in configs.items():
        row = db.query(WxSystemConfig).filter(
            WxSystemConfig.corp_id == cid, WxSystemConfig.config_key == key
        ).first()
        if not row:
            row = WxSystemConfig(corp_id=cid, config_key=key)
            db.add(row)
        row.config_value = str(value)
    db.commit()
    return {"success": True, "message": "系统参数保存成功"}


# ========== 用户权限 ==========

class UpdateRoleRequest(BaseModel):
    userid: str
    role: int


@router.get("/users", summary="获取用户列表")
async def get_users(db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    users = db.query(SysUser).filter(SysUser.corp_id == cid).order_by(SysUser.role).all()
    return [
        {
            "userid": u.userid, "username": u.username, "real_name": u.real_name,
            "department": u.department, "role": u.role,
            "is_active": bool(u.is_active),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]


@router.post("/users/role", summary="更新用户角色")
async def update_user_role(req: UpdateRoleRequest, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    if req.role not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="角色无效")
    user = db.query(SysUser).filter(
        SysUser.corp_id == cid, SysUser.userid == req.userid
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.role = req.role
    db.commit()
    return {"success": True, "message": "角色已更新"}


class SetActiveRequest(BaseModel):
    userid: str
    is_active: bool


@router.post("/users/active", summary="授权/停用用户登录(审核制)")
async def set_user_active(req: SetActiveRequest, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    user = db.query(SysUser).filter(
        SysUser.corp_id == cid, SysUser.userid == req.userid
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = req.is_active
    db.commit()
    return {"success": True, "message": "已授权登录" if req.is_active else "已停用登录"}


# ========== 同步日志 ==========

@router.get("/sync-logs", summary="获取同步日志")
async def get_sync_logs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                        db: Session = Depends(get_db),
                        current_user: dict = Depends(get_current_user)):
    cid = _corp_id(current_user)
    query = db.query(WxSyncLog).filter(WxSyncLog.corp_id == cid) \
        .order_by(WxSyncLog.started_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "sync_type": lg.sync_type, "status": lg.status,
                "status_name": SYNC_STATUS_NAMES.get(lg.status, ""),
                "total_count": lg.total_count, "success_count": lg.success_count,
                "fail_count": lg.fail_count, "error_msg": lg.error_msg,
                "started_at": lg.started_at.isoformat() if lg.started_at else None,
                "finished_at": lg.finished_at.isoformat() if lg.finished_at else None,
            }
            for lg in logs
        ],
    }
