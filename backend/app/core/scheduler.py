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
    """会话存档增量同步：子进程隔离拉新消息→解密→入库。游标续传，每次只拉新增。"""
    from app.core import wework_finance
    if not wework_finance.is_available():
        return
    from app.services.chat_archive_service import run_worker
    try:
        r = run_worker("sync")
        if r.get("stored"):
            print(f"[archive_sync] 入库 {r['stored']} 条，seq={r.get('seq')}")
    except Exception as e:
        print(f"[archive_sync] 失败: {e}")


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
    # 会话存档增量同步：每 10 分钟拉一次新消息
    scheduler.add_job(archive_sync_job, "interval", minutes=10,
                      id="archive_sync", replace_existing=True)
    # 启动后：先同步消息(60s)，再跑全量分析(180s)，保证分析基于最新消息
    scheduler.add_job(archive_sync_job, "date",
                      run_date=datetime.now() + timedelta(seconds=60),
                      id="archive_sync_startup", replace_existing=True)
    scheduler.add_job(auto_analysis_job, "date",
                      run_date=datetime.now() + timedelta(seconds=180),
                      id="auto_analysis_startup", replace_existing=True)
    scheduler.start()
