"""
认证相关API：企业微信OAuth2登录、JWT令牌管理
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.core.wxwork_client import WxWorkClient, WxWorkAPIError
from app.models.models import SysUser, WxCorpConfig
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])

# 角色常量：1 超管 / 2 管理员 / 3 运营（数值越大权限越低）
ROLE_OPERATOR = 3


class LoginRequest(BaseModel):
    code: str
    corp_id: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_info: dict


@router.post("/login/wxwork", summary="企业微信OAuth2登录")
async def login_with_wxwork(req: LoginRequest, db: Session = Depends(get_db)):
    """
    通过企业微信OAuth2 code换取系统JWT令牌
    前端从企业微信获取code后调用此接口
    """
    corp_id = req.corp_id or settings.WX_CORP_ID

    config = db.query(WxCorpConfig).filter(
        WxCorpConfig.corp_id == corp_id,
        WxCorpConfig.is_active == True,
    ).first()

    if not config:
        raise HTTPException(status_code=400, detail="企业配置不存在，请先完成API配置")

    try:
        client = WxWorkClient(corp_id=corp_id, corp_secret=config.corp_secret)
        user_data = await client.get_user_info_by_code(req.code)
        userid = user_data.get("UserId") or user_data.get("userid", "")

        if not userid:
            raise HTTPException(status_code=401, detail="无法获取用户信息，请确认企业微信授权")

        user = db.query(SysUser).filter(
            SysUser.corp_id == corp_id,
            SysUser.userid == userid,
        ).first()

        if not user:
            # 安全默认：新用户一律按最低权限「运营」创建，需由超管手动提权
            try:
                user_detail = await client.get_user_info(userid)
                user = SysUser(
                    corp_id=corp_id, userid=userid,
                    username=user_detail.get("name", userid),
                    real_name=user_detail.get("name", ""),
                    avatar_url=user_detail.get("avatar", ""),
                    email=user_detail.get("email", ""),
                    mobile=user_detail.get("mobile", ""),
                    role=ROLE_OPERATOR,
                )
                db.add(user)
            except Exception:
                user = SysUser(corp_id=corp_id, userid=userid,
                               username=userid, role=ROLE_OPERATOR)
                db.add(user)

        user.last_login_at = datetime.now()
        db.commit()
        db.refresh(user)

    except WxWorkAPIError as e:
        raise HTTPException(status_code=401, detail=f"企业微信认证失败: {e.errmsg}")

    token_data = {
        "sub": userid, "corp_id": corp_id,
        "role": user.role, "username": user.username,
    }
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        user_info={
            "userid": user.userid, "username": user.username,
            "real_name": user.real_name, "avatar_url": user.avatar_url,
            "role": user.role, "corp_id": corp_id,
        },
    )


@router.post("/login/demo", summary="快速登录（演示数据 或 已配置的真实企业）")
async def login_demo(db: Session = Depends(get_db)):
    """快速登录：仅演示模式可用；配了真实企业(WX_CORP_ID)则关闭，强制账号密码登录。"""
    if settings.WX_CORP_ID:
        raise HTTPException(status_code=403, detail="演示登录已关闭，请用账号密码登录")
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="请使用账号密码登录")
    corp_id = "demo_corp"
    userid = "admin"
    display = "演示管理员"
    user = db.query(SysUser).filter(
        SysUser.corp_id == corp_id, SysUser.userid == userid
    ).first()
    if not user:
        user = SysUser(corp_id=corp_id, userid=userid, username=display,
                       real_name=display, role=1)
        db.add(user)
    user.last_login_at = datetime.now()
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": userid, "corp_id": corp_id, "role": user.role, "username": user.username,
    })
    return TokenResponse(
        access_token=token,
        user_info={"userid": userid, "username": user.username, "real_name": user.real_name,
                   "avatar_url": "", "role": user.role, "corp_id": corp_id},
    )


class PasswordLoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login/password", summary="账号密码登录")
async def login_password(req: PasswordLoginRequest, db: Session = Depends(get_db)):
    from app.core.security import verify_password
    corp_id = settings.WX_CORP_ID or "demo_corp"
    user = db.query(SysUser).filter(
        SysUser.corp_id == corp_id, SysUser.userid == req.username
    ).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    user.last_login_at = datetime.now()
    db.commit()
    token = create_access_token({
        "sub": user.userid, "corp_id": corp_id, "role": user.role, "username": user.username,
    })
    return TokenResponse(
        access_token=token,
        user_info={"userid": user.userid, "username": user.username,
                   "real_name": user.real_name, "avatar_url": user.avatar_url or "",
                   "role": user.role, "corp_id": corp_id},
    )


@router.get("/me", summary="获取当前用户信息")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.get("/wxwork/oauth_url", summary="获取企业微信OAuth2授权URL")
async def get_oauth_url(redirect_uri: str, corp_id: Optional[str] = None):
    _corp_id = corp_id or settings.WX_CORP_ID
    client = WxWorkClient(corp_id=_corp_id)
    url = client.get_oauth_url(redirect_uri)
    return {"oauth_url": url}
