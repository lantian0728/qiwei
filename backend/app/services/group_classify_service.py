"""群客户类型分类：判断每个群是『代理』(同行货代/转单/目的港等B端)还是『直客』(终端货主)。

依据：群名 + 群内客户发言样本，AI(智谱)批量判别。
为避开上千群全过 AI(智谱免费版 1QPS)，只对『有客户发言的群』走 AI，其余用群名规则兜底。
"""
from typing import Dict, Any, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import doubao
from app.core.config import settings
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

    def _samples(self, corp_id: str, chat_id: str, n: int = 15) -> List[str]:
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
                {"role": "system", "content": "你是资深货代运营，擅长区分同行(代理)和终端货主(直客)，只返回JSON数组，不要解释。"},
                {"role": "user", "content":
                    "判断每个微信群是『代理』还是『直客』。\n"
                    "【代理 agent】对方是同行/货代公司/转运方/目的港代理。典型信号：群名含 物流/货代/国际/"
                    "供应链/转运/freight/logistics；聊 订舱、走票、SO、柜号、提单、开船、清关、"
                    "『报价给我客户』『你们这边能走吗』『我客户要发』『配合操作下』，是同行之间对接业务。\n"
                    "【直客 direct】对方是终端货主/卖家/工厂/个人。典型信号：聊 『我要发这批货』『我的货到哪了』"
                    "『帮我寄』『我是做亚马逊的』『我店铺』，只关心自己这票货。\n"
                    "判断要点：发言更像『同行帮各自客户对接订舱』→代理；更像『自己有货要发』→直客。"
                    "群名像物流公司名→偏代理；像店铺/个人/工厂名→偏直客。拿不准给较低 confidence。\n"
                    f"数据：{payload}\n"
                    '返回数组：[{"i":序号,"kind":"agent或direct","confidence":0到100整数}]'},
            ], timeout=90, model=(settings.DOUBAO_CLASSIFY_MODEL or None))
            arr = doubao.parse_json_array(text)
            return {int(r["i"]): r for r in arr if isinstance(r, dict) and "i" in r}
        except Exception:
            return {}

    async def classify_all(self, corp_id: str, only_unknown: bool = False) -> Dict[str, Any]:
        groups = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        ).all()
        # 手动确认过(conf=100)的群绝不动；only_unknown 时也跳过已判定的
        targets = [g for g in groups
                   if g.client_kind_conf != 100
                   and not (only_unknown and g.client_kind in ("agent", "direct"))]

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

    def set_kind(self, corp_id: str, chat_id: str, kind: str) -> Dict[str, Any]:
        """手动设置群的代理/直客并锁定(conf=100，之后 AI 分类不再覆盖)。"""
        g = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.chat_id == chat_id
        ).first()
        if g:
            g.client_kind = kind if kind in ("agent", "direct", "unknown") else "unknown"
            g.client_kind_conf = 100
            self.db.commit()
        return self.summary(corp_id)

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
