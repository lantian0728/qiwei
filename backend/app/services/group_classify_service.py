"""群客户类型分类：判断每个群是『代理』(同行货代/转单/目的港等B端)还是『直客』(终端货主)。

依据：群名 + 群内客户发言样本，AI(智谱)批量判别。
为避开上千群全过 AI(智谱免费版 1QPS)，只对『有客户发言的群』走 AI，其余用群名规则兜底。
"""
from typing import Dict, Any, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import doubao
from app.models.models import WxGroup, WxMessage

BATCH = 12  # 每次打包给 AI 的群数

# 群名里出现这些词，规则兜底判为『代理(同行)』
AGENT_WORDS = [
    "物流", "货代", "国际", "供应链", "速运", "快递", "报关", "清关",
    "专线", "转运", "同行", "freight", "forwarding", "logistics", "cargo",
]


class GroupClassifyService:
    def __init__(self, db: Session):
        self.db = db

    def _samples(self, corp_id: str, chat_id: str, n: int = 6) -> List[str]:
        """取该群最近的客户发言(客户说什么最能区分代理/直客)。"""
        rows = self.db.query(WxMessage.content).filter(
            WxMessage.corp_id == corp_id, WxMessage.chat_id == chat_id,
            WxMessage.sender_type == 2, WxMessage.msg_type == "text",
        ).order_by(WxMessage.send_time.desc()).limit(n).all()
        return [r[0] for r in rows if r[0]][:n]

    def _rule_kind(self, name: str) -> str:
        nm = (name or "").lower()
        return "agent" if any(w.lower() in nm for w in AGENT_WORDS) else "direct"

    def _apply(self, g: WxGroup, kind: str, conf: int):
        g.client_kind = kind if kind in ("agent", "direct") else "unknown"
        g.client_kind_conf = conf

    async def _ai_batch(self, batch: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        payload = [{"i": i, "群名": it["name"], "客户发言": it["samples"]}
                   for i, it in enumerate(batch)]
        try:
            text = await doubao.chat([
                {"role": "system", "content": "你是货代公司运营助手，只返回JSON数组，不要解释。"},
                {"role": "user", "content":
                    "判断每个微信群是『代理』还是『直客』。"
                    "代理(agent)=同行货代/转单方/目的港代理等B端合作方，群里聊订舱、走票、同行报价、"
                    "『你们能走吗』、配合操作、对方也是物流公司；"
                    "直客(direct)=终端货主/卖家/工厂，聊『我要发这批货』『我的货到哪了』『帮我寄』。"
                    f"\n数据：{payload}\n"
                    '返回数组：[{"i":序号,"kind":"agent或direct","confidence":0到100整数}]'},
            ], timeout=60)
            arr = doubao.parse_json_array(text)
            return {int(r["i"]): r for r in arr if isinstance(r, dict) and "i" in r}
        except Exception:
            return {}

    async def classify_all(self, corp_id: str, only_unknown: bool = False) -> Dict[str, Any]:
        groups = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        ).all()
        targets = [g for g in groups
                   if not (only_unknown and g.client_kind in ("agent", "direct"))]

        # 拆分：有客户发言的走 AI，其余群名规则兜底
        ai_items = []
        for g in targets:
            samples = self._samples(corp_id, g.chat_id)
            if samples:
                ai_items.append({"g": g, "name": g.group_name, "samples": samples})
            else:
                self._apply(g, self._rule_kind(g.group_name), 30)
        self.db.commit()

        ai_used = 0
        if doubao.is_available() and ai_items:
            for start in range(0, len(ai_items), BATCH):
                batch = ai_items[start:start + BATCH]
                res = await self._ai_batch(batch)
                for idx, it in enumerate(batch):
                    r = res.get(idx)
                    if r and r.get("kind") in ("agent", "direct"):
                        self._apply(it["g"], r["kind"], int(r.get("confidence", 70)))
                        ai_used += 1
                    else:
                        self._apply(it["g"], self._rule_kind(it["name"]), 40)
                self.db.commit()
        else:
            for it in ai_items:
                self._apply(it["g"], self._rule_kind(it["name"]), 40)
            self.db.commit()

        out = self.summary(corp_id)
        out["ai_used"] = ai_used
        return out

    def summary(self, corp_id: str) -> Dict[str, Any]:
        rows = self.db.query(WxGroup.client_kind, func.count(WxGroup.id)).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        ).group_by(WxGroup.client_kind).all()
        m = {k: n for k, n in rows}
        return {
            "agent": m.get("agent", 0),
            "direct": m.get("direct", 0),
            "unknown": m.get("unknown", 0),
            "total": sum(m.values()),
            "ai_available": doubao.is_available(),
        }
