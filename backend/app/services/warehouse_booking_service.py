"""亚马逊仓预约情况：把每周公众号/元宝总结的文本，用 AI 解析成各仓推迟天数，存库供预计 DW。

DW 逻辑：货到港后，预计可入仓日 = 到港日 + 该仓预约推迟天数(本服务提供)。
数据每周更新一次：粘贴文本 → glm-5.1 解析 → 重建快照。
"""
from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.core import doubao
from app.core.config import settings
from app.models.models import WxWarehouseBooking


class WarehouseBookingService:
    def __init__(self, db: Session):
        self.db = db

    async def parse_and_save(self, corp_id: str, text: str, week_label: str = "") -> Dict[str, Any]:
        if not doubao.is_available():
            return {"saved": 0, "error": "未配置 AI"}
        try:
            raw = await doubao.chat([
                {"role": "system", "content": "你是物流数据解析助手，只返回 JSON 数组，不要解释。"},
                {"role": "user", "content":
                    "下面是美国亚马逊各仓预约情况周报。提取每个【亚马逊】仓的预约推迟情况，规则：\n"
                    "- 推迟N周 → delay_days=N*7, status='推迟'\n"
                    "- 不批约/不批 → status='不批约', delay_days=99\n"
                    "- 关单/关仓/不收货/已关 → status='关单', delay_days=99\n"
                    "- 需转仓 → status='转仓', delay_days=14\n"
                    "- 爆仓/卸柜慢 → status='爆仓', delay_days=14\n"
                    "仓代码简写要展开：TEB9/4 → TEB9,TEB4；LGB4/6 → LGB4,LGB6；PHL5/6 → PHL5,PHL6。\n"
                    "只要亚马逊仓，沃尔玛/Wayfair 的忽略。\n"
                    f"周报：\n{text}\n"
                    '返回数组：[{"wh":"仓代码","delay_days":数字,"status":"推迟/不批约/关单/转仓/爆仓"}]'},
            ], timeout=120, model=(settings.DOUBAO_CLASSIFY_MODEL or None))
        except Exception as e:
            return {"saved": 0, "error": f"AI 解析失败：{str(e)[:80]}"}

        arr = doubao.parse_json_array(raw)
        # 本周快照：清旧重建
        self.db.query(WxWarehouseBooking).filter(
            WxWarehouseBooking.corp_id == corp_id
        ).delete()
        saved = []
        for r in arr:
            if not isinstance(r, dict):
                continue
            wh = (r.get("wh") or "").strip().upper()
            if not wh:
                continue
            self.db.add(WxWarehouseBooking(
                corp_id=corp_id, warehouse_code=wh,
                delay_days=int(r.get("delay_days", 0) or 0),
                status=(r.get("status") or "")[:32],
                week_label=week_label or datetime.now().strftime("%Y.%m.%d"),
            ))
            saved.append(wh)
        self.db.commit()
        return {"saved": len(saved), "warehouses": saved}

    def list_all(self, corp_id: str) -> List[Dict[str, Any]]:
        rows = self.db.query(WxWarehouseBooking).filter(
            WxWarehouseBooking.corp_id == corp_id
        ).order_by(WxWarehouseBooking.delay_days.desc()).all()
        return [{"warehouse": r.warehouse_code, "delay_days": r.delay_days,
                 "status": r.status, "week_label": r.week_label} for r in rows]

    def get_delay(self, corp_id: str, warehouse_code: str):
        if not warehouse_code:
            return None
        r = self.db.query(WxWarehouseBooking).filter(
            WxWarehouseBooking.corp_id == corp_id,
            WxWarehouseBooking.warehouse_code == warehouse_code.upper(),
        ).first()
        return {"delay_days": r.delay_days, "status": r.status} if r else None
