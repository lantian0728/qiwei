"""
数据模型：企微群会话分析系统全部数据表

字段命名与 api/groups.py、api/auth.py、api/admin.py 中的查询保持一致。
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime, Date,
    Numeric, Index, UniqueConstraint,
)

from app.core.database import Base


class SysUser(Base):
    """系统用户（由企业微信成员映射而来）"""
    __tablename__ = "sys_user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    userid = Column(String(128), nullable=False, comment="企业微信 UserId")
    username = Column(String(128), default="")
    real_name = Column(String(128), default="")
    avatar_url = Column(String(512), default="")
    email = Column(String(128), default="")
    mobile = Column(String(32), default="")
    department = Column(String(128), default="")
    role = Column(Integer, default=3, comment="1超管 2管理员 3运营")
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("corp_id", "userid", name="uq_user_corp_userid"),)


class WxCorpConfig(Base):
    """企业微信 API 配置"""
    __tablename__ = "wx_corp_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), unique=True, nullable=False)
    corp_name = Column(String(128), default="")
    agent_id = Column(String(64), default="")
    corp_secret = Column(String(256), default="", comment="加密存储建议")
    token = Column(String(128), default="")
    encoding_aes_key = Column(String(128), default="")
    webhook_url = Column(String(512), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WxGroup(Base):
    """企业微信群"""
    __tablename__ = "wx_group"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    chat_id = Column(String(128), nullable=False, comment="群唯一ID")
    group_name = Column(String(256), default="")
    group_type = Column(Integer, default=1, comment="1客户群 2内部群 3项目群 4渠道群")
    owner_userid = Column(String(128), default="")
    owner_name = Column(String(128), default="")
    member_count = Column(Integer, default=0)
    notice = Column(Text, default="")

    activity_level = Column(Integer, default=4, comment="1高 2正常 3低 4沉默")
    activity_score = Column(Numeric(6, 2), default=0)

    is_key_group = Column(Boolean, default=False, comment="重点群")
    is_problem_group = Column(Boolean, default=False, comment="问题群")
    is_monitored = Column(Boolean, default=True, comment="是否纳入监测")
    tags = Column(String(512), default="")

    last_msg_time = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=True, comment="群创建时间")

    __table_args__ = (
        UniqueConstraint("corp_id", "chat_id", name="uq_group_corp_chat"),
        Index("ix_group_level", "corp_id", "activity_level"),
    )


class WxGroupMember(Base):
    """群成员"""
    __tablename__ = "wx_group_member"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    chat_id = Column(String(128), index=True, nullable=False)
    userid = Column(String(128), nullable=False)
    member_name = Column(String(128), default="")
    member_type = Column(Integer, default=1, comment="1企业成员 2外部联系人")
    is_owner = Column(Boolean, default=False)
    avatar_url = Column(String(512), default="")
    join_time = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("corp_id", "chat_id", "userid", name="uq_member_corp_chat_user"),
    )


class WxMessage(Base):
    """群消息（仅元数据，用于统计；不存敏感正文也可）"""
    __tablename__ = "wx_message"

    # SQLite 仅 INTEGER 主键自增，BIGINT 不自增；用 variant 兼容 MySQL(BIGINT)/SQLite(INTEGER)
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    chat_id = Column(String(128), index=True, nullable=False)
    msgid = Column(String(128), default="")
    sender_userid = Column(String(128), default="")
    sender_name = Column(String(128), default="")
    sender_type = Column(Integer, default=1, comment="1企业成员 2外部联系人")
    msg_type = Column(String(32), default="text")
    content = Column(Text, default="")
    is_at = Column(Boolean, default=False, comment="是否@了人")
    at_list = Column(Text, default="", comment="被@的userid，逗号分隔")
    send_time = Column(DateTime, index=True, nullable=False)

    __table_args__ = (Index("ix_msg_chat_time", "corp_id", "chat_id", "send_time"),)


class WxGroupDailyStat(Base):
    """群每日统计快照"""
    __tablename__ = "wx_group_daily_stat"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    chat_id = Column(String(128), index=True, nullable=False)
    stat_date = Column(Date, index=True, nullable=False)

    total_msg_count = Column(Integer, default=0)
    active_member_count = Column(Integer, default=0)
    reply_rate = Column(Numeric(5, 4), default=0, comment="回复率 0~1")
    activity_score = Column(Numeric(6, 2), default=0)

    __table_args__ = (
        UniqueConstraint("corp_id", "chat_id", "stat_date", name="uq_stat_corp_chat_date"),
    )


class WxGroupTag(Base):
    """群标签字典"""
    __tablename__ = "wx_group_tag"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    tag_name = Column(String(64), nullable=False)
    color = Column(String(16), default="#409EFF")
    created_at = Column(DateTime, default=datetime.now)


class WxGroupTagRel(Base):
    """群-标签 关联"""
    __tablename__ = "wx_group_tag_rel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    chat_id = Column(String(128), index=True, nullable=False)
    tag_id = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("chat_id", "tag_id", name="uq_tagrel_chat_tag"),
    )


class WxAlert(Base):
    """预警记录"""
    __tablename__ = "wx_alert"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    chat_id = Column(String(128), default="", index=True)
    group_name = Column(String(256), default="")
    alert_type = Column(Integer, default=1, comment="1沉默 2活跃度下降 3其他")
    alert_level = Column(Integer, default=2, comment="1严重 2警告 3提示")
    content = Column(String(512), default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now, index=True)


class WxSyncLog(Base):
    """数据同步日志"""
    __tablename__ = "wx_sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False)
    sync_type = Column(String(32), default="group", comment="group/member/message/stat")
    status = Column(Integer, default=1, comment="1进行中 2成功 3失败")
    total_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    error_msg = Column(String(512), default="")
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)


class WxSystemConfig(Base):
    """系统参数（键值对，按企业隔离）"""
    __tablename__ = "wx_system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_id = Column(String(64), index=True, nullable=False, default="_global")
    config_key = Column(String(64), nullable=False)
    config_value = Column(String(256), default="")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("corp_id", "config_key", name="uq_syscfg_corp_key"),
    )
