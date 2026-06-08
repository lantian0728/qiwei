"""客户业务量看板：从 NextSLS 运单按客户聚合「单量/货量/金额」，对比本期 vs 上期，揪掉量客户。

老板视角:消息量是虚的,单量/货量/金额才是真金白银。谁在掉单=谁在掉钱。
- 单量最可靠(每票一单)；货量(chargeable_weight)/金额(sell_charge_amount)未结算时可能为 0，仅供参考。
- 掉量预警:本期单量比上期跌一半以上(且上期有量)。
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.core import nextsls
from app.core.nextsls import NextSLSClient
from app.services.cargo_watch_service import _parse_time


def _pct(cur: float, prev: float) -> float:
    if prev <= 0:
        return 100.0 if cur > 0 else 0.0
    return round((cur - prev) / prev * 100, 1)


class CustomerBusinessService:
    def __init__(self, db: Session):
        self.db = db

    async def ranking(self, corp_id: str, days: int = 30,
                      max_pages: int = 40, page_size: int = 50) -> Dict[str, Any]:
        if not nextsls.is_available():
            return {"available": False, "customers": []}
        client = NextSLSClient()
        now = datetime.now()
        cur_start = now - timedelta(days=days)
        prev_start = now - timedelta(days=2 * days)

        # user_number -> {username, cur:[单,货,额], prev:[单,货,额]}
        agg: Dict[str, Dict[str, Any]] = {}
        for page in range(1, max_pages + 1):
            try:
                rows = await client.shipment_list(page=page, page_size=page_size)
            except Exception:
                break
            if not rows:
                break
            for s in rows:
                created = _parse_time(s.get("created"))
                if not created or created < prev_start:
                    continue
                un = s.get("user_number", "") or s.get("username", "")
                c = agg.setdefault(un, {
                    "username": s.get("username", "") or un,
                    "cur": [0, 0.0, 0.0], "prev": [0, 0.0, 0.0],
                })
                bucket = c["cur"] if created >= cur_start else c["prev"]
                bucket[0] += 1
                try:
                    bucket[1] += float(s.get("chargeable_weight") or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    bucket[2] += float(s.get("sell_charge_amount") or 0)
                except (TypeError, ValueError):
                    pass
            if len(rows) < page_size:
                break

        customers = []
        for un, c in agg.items():
            cur, prev = c["cur"], c["prev"]
            customers.append({
                "user_number": un,
                "username": c["username"],
                "cur_orders": cur[0], "prev_orders": prev[0],
                "cur_weight": round(cur[1], 1), "cur_amount": round(cur[2], 2),
                "order_change": _pct(cur[0], prev[0]),
                "dropping": prev[0] >= 4 and cur[0] < prev[0] * 0.5,  # 上期≥4单且本期跌一半
            })
        customers.sort(key=lambda x: (-x["cur_orders"], -x["cur_amount"]))
        return {
            "available": True,
            "days": days,
            "customers": customers,
            "dropping": [c for c in customers if c["dropping"]],
        }
