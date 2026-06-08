"""
豆包大模型（火山方舟 Ark，OpenAI 兼容协议）共享调用封装。
未配置 DOUBAO_API_KEY 时 is_available() 返回 False，调用方应走规则兜底。
"""
import json
from typing import List, Dict, Any

import httpx

from app.core.config import settings


def is_available() -> bool:
    return bool(settings.DOUBAO_API_KEY)


async def chat(messages: List[Dict[str, str]], temperature: float = 0.3, timeout: int = 30) -> str:
    """调用 Ark chat/completions，返回模型文本。"""
    payload = {
        "model": settings.DOUBAO_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.DOUBAO_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.DOUBAO_BASE_URL}/chat/completions",
            json=payload, headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def parse_json(text: str) -> Dict[str, Any]:
    """容错解析模型返回的 JSON（去掉 ```json 包裹、截取花括号）。"""
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}
