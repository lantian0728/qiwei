"""
AI 群日报服务

- 每群每日：一句话摘要 + 情绪 + 风险 + 关键词
- 配置了豆包 → 用大模型生成；否则规则兜底（保证开箱可用）
- 高风险自动生成预警，汇入「今日必须处理」「风险雷达」
含一个货代场景风险关键词扫描器，供投诉雷达模块复用。
"""
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Tuple

from sqlalchemy.orm import Session

from app.core import doubao
from app.models.models import (
    WxMessage, WxGroup, WxGroupDailySummary, WxAlert,
)

SENTIMENT_NAMES = {"positive": "正面", "neutral": "中性", "negative": "负面"}
RISK_NAMES = {"none": "无", "low": "低", "medium": "中", "high": "高"}

# 货代场景风险词 → 权重（命中越多/越重，风险越高）
RISK_KEYWORDS = {
    "投诉": 3, "差评": 3, "索赔": 3, "丢件": 3, "丢失": 3, "破损": 2, "损坏": 2,
    "扣货": 3, "查验": 2, "查扣": 3, "被税": 2, "罚款": 2, "退运": 3,
    "延误": 2, "延迟": 2, "怎么还没": 2, "催": 1, "太慢": 2, "退款": 3,
    "别家": 2, "比价": 2, "更便宜": 2, "换一家": 3, "不做了": 3, "取消": 2,
    "账单": 1, "多收": 2, "乱收费": 3, "对不上": 1,
}


def scan_risk(contents: List[str]) -> Tuple[str, int, List[str]]:
    """扫描文本风险，返回 (risk_level, score, matched_keywords)。"""
    matched: Dict[str, int] = {}
    total_weight = 0
    for text in contents:
        if not text:
            continue
        for kw, w in RISK_KEYWORDS.items():
            if kw in text:
                matched[kw] = matched.get(kw, 0) + 1
                total_weight += w
    if total_weight >= 6:
        risk = "high"
    elif total_weight >= 3:
        risk = "medium"
    elif total_weight >= 1:
        risk = "low"
    else:
        risk = "none"
    top = sorted(matched.keys(), key=lambda k: -matched[k] * RISK_KEYWORDS[k])[:5]
    return risk, total_weight, top


SYSTEM_PROMPT = (
    "你是国际物流货代公司的客户群运营助手。根据某客户群今天的聊天记录，"
    "用一句话总结今天群里发生了什么、客户关心什么、有无投诉或流失风险。只返回 JSON，不要多余文字。"
)
USER_TEMPLATE = (
    "群名：{group}\n今日消息（客户C/客服S）：\n{messages}\n\n"
    '返回 JSON：{{"summary":"一句话(40字内)","sentiment":"positive|neutral|negative",'
    '"score":0到100整数,"risk":"none|low|medium|high","keywords":["最多5个关键词"]}}'
)


