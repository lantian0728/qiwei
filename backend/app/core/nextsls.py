"""
新智慧 NextSLS TMS MPAPI v5 客户端

认证：Authorization: Bearer <NEXTSLS_TOKEN>
仅封装查件相关只读接口：运单列表、运单路由(轨迹)、批量轨迹。
（注：本企业密钥对 /user/list 无权限，客户名单改由运单列表汇总得到。）
未配置 NEXTSLS_TOKEN 时 is_available() 返回 False。
"""
from typing import Dict, Any, List, Optional

import httpx

from app.core.config import settings


class NextSLSError(Exception):
    def __init__(self, info: str):
        self.info = info
        super().__init__(info)


def is_available() -> bool:
    return bool(settings.NEXTSLS_TOKEN)


class NextSLSClient:
    def __init__(self):
        self.base = settings.NEXTSLS_BASE_URL.rstrip("/")
        self.token = settings.NEXTSLS_TOKEN

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.token:
            raise NextSLSError("未配置 NEXTSLS_TOKEN")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{self.base}{path}", json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != 1:
            raise NextSLSError(data.get("info", "请求失败"))
        return data.get("data", {})

    # ---------- 运单列表 ----------
    async def shipment_list(self, *, page: int = 1, page_size: int = 30,
                            user_number: str = "", waybill_id: str = "",
                            shipment_id: str = "", status: str = "",
                            start_time: str = "", end_time: str = "") -> List[Dict[str, Any]]:
        body = {"shipment": {
            "page": page, "page_size": page_size,
            "user_number": user_number, "waybill_id": waybill_id,
            "shipment_id": shipment_id, "status": status,
            "start_time": start_time, "end_time": end_time,
        }}
        data = await self._post("/shipment/list", body)
        return data.get("shipment", []) or []

    # ---------- 运单路由(轨迹) ----------
    async def shipment_tracking(self, *, shipment_id: str = "",
                                client_reference: str = "", parcel_number: str = "",
                                language: str = "zh") -> Dict[str, Any]:
        body = {"shipment": {
            "shipment_id": shipment_id, "client_reference": client_reference,
            "parcel_number": parcel_number, "language": language,
        }}
        data = await self._post("/shipment/tracking", body)
        return data.get("shipment", {}) or {}

    async def batch_tracking(self, queries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        body = {"shipment": [
            {"shipment_id": q.get("shipment_id", ""),
             "client_reference": q.get("client_reference", ""),
             "language": "zh"} for q in queries[:30]
        ]}
        data = await self._post("/shipment/batch_tracking", body)
        return data.get("shipment", []) or []


# 订单状态中文映射
STATUS_NAMES = {
    "ready": "已下单", "picked": "已收货", "in_transit": "转运中",
    "delivered": "已签收", "returned": "退件", "cancelled": "已取消",
}
