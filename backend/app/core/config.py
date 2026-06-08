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
    WX_AGENT_ID: str = ""
    WX_CORP_SECRET: str = ""   # 自建应用Secret(含客户联系权限),配置后自动接入真实企业

    # CORS（逗号分隔）
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 演示模式
    DEMO_MODE: bool = True

    # 大模型（OpenAI 兼容）—— 默认智谱 GLM，用于AI日报/情绪/客户匹配
    # 变量名沿用 DOUBAO_* 但实际指向所配的服务（现为智谱）
    DOUBAO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    DOUBAO_MODEL: str = "glm-4.7-flash"

    # 新智慧 NextSLS TMS MPAPI —— 用于查件/运单/客户
    NEXTSLS_TOKEN: str = ""
    NEXTSLS_BASE_URL: str = "https://zjyxgj.nextsls.com/mpapi/v5"

    # 企业微信「会话内容存档」(仅服务器Linux + 原生SDK可用)
    WX_ARCHIVE_CORPID: str = ""          # 留空则用 WX_CORP_ID
    WX_ARCHIVE_SECRET: str = ""          # 会话存档专用 Secret
    WX_ARCHIVE_SDK_PATH: str = ""        # libWeWorkFinanceSdk_C.so 绝对路径
    WX_ARCHIVE_PRIVATE_KEY_PATH: str = ""  # RSA 私钥 PEM 文件路径(公钥已传企微后台)
    WX_ARCHIVE_PUBLIC_KEY_VER: int = 0   # 只解此版本公钥加密的消息；0=不限(私钥不符会崩，务必设为后台贴的版本号)

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