class AIReportService:
    def __init__(self, db: Session):
        self.db = db

    def _day_messages(self, corp_id: str, chat_id: str, day: date) -> List[WxMessage]:
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        return self.db.query(WxMessage).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.chat_id == chat_id,
            WxMessage.send_time >= start,
            WxMessage.send_time <= end,
        ).order_by(WxMessage.send_time).all()

    async def generate_group_daily(self, corp_id: str, chat_id: str,
                                   group_name: str, day: date) -> WxGroupDailySummary:
        msgs = self._day_messages(corp_id, chat_id, day)
        customer_texts = [m.content for m in msgs if m.sender_type == 2 and m.content]
        total, cust, staff = len(msgs), len(customer_texts), sum(1 for m in msgs if m.sender_type == 1)

        risk, _w, kws = scan_risk(customer_texts)
        result = {
            "summary": "", "sentiment": "neutral", "score": 50,
            "risk": risk, "keywords": kws, "generated_by": "rule",
        }

        if doubao.is_available() and customer_texts:
            try:
                lines = []
                for m in msgs[-50:]:
                    tag = "C" if m.sender_type == 2 else "S"
                    lines.append(f"{tag}: {m.content}")
                text = await doubao.chat([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_TEMPLATE.format(
                        group=group_name, messages="\n".join(lines))},
                ])
                parsed = doubao.parse_json(text)
                if parsed.get("summary"):
                    result.update({
                        "summary": parsed.get("summary", "")[:200],
                        "sentiment": parsed.get("sentiment", "neutral"),
                        "score": int(parsed.get("score", 50)),
                        "risk": parsed.get("risk", risk),
                        "keywords": parsed.get("keywords", kws)[:5],
                        "generated_by": "ai",
                    })
            except Exception:
                pass  # 失败回退规则版

        if not result["summary"]:
            risk_phrase = {
                "high": "出现高风险信号，需立即跟进", "medium": "有风险苗头，建议关注",
                "low": "有轻微关注点", "none": "无明显异常",
            }[result["risk"]]
            if total == 0:
                result["summary"] = "今日无消息"
            else:
                kw_str = ("，关键词：" + "、".join(kws)) if kws else ""
                result["summary"] = f"今日{total}条(客户{cust}/客服{staff})，{risk_phrase}{kw_str}"
            if result["risk"] in ("high", "medium"):
                result["sentiment"], result["score"] = "negative", 30

        # 落库（按 群+日期 upsert）
        row = self.db.query(WxGroupDailySummary).filter(
            WxGroupDailySummary.corp_id == corp_id,
            WxGroupDailySummary.chat_id == chat_id,
            WxGroupDailySummary.summary_date == day,
        ).first()
        if not row:
            row = WxGroupDailySummary(corp_id=corp_id, chat_id=chat_id, summary_date=day)
            self.db.add(row)
        row.group_name = group_name
        row.summary = result["summary"]
        row.sentiment = result["sentiment"]
        row.sentiment_score = result["score"]
        row.risk = result["risk"]
        row.keywords = ",".join(result["keywords"]) if result["keywords"] else ""
        row.msg_count = total
        row.generated_by = result["generated_by"]
        row.generated_at = datetime.now()
        self.db.commit()

        self._maybe_alert(corp_id, chat_id, group_name, day, result)
        return row

    def _maybe_alert(self, corp_id, chat_id, group_name, day, result):
        if result["risk"] not in ("high", "medium"):
            return
        # 同群当天同类风险预警只建一条
        exists = self.db.query(WxAlert).filter(
            WxAlert.corp_id == corp_id, WxAlert.chat_id == chat_id,
            WxAlert.alert_type == 3,
        ).filter(WxAlert.created_at >= datetime.combine(day, datetime.min.time())).first()
        if exists:
            return
        self.db.add(WxAlert(
            corp_id=corp_id, chat_id=chat_id, group_name=group_name,
            alert_type=3, alert_level=1 if result["risk"] == "high" else 2,
            content=f"{group_name}：{result['summary']}", is_read=False,
        ))
        self.db.commit()

    async def generate_all(self, corp_id: str, day: date) -> Dict[str, Any]:
        groups = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        ).all()
        n = 0
        for g in groups:
            await self.generate_group_daily(corp_id, g.chat_id, g.group_name, day)
            n += 1
        return {"generated": n, "date": str(day), "ai": doubao.is_available()}

    async def generate_active(self, corp_id: str, day: date = None) -> Dict[str, Any]:
        """只对当天有消息的群生成日报（增量同步后调用，避免全量上千群空跑）。"""
        day = day or date.today()
        start_dt = datetime.combine(day, datetime.min.time())
        chat_ids = [r[0] for r in self.db.query(WxMessage.chat_id).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.send_time >= start_dt,
        ).distinct().all()]
        n = 0
        for cid in chat_ids:
            g = self.db.query(WxGroup).filter(
                WxGroup.corp_id == corp_id, WxGroup.chat_id == cid
            ).first()
            await self.generate_group_daily(corp_id, cid, g.group_name if g else cid, day)
            n += 1
        return {"generated": n, "active_only": True, "date": str(day)}

    def get_summaries(self, corp_id: str, day: date) -> List[Dict[str, Any]]:
        rows = self.db.query(WxGroupDailySummary).filter(
            WxGroupDailySummary.corp_id == corp_id,
            WxGroupDailySummary.summary_date == day,
            WxGroupDailySummary.msg_count > 0,
        ).all()
        risk_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
        rows.sort(key=lambda r: (risk_order.get(r.risk, 9), -r.msg_count))
        return [
            {
                "chat_id": r.chat_id, "group_name": r.group_name,
                "summary": r.summary, "sentiment": r.sentiment,
                "sentiment_name": SENTIMENT_NAMES.get(r.sentiment, ""),
                "sentiment_score": r.sentiment_score,
                "risk": r.risk, "risk_name": RISK_NAMES.get(r.risk, ""),
                "keywords": r.keywords.split(",") if r.keywords else [],
                "msg_count": r.msg_count, "generated_by": r.generated_by,
            }
            for r in rows
        ]

    def global_brief(self, corp_id: str, day: date) -> Dict[str, Any]:
        rows = self.db.query(WxGroupDailySummary).filter(
            WxGroupDailySummary.corp_id == corp_id,
            WxGroupDailySummary.summary_date == day,
            WxGroupDailySummary.msg_count > 0,
        ).all()
        if not rows:
            return {"has_report": False,
                    "brief": "今日还没生成 AI 日报，点「生成今日日报」即可。"}
        total_msgs = sum(r.msg_count for r in rows)
        high = [r for r in rows if r.risk == "high"]
        medium = [r for r in rows if r.risk == "medium"]
        neg = [r for r in rows if r.sentiment == "negative"]
        parts = [f"今日 {len(rows)} 个群共 {total_msgs} 条消息"]
        if high:
            parts.append(f"{len(high)} 个群高风险（{('、'.join(r.group_name for r in high[:3]))}）")
        if medium:
            parts.append(f"{len(medium)} 个群有风险苗头")
        if neg:
            parts.append(f"{len(neg)} 个群情绪偏负面")
        if not high and not medium:
            parts.append("整体平稳，无明显投诉/流失风险")
        return {
            "has_report": True,
            "by_ai": any(r.generated_by == "ai" for r in rows),
            "high_risk": len(high), "medium_risk": len(medium),
            "brief": "；".join(parts) + "。",
        }
