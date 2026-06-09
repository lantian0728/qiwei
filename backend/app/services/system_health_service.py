"""系统自监控：检测会话存档/AI/TMS 是否在线 + 数据新鲜度，防止系统静默哑火。

老板痛点:数据某天断了没人发现,比没有系统更危险。
- 会话存档:配置在 + 最近消息时间(工作时间内超 2 小时无新消息 → 警告，可能断了)
- 智谱AI / 新智慧TMS:配置在
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import wework_finance, doubao, nextsls
from app.models.models import WxMessage


class SystemHealthService:
    def __init__(self, db: Session):
        self.db = db

    def check(self, corp_id: str) -> Dict[str, Any]:
        now = datetime.now()
        last_msg = self.db.query(func.max(WxMessage.send_time)).filter(
            WxMessage.corp_id == corp_id
        ).scalar()
        fresh_min = int((now - last_msg).total_seconds() // 60) if last_msg else None
        in_work = 9 <= now.hour < 21

        items = []

        # 会话存档(消息流命脉)
        arch_ok = wework_finance.is_available()
        if not arch_ok:
            arch_level, arch_detail = "error", "未配置 / SDK 未就绪"
        elif fresh_min is None:
            arch_level, arch_detail = "warn", "尚无消息入库"
        elif in_work and fresh_min > 120:
            arch_level, arch_detail = "warn", f"已 {fresh_min} 分钟无新消息(工作时段,疑似中断)"
        else:
            arch_level, arch_detail = "ok", f"最近消息 {fresh_min} 分钟前"
        items.append({"key": "archive", "name": "会话存档", "level": arch_level, "detail": arch_detail})

        # 智谱 AI
        ai_ok = doubao.is_available()
        items.append({"key": "ai", "name": "智谱 AI", "level": "ok" if ai_ok else "error",
                      "detail": "已配置" if ai_ok else "未配置 Key"})

        # 新智慧 TMS
        tms_ok = nextsls.is_available()
        items.append({"key": "tms", "name": "新智慧 TMS", "level": "ok" if tms_ok else "error",
                      "detail": "已配置" if tms_ok else "未配置 Token"})

        levels = [i["level"] for i in items]
        overall = "error" if "error" in levels else "warn" if "warn" in levels else "ok"
        return {"overall": overall, "items": items, "last_message_min": fresh_min}
