"""
客户流失预警服务

信号（针对客户群）：
- 货量骤降：近 7 天消息量较前 7 天下降比例
- 竞品比价：出现"别家/更便宜/换一家/不做了"等词
- 催问频繁：出现"怎么还没/催/太慢/延误"等词
- 已沉默：活跃度等级为沉默
综合给出流失风险等级 + 原因，高/中风险自动生成预警(alert_type=2 客户流失)。
"""
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    WxGroup, WxGroupDailyStat, WxMessage, WxAlert,
)
from app.services.activity_service import LEVEL_SILENT, LEVEL_LOW

COMPETE_WORDS = ["别家", "比价", "更便宜", "换一家", "不做了", "取消合作", "换货代"]
URGE_WORDS = ["怎么还没", "催", "太慢", "延误", "延迟", "急", "什么时候到"]


class ChurnService:
    def __init__(self, db: Session):
        self.db = db

    def _volume(self, corp_id: str, chat_id: str, start: date, end: date) -> int:
        v = self.db.query(func.sum(WxGroupDailyStat.total_msg_count)).filter(
            WxGroupDailyStat.corp_id == corp_id,
            WxGroupDailyStat.chat_id == chat_id,
            WxGroupDailyStat.stat_date >= start,
            WxGroupDailyStat.stat_date <= end,
        ).scalar()
        return int(v or 0)

    def _customer_texts(self, corp_id: str, chat_id: str, days: int = 7) -> List[str]:
        since = datetime.now() - timedelta(days=days)
        rows = self.db.query(WxMessage.content).filter(
            WxMessage.corp_id == corp_id, WxMessage.chat_id == chat_id,
            WxMessage.sender_type == 2, WxMessage.send_time >= since,
        ).all()
        return [r[0] for r in rows if r[0]]

    def assess_group(self, corp_id: str, group: WxGroup) -> Dict[str, Any]:
        today = date.today()
        last7 = self._volume(corp_id, group.chat_id, today - timedelta(days=6), today)
        prev7 = self._volume(corp_id, group.chat_id, today - timedelta(days=13), today - timedelta(days=7))
        drop_pct = round((prev7 - last7) / prev7 * 100, 1) if prev7 > 0 else 0

        texts = self._customer_texts(corp_id, group.chat_id, 7)
        compete = sum(1 for t in texts for w in COMPETE_WORDS if w in t)
        urge = sum(1 for t in texts for w in URGE_WORDS if w in t)

        score = 0.0
        reasons: List[str] = []
        if drop_pct >= 40:
            score += min(drop_pct, 80) * 0.5
            reasons.append(f"货量骤降 {drop_pct}%")
        elif drop_pct >= 20:
            score += 10
            reasons.append(f"货量下降 {drop_pct}%")
        if compete > 0:
            score += 20 + compete * 5
            reasons.append(f"出现竞品比价 {compete} 次")
        if urge >= 3:
            score += 10 + urge * 2
            reasons.append(f"催问频繁 {urge} 次")
        if group.activity_level == LEVEL_SILENT:
            score += 30
            reasons.append("群已沉默")
        elif group.activity_level == LEVEL_LOW:
            score += 12
            reasons.append("活跃度偏低")

        score = round(min(score, 100), 1)
        if score >= 50:
            risk = "high"
        elif score >= 25:
            risk = "medium"
        elif score >= 10:
            risk = "low"
        else:
            risk = "none"

        return {
            "chat_id": group.chat_id, "group_name": group.group_name,
            "is_key_group": group.is_key_group,
            "owner_name": group.owner_name, "member_count": group.member_count,
            "last7_volume": last7, "prev7_volume": prev7, "drop_pct": drop_pct,
            "compete_hits": compete, "urge_hits": urge,
            "churn_score": score, "churn_risk": risk,
            "reasons": reasons or ["暂无异常"],
        }

    def list_at_risk(self, corp_id: str, only_customer: bool = True) -> Dict[str, Any]:
        q = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        )
        if only_customer:
            q = q.filter(WxGroup.group_type.in_([1, 4]))  # 客户群/渠道群
        groups = q.all()
        items = [self.assess_group(corp_id, g) for g in groups]
        order = {"high": 0, "medium": 1, "low": 2, "none": 3}
        items.sort(key=lambda x: (order[x["churn_risk"]], -x["churn_score"]))

        return {
            "total": len(items),
            "high": sum(1 for i in items if i["churn_risk"] == "high"),
            "medium": sum(1 for i in items if i["churn_risk"] == "medium"),
            "items": items,
        }

    def generate_alerts(self, corp_id: str) -> int:
        result = self.list_at_risk(corp_id)
        today_start = datetime.combine(date.today(), datetime.min.time())
        n = 0
        for it in result["items"]:
            if it["churn_risk"] not in ("high", "medium"):
                continue
            exists = self.db.query(WxAlert).filter(
                WxAlert.corp_id == corp_id, WxAlert.chat_id == it["chat_id"],
                WxAlert.alert_type == 2, WxAlert.created_at >= today_start,
            ).first()
            if exists:
                continue
            self.db.add(WxAlert(
                corp_id=corp_id, chat_id=it["chat_id"], group_name=it["group_name"],
                alert_type=2, alert_level=1 if it["churn_risk"] == "high" else 2,
                content=f"{it['group_name']}：流失风险（{ '、'.join(it['reasons']) }）",
                is_read=False,
            ))
            n += 1
        self.db.commit()
        return n
