"""
企微群会话分析系统 - 后端入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import models  # noqa: F401  确保模型被注册
from app.api import auth, groups, admin, alerts, staff, dashboard, ai, churn, tracking, archive


def _auto_migrate():
    """轻量自动迁移：create_all 只建新表、不给老表补列。
    这里对比模型与实际表结构，为老表 ALTER ADD 缺失的列（SQLite/MySQL 通用）。"""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                try:
                    coltype = col.type.compile(engine.dialect)
                    conn.execute(text(
                        f'ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}'
                    ))
                    print(f"[migrate] 已补列 {table.name}.{col.name}")
                except Exception as e:
                    print(f"[migrate] 跳过 {table.name}.{col.name}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建表 + 自动补列
    Base.metadata.create_all(bind=engine)
    try:
        _auto_migrate()
    except Exception as e:
        print(f"[migrate] 自动迁移失败: {e}")

    # 真实企业：配了 CorpID + Secret 就自动写入企业配置，「快速登录」后即可同步真实群
    if settings.WX_CORP_ID and settings.WX_CORP_SECRET:
        from app.models.models import WxCorpConfig
        db = SessionLocal()
        try:
            cfg = db.query(WxCorpConfig).filter(
                WxCorpConfig.corp_id == settings.WX_CORP_ID
            ).first()
            if not cfg:
                cfg = WxCorpConfig(corp_id=settings.WX_CORP_ID)
                db.add(cfg)
            cfg.agent_id = settings.WX_AGENT_ID or cfg.agent_id
            cfg.corp_secret = settings.WX_CORP_SECRET
            cfg.is_active = True
            db.commit()
        finally:
            db.close()

    # 演示模式：首次启动自动生成演示数据
    if settings.DEMO_MODE:
        from app.services.sync_service import MockDataService
        from app.services.ai_report_service import AIReportService
        from datetime import date
        db = SessionLocal()
        try:
            result = MockDataService(db, "demo_corp").generate_demo_data()
            # 首次生成演示数据后，顺带产出今日 AI 日报（规则版，配了豆包则为 AI 版）
            if not result.get("skipped"):
                await AIReportService(db).generate_all("demo_corp", date.today())
                from app.services.churn_service import ChurnService
                ChurnService(db).generate_alerts("demo_corp")
        finally:
            db.close()

    # 启动后台调度器：全量AI分析 + 轨迹巡检推送（全自动）
    try:
        from app.core.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"[scheduler] 启动失败: {e}")

    yield


app = FastAPI(
    title="企微群会话分析系统",
    description="企业微信群数据监测 · 活跃度分析 · 智能运营管理（只读监测）",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 所有业务路由统一挂在 /api 下
app.include_router(auth.router, prefix="/api")
app.include_router(groups.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(staff.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(churn.router, prefix="/api")
app.include_router(tracking.router, prefix="/api")
app.include_router(archive.router, prefix="/api")


@app.get("/api/health", tags=["系统"], summary="健康检查")
async def health():
    return {"status": "ok", "demo_mode": settings.DEMO_MODE}
