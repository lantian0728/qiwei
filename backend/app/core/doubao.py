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
               timeout: int = 30, max_retries: int = 2, model: str = None) -> str:
    """调用大模型 chat/completions（OpenAI 兼容），返回文本。
    model 可覆盖默认模型(如分类用更高级模型)。免费版限频(429/1302)时自动退避重试。"""
    headers = {
        "Authorization": f"Bearer {settings.DOUBAO_API_KEY}",
        "Content-Type": "application/json",
    }
    cur_model = model or settings.DOUBAO_MODEL
    for attempt in range(max_retries + 1):
        payload = {"model": cur_model, "messages": messages, "temperature": temperature}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.DOUBAO_BASE_URL}/chat/completions",
                json=payload, headers=headers,
            )
            data = resp.json()
        err = data.get("error") if isinstance(data, dict) else None
        if err:
            code = str(err.get("code")) if isinstance(err, dict) else ""
            # 指定的高级模型不可用(余额不足/无权限/不存在)→ 自动回退到免费默认模型
            if cur_model != settings.DOUBAO_MODEL:
                cur_model = settings.DOUBAO_MODEL
                continue
            # 限频：退避重试
            if (resp.status_code == 429 or code in ("1302", "429")) and attempt < max_retries:
                await asyncio.sleep(2 + attempt * 2)
                continue
            raise RuntimeError(f"LLM错误: {err}")
        resp.raise_for_status()
        return data["choices"][0]["message"]["content"].strip()
    raise RuntimeError("LLM 重试失败")


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
