"""货物节点异常巡检：从 NextSLS 运单列表揪出异常货物，在客户发现前先预警。

判异常依据(运单列表自带字段，无需 tracking 权限)：
- holdup=1        → 滞留(卡住)
- is_problematic=1→ 问题件
- status=returned → 退件
- expected_arrived_time 已过且未签收 → 超预计到达
- status=ready 且下单超 N 天    → 久未发货
异常生成 WxAlert(alert_type=4)，汇入作战室「今日必须处理」。
"""
from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.core import nextsls
from app.core.nextsls import NextSLSClient
from app.models.models import WxAlert, WxGroupCustomer

CARGO_ALERT_TYPE = 4


def _parse_time(v) -> "datetime | None":
    if v in (None, "", 0, "0"):
        return None
    try:
        s = str(v).strip()
        if s.isdigit():
            ts = int(s)
            if ts > 1e12:  # 毫秒
                ts //= 1000
            return datetime.fromtimestamp(ts)
        return datetime.fromisoformat(s.replace("/", "-")[:19])
    except Exception:
        return None


class CargoWatchService:
    _aging_cache: dict = {}   # service_name -> 中位时效(天)
    _aging_ts = None

    def __init__(self, db: Session):
        self.db = db

    async def _ensure_aging(self, client) -> None:
        """从历史已签收运单自学各渠道中位时效(开船→签收)，缓存 24 小时。"""
        if (CargoWatchService._aging_cache and CargoWatchService._aging_ts
                and (datetime.now() - CargoWatchService._aging_ts).total_seconds() < 86400):
            return
        from collections import defaultdict
        from statistics import median
        chan = defaultdict(list)
        for pg in range(1, 31):
            try:
                rows = await client.shipment_list(page=pg, page_size=50, status="delivered")
            except Exception:
                break
            if not rows:
                break
            for s in rows:
                st = _parse_time(s.get("ship_time"))
                dt = _parse_time(s.get("delivered_time"))
                if st and dt and dt > st:
                    chan[s.get("service_name", "")].append((dt - st).days)
            if len(rows) < 50:
                break
        CargoWatchService._aging_cache = {n: median(d) for n, d in chan.items() if len(d) >= 10}
        CargoWatchService._aging_ts = datetime.now()

    def _get_aging(self, service: str) -> float:
        """该渠道中位时效；样本不足用按渠道名的兜底默认值。"""
        a = CargoWatchService._aging_cache.get(service)
        if a:
            return a
        s = service or ""
        if any(k in s for k in ("空派", "UPS", "FEDEX", "DHL", "小包", "快速达", "云速达")):
            return 10
        if "海派" in s:
            return 22
        if "限时达" in s:
            return 28
        if any(k in s for k in ("普船", "海运", "铁路", "卡航")):
            return 35
        return 30

    async def scan_problems(self, corp_id: str, max_pages: int = 20,
                            page_size: int = 50, overdue_ready_days: int = 7) -> List[Dict[str, Any]]:
        if not nextsls.is_available():
            return []
        client = NextSLSClient()
        await self._ensure_aging(client)  # 先学好各渠道时效基线
        cust_map = {
            wc.user_number: wc for wc in self.db.query(WxGroupCustomer).filter(
                WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.user_number != ""
            ).all()
        }
        now = datetime.now()
        problems: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            try:
                rows = await client.shipment_list(page=page, page_size=page_size)
            except Exception:
                break
            if not rows:
                break
            for s in rows:
                status = s.get("status", "")
                issues, level = [], 2
                # 已签收/取消的单已结束，不再报"进行中异常"(避免历史问题件刷屏)
                active = status not in ("delivered", "cancelled", "returned")
                if active and str(s.get("holdup", 0)) not in ("0", "", "None"):
                    issues.append("滞留"); level = 1
                if active and str(s.get("is_problematic", 0)) not in ("0", "", "None"):
                    issues.append("问题件"); level = 1
                if status == "returned":
                    issues.append("退件"); level = 1
                eta = _parse_time(s.get("expected_arrived_time"))
                if active and eta and eta < now:
                    issues.append(f"超预计到达{(now - eta).days}天")
                created = _parse_time(s.get("created"))
                if status == "ready" and created and (now - created).days > overdue_ready_days:
                    issues.append(f"下单{(now - created).days}天未发货")
                # 收货未开船(压仓)
                if status == "picked":
                    pt = _parse_time(s.get("picking_time"))
                    if pt and (now - pt).days > 5:
                        issues.append(f"收货{(now - pt).days}天未开船")
                # 在途超时(按该渠道自学时效 ×1.4)
                if status == "in_transit":
                    st2 = _parse_time(s.get("ship_time"))
                    if st2:
                        d2 = (now - st2).days
                        base = self._get_aging(s.get("service_name", ""))
                        if d2 > base * 1.4:
                            issues.append(f"在途{d2}天(该渠道约{int(base)}天)")
                            if d2 > base * 1.8:
                                level = 1
                if not issues:
                    continue
                un = s.get("user_number", "")
                wc = cust_map.get(un)
                to = s.get("to_address") or {}
                problems.append({
                    "shipment_id": s.get("shipment_id", ""),
                    "username": s.get("username", "") or un,
                    "user_number": un,
                    "service_name": s.get("service_name", ""),
                    "dest": (to.get("country", "") + (to.get("state_code", "") or "")),
                    "status": status,
                    "issues": issues,
                    "level": level,
                    "chat_id": wc.chat_id if wc else "",
                    "group_name": wc.group_name if wc else "",
                    "amazon_ref": s.get("amazon_ref_id", ""),
                })
            if len(rows) < page_size:
                break
        # 高优先级(滞留/问题件/退件)排前
        problems.sort(key=lambda p: p["level"])
        return problems

    async def refresh_alerts(self, corp_id: str) -> Dict[str, Any]:
        """重建货物异常快照：按客户聚合，每个客户一条(汇总各类异常票数)，避免刷屏。"""
        from collections import Counter
        problems = await self.scan_problems(corp_id)

        by_cust: Dict[str, Dict[str, Any]] = {}
        for p in problems:
            key = p["user_number"] or p["username"]
            g = by_cust.setdefault(key, {
                "username": p["username"], "chat_id": "", "group_name": "",
                "level": 2, "issues": Counter(),
            })
            g["chat_id"] = g["chat_id"] or p["chat_id"]
            g["group_name"] = g["group_name"] or p["group_name"]
            g["level"] = min(g["level"], p["level"])
            for i in p["issues"]:
                cat = ("问题件" if "问题件" in i else "滞留" if "滞留" in i
                       else "退件" if "退件" in i else "超期" if "超" in i
                       else "久未发货" if "未发货" in i else i)
                g["issues"][cat] += 1

        self.db.query(WxAlert).filter(
            WxAlert.corp_id == corp_id,
            WxAlert.alert_type == CARGO_ALERT_TYPE,
            WxAlert.is_read == False,
        ).delete()
        for g in by_cust.values():
            summary = "、".join(f"{n}票{cat}" for cat, n in g["issues"].most_common())
            self.db.add(WxAlert(
                corp_id=corp_id,
                chat_id=g["chat_id"],
                group_name=g["group_name"] or g["username"],
                alert_type=CARGO_ALERT_TYPE,
                alert_level=g["level"],
                is_read=False,
                content=f"{g['username']}：{summary}",
            ))
        self.db.commit()
        return {"problems": len(problems), "customers": len(by_cust)}
