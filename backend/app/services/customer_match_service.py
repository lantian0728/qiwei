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
    async def _match_one(self, candidate: str, directory: List[Dict[str, str]]
                         ) -> Tuple[Optional[Dict[str, str]], int]:
        if not candidate or not directory:
            return None, 0
        # difflib 粗筛 top10
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
        if not scored:
            return None, 0
        top = scored[:10]

        # 豆包在 top10 里语义选最优
        if doubao.is_available() and len(top) > 1:
            names = [d["username"] for _, d in top]
            try:
                text = await doubao.chat([
                    {"role": "system", "content": "你是物流客户匹配助手，只返回JSON。"},
                    {"role": "user", "content":
                        f'群名提取出的客户候选："{candidate}"。\n候选客户名单：{names}\n'
                        '从名单里选出最可能是同一客户的一个，返回 '
                        '{"match":"客户名或空字符串","confidence":0到100整数}'},
                ])
                parsed = doubao.parse_json(text)
                m = parsed.get("match")
                if m:
                    for _, d in top:
                        if d["username"] == m:
                            return d, int(parsed.get("confidence", 70))
            except Exception:
                pass

        best_ratio, best = top[0]
        return best, int(best_ratio * 100)

    async def match_all(self, corp_id: str, only_unconfirmed: bool = True) -> Dict[str, Any]:
        directory = await self.build_directory()
        groups = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
        ).all()

        matched = 0
        for g in groups:
            row = self.db.query(WxGroupCustomer).filter(
                WxGroupCustomer.corp_id == corp_id, WxGroupCustomer.chat_id == g.chat_id
            ).first()
            if row and row.match_status == "confirmed" and only_unconfirmed:
                continue
            candidate = extract_candidate_rule(g.group_name)
            best, conf = await self._match_one(candidate, directory)

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
        return {"total_groups": len(groups), "matched": matched,
                "directory_size": len(directory), "ai": doubao.is_available()}

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
