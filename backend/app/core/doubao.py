"""
豆包大模型（火山方舟 Ark，OpenAI 兼容协议）共享调用封装。
未配置 DOUBAO_API_KEY 时 is_available() 返回 False，调用方应走规则兜底。
"""
import json
import asyncio
from typing import List, Dict, Any

import httpx

from app.core.config import settings


def is_available() -> bool:
    return bool(settings.DOUBAO_API_KEY)


async def chat(messages: List[Dict[str, str]], temperature: float = 0.3,
               timeout: int = 30, max_retries: int = 2) -> str:
    """调用大模型 chat/completions（OpenAI 兼容），返回文本。
    免费版限频(429/1302)时自动退避重试。"""
    payload = {
        "model": settings.DOUBAO_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.DOUBAO_API_KEY}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(max_retries + 1):
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.DOUBAO_BASE_URL}/chat/completions",
                json=payload, headers=headers,
            )
            data = resp.json()
        # 限频：等待后重试
        err = data.get("error") if isinstance(data, dict) else None
        rate_limited = resp.status_code == 429 or (
            isinstance(err, dict) and str(err.get("code")) in ("1302", "429"))
        if rate_limited and attempt < max_retries:
            await asyncio.sleep(2 + attempt * 2)
            continue
        if err:
            raise RuntimeError(f"LLM错误: {err}")
        resp.raise_for_status()
        return data["choices"][0]["message"]["content"].strip()
    raise RuntimeError(f"LLM限频重试失败: {last_err}")


def parse_json_array(text: str) -> List[Any]:
    """容错解析模型返回的 JSON 数组（去掉 ```json 包裹、截取方括号）。"""
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            try:
                v = json.loads(text[start:end + 1])
                return v if isinstance(v, list) else []
            except json.JSONDecodeError:
                pass
    return []


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
