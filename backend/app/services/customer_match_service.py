"""
群 ↔ 新智慧客户 匹配服务

1. 客户名单：从运单列表(/shipment/list)汇总去重(本密钥无 /user/list 权限)
2. 识别群名里的客户：豆包优先，否则规则(去掉"群/专线/VIP/数字"等噪声)
3. 模糊匹配候选名 ↔ 客户名单，存映射，运营可确认/纠正
"""
import re
import difflib
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core import doubao, nextsls
from app.core.nextsls import NextSLSClient
from app.models.models import WxGroup, WxGroupCustomer

# 群名里要剔除的噪声词
NOISE_WORDS = [
    "群", "客户群", "客户", "服务", "对接", "交流", "答疑", "通知", "vip", "VIP",
    "美森", "以星", "盐田", "海运", "空运", "卡派", "快递", "专线", "头程",
    "fba", "FBA", "亚马逊", "渠道", "项目", "内部", "官方", "物流", "国际",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
]


def extract_candidate_rule(group_name: str) -> str:
    """规则版：从群名提取客户候选名。"""
    name = group_name or ""
    name = re.sub(r"[0-9０-９]+", "", name)
    name = re.sub(r"[-_·、,，/|()（）【】\[\]]+", " ", name)
    for w in NOISE_WORDS:
        name = name.replace(w, " ")
    parts = [p for p in name.split() if len(p) >= 2]
    # 取最长的有意义片段（通常是公司/人名）
    return max(parts, key=len) if parts else (group_name or "").strip()


