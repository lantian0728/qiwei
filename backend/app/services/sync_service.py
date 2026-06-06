"""
数据同步服务

- GroupSyncService：调用企业微信 API 拉取真实客户群 -> 落库 -> 重算活跃度
- MockDataService：无凭证时生成一批可演示的模拟数据
"""
import random
from datetime import datetime, timedelta, date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    WxGroup, WxGroupMember, WxGroupDailyStat, WxMessage,
    WxCorpConfig, WxSyncLog, WxAlert,
)
from app.core.wxwork_client import WxWorkClient, WxWorkAPIError
from app.services.activity_service import ActivityLevelService, score_to_level, LEVEL_SILENT


class GroupSyncService:
    def __init__(self, db: Session, corp_id: str):
        self.db = db
        self.corp_id = corp_id

    async def sync_customer_groups(self) -> WxSyncLog:
        """从企业微信拉取客户群列表与详情，写入/更新本地。"""
        log = WxSyncLog(corp_id=self.corp_id, sync_type="group", status=1,
                        started_at=datetime.now())
        self.db.add(log)
        self.db.commit()

        config = self.db.query(WxCorpConfig).filter(
            WxCorpConfig.corp_id == self.corp_id
        ).first()
        if not config or not config.corp_secret:
            log.status = 3
            log.error_msg = "企业配置不存在或缺少 Secret"
            log.finished_at = datetime.now()
            self.db.commit()
            return log

        client = WxWorkClient(corp_id=self.corp_id, corp_secret=config.corp_secret)
        total = success = fail = 0

        try:
            cursor = ""
            chat_ids = []
            while True:
                resp = await client.list_group_chats(cursor=cursor, limit=100)
                for item in resp.get("group_chat_list", []):
                    chat_ids.append(item["chat_id"])
                cursor = resp.get("next_cursor", "")
                if not cursor:
                    break

            total = len(chat_ids)
            for chat_id in chat_ids:
                try:
                    detail = (await client.get_group_chat_detail(chat_id)).get("group_chat", {})
                    self._upsert_group(detail)
                    success += 1
                except WxWorkAPIError:
                    fail += 1

            # 重算活跃度
            ActivityLevelService(self.db).recompute_all(self.corp_id)

            log.status = 2
        except WxWorkAPIError as e:
            log.status = 3
            log.error_msg = str(e)
        finally:
            log.total_count = total
            log.success_count = success
            log.fail_count = fail
            log.finished_at = datetime.now()
            self.db.commit()

        return log

    def _upsert_group(self, detail: dict) -> WxGroup:
        chat_id = detail.get("chat_id")
        group = self.db.query(WxGroup).filter(
            WxGroup.corp_id == self.corp_id,
            WxGroup.chat_id == chat_id,
        ).first()
        if not group:
            group = WxGroup(corp_id=self.corp_id, chat_id=chat_id)
            self.db.add(group)

        group.group_name = detail.get("name", group.group_name or "")
        group.owner_userid = detail.get("owner", group.owner_userid or "")
        group.notice = detail.get("notice", group.notice or "")
        members = detail.get("member_list", [])
        group.member_count = len(members) or group.member_count
        ct = detail.get("create_time")
        if ct:
            group.create_time = datetime.fromtimestamp(ct)
        group.last_synced_at = datetime.now()

        # 同步成员
        for m in members:
            self._upsert_member(chat_id, m, group.owner_userid)

        self.db.commit()
        return group

    def _upsert_member(self, chat_id: str, m: dict, owner_userid: str):
        userid = m.get("userid")
        member = self.db.query(WxGroupMember).filter(
            WxGroupMember.corp_id == self.corp_id,
            WxGroupMember.chat_id == chat_id,
            WxGroupMember.userid == userid,
        ).first()
        if not member:
            member = WxGroupMember(corp_id=self.corp_id, chat_id=chat_id, userid=userid)
            self.db.add(member)
        member.member_name = m.get("name", member.member_name or "")
        member.member_type = m.get("type", 1)
        member.is_owner = (userid == owner_userid)
        jt = m.get("join_time")
        if jt:
            member.join_time = datetime.fromtimestamp(jt)
        member.is_active = True


