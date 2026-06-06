"""
情绪分析服务 —— 接入豆包大模型（火山方舟 Ark，OpenAI 兼容协议）

用途：对群内客户消息做情绪倾向分析，识别负面情绪/投诉风险，辅助运营预警。
未配置 DOUBAO_API_KEY 时优雅降级（返回 available=False）。
"""
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import WxMessage

SENTIMENT_NAMES = {"positive": "正面", "neutral": "中性", "negative": "负面"}

SYSTEM_PROMPT = (
    "你是企业客户群的会话情绪分析助手。"
    "请根据给定的客户消息，判断整体情绪倾向，识别是否存在不满、投诉、催促或流失风险。"
    "只返回 JSON，不要任何额外文字。"
)

USER_PROMPT_TEMPLATE = (
    "以下是某客户群近期的客户发言（每行一条）：\n"
    "{messages}\n\n"
    "请输出 JSON，字段如下：\n"
    '{{"sentiment": "positive|neutral|negative", '
    '"score": 0到100的整数(越高越正面), '
    '"risk": "none|low|medium|high", '
    '"summary": "一句话总结群内情绪与需要关注的点", '
    '"keywords": ["最多5个负面/关注关键词"]}}'
)


class DoubaoSentimentService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def is_available() -> bool:
        return bool(settings.DOUBAO_API_KEY)

    async def analyze_group(self, corp_id: str, chat_id: str,
                            days: int = 7, max_messages: int = 60) -> Dict[str, Any]:
        if not self.is_available():
            return {
                "available": False,
                "message": "未配置豆包 API Key，情绪分析不可用。请在后台或 .env 配置 DOUBAO_API_KEY。",
            }

        since = datetime.now() - timedelta(days=days)
        msgs: List[WxMessage] = self.db.query(WxMessage).filter(
            WxMessage.corp_id == corp_id,
            WxMessage.chat_id == chat_id,
            WxMessage.sender_type == 2,  # 仅分析客户（外部联系人）发言
            WxMessage.send_time >= since,
        ).order_by(WxMessage.send_time.desc()).limit(max_messages).all()

        contents = [m.content for m in msgs if m.content and m.content.strip()]
        if not contents:
            return {"available": True, "analyzed": False,
                    "message": "近期没有可分析的客户文本消息"}

        result = await self._call_doubao(contents)
        result.update({"available": True, "analyzed": True,
                       "message_count": len(contents)})
        if "sentiment" in result:
            result["sentiment_name"] = SENTIMENT_NAMES.get(result["sentiment"], "")
        return result

    async def _call_doubao(self, contents: List[str]) -> Dict[str, Any]:
        user_prompt = USER_PROMPT_TEMPLATE.format(messages="\n".join(contents[:60]))
        payload = {
            "model": settings.DOUBAO_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {settings.DOUBAO_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.DOUBAO_BASE_URL}/chat/completions",
                json=payload, headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"].strip()
        return self._parse_json(text)

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        # 容错：去掉可能的 ```json 代码块包裹
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 兜底：尝试截取第一个 { 到最后一个 }
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            return {"sentiment": "neutral", "score": 50, "risk": "none",
                    "summary": "模型返回无法解析", "keywords": [], "raw": text}