class CustomerMatchService:
    _directory_cache: List[Dict[str, str]] = []  # [{user_number, username}]

    def __init__(self, db: Session):
        self.db = db

    # ---------- 客户名单 ----------
    async def build_directory(self, max_pages: int = 5, page_size: int = 100,
                              refresh: bool = False) -> List[Dict[str, str]]:
        if self._directory_cache and not refresh:
            return self._directory_cache
        if not nextsls.is_available():
            return []
        client = NextSLSClient()
        seen: Dict[str, str] = {}
        for page in range(1, max_pages + 1):
            try:
                rows = await client.shipment_list(page=page, page_size=page_size)
            except Exception:
                break
            if not rows:
                break
            for s in rows:
                un = s.get("user_number")
                if un and un not in seen:
                    seen[un] = s.get("username", "")
            if len(rows) < page_size:
                break
        self._directory_cache = [{"user_number": k, "username": v} for k, v in seen.items()]
        return self._directory_cache

    # ---------- 匹配 ----------
    # 置信度阈值：difflib 高于此直接采用、低于下限直接判无；中间地带交给智谱批量精修
    _AI_HIGH = 0.85   # ratio≥此：规则已很确定，不必问AI
    _AI_LOW = 0.35    # ratio<此：基本不可能，不必问AI
    _AI_BATCH = 60    # 每次智谱调用打包的群数量上限

    def _difflib_top(self, candidate: str, directory: List[Dict[str, str]], n: int = 6
                     ) -> List[Tuple[float, Dict[str, str]]]:
        """difflib 粗筛，返回 top-n [(ratio, 客户)]。"""
        if not candidate or not directory:
            return []
        scored = []
        for d in directory:
            uname = d["username"] or ""
            if not uname:
                continue
            if candidate in uname or uname in candidate:
                ratio = 0.9
            else:
                ratio = difflib.SequenceMatcher(None, candidate, uname).ratio()
            scored.append((ratio, d))
        scored.sort(key=lambda x: -x[0])
        return scored[:n]

    async def _ai_match_batch(self, items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """批量精修：一次调用把多个群的候选名+可选客户打包给智谱，返回 {i: {match, confidence}}。
        失败返回空 dict（调用方走 difflib 兜底）。"""
        if not items:
            return {}
        payload_items = [
            {"i": it["i"], "群名候选": it["candidate"], "可选客户": it["names"]}
            for it in items
        ]
        try:
            text = await doubao.chat([
                {"role": "system", "content": "你是物流客户名称匹配助手，只返回JSON数组，不要解释。"},
                {"role": "user", "content":
                    "下面每条是一个微信群提取出的客户候选名，以及从客户库里粗筛出的可选客户名单。"
                    "请为每条从它自己的『可选客户』里挑出最可能是同一客户的一个；"
                    "若都不像则 match 用空字符串。confidence 是 0-100 的整数。\n"
                    f"数据：{payload_items}\n"
                    '严格返回数组：[{"i":序号,"match":"客户名或空","confidence":整数}, ...]'},
            ], timeout=90)
            parsed = doubao.parse_json_array(text)
            out: Dict[int, Dict[str, Any]] = {}
            for r in parsed:
                if isinstance(r, dict) and "i" in r:
                    out[int(r["i"])] = r
            return out
        except Exception:
            return {}

    async def match_all(self, corp_id: str, only_unconfirmed: bool = True) -> Dict[str, Any]:
        import asyncio
        directory = await self.build_directory()
        groups = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        ).all()

        # 1) 全量 difflib 粗筛（秒级），同时挑出需要 AI 精修的「模糊地带」群
        targets = []          # [{g, row, candidate, top}]
        ai_pending = []       # [{i, candidate, names, idx}]  idx=targets下标
        for g in groups:
            row = self.db.query(WxGroupCustomer).filter(
                WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.chat_id == g.chat_id
            ).first()
            if row and row.match_status == "confirmed" and only_unconfirmed:
                continue
            candidate = extract_candidate_rule(g.group_name)
            top = self._difflib_top(candidate, directory)
            idx = len(targets)
            targets.append({"g": g, "row": row, "candidate": candidate, "top": top})
            if top and self._AI_LOW <= top[0][0] < self._AI_HIGH and len(top) > 1:
                ai_pending.append({"i": idx, "candidate": candidate,
                                   "names": [d["username"] for _, d in top]})

        # 2) 模糊地带分批（每批60）一次性丢给智谱批量精修
        ai_picks: Dict[int, Dict[str, Any]] = {}
        ai_calls = 0
        if doubao.is_available() and ai_pending:
            for start in range(0, len(ai_pending), self._AI_BATCH):
                batch = ai_pending[start:start + self._AI_BATCH]
                res = await self._ai_match_batch(batch)
                ai_calls += 1
                ai_picks.update(res)
                if start + self._AI_BATCH < len(ai_pending):
                    await asyncio.sleep(1)  # 批间轻微间隔，避让限频

        # 3) 落库：AI 命中优先，否则用 difflib top1
        matched = 0
        ai_used = 0
        for idx, t in enumerate(targets):
            g, row, candidate, top = t["g"], t["row"], t["candidate"], t["top"]
            best, conf = (top[0][1], int(top[0][0] * 100)) if top else (None, 0)

            pick = ai_picks.get(idx)
            if pick and pick.get("match"):
                for _, d in top:
                    if d["username"] == pick["match"]:
                        best = d
                        conf = int(pick.get("confidence", 70))
                        ai_used += 1
                        break

            if not row:
                row = WxGroupCustomer(corp_id=corp_id, chat_id=g.chat_id)
                self.db.add(row)
            row.group_name = g.group_name
            row.candidate = candidate
            if best and conf >= 50:
                row.user_number = best["user_number"]
                row.customer_name = best["username"]
                row.confidence = conf
                row.match_status = "auto"
                matched += 1
            else:
                row.user_number = ""
                row.customer_name = ""
                row.confidence = conf
                row.match_status = "none"
        self.db.commit()
        return {"total_groups": len(targets), "matched": matched,
                "directory_size": len(directory), "ai": doubao.is_available(),
                "ai_used": ai_used, "ai_calls": ai_calls}

    def list_mappings(self, corp_id: str) -> List[Dict[str, Any]]:
        rows = self.db.query(WxGroupCustomer).filter(
            WxGroupCustomer.corp_id == corp_id
        ).all()
        return [
            {
                "chat_id": r.chat_id, "group_name": r.group_name,
                "candidate": r.candidate, "user_number": r.user_number,
                "customer_name": r.customer_name, "confidence": r.confidence,
                "match_status": r.match_status,
            }
            for r in rows
        ]

    def set_mapping(self, corp_id: str, chat_id: str,
                    user_number: str, customer_name: str) -> WxGroupCustomer:
        row = self.db.query(WxGroupCustomer).filter(
            WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.chat_id == chat_id
        ).first()
        if not row:
            row = WxGroupCustomer(corp_id=corp_id, chat_id=chat_id)
            self.db.add(row)
        row.user_number = user_number
        row.customer_name = customer_name
        row.confidence = 100
        row.match_status = "confirmed"
        self.db.commit()
        return row

    def get_customer(self, corp_id: str, chat_id: str) -> Optional[WxGroupCustomer]:
        return self.db.query(WxGroupCustomer).filter(
            WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.chat_id == chat_id
        ).first()
