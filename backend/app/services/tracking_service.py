"""
查件服务 —— 基于新智慧 NextSLS

- 按单号查轨迹（系统运单号 / 客户单号）
- 按群查：群→客户(映射)→该客户近期运单 + 状态
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.core import nextsls
from app.core.nextsls import NextSLSClient, STATUS_NAMES
from app.services.customer_match_service import CustomerMatchService


def _fmt_traces(traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for t in traces or []:
        ts = t.get("time")
        when = ""
        if ts:
            try:
                when = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                when = str(ts)
        out.append({
            "info": t.get("info", ""), "time": when,
            "location": t.get("location", ""), "remark": t.get("remark", ""),
        })
    return out


class TrackingService:
    def __init__(self, db: Session):
        self.db = db

    async def track_by_number(self, number: str) -> Dict[str, Any]:
        """先按系统运单号查，查不到再按客户单号(client_reference)查。"""
        if not nextsls.is_available():
            return {"available": False, "message": "未配置新智慧 NEXTSLS_TOKEN"}
        client = NextSLSClient()
        number = (number or "").strip()
        if not number:
            return {"available": True, "found": False, "message": "请输入单号"}

        ship = await client.shipment_tracking(shipment_id=number)
        if not ship or not ship.get("traces"):
            ship = await client.shipment_tracking(client_reference=number)
        if not ship:
            return {"available": True, "found": False, "message": "未查到该单号"}

        return {
            "available": True, "found": True,
            "shipment_id": ship.get("shipment_id", ""),
            "status": ship.get("status", ""),
            "status_name": STATUS_NAMES.get(ship.get("status", ""), ship.get("status", "")),
            "carrier_code": ship.get("carrier_code", ""),
            "tracking_number": ship.get("tracking_number", ""),
            "traces": _fmt_traces(ship.get("traces", [])),
        }

    async def track_by_group(self, corp_id: str, chat_id: str,
                             limit: int = 10) -> Dict[str, Any]:
        """群→客户→该客户近期运单列表(含状态)。"""
        if not nextsls.is_available():
            return {"available": False, "message": "未配置新智慧 NEXTSLS_TOKEN"}

        mapping = CustomerMatchService(self.db).get_customer(corp_id, chat_id)
        if not mapping or not mapping.user_number:
            return {"available": True, "matched": False,
                    "message": "该群尚未匹配到客户，请先在「客户匹配」里关联或确认"}

        client = NextSLSClient()
        rows = await client.shipment_list(user_number=mapping.user_number,
                                          page=1, page_size=limit)
        shipments = [
            {
                "shipment_id": s.get("shipment_id", ""),
                "client_reference": s.get("client_reference", ""),
                "service_name": s.get("service_name", ""),
                "status": s.get("status", ""),
                "status_name": STATUS_NAMES.get(s.get("status", ""), s.get("status", "")),
                "parcel_count": s.get("parcel_count", 0),
                "main_name": s.get("main_name", ""),
                "outer_carrier_tracking_number": s.get("outer_carrier_tracking_number", ""),
            }
            for s in rows
        ]
        return {
            "available": True, "matched": True,
            "customer_name": mapping.customer_name,
            "user_number": mapping.user_number,
            "count": len(shipments),
            "shipments": shipments,
        }
