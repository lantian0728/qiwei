"""
群管理API：群列表、群详情、群成员、活跃度分级
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import WxGroup, WxGroupMember, WxGroupDailyStat
from app.services.activity_service import (
    ActivityLevelService, StatisticsService,
    LEVEL_NAMES, LEVEL_COLORS, LEVEL_HIGH, LEVEL_NORMAL, LEVEL_LOW, LEVEL_SILENT,
)
from app.services.sync_service import GroupSyncService, MockDataService

router = APIRouter(prefix="/groups", tags=["群管理"])


# ========== 群列表 ==========

@router.get("", summary="获取群列表")
@router.get("/", summary="获取群列表", include_in_schema=False)
async def list_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    group_type: Optional[int] = Query(None, description="群类型：1客户群 2内部群 3项目群 4渠道群"),
    activity_level: Optional[int] = Query(None, description="活跃度等级：1高 2正常 3低 4沉默"),
    keyword: Optional[str] = Query(None, description="搜索关键词（群名）"),
    is_key_group: Optional[bool] = Query(None),
    sort_by: str = Query("activity_score", description="排序字段"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    query = db.query(WxGroup).filter(
        WxGroup.corp_id == corp_id,
        WxGroup.is_monitored == True,
    )

    if group_type:
        query = query.filter(WxGroup.group_type == group_type)
    if activity_level:
        query = query.filter(WxGroup.activity_level == activity_level)
    if keyword:
        query = query.filter(WxGroup.group_name.like(f"%{keyword}%"))
    if is_key_group is not None:
        query = query.filter(WxGroup.is_key_group == is_key_group)

    total = query.count()

    sort_col = getattr(WxGroup, sort_by, WxGroup.activity_score)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    groups = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [_format_group(g) for g in groups],
    }


@router.get("/level-summary", summary="获取各活跃度等级汇总")
async def get_level_summary(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    return ActivityLevelService(db).get_level_summary(corp_id)


@router.get("/by-level/{level}", summary="按活跃度等级获取群列表")
async def get_groups_by_level(
    level: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    if level not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="活跃度等级无效，应为1-4")
    result = ActivityLevelService(db).get_groups_by_level(corp_id, level, page, page_size)
    result["items"] = [_format_group(g) for g in result.pop("groups", [])]
    return result


@router.get("/overview", summary="群总览仪表盘数据")
async def get_overview(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)

    total_groups = db.query(func.count(WxGroup.id)).filter(
        WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
    ).scalar() or 0

    total_members = db.query(func.sum(WxGroup.member_count)).filter(
        WxGroup.corp_id == corp_id, WxGroup.is_monitored == True
    ).scalar() or 0

    today = date.today()
    today_stats = db.query(
        func.sum(WxGroupDailyStat.total_msg_count).label("total_msgs"),
        func.sum(WxGroupDailyStat.active_member_count).label("active_members"),
        func.avg(WxGroupDailyStat.reply_rate).label("avg_reply_rate"),
    ).filter(
        WxGroupDailyStat.corp_id == corp_id,
        WxGroupDailyStat.stat_date == today,
    ).first()

    level_dist = db.query(
        WxGroup.activity_level, func.count(WxGroup.id).label("count"),
    ).filter(
        WxGroup.corp_id == corp_id, WxGroup.is_monitored == True,
    ).group_by(WxGroup.activity_level).all()
    level_map = {r.activity_level: r.count for r in level_dist}

    from app.models.models import WxAlert
    unread_alerts = db.query(func.count(WxAlert.id)).filter(
        WxAlert.corp_id == corp_id, WxAlert.is_read == False,
    ).scalar() or 0

    return {
        "total_groups": total_groups,
        "total_members": int(total_members),
        "today_messages": int(today_stats.total_msgs or 0),
        "today_active_members": int(today_stats.active_members or 0),
        "avg_reply_rate": round(float(today_stats.avg_reply_rate or 0) * 100, 2),
        "unread_alerts": unread_alerts,
        "level_distribution": {
            "high": level_map.get(LEVEL_HIGH, 0),
            "normal": level_map.get(LEVEL_NORMAL, 0),
            "low": level_map.get(LEVEL_LOW, 0),
            "silent": level_map.get(LEVEL_SILENT, 0),
        },
    }


# ========== 代理/直客分类 ==========

@router.post("/classify/run", summary="AI分类群：代理/直客")
async def classify_run(
    only_unknown: bool = Query(False, description="只分还没判定的群"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    from app.services.group_classify_service import GroupClassifyService
    return await GroupClassifyService(db).classify_all(corp_id, only_unknown)


@router.get("/classify/summary", summary="代理/直客数量统计")
async def classify_summary(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    from app.services.group_classify_service import GroupClassifyService
    return GroupClassifyService(db).summary(corp_id)


# ========== 单群详情 ==========

@router.get("/{chat_id}", summary="获取群详情")
async def get_group_detail(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    group = _get_group_or_404(db, corp_id, chat_id)
    return _format_group(group, detail=True)


@router.get("/{chat_id}/members", summary="获取群成员列表")
async def get_group_members(
    chat_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    _get_group_or_404(db, corp_id, chat_id)

    query = db.query(WxGroupMember).filter(
        WxGroupMember.corp_id == corp_id,
        WxGroupMember.chat_id == chat_id,
        WxGroupMember.is_active == True,
    )
    total = query.count()
    members = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "userid": m.userid, "member_name": m.member_name,
                "member_type": m.member_type, "is_owner": m.is_owner,
                "join_time": m.join_time.isoformat() if m.join_time else None,
                "avatar_url": m.avatar_url,
            }
            for m in members
        ],
    }


@router.get("/{chat_id}/stats", summary="获取群统计数据")
async def get_group_stats(
    chat_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    _get_group_or_404(db, corp_id, chat_id)

    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=7)

    svc = StatisticsService()
    daily_stats = db.query(WxGroupDailyStat).filter(
        WxGroupDailyStat.corp_id == corp_id,
        WxGroupDailyStat.chat_id == chat_id,
        WxGroupDailyStat.stat_date >= start_date,
        WxGroupDailyStat.stat_date <= end_date,
    ).order_by(WxGroupDailyStat.stat_date).all()

    silent_members = svc.get_silent_members(db, chat_id, corp_id, days=7)

    return {
        "date_range": {"start": str(start_date), "end": str(end_date)},
        "reply_stats": svc.calculate_reply_rate(db, chat_id, corp_id, start_date, end_date),
        "response_stats": svc.calculate_response_rate(db, chat_id, corp_id, start_date, end_date),
        "response_time": svc.calculate_avg_response_time(db, chat_id, corp_id, start_date, end_date),
        "member_ranking": svc.get_member_speak_ranking(db, chat_id, corp_id, start_date, end_date),
        "hourly_distribution": svc.get_hourly_distribution(db, chat_id, corp_id, start_date, end_date),
        "at_stats": svc.get_at_mention_stats(db, chat_id, corp_id, start_date, end_date),
        "silent_members_count": len(silent_members),
        "silent_members": silent_members[:10],
        "daily_trend": [
            {
                "date": str(s.stat_date), "total_msgs": s.total_msg_count,
                "active_members": s.active_member_count,
                "reply_rate": float(s.reply_rate), "activity_score": float(s.activity_score),
            }
            for s in daily_stats
        ],
    }


# ========== 群管理操作 ==========

class UpdateGroupRequest(BaseModel):
    is_key_group: Optional[bool] = None
    is_problem_group: Optional[bool] = None
    tags: Optional[str] = None
    is_monitored: Optional[bool] = None


@router.patch("/{chat_id}", summary="更新群标记信息")
async def update_group(
    chat_id: str,
    req: UpdateGroupRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    group = _get_group_or_404(db, corp_id, chat_id)

    if req.is_key_group is not None:
        group.is_key_group = req.is_key_group
    if req.is_problem_group is not None:
        group.is_problem_group = req.is_problem_group
    if req.tags is not None:
        group.tags = req.tags
    if req.is_monitored is not None:
        group.is_monitored = req.is_monitored

    db.commit()
    return {"success": True, "message": "更新成功"}


@router.get("/{chat_id}/sentiment", summary="群消息情绪分析（豆包AI）")
async def get_group_sentiment(
    chat_id: str,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    _get_group_or_404(db, corp_id, chat_id)
    from app.services.sentiment_service import DoubaoSentimentService
    return await DoubaoSentimentService(db).analyze_group(corp_id, chat_id, days=days)


@router.get("/{chat_id}/messages", summary="群聊天记录(带客服/客户标识)")
async def get_group_messages(
    chat_id: str,
    limit: int = Query(120, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    _get_group_or_404(db, corp_id, chat_id)
    from app.models.models import WxMessage
    msgs = db.query(WxMessage).filter(
        WxMessage.corp_id == corp_id, WxMessage.chat_id == chat_id,
    ).order_by(WxMessage.send_time.desc()).limit(limit).all()
    msgs.reverse()  # 取最近 N 条后按时间正序展示
    return {
        "total": len(msgs),
        "items": [
            {
                "time": m.send_time.strftime("%m-%d %H:%M") if m.send_time else "",
                "sender_name": m.sender_name or m.sender_userid or "未知",
                "is_staff": m.sender_type == 1,
                "role": "客服" if m.sender_type == 1 else "客户",
                "msg_type": m.msg_type,
                "content": m.content or "",
            }
            for m in msgs
        ],
    }


@router.get("/{chat_id}/digest", summary="AI提炼群聊重点(过滤后呈现)")
async def get_group_digest(
    chat_id: str,
    day: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)
    g = _get_group_or_404(db, corp_id, chat_id)
    from app.services.ai_report_service import AIReportService
    return await AIReportService(db).group_digest(corp_id, chat_id, g.group_name, day)


@router.post("/sync", summary="手动触发群列表同步")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    corp_id = _require_corp_id(current_user)

    async def do_sync():
        # 后台任务使用独立会话，避免复用已随请求关闭的 session
        from app.core.database import SessionLocal
        from app.models.models import WxCorpConfig
        task_db = SessionLocal()
        try:
            config = task_db.query(WxCorpConfig).filter(
                WxCorpConfig.corp_id == corp_id
            ).first()
            if config and config.corp_secret:
                await GroupSyncService(task_db, corp_id).sync_customer_groups()
            else:
                # 无凭证：生成演示数据
                MockDataService(task_db, corp_id).generate_demo_data()
        finally:
            task_db.close()

    background_tasks.add_task(do_sync)
    return {"success": True, "message": "同步任务已触发，请稍后刷新"}


# ========== 工具函数 ==========

def _require_corp_id(current_user: dict) -> str:
    """从已认证用户取出 corp_id，缺失则拒绝（不静默兜底）。"""
    corp_id = current_user.get("corp_id")
    if not corp_id:
        raise HTTPException(status_code=400, detail="令牌缺少企业信息，请重新登录")
    return corp_id


def _get_group_or_404(db: Session, corp_id: str, chat_id: str) -> WxGroup:
    group = db.query(WxGroup).filter(
        WxGroup.corp_id == corp_id, WxGroup.chat_id == chat_id,
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    return group


def _format_group(group: WxGroup, detail: bool = False) -> dict:
    type_names = {1: "客户群", 2: "内部群", 3: "项目群", 4: "渠道群"}
    result = {
        "chat_id": group.chat_id, "group_name": group.group_name,
        "group_type": group.group_type,
        "group_type_name": type_names.get(group.group_type, "其他"),
        "owner_userid": group.owner_userid, "owner_name": group.owner_name,
        "member_count": group.member_count,
        "activity_level": group.activity_level,
        "activity_level_name": LEVEL_NAMES.get(group.activity_level, ""),
        "activity_level_color": LEVEL_COLORS.get(group.activity_level, "#909399"),
        "activity_score": float(group.activity_score),
        "is_key_group": group.is_key_group, "is_problem_group": group.is_problem_group,
        "is_monitored": group.is_monitored, "tags": group.tags,
        "client_kind": group.client_kind, "client_kind_conf": group.client_kind_conf,
        "last_msg_time": group.last_msg_time.isoformat() if group.last_msg_time else None,
        "last_synced_at": group.last_synced_at.isoformat() if group.last_synced_at else None,
        "create_time": group.create_time.isoformat() if group.create_time else None,
    }
    if detail:
        result["notice"] = group.notice
    return result
