"""会话存档子进程 worker。

原生 SDK(libWeWorkFinanceSdk_C.so) 在本环境存在偶发堆损坏(free(): invalid pointer)，
是 C 层崩溃，Python 的 try 拦不住。对策：把 SDK 调用隔离到独立子进程，
崩溃只会让子进程非 0 退出，由主进程 run_worker 从已落库的游标续传重试。

用法: python -m app.services.archive_worker [ff|sync]
  ff   - 快速跳过历史，游标顶到最新(不解密)
  sync - 拉取+解密+入库
结果以最后一行 "RESULT {json}" 输出。
"""
import sys
import json

from app.core.database import SessionLocal
from app.services.chat_archive_service import ChatArchiveService


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "sync"
    db = SessionLocal()
    try:
        svc = ChatArchiveService(db)
        r = svc.fast_forward() if mode == "ff" else svc.sync()
    finally:
        db.close()
    sys.stdout.write("RESULT " + json.dumps(r, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
