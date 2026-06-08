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
    def __init__(self, db: Session):
        self.db = db

    async def scan_problems(self, corp_id: str, max_pages: int = 20,
                            page_size: int = 50, overdue_ready_days: int = 5) -> List[Dict[str, Any]]:
        if not nextsls.is_available():
            return []
        client = NextSLSClient()
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
                if str(s.get("holdup", 0)) not in ("0", "", "None"):
                    issues.append("滞留"); level = 1
                if str(s.get("is_problematic", 0)) not in ("0", "", "None"):
                    issues.append("问题件"); level = 1
                if status == "returned":
                    issues.append("退件"); level = 1
                eta = _parse_time(s.get("expected_arrived_time"))
                if eta and eta < now and status not in ("delivered", "cancelled", "returned"):
                    issues.append(f"超预计到达{(now - eta).days}天")
                created = _parse_time(s.get("created"))
                if status == "ready" and created and (now - created).days >= overdue_ready_days:
                    issues.append(f"下单{(now - created).days}天未发货")
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
        """重建货物异常快照：清掉旧的未读货物预警，按当前扫描结果重插。"""
        problems = await self.scan_problems(corp_id)
        self.db.query(WxAlert).filter(
            WxAlert.corp_id == corp_id,
            WxAlert.alert_type == CARGO_ALERT_TYPE,
            WxAlert.is_read == False,
        ).delete()
        for p in problems:
            self.db.add(WxAlert(
                corp_id=corp_id,
                chat_id=p["chat_id"],
                group_name=p["group_name"] or p["username"],
                alert_type=CARGO_ALERT_TYPE,
                alert_level=p["level"],
                is_read=False,
                content=f"{p['username']} 单号{p['shipment_id']}"
                        f"({p['service_name']}→{p['dest']})：{'、'.join(p['issues'])}",
            ))
        self.db.commit()
        return {"problems": len(problems)}
