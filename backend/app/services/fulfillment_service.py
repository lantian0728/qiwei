"""FBA 头程履约预测：用自学的渠道时效，对每票「未入仓」货算预计入仓日 + 进度健康。

DW 来源(方案A)=到港推理(渠道实际时效)+海外仓反馈，不依赖亚马逊后台。
- 在途(in_transit)：预计入仓 = 开船日 + 渠道中位时效；已在途超时效→红(会拖)
- 待开船(picked)/待发货(ready)：早期阶段，压单则黄
拉 TMS 较慢，结果缓存 2 小时，由后台 job 预算。
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.core import nextsls
from app.core.nextsls import NextSLSClient
from app.models.models import WxGroupCustomer
from app.services.cargo_watch_service import CargoWatchService, _parse_time

ACTIVE = ("ready", "picked", "in_transit")


class FulfillmentService:
    _cache: Dict[Any, Dict[str, Any]] = {}

    def __init__(self, db: Session):
        self.db = db

    async def forecast(self, corp_id: str, max_pages: int = 40,
                       page_size: int = 50, use_cache: bool = True) -> Dict[str, Any]:
        c = FulfillmentService._cache.get(corp_id)
        if use_cache and c and (datetime.now() - c["ts"]).total_seconds() < 7200:
            return c["data"]
        if use_cache:
            return {"available": True, "computing": True, "items": [], "summary": {}}
        if not nextsls.is_available():
            return {"available": False, "items": [], "summary": {}}

        client = NextSLSClient()
        cargo = CargoWatchService(self.db)
        await cargo._ensure_aging(client)  # 确保渠道时效已学
        cust_map = {
            wc.user_number: wc for wc in self.db.query(WxGroupCustomer).filter(
                WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.user_number != ""
            ).all()
        }
        now = datetime.now()
        items: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            try:
                rows = await client.shipment_list(page=page, page_size=page_size)
            except Exception:
                break
            if not rows:
                break
            for s in rows:
                status = s.get("status", "")
                if status not in ACTIVE:
                    continue
                service = s.get("service_name", "")
                aging = cargo._get_aging(service)
                ship = _parse_time(s.get("ship_time"))
                stage, eta_in, remain, elapsed, health = "待发货", None, None, None, "green"

                if status == "in_transit" and ship:
                    elapsed = (now - ship).days
                    eta_in = ship + timedelta(days=aging)
                    remain = (eta_in - now).days
                    health = "red" if elapsed > aging else "yellow" if elapsed > aging * 0.75 else "green"
                    stage = "在途"
                elif status == "picked":
                    stage = "待开船"
                    pt = _parse_time(s.get("picking_time"))
                    eta_in = (pt or now) + timedelta(days=aging)
                    remain = (eta_in - now).days
                    health = "yellow" if (pt and (now - pt).days > 5) else "green"
                else:  # ready
                    stage = "待发货"
                    cr = _parse_time(s.get("created"))
                    eta_in = (cr or now) + timedelta(days=aging + 3)
                    remain = (eta_in - now).days
                    health = "yellow" if (cr and (now - cr).days > 7) else "green"

                un = s.get("user_number", "")
                wc = cust_map.get(un)
                to = s.get("to_address") or {}
                items.append({
                    "shipment_id": s.get("shipment_id", ""),
                    "username": s.get("username", "") or un,
                    "service_name": service,
                    "warehouse": s.get("to_warehouse_code") or to.get("name", "") or "",
                    "stage": stage,
                    "ship_date": ship.strftime("%m-%d") if ship else "",
                    "eta_in": eta_in.strftime("%m-%d") if eta_in else "",
                    "elapsed": elapsed, "remain": remain, "aging": int(aging),
                    "health": health,
                    "group_name": wc.group_name if wc else "",
                    "chat_id": wc.chat_id if wc else "",
                })
            if len(rows) < page_size:
                break

        order = {"red": 0, "yellow": 1, "green": 2}
        items.sort(key=lambda x: (order.get(x["health"], 3),
                                  x["remain"] if x["remain"] is not None else 999))
        summary = {
            "red": sum(1 for i in items if i["health"] == "red"),
            "yellow": sum(1 for i in items if i["health"] == "yellow"),
            "green": sum(1 for i in items if i["health"] == "green"),
            "total": len(items),
        }
        data = {"available": True, "computing": False, "items": items, "summary": summary}
        FulfillmentService._cache[corp_id] = {"data": data, "ts": datetime.now()}
        return data