class MockDataService:
    """演示数据生成：无需企业微信凭证即可填充一批可视化数据。"""

    GROUP_NAMES = [
        "深圳大客户服务群", "义乌外贸一群", "美西专线VIP群", "亚马逊卖家对接群",
        "华东渠道商群", "跨境物流答疑群", "重点客户-张总群", "东南亚专线群",
        "海运拼柜交流群", "报关单证服务群", "义乌小商品出口群", "美东FBA头程群",
    ]
    STAFF = [("staff_li", "李经理"), ("staff_wang", "王客服"), ("staff_zhao", "赵主管")]
    CUSTOMERS = [("cus_a", "陈先生"), ("cus_b", "刘女士"), ("cus_c", "周总"),
                 ("cus_d", "黄经理"), ("cus_e", "吴老板")]

    def __init__(self, db: Session, corp_id: str):
        self.db = db
        self.corp_id = corp_id

    def generate_demo_data(self) -> dict:
        # 已有数据则跳过，避免重复
        existing = self.db.query(WxGroup).filter(WxGroup.corp_id == self.corp_id).count()
        if existing > 0:
            return {"skipped": True, "groups": existing}

        log = WxSyncLog(corp_id=self.corp_id, sync_type="demo", status=1,
                        started_at=datetime.now())
        self.db.add(log)
        self.db.commit()

        rnd = random.Random(42)  # 固定种子，演示数据稳定
        now = datetime.now()
        group_count = 0

        for idx, name in enumerate(self.GROUP_NAMES):
            chat_id = f"demo_chat_{idx:03d}"
            gtype = rnd.choice([1, 1, 1, 2, 3, 4])  # 偏向客户群
            member_count = rnd.randint(8, 60)
            owner = rnd.choice(self.STAFF)

            group = WxGroup(
                corp_id=self.corp_id, chat_id=chat_id, group_name=name,
                group_type=gtype, owner_userid=owner[0], owner_name=owner[1],
                member_count=member_count, is_monitored=True,
                is_key_group=(idx % 4 == 0),
                create_time=now - timedelta(days=rnd.randint(30, 300)),
                last_synced_at=now,
            )
            self.db.add(group)

            # 成员
            self.db.add(WxGroupMember(
                corp_id=self.corp_id, chat_id=chat_id, userid=owner[0],
                member_name=owner[1], member_type=1, is_owner=True,
                join_time=group.create_time, is_active=True,
            ))
            for sid, sname in self.STAFF:
                if sid == owner[0]:
                    continue
                self.db.add(WxGroupMember(
                    corp_id=self.corp_id, chat_id=chat_id, userid=sid,
                    member_name=sname, member_type=1, is_active=True,
                    join_time=group.create_time,
                ))
            for cid, cname in rnd.sample(self.CUSTOMERS, k=rnd.randint(2, len(self.CUSTOMERS))):
                self.db.add(WxGroupMember(
                    corp_id=self.corp_id, chat_id=chat_id, userid=cid,
                    member_name=cname, member_type=2, is_active=True,
                    join_time=group.create_time,
                ))

            # 近 14 天消息 + 日统计
            activity_base = rnd.choice([0.05, 0.3, 0.6, 0.9])  # 决定群冷热
            last_msg_time = None
            for d in range(14):
                day = (now - timedelta(days=13 - d)).date()
                questions = max(0, int(rnd.gauss(activity_base * 16, 3)))
                day_msgs = self._gen_day_messages(chat_id, day, questions, rnd)
                msg_count = len(day_msgs)
                if day_msgs:
                    last_msg_time = max(m.send_time for m in day_msgs)

                active_members = min(member_count, len({m.sender_userid for m in day_msgs}))
                staff_msgs = sum(1 for m in day_msgs if m.sender_type == 1)
                cust_msgs = sum(1 for m in day_msgs if m.sender_type == 2)
                reply_rate = min(staff_msgs / cust_msgs, 1.0) if cust_msgs else (1.0 if staff_msgs else 0.0)
                score = min(msg_count / 40.0, 1.0) * 70 + reply_rate * 30

                self.db.add(WxGroupDailyStat(
                    corp_id=self.corp_id, chat_id=chat_id, stat_date=day,
                    total_msg_count=msg_count, active_member_count=active_members,
                    reply_rate=round(reply_rate, 4), activity_score=round(score, 2),
                ))

            group.last_msg_time = last_msg_time
            group_count += 1

        self.db.commit()

        # 重算活跃度等级
        ActivityLevelService(self.db).recompute_all(self.corp_id)

        # 给沉默群生成预警
        self._gen_alerts()

        log.status = 2
        log.total_count = group_count
        log.success_count = group_count
        log.finished_at = datetime.now()
        self.db.commit()

        return {"skipped": False, "groups": group_count}

    # 货代场景话术（让客服效能/情绪分析有真实文本可分析）
    CUSTOMER_QUESTIONS = [
        "我的货到哪了？", "深圳到洛杉矶现在什么价？", "这周还有舱吗？能不能加塞",
        "怎么还没派送啊，客户催得急", "被海关查验了怎么办？", "账单是不是多收了？",
        "别家报价更低，能不能再降点", "截单时间是几点？", "这批走美森还是以星？",
        "FBA 入仓预约好了吗", "提单什么时候出", "清关需要补什么资料",
    ]
    STAFF_REPLIES = [
        "您好，马上帮您查一下轨迹", "稍等，这边核实后回复您", "今天 18 点前截单哦",
        "已经在派送途中，预计明天到", "查验是常规抽查，我们盯着，别担心", "账单我让财务复核下",
        "价格已经是优惠价了，量大可以再谈", "提单今天会出，出了发您",
    ]

    def _gen_day_messages(self, chat_id: str, day: date, questions: int, rnd: random.Random):
        """以"客户提问→客服回复"为单位生成真实对话，含合理首响时延与少量超时。"""
        msgs = []
        base = datetime.combine(day, datetime.min.time())

        def add(sid, sname, stype, send_time, content, is_at=False):
            m = WxMessage(
                corp_id=self.corp_id, chat_id=chat_id,
                sender_userid=sid, sender_name=sname, sender_type=stype,
                msg_type="text", content=content, is_at=is_at, send_time=send_time,
            )
            self.db.add(m)
            msgs.append(m)

        for _ in range(questions):
            hour = rnd.choices(
                population=list(range(24)),
                weights=[1, 0, 0, 0, 0, 1, 2, 4, 9, 11, 11, 9, 6, 8, 11, 11, 9, 7, 6, 4, 3, 2, 1, 1],
                k=1,
            )[0]
            ctime = base + timedelta(hours=hour, minutes=rnd.randint(0, 59), seconds=rnd.randint(0, 59))
            cust = rnd.choice(self.CUSTOMERS)
            add(cust[0], cust[1], 2, ctime, rnd.choice(self.CUSTOMER_QUESTIONS), is_at=(rnd.random() < 0.2))

            # 工作时间内 94% 会被回复；其中约 12% 是超时回复
            if 9 <= hour < 21 and rnd.random() < 0.94:
                if rnd.random() < 0.12:
                    delay = rnd.uniform(32, 75)    # 超时
                else:
                    delay = max(1.0, rnd.gauss(9, 5))   # 正常首响 ~9 分钟
                staff = rnd.choice(self.STAFF)
                add(staff[0], staff[1], 1, ctime + timedelta(minutes=delay), rnd.choice(self.STAFF_REPLIES))
                # 偶尔客户追加一句
                if rnd.random() < 0.3:
                    add(cust[0], cust[1], 2, ctime + timedelta(minutes=delay + rnd.uniform(1, 8)), "好的，谢谢")
        return msgs

    def _gen_alerts(self):
        silent_groups = self.db.query(WxGroup).filter(
            WxGroup.corp_id == self.corp_id,
            WxGroup.activity_level == LEVEL_SILENT,
        ).all()
        for g in silent_groups:
            self.db.add(WxAlert(
                corp_id=self.corp_id, chat_id=g.chat_id, group_name=g.group_name,
                alert_type=1, alert_level=2,
                content=f"群「{g.group_name}」连续多日无消息，已进入沉默状态",
                is_read=False,
            ))
        self.db.commit()
