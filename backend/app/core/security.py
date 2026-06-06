"""
安全相关：JWT 签发与校验、当前用户依赖
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login/wxwork", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """从 JWT 解析当前用户信息，返回 token 里的 payload。"""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已过期或无效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exc

    userid = payload.get("sub")
    if not userid:
        raise credentials_exc

    return {
        "userid": userid,
        "corp_id": payload.get("corp_id"),
        "role": payload.get("role"),
        "username": payload.get("username"),
    }


def require_roles(*allowed_roles: int):
    """角色守卫：1 超管 / 2 管理员 / 3 运营。数值越小权限越高。"""
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        role = current_user.get("role")
        if role is None or role not in allowed_roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user
    return checker
