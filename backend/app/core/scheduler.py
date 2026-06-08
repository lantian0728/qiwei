"""
后台调度器（APScheduler）：让分析与推送全自动，无需手动点。
- 每天 08:30 全量 AI 分析（AI日报/风险/流失），各板块自动有结论
- 每 30 分钟轨迹巡检，状态变化自动推送到配了机器人的群
- 启动后 1 分钟先跑一次全量分析，免得等到第二天
"""
import asyncio
from datetime import datetime, timedelta, date

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _corp_ids(db):
    from app.models.models import WxCorpConfig
    ids = [c.corp_id for c in db.query(WxCorpConfig).filter(WxCorpConfig.is_active == True).all()]
    if settings.WX_CORP_ID and settings.WX_CORP_ID not in ids:
        ids.append(settings.WX_CORP_ID)
    return ids


def auto_analysis_job():
    """全量 AI 分析：AI日报 + 风险 + 流失预警。"""
    from app.services.ai_report_service import AIReportService
    from app.services.churn_service import ChurnService
    db = SessionLocal()
    try:
        for cid in _corp_ids(db):
            try:
                asyncio.run(AIReportService(db).generate_all(cid, date.today()))
                ChurnService(db).generate_alerts(cid)
            except Exception as e:
                print(f"[auto_analysis] {cid} 失败: {e}")
    finally:
        db.close()


def archive_sync_job():
    """会话存档增量同步 + 同步后自动重算派生数据（统计/活跃度/日报/流失全靠它）。"""
    from app.core import wework_finance
    if not wework_finance.is_available():
        return
    from app.services.chat_archive_service import run_worker
    try:
        r = run_worker("sync")
    except Exception as e:
        print(f"[archive_sync] 同步失败: {e}")
        return
    if not r.get("stored"):
        return
    corp = settings.WX_ARCHIVE_CORPID or settings.WX_CORP_ID
    today = date.today()
    db = SessionLocal()
    try:
        from app.services.activity_service import ActivityLevelService
        from app.services.churn_service import ChurnService
        ActivityLevelService(db).recompute_daily_stats(corp, today)  # 只算今日统计(轻,高频)
        ChurnService(db).generate_alerts(corp)                 # 流失预警(无AI)
        print(f"[archive_sync] 入库 {r['stored']} 条并已重算今日统计")
    except Exception as e:
        print(f"[archive_sync] 重算失败: {e}")
    finally:
        db.close()


def ai_report_job():
    """AI 日报：逐群过智谱(免费版1QPS)，单独低频跑，避免和高频同步撞限频。"""
    from app.core import wework_finance
    if not wework_finance.is_available():
        return
    corp = settings.WX_ARCHIVE_CORPID or settings.WX_CORP_ID
    db = SessionLocal()
    try:
        from app.services.activity_service import ActivityLevelService
        from app.services.ai_report_service import AIReportService
        ActivityLevelService(db).recompute_all(corp)   # 全量活跃度评分(变化慢,低频)
        asyncio.run(AIReportService(db).generate_active(corp, date.today()))
    except Exception as e:
        print(f"[ai_report] 失败: {e}")
    finally:
        db.close()


def tracking_watch_job():
    """轨迹变化巡检 + 群机器人推送。"""
    from app.services.push_service import run_tracking_push
    db = SessionLocal()
    try:
        for cid in _corp_ids(db):
            try:
                asyncio.run(run_tracking_push(db, cid))
            except Exception as e:
                print(f"[tracking_watch] {cid} 失败: {e}")
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(auto_analysis_job, "cron", hour=8, minute=30,
                      id="auto_analysis", replace_existing=True)
    scheduler.add_job(tracking_watch_job, "interval", minutes=30,
                      id="tracking_watch", replace_existing=True)
    # 会话存档同步+今日统计(无AI,轻)：每 1 分钟，消息/客服效能准实时
    scheduler.add_job(archive_sync_job, "interval", minutes=1,
                      id="archive_sync", replace_existing=True)
    # AI 日报(调智谱1QPS)：每 30 分钟，避免和高频同步撞限频
    scheduler.add_job(ai_report_job, "interval", minutes=30,
                      id="ai_report", replace_existing=True)
    # 启动后：先同步消息(60s)，再跑 AI 日报(200s)
    scheduler.add_job(archive_sync_job, "date",
                      run_date=datetime.now() + timedelta(seconds=60),
                      id="archive_sync_startup", replace_existing=True)
    scheduler.add_job(ai_report_job, "date",
                      run_date=datetime.now() + timedelta(seconds=200),
                      id="ai_report_startup", replace_existing=True)
    scheduler.start()
