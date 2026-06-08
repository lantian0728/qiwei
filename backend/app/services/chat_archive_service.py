"""
会话存档同步：拉取企业微信群聊记录 → 解密 → 写入 WxMessage
写入后，客服效能/AI日报/情绪/查件触发 全部基于真实消息。

仅服务器(Linux + SDK)可运行。游标(seq)存于 WxSystemConfig。
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.core import wework_finance
from app.core.config import settings
from app.models.models import WxMessage, WxGroup, WxGroupMember, WxSystemConfig

SEQ_KEY = "wx_archive_seq"


class ChatArchiveService:
    def __init__(self, db: Session):
        self.db = db
        self.corp_id = settings.WX_ARCHIVE_CORPID or settings.WX_CORP_ID

    def _get_seq(self) -> int:
        row = self.db.query(WxSystemConfig).filter(
            WxSystemConfig.corp_id == self.corp_id, WxSystemConfig.config_key == SEQ_KEY
        ).first()
        try:
            return int(row.config_value) if row and row.config_value else 0
        except ValueError:
            return 0

    def _set_seq(self, seq: int):
        row = self.db.query(WxSystemConfig).filter(
            WxSystemConfig.corp_id == self.corp_id, WxSystemConfig.config_key == SEQ_KEY
        ).first()
        if not row:
            row = WxSystemConfig(corp_id=self.corp_id, config_key=SEQ_KEY)
            self.db.add(row)
        row.config_value = str(seq)
        self.db.commit()

    def _monitored_rooms(self) -> set:
        return {
            g.chat_id for g in self.db.query(WxGroup.chat_id).filter(
                WxGroup.corp_id == self.corp_id, WxGroup.is_monitored == True
            ).all()
        }

    def _staff_ids(self, chat_id: str) -> Dict[str, str]:
        """该群企业成员 userid→姓名，用于区分客服/客户。"""
        return {
            m.userid: m.member_name for m in self.db.query(WxGroupMember).filter(
                WxGroupMember.corp_id == self.corp_id,
                WxGroupMember.chat_id == chat_id,
            ).all()
        }

    def fast_forward(self, batch_limit: int = 1000) -> Dict[str, Any]:
        """快速把游标顶到最新：只读 seq、不解密，跳过全部历史(避免逐条解密旧版本崩溃)。
        贴新公钥后调用一次，之后日常 sync 只处理新产生的消息。"""
        if not wework_finance.is_available():
            return {"available": False, "message": "未配置会话存档"}
        sdk = wework_finance.WeWorkFinanceSDK()
        seq = self._get_seq()
        scanned = 0
        try:
            while True:
                records = sdk.get_chat_data(seq, batch_limit)
                if not records:
                    break
                seq = max(int(r.get("seq", seq)) for r in records)
                scanned += len(records)
                self._set_seq(seq)
                if len(records) < batch_limit:
                    break
        finally:
            sdk.close()
        return {"available": True, "scanned": scanned, "seq": seq}

    def sync(self, max_batches: int = 50, batch_limit: int = 100) -> Dict[str, Any]:
        if not wework_finance.is_available():
            return {"available": False,
                    "message": "未配置会话存档(SDK路径/Secret/私钥)，仅服务器可用"}

        target_ver = settings.WX_ARCHIVE_PUBLIC_KEY_VER  # 只解此版本；0=不限
        sdk = wework_finance.WeWorkFinanceSDK()
        rooms = self._monitored_rooms()
        seq = self._get_seq()
        stored = skipped = ver_skipped = 0
        member_cache: Dict[str, Dict[str, str]] = {}

        try:
            for _ in range(max_batches):
                records = sdk.get_chat_data(seq, batch_limit)
                if not records:
                    break
                for rec in records:
                    seq = max(seq, int(rec.get("seq", seq)))
                    # 关键：版本不符的消息(旧密钥加密)直接跳过，绝不调解密，避免 C 层崩溃
                    if target_ver and int(rec.get("publickey_ver", 0)) != target_ver:
                        ver_skipped += 1
                        continue
                    try:
                        msg = sdk.decrypt_message(
                            rec["encrypt_random_key"], rec["encrypt_chat_msg"])
                    except Exception:
                        skipped += 1
                        continue
                    if self._store_message(msg, rooms, member_cache):
                        stored += 1
                    else:
                        skipped += 1
                self._set_seq(seq)
                if len(records) < batch_limit:
                    break
        finally:
            sdk.close()

        return {"available": True, "stored": stored, "skipped": skipped,
                "ver_skipped": ver_skipped, "seq": seq}

    def _store_message(self, msg: Dict[str, Any], rooms: set,
                       member_cache: Dict[str, Dict[str, str]]) -> bool:
        roomid = msg.get("roomid")
        if not roomid or roomid not in rooms:
            return False  # 只存被监测的群聊
        msgtype = msg.get("msgtype", "")
        msgid = msg.get("msgid", "")

        # 去重
        if msgid and self.db.query(WxMessage.id).filter(
            WxMessage.corp_id == self.corp_id, WxMessage.chat_id == roomid,
            WxMessage.msgid == msgid,
        ).first():
            return False

        sender = msg.get("from", "")
        if roomid not in member_cache:
            member_cache[roomid] = self._staff_ids(roomid)
        members = member_cache[roomid]
        is_staff = sender in members
        sender_name = members.get(sender, sender)

        content = ""
        is_at = False
        if msgtype == "text":
            content = (msg.get("text") or {}).get("content", "")
        else:
            content = f"[{msgtype}]"  # 非文本只记类型，供活跃度统计

        ts = msg.get("msgtime", 0)
        try:
            send_time = datetime.fromtimestamp(int(ts) / 1000)
        except Exception:
            send_time = datetime.now()

        self.db.add(WxMessage(
            corp_id=self.corp_id, chat_id=roomid, msgid=msgid,
            sender_userid=sender, sender_name=sender_name,
            sender_type=1 if is_staff else 2,
            msg_type=msgtype or "text", content=content,
            is_at=is_at, send_time=send_time,
        ))
        self.db.commit()
        return True
