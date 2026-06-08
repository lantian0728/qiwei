"""会话存档子进程 worker（纯 SDK，绝不接触数据库）。

实测：原生 .so 与 SQLite 的 C 库在同进程会触发 free(): invalid pointer 崩溃。
而只加载 SDK（不加载 SQLAlchemy/SQLite）的纯扫描进程稳定。
因此 worker 只做 SDK 取数+解密，结果用 JSON 经 stdout 交给主进程入库。

用法: python -m app.services.archive_worker <ff|sync> <start_seq> [max_batches] [limit]
输出最后一行: RESULT {json}
  ff   -> {end_seq, scanned, reached_end}
  sync -> {end_seq, scanned, reached_end, messages:[{seq,msgid,roomid,from,msgtype,content,msgtime}]}
崩溃则进程非 0 退出（无 RESULT 行），由主进程 run_worker 续传/重试/跳段。
"""
import sys
import json

from app.core import wework_finance as wf
from app.core.config import settings


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "sync"
    start_seq = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    max_batches = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 1000

    target_ver = settings.WX_ARCHIVE_PUBLIC_KEY_VER
    sdk = wf.WeWorkFinanceSDK()
    seq = start_seq
    scanned = 0
    reached_end = False
    messages = []
    try:
        for _ in range(max_batches):
            recs = sdk.get_chat_data(seq, limit)
            if not recs:
                reached_end = True
                break
            for rec in recs:
                seq = max(seq, int(rec.get("seq", seq)))
                if mode == "sync":
                    # 版本不符(旧密钥)直接跳过，绝不解密，避免 C 崩
                    if target_ver and int(rec.get("publickey_ver", 0)) != target_ver:
                        continue
                    try:
                        m = sdk.decrypt_message(
                            rec["encrypt_random_key"], rec["encrypt_chat_msg"])
                    except Exception:
                        continue
                    mtype = m.get("msgtype", "") or "text"
                    content = (m.get("text") or {}).get("content", "") if mtype == "text" else ""
                    messages.append({
                        "seq": rec.get("seq"),
                        "msgid": m.get("msgid", ""),
                        "roomid": m.get("roomid", ""),
                        "from": m.get("from", ""),
                        "msgtype": mtype,
                        "content": content,
                        "msgtime": m.get("msgtime", 0),
                    })
            scanned += len(recs)
            if len(recs) < limit:
                reached_end = True
                break
    finally:
        sdk.close()

    out = {"end_seq": seq, "scanned": scanned, "reached_end": reached_end}
    if mode == "sync":
        out["messages"] = messages
    sys.stdout.write("RESULT " + json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
