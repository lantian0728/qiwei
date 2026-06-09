"""DW 核准看板：转运中的货按目的仓分组，预填预计 DW，逐票人工核准后写入。

预填 DW(预计入仓日) = 开船日 + 渠道实际时效(自学) + 该仓当前预约推迟(公众号数据)
人工核准：用户确认/改 DW → 写入 WxShipmentDW(status=approved)。
"""
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.core import nextsls
from app.core.nextsls import NextSLSClient
from app.models.models import WxShipmentDW, WxGroupCustomer
from app.services.cargo_watch_service import CargoWatchService, _parse_time
from app.services.warehouse_booking_service import WarehouseBookingService


class DWService:
    _cache: Dict[Any, Dict[str, Any]] = {}

    def __init__(self, db: Session):
        self.db = db

    async def board(self, corp_id: str, use_cache: bool = True,
                    max_pages: int = 40, page_size: int = 50) -> Dict[str, Any]:
        c = DWService._cache.get(corp_id)
        if use_cache and c and (datetime.now() - c["ts"]).total_seconds() < 7200:
            return c["data"]
        if use_cache:
            return {"available": True, "computing": True, "warehouses": [], "total": 0}
        if not nextsls.is_available():
            return {"available": False, "warehouses": [], "total": 0}

        client = NextSLSClient()
        cargo = CargoWatchService(self.db)
        await cargo._ensure_aging(client)
        wh_svc = WarehouseBookingService(self.db)
        appr = {r.shipment_id: r for r in self.db.query(WxShipmentDW).filter(
            WxShipmentDW.corp_id == corp_id).all()}
        cust_map = {wc.user_number: wc for wc in self.db.query(WxGroupCustomer).filter(
            WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.user_number != "").all()}

        groups: Dict[str, list] = {}
        for page in range(1, max_pages + 1):
            try:
                rows = await client.shipment_list(page=page, page_size=page_size, status="in_transit")
            except Exception:
                break
            if not rows:
                break
            for s in rows:
                wh = (s.get("to_warehouse_code") or (s.get("to_address") or {}).get("name", "") or "未知").upper()
                service = s.get("service_name", "")
                ship = _parse_time(s.get("ship_time"))
                aging = cargo._get_aging(service)
                whb = wh_svc.get_delay(corp_id, wh)
                delay = whb["delay_days"] if whb else 0
                wh_status = whb["status"] if whb else ""
                extra = delay if delay < 99 else 0  # 不批约/关单不加进日期,单独标注
                eta_dw = ""
                if ship:
                    eta_dw = (ship + timedelta(days=int(aging) + extra)).strftime("%Y-%m-%d")
                sid = s.get("shipment_id", "")
                rec = appr.get(sid)
                un = s.get("user_number", "")
                wc = cust_map.get(un)
                groups.setdefault(wh, []).append({
                    "shipment_id": sid,
                    "username": s.get("username", "") or un,
                    "service_name": service,
                    "ship_date": ship.strftime("%m-%d") if ship else "",
                    "aging": int(aging), "delay_days": delay, "wh_status": wh_status,
                    "eta_dw": rec.eta_dw if rec else eta_dw,
                    "status": rec.status if rec else "pending",
                    "group_name": wc.group_name if wc else "",
                })
            if len(rows) < page_size:
                break

        result = []
        for wh, items in groups.items():
            whb = wh_svc.get_delay(corp_id, wh)
            result.append({
                "warehouse": wh,
                "delay_days": whb["delay_days"] if whb else 0,
                "wh_status": whb["status"] if whb else "",
                "count": len(items),
                "pending": sum(1 for i in items if i["status"] == "pending"),
                "items": items,
            })
        # 推迟多的仓排前(99=不批约/关单也靠前)
        result.sort(key=lambda x: (-x["delay_days"], -x["count"]))
        data = {"available": True, "computing": False,
                "warehouses": result, "total": sum(x["count"] for x in result)}
        DWService._cache[corp_id] = {"data": data, "ts": datetime.now()}
        return data

    def approve(self, corp_id: str, shipment_id: str, eta_dw: str,
                warehouse: str = "", service_name: str = "", delay_days: int = 0) -> Dict[str, Any]:
        rec = self.db.query(WxShipmentDW).filter(
            WxShipmentDW.corp_id == corp_id, WxShipmentDW.shipment_id == shipment_id
        ).first()
        if not rec:
            rec = WxShipmentDW(corp_id=corp_id, shipment_id=shipment_id)
            self.db.add(rec)
        rec.eta_dw = eta_dw
        rec.warehouse = warehouse
        rec.service_name = service_name
        rec.delay_days = int(delay_days or 0)
        rec.status = "approved"
        rec.updated_at = datetime.now()
        self.db.commit()
        # 更新缓存里该票状态(避免整表重算)
        c = DWService._cache.get(corp_id)
        if c:
            for whg in c["data"].get("warehouses", []):
                for it in whg["items"]:
                    if it["shipment_id"] == shipment_id:
                        it["status"] = "approved"
                        it["eta_dw"] = eta_dw
                whg["pending"] = sum(1 for i in whg["items"] if i["status"] == "pending")
        return {"success": True, "shipment_id": shipment_id, "eta_dw": eta_dw}
