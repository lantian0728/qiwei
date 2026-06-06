"""
企业微信 API 客户端（只读监测用）
封装：access_token 获取、OAuth2 登录、用户信息、客户群列表/详情

注意：所有接口均为企业微信官方只读接口，不发送任何消息。
真实调用需要在「管理后台」配置可信 IP 与对应权限的自建应用 Secret。
"""
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx

WX_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WxWorkAPIError(Exception):
    """企业微信接口返回 errcode != 0 时抛出。"""

    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"[{errcode}] {errmsg}")


class WxWorkClient:
    # 进程内简单缓存 access_token：{(corp_id, secret): (token, expire_ts)}
    _token_cache: Dict[str, Any] = {}

    def __init__(self, corp_id: str, corp_secret: Optional[str] = None):
        self.corp_id = corp_id
        self.corp_secret = corp_secret

    # ---------- 基础请求 ----------

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{WX_API_BASE}{path}", params=params)
            data = resp.json()
        if data.get("errcode", 0) != 0:
            raise WxWorkAPIError(data.get("errcode"), data.get("errmsg", "unknown error"))
        return data

    async def _post(self, path: str, params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{WX_API_BASE}{path}", params=params, json=body)
            data = resp.json()
        if data.get("errcode", 0) != 0:
            raise WxWorkAPIError(data.get("errcode"), data.get("errmsg", "unknown error"))
        return data

    # ---------- access_token ----------

    async def get_access_token(self) -> str:
        if not self.corp_secret:
            raise WxWorkAPIError(-1, "缺少 corp_secret，无法获取 access_token")

        cache_key = f"{self.corp_id}:{self.corp_secret}"
        cached = self._token_cache.get(cache_key)
        if cached and cached[1] > time.time():
            return cached[0]

        data = await self._get("/gettoken", {
            "corpid": self.corp_id,
            "corpsecret": self.corp_secret,
        })
        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        # 提前 5 分钟过期，留出余量
        self._token_cache[cache_key] = (token, time.time() + expires_in - 300)
        return token

    # ---------- OAuth2 登录 ----------

    def get_oauth_url(self, redirect_uri: str, state: str = "wxwork") -> str:
        """构造企业微信网页授权 URL（用户同意后回调带 code）。"""
        params = {
            "appid": self.corp_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "snsapi_base",
            "state": state,
        }
        return f"https://open.weixin.qq.com/connect/oauth2/authorize?{urlencode(params)}#wechat_redirect"

    async def get_user_info_by_code(self, code: str) -> Dict[str, Any]:
        """用 OAuth2 code 换取登录用户的 UserId。"""
        token = await self.get_access_token()
        return await self._get("/auth/getuserinfo", {"access_token": token, "code": code})

    async def get_user_info(self, userid: str) -> Dict[str, Any]:
        """获取通讯录中用户的详细信息。"""
        token = await self.get_access_token()
        return await self._get("/user/get", {"access_token": token, "userid": userid})

    # ---------- 客户群（只读） ----------

    async def list_group_chats(self, owner_filter: Optional[List[str]] = None,
                               cursor: str = "", limit: int = 100) -> Dict[str, Any]:
        """获取客户群列表（externalcontact/groupchat/list）。"""
        token = await self.get_access_token()
        body: Dict[str, Any] = {"status_filter": 0, "limit": limit}
        if owner_filter:
            body["owner_filter"] = {"userid_list": owner_filter}
        if cursor:
            body["cursor"] = cursor
        return await self._post("/externalcontact/groupchat/list", {"access_token": token}, body)

    async def get_group_chat_detail(self, chat_id: str) -> Dict[str, Any]:
        """获取客户群详情（含成员）。"""
        token = await self.get_access_token()
        return await self._post(
            "/externalcontact/groupchat/get",
            {"access_token": token},
            {"chat_id": chat_id, "need_name": 1},
        )

    async def test_connection(self) -> bool:
        """测试凭证是否有效（能否拿到 access_token）。"""
        await self.get_access_token()
        return True
