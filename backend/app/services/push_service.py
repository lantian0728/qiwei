"""
轨迹自动推送：巡检已配机器人的群对应客户的运单，状态变化时推送到群。
首次见到的运单只记录基线、不推送（避免把历史全刷一遍）。
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.core import nextsls, groupbot
from app.core.nextsls import NextSLSClient, STATUS_NAMES
from app.models.models import WxGroupCustomer, WxShipmentStatus


def _format(s: Dict[str, Any]) -> str:
    sid = s.get("client_reference") or s.get("shipment_id")
    status_name = STATUS_NAMES.get(s.get("status", ""), s.get("status", ""))
    svc = s.get("service_name", "")
    line = f"📦 运单 {sid} 状态更新：{status_name}"
    if svc:
        line += f"\n服务：{svc}"
    tn = s.get("outer_carrier_tracking_number")
    if tn:
        line += f"\n跟踪号：{tn}"
    return line


async def run_tracking_push(db: Session, corp_id: str) -> Dict[str, Any]:
    """对所有配置了 webhook 的群执行一次轨迹变化巡检与推送。"""
    if not nextsls.is_available():
        return {"available": False}

    targets = db.query(WxGroupCustomer).filter(
        WxGroupCustomer.corp_id == corp_id,
        WxGroupCustomer.webhook_url != "",
        WxGroupCustomer.user_number != "",
    ).all()
    if not targets:
        return {"available": True, "targets": 0, "pushed": 0}

    client = NextSLSClient()
    pushed = checked = 0

    for t in targets:
        try:
            shipments = await client.shipment_list(user_number=t.user_number, page=1, page_size=20)
        except Exception:
            continue
        for s in shipments:
            sid = s.get("shipment_id")
            if not sid:
                continue
            checked += 1
            status = s.get("status", "")
            row = db.query(WxShipmentStatus).filter(
                WxShipmentStatus.corp_id == corp_id,
                WxShipmentStatus.shipment_id == sid,
            ).first()
            if row is None:
                # 首次见到：记基线，不推送
                db.add(WxShipmentStatus(
                    corp_id=corp_id, chat_id=t.chat_id, shipment_id=sid,
                    client_reference=s.get("client_reference", ""), status=status,
                ))
                continue
            if row.status != status:
                row.status = status
                ok = await groupbot.send_text(t.webhook_url, _format(s))
                if ok:
                    row.last_pushed_at = datetime.now()
                    pushed += 1
        db.commit()

    return {"available": True, "targets": len(targets), "checked": checked, "pushed": pushed}
