"""
活跃度分级与统计服务

- ActivityLevelService：四级分类、等级汇总、按等级取群、重算评分
- StatisticsService：回复率、响应率、响应时长、发言排名、时段分布、@统计、沉默成员
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.models import (
    WxGroup, WxGroupMember, WxGroupDailyStat, WxMessage,
)

# ========== 活跃度等级常量 ==========
LEVEL_HIGH = 1     # 高活跃
LEVEL_NORMAL = 2   # 正常
LEVEL_LOW = 3      # 低活跃
LEVEL_SILENT = 4   # 沉默

LEVEL_NAMES = {
    LEVEL_HIGH: "高活跃",
    LEVEL_NORMAL: "正常",
    LEVEL_LOW: "低活跃",
    LEVEL_SILENT: "沉默",
}

LEVEL_COLORS = {
    LEVEL_HIGH: "#67C23A",
    LEVEL_NORMAL: "#409EFF",
    LEVEL_LOW: "#E6A23C",
    LEVEL_SILENT: "#909399",
}

# 默认分级阈值（可被系统参数覆盖）
DEFAULT_HIGH_THRESHOLD = 70
DEFAULT_NORMAL_THRESHOLD = 40
DEFAULT_LOW_THRESHOLD = 15


def score_to_level(score: float,
                   high: float = DEFAULT_HIGH_THRESHOLD,
                   normal: float = DEFAULT_NORMAL_THRESHOLD,
                   low: float = DEFAULT_LOW_THRESHOLD) -> int:
    if score >= high:
        return LEVEL_HIGH
    if score >= normal:
        return LEVEL_NORMAL
    if score >= low:
        return LEVEL_LOW
    return LEVEL_SILENT


class ActivityLevelService:
    def __init__(self, db: Session):
        self.db = db

    def get_level_summary(self, corp_id: str) -> Dict[str, Any]:
        """各活跃度等级的群数量与占比汇总。"""
        rows = self.db.query(
            WxGroup.activity_level,
            func.count(WxGroup.id).label("count"),
        ).filter(
            WxGroup.corp_id == corp_id,
            WxGroup.is_monitored == True,
        ).group_by(WxGroup.activity_level).all()

        count_map = {r.activity_level: r.count for r in rows}
        total = sum(count_map.values()) or 0

        levels = []
        for lv in (LEVEL_HIGH, LEVEL_NORMAL, LEVEL_LOW, LEVEL_SILENT):
            cnt = count_map.get(lv, 0)
            levels.append({
                "level": lv,
                "level_name": LEVEL_NAMES[lv],
                "color": LEVEL_COLORS[lv],
                "count": cnt,
                "percent": round(cnt / total * 100, 1) if total else 0,
            })

        return {"total": total, "levels": levels}

    def get_groups_by_level(self, corp_id: str, level: int,
                            page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        query = self.db.query(WxGroup).filter(
            WxGroup.corp_id == corp_id,
            WxGroup.is_monitored == True,
            WxGroup.activity_level == level,
        ).order_by(WxGroup.activity_score.desc())

        total = query.count()
        groups = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "level": level,
            "level_name": LEVEL_NAMES.get(level, ""),
            "groups": groups,
        }

    def recompute_group_score(self, group: WxGroup,
                              thresholds: Optional[Dict[str, float]] = None) -> WxGroup:
        """
        基于近 7 天日统计重算单群活跃度评分与等级。
        评分 = 加权(日均消息量, 活跃成员占比, 平均回复率, 沉默惩罚)，归一化到 0~100。
        """
        thresholds = thresholds or {}
        today = date.today()
        start = today - timedelta(days=7)

        stats = self.db.query(WxGroupDailyStat).filter(
            WxGroupDailyStat.corp_id == group.corp_id,
            WxGroupDailyStat.chat_id == group.chat_id,
            WxGroupDailyStat.stat_date >= start,
            WxGroupDailyStat.stat_date <= today,
        ).all()

        if not stats:
            group.activity_score = 0
            group.activity_level = LEVEL_SILENT
            return group

        days = max(len(stats), 1)
        avg_msgs = sum(s.total_msg_count for s in stats) / days
        avg_active = sum(s.active_member_count for s in stats) / days
        avg_reply = sum(float(s.reply_rate) for s in stats) / days

        member_count = group.member_count or 1
        active_ratio = min(avg_active / member_count, 1.0)

        # 消息量得分：以 50 条/天为满分参考
        msg_score = min(avg_msgs / 50.0, 1.0) * 45
        active_score = active_ratio * 30
        reply_score = avg_reply * 25
        score = msg_score + active_score + reply_score

        # 沉默惩罚：最近一次消息超过 3 天直接判沉默
        if group.last_msg_time and (datetime.now() - group.last_msg_time).days >= 3:
            score = min(score, 10)

        score = round(max(0.0, min(score, 100.0)), 2)
        group.activity_score = score
        group.activity_level = score_to_level(
            score,
            thresholds.get("high", DEFAULT_HIGH_THRESHOLD),
            thresholds.get("normal", DEFAULT_NORMAL_THRESHOLD),
            thresholds.get("low", DEFAULT_LOW_THRESHOLD),
        )
        return group

    def recompute_all(self, corp_id: str, thresholds: Optional[Dict[str, float]] = None) -> int:
        groups = self.db.query(WxGroup).filter(WxGroup.corp_id == corp_id).all()
        for g in groups:
            self.recompute_group_score(g, thresholds)
        self.db.commit()
        return len(groups)

    def recompute_daily_stats(self, corp_id: str, day: Optional[date] = None) -> int:
        """从 WxMessage 聚合当天每群统计，写入 WxGroupDailyStat（驾驶舱/活跃度依赖此表）。"""
        day = day or date.today()
        start_dt = datetime.combine(day, datetime.min.time())
        end_dt = datetime.combine(day, datetime.max.time())
        rows = self.db.query(
            WxMessage.chat_id,
            func.count(WxMessage.id).label("msgs"),
            func.count(func.distinct(WxMessage.sender_userid)).label("actives"),
            func.sum(case((WxMessage.sender_type == 1, 1), else_=0)).label("staff"),
            func.sum(case((WxMessage.sender_type == 2, 1), else_=0)).label("cust"),
            func.max(WxMessage.send_time).label("last"),
        ).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.send_time >= start_dt,
            WxMessage.send_time <= end_dt,
        ).group_by(WxMessage.chat_id).all()

        n = 0
        for r in rows:
            staff = int(r.staff or 0)
            cust = int(r.cust or 0)
            reply = min(staff / cust, 1.0) if cust else (1.0 if staff else 0.0)
            stat = self.db.query(WxGroupDailyStat).filter(
                WxGroupDailyStat.corp_id == corp_id,
                WxGroupDailyStat.chat_id == r.chat_id,
                WxGroupDailyStat.stat_date == day,
            ).first()
            if not stat:
                stat = WxGroupDailyStat(corp_id=corp_id, chat_id=r.chat_id, stat_date=day)
                self.db.add(stat)
            stat.total_msg_count = int(r.msgs or 0)
            stat.active_member_count = int(r.actives or 0)
            stat.reply_rate = round(reply, 4)
            # 顺带更新群的最近消息时间（活跃度沉默惩罚要用）
            g = self.db.query(WxGroup).filter(
                WxGroup.corp_id == corp_id, WxGroup.chat_id == r.chat_id
            ).first()
            if g and r.last and (not g.last_msg_time or r.last > g.last_msg_time):
                g.last_msg_time = r.last
            n += 1
        self.db.commit()
        return n

    def recompute(self, corp_id: str, day: Optional[date] = None) -> Dict[str, int]:
        """一站式：先把消息聚合成当天统计，再据近7天统计重算各群活跃度等级。"""
        stat_groups = self.recompute_daily_stats(corp_id, day)
        scored = self.recompute_all(corp_id)
        return {"stat_groups": stat_groups, "scored_groups": scored}


class StatisticsService:
    """单群细粒度统计。所有方法显式接收 db。"""

    def _messages_query(self, db: Session, chat_id: str, corp_id: str,
                        start_date: date, end_date: date):
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        return db.query(WxMessage).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.chat_id == chat_id,
            WxMessage.send_time >= start_dt,
            WxMessage.send_time <= end_dt,
        )

    def calculate_reply_rate(self, db: Session, chat_id: str, corp_id: str,
                             start_date: date, end_date: date) -> Dict[str, Any]:
        """
        回复率：客户发言后，企业成员在合理时间内有回应的比例。
        简化口径：企业成员消息数 / 外部联系人消息数（封顶 1.0）。
        """
        msgs = self._messages_query(db, chat_id, corp_id, start_date, end_date).all()
        total = len(msgs)
        staff = sum(1 for m in msgs if m.sender_type == 1)
        customer = sum(1 for m in msgs if m.sender_type == 2)
        rate = min(staff / customer, 1.0) if customer else (1.0 if staff else 0.0)
        return {
            "total_messages": total,
            "staff_messages": staff,
            "customer_messages": customer,
            "reply_rate": round(rate * 100, 2),
        }

    def calculate_response_rate(self, db: Session, chat_id: str, corp_id: str,
                                start_date: date, end_date: date) -> Dict[str, Any]:
        """响应率：被@或客户提问后有人接话的比例（简化为有回应的客户消息占比）。"""
        msgs = self._messages_query(db, chat_id, corp_id, start_date, end_date) \
            .order_by(WxMessage.send_time).all()
        customer_msgs = [m for m in msgs if m.sender_type == 2]
        if not customer_msgs:
            return {"responded": 0, "customer_total": 0, "response_rate": 0.0}

        responded = 0
        for cm in customer_msgs:
            # 该客户消息之后 2 小时内是否有企业成员发言
            window_end = cm.send_time + timedelta(hours=2)
            has_resp = any(
                m.sender_type == 1 and cm.send_time < m.send_time <= window_end
                for m in msgs
            )
            if has_resp:
                responded += 1
        rate = responded / len(customer_msgs)
        return {
            "responded": responded,
            "customer_total": len(customer_msgs),
            "response_rate": round(rate * 100, 2),
        }

    def calculate_avg_response_time(self, db: Session, chat_id: str, corp_id: str,
                                    start_date: date, end_date: date) -> Dict[str, Any]:
        """平均响应时长（分钟）：客户发言到企业成员首次回应的间隔均值。"""
        msgs = self._messages_query(db, chat_id, corp_id, start_date, end_date) \
            .order_by(WxMessage.send_time).all()
        deltas: List[float] = []
        for i, cm in enumerate(msgs):
            if cm.sender_type != 2:
                continue
            for m in msgs[i + 1:]:
                if m.sender_type == 1:
                    deltas.append((m.send_time - cm.send_time).total_seconds() / 60.0)
                    break
        avg = round(sum(deltas) / len(deltas), 1) if deltas else 0.0
        return {"avg_response_minutes": avg, "samples": len(deltas)}

    def get_member_speak_ranking(self, db: Session, chat_id: str, corp_id: str,
                                 start_date: date, end_date: date, top_n: int = 10) -> List[Dict]:
        """成员发言排名。"""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        rows = db.query(
            WxMessage.sender_userid,
            WxMessage.sender_name,
            func.count(WxMessage.id).label("cnt"),
        ).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.chat_id == chat_id,
            WxMessage.send_time >= start_dt,
            WxMessage.send_time <= end_dt,
        ).group_by(WxMessage.sender_userid, WxMessage.sender_name) \
            .order_by(func.count(WxMessage.id).desc()).limit(top_n).all()
        return [
            {"userid": r.sender_userid, "name": r.sender_name or r.sender_userid, "msg_count": r.cnt}
            for r in rows
        ]

    def get_hourly_distribution(self, db: Session, chat_id: str, corp_id: str,
                                start_date: date, end_date: date) -> List[Dict]:
        """24 小时消息分布（用 Python 聚合，兼容各数据库）。"""
        msgs = self._messages_query(db, chat_id, corp_id, start_date, end_date).all()
        buckets = [0] * 24
        for m in msgs:
            buckets[m.send_time.hour] += 1
        return [{"hour": h, "count": c} for h, c in enumerate(buckets)]

    def get_at_mention_stats(self, db: Session, chat_id: str, corp_id: str,
                             start_date: date, end_date: date) -> Dict[str, Any]:
        """@提及统计。"""
        msgs = self._messages_query(db, chat_id, corp_id, start_date, end_date).all()
        at_count = sum(1 for m in msgs if m.is_at)
        return {"at_message_count": at_count, "total_messages": len(msgs)}

    def get_silent_members(self, db: Session, chat_id: str, corp_id: str,
                           days: int = 7) -> List[Dict]:
        """近 N 天未发言的群成员。"""
        since = datetime.now() - timedelta(days=days)
        members = db.query(WxGroupMember).filter(
            WxGroupMember.corp_id == corp_id,
            WxGroupMember.chat_id == chat_id,
            WxGroupMember.is_active == True,
        ).all()

        spoken = {
            r[0] for r in db.query(WxMessage.sender_userid).filter(
                WxMessage.corp_id == corp_id,
                WxMessage.chat_id == chat_id,
                WxMessage.send_time >= since,
            ).distinct().all()
        }

        silent = [m for m in members if m.userid not in spoken]
        return [
            {"userid": m.userid, "member_name": m.member_name or m.userid,
             "member_type": m.member_type, "is_owner": m.is_owner}
            for m in silent
        ]
