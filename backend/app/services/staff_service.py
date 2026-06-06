"""
客服效能服务

口径（均可在「配置后台」系统参数里改）：
- 首响时长：客户发言 → 第一个企业成员回复 的间隔（会话级，连续客户消息以第一条计）
- 工作时间：默认 09:00–21:00，此时段外的客户消息不计入超时考核
- 超时阈值(SLA)：默认 30 分钟，工作时间内超过算超时
统计维度：按客服(企业成员) + 按群 双视角
"""
import statistics
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from app.models.models import WxMessage, WxGroup, WxGroupMember, WxSystemConfig

DEFAULT_WORK_START = 9
DEFAULT_WORK_END = 21
DEFAULT_SLA_MINUTES = 30


class StaffPerformanceService:
    def __init__(self, db: Session):
        self.db = db

    # ---------- 配置 ----------
    def get_config(self, corp_id: str) -> Dict[str, int]:
        rows = self.db.query(WxSystemConfig).filter(WxSystemConfig.corp_id == corp_id).all()
        m = {r.config_key: r.config_value for r in rows}

        def geti(key: str, default: int) -> int:
            try:
                return int(float(m[key]))
            except (KeyError, ValueError, TypeError):
                return default

        return {
            "work_start_hour": geti("work_start_hour", DEFAULT_WORK_START),
            "work_end_hour": geti("work_end_hour", DEFAULT_WORK_END),
            "sla_minutes": geti("sla_minutes", DEFAULT_SLA_MINUTES),
        }

    # ---------- 核心：把消息流拆成"首响事件" ----------
    def _build_events(self, corp_id: str, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        cfg = self.get_config(corp_id)
        ws, we, sla = cfg["work_start_hour"], cfg["work_end_hour"], cfg["sla_minutes"]

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        # 只统计被监测的群
        monitored = {
            g.chat_id: g.group_name for g in self.db.query(WxGroup).filter(
                WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
            ).all()
        }

        msgs = self.db.query(WxMessage).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.send_time >= start_dt,
            WxMessage.send_time <= end_dt,
        ).order_by(WxMessage.chat_id, WxMessage.send_time).all()

        # 超过该时长仍无人回复，视为"未响应"，不再把后续回复算到这条提问上
        abandon_min = max(180, sla * 4)

        events: List[Dict[str, Any]] = []
        cur_chat = None
        pending = None  # 待回复的客户首条消息时间(datetime)

        def in_business(dt: datetime) -> bool:
            return ws <= dt.hour < we

        def flush_unanswered(chat_id):
            nonlocal pending
            if pending is not None and chat_id in monitored and in_business(pending):
                events.append({
                    "chat_id": chat_id, "group_name": monitored.get(chat_id, ""),
                    "customer_time": pending, "staff_userid": None, "staff_name": None,
                    "wait_min": None, "answered": False, "timeout": True, "in_business": True,
                })
            pending = None

        for m in msgs:
            if m.chat_id not in monitored:
                continue
            if m.chat_id != cur_chat:
                if cur_chat is not None:
                    flush_unanswered(cur_chat)
                cur_chat = m.chat_id
                pending = None

            # 跨天 或 挂太久 → 旧提问判未响应，开启新会话
            if pending is not None and (
                pending.date() != m.send_time.date()
                or (m.send_time - pending).total_seconds() / 60.0 > abandon_min
            ):
                flush_unanswered(m.chat_id)

            if m.sender_type == 2:  # 客户
                if pending is None:
                    pending = m.send_time
            else:  # 企业成员回复
                if pending is not None:
                    wait = (m.send_time - pending).total_seconds() / 60.0
                    biz = in_business(pending)
                    events.append({
                        "chat_id": m.chat_id, "group_name": monitored.get(m.chat_id, ""),
                        "customer_time": pending, "staff_userid": m.sender_userid,
                        "staff_name": m.sender_name or m.sender_userid,
                        "wait_min": round(wait, 1), "answered": True,
                        "timeout": biz and wait > sla, "in_business": biz,
                    })
                    pending = None
        if cur_chat is not None:
            flush_unanswered(cur_chat)

        return events

    # ---------- 客服排名榜 ----------
    def staff_ranking(self, corp_id: str, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        events = self._build_events(corp_id, start_date, end_date)

        # 每个客服管的群数（企业成员身份）
        staff_groups: Dict[str, set] = {}
        for mem in self.db.query(WxGroupMember).filter(
            WxGroupMember.corp_id == corp_id,
            WxGroupMember.member_type == 1,
            WxGroupMember.is_active == True,
        ).all():
            staff_groups.setdefault(mem.userid, set()).add(mem.chat_id)

        # 每个客服发言数
        agg: Dict[str, Dict[str, Any]] = {}
        for ev in events:
            if not ev["answered"]:
                continue
            uid = ev["staff_userid"]
            a = agg.setdefault(uid, {"name": ev["staff_name"], "waits": [], "timeout": 0, "answered": 0})
            a["answered"] += 1
            if ev.get("in_business"):
                a["waits"].append(ev["wait_min"])
            if ev["timeout"]:
                a["timeout"] += 1

        result = []
        for uid, a in agg.items():
            waits = a["waits"]
            result.append({
                "userid": uid,
                "name": a["name"],
                "group_count": len(staff_groups.get(uid, set())),
                "answered_count": a["answered"],
                "avg_first_response": round(statistics.mean(waits), 1) if waits else 0,
                "median_first_response": round(statistics.median(waits), 1) if waits else 0,
                "timeout_count": a["timeout"],
                "timeout_rate": round(a["timeout"] / a["answered"] * 100, 1) if a["answered"] else 0,
            })
        # 按响应数降序、超时率升序
        result.sort(key=lambda x: (-x["answered_count"], x["timeout_rate"]))
        return result

    # ---------- 概览 ----------
    def overview(self, corp_id: str, start_date: date, end_date: date) -> Dict[str, Any]:
        events = self._build_events(corp_id, start_date, end_date)
        biz_events = [e for e in events if e.get("in_business") or not e["answered"]]
        answered = [e for e in events if e["answered"] and e.get("in_business")]
        waits = [e["wait_min"] for e in answered]
        unanswered = [e for e in events if not e["answered"]]
        timeouts = [e for e in events if e["timeout"]]
        total_q = len(answered) + len(unanswered)
        return {
            "total_questions": total_q,
            "answered": len(answered),
            "unanswered": len(unanswered),
            "avg_first_response": round(statistics.mean(waits), 1) if waits else 0,
            "median_first_response": round(statistics.median(waits), 1) if waits else 0,
            "timeout_count": len(timeouts),
            "timeout_rate": round(len(timeouts) / total_q * 100, 1) if total_q else 0,
            "config": self.get_config(corp_id),
        }

    # ---------- 超时/未响应清单 ----------
    def timeout_list(self, corp_id: str, start_date: date, end_date: date,
                     limit: int = 50) -> List[Dict[str, Any]]:
        events = self._build_events(corp_id, start_date, end_date)
        bad = [e for e in events if e["timeout"]]
        bad.sort(key=lambda e: e["customer_time"], reverse=True)
        out = []
        for e in bad[:limit]:
            out.append({
                "chat_id": e["chat_id"],
                "group_name": e["group_name"],
                "customer_time": e["customer_time"].isoformat(),
                "answered": e["answered"],
                "wait_min": e["wait_min"],
                "staff_name": e["staff_name"],
                "status": "回复超时" if e["answered"] else "未回复",
            })
        return out
