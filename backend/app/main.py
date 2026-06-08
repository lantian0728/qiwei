"""
企微群会话分析系统 - 后端入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import models  # noqa: F401  确保模型被注册
from app.api import auth, groups, admin, alerts, staff, dashboard, ai, churn, tracking


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建表
    Base.metadata.create_all(bind=engine)
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


@app.get("/api/health", tags=["系统"], summary="健康检查")
async def health():
    return {"status": "ok", "demo_mode": settings.DEMO_MODE}
