"""
企业微信群机器人推送（webhook）
群里手动添加机器人后，复制其 webhook 地址；本模块向该地址发文本消息。
这是企微唯一能"程序全自动、静默推送到指定群"的方式。
"""
import httpx


async def send_text(webhook_url: str, content: str) -> bool:
    if not webhook_url:
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={
            "msgtype": "text",
            "text": {"content": content},
        })
        data = resp.json()
    return data.get("errcode", -1) == 0
