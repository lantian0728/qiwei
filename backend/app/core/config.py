"""
应用配置：从环境变量 / .env 读取
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库
    DATABASE_URL: str = "sqlite:///./wxwork_analytics.db"

    # JWT
    SECRET_KEY: str = "change-me-to-a-long-random-secret-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # 企业微信
    WX_CORP_ID: str = ""

    # CORS（逗号分隔）
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 演示模式
    DEMO_MODE: bool = True

    # 豆包大模型（火山方舟 Ark，OpenAI 兼容协议）—— 用于消息情绪分析
    DOUBAO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    DOUBAO_MODEL: str = "doubao-pro-32k"  # 填你在方舟创建的推理接入点ID或模型名

    # 新智慧 NextSLS TMS MPAPI —— 用于查件/运单/客户
    NEXTSLS_TOKEN: str = ""
    NEXTSLS_BASE_URL: str = "https://zjyxgj.nextsls.com/mpapi/v5"

    # 企业微信「会话内容存档」(仅服务器Linux + 原生SDK可用)
    WX_ARCHIVE_CORPID: str = ""          # 留空则用 WX_CORP_ID
    WX_ARCHIVE_SECRET: str = ""          # 会话存档专用 Secret
    WX_ARCHIVE_SDK_PATH: str = ""        # libWeWorkFinanceSdk_C.so 绝对路径
    WX_ARCHIVE_PRIVATE_KEY_PATH: str = ""  # RSA 私钥 PEM 文件路径(公钥已传企微后台)

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
