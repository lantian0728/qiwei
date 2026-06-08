"""
企业微信「会话内容存档」原生 SDK 封装（ctypes）

⚠️ 仅在 Linux 服务器、放置了 libWeWorkFinanceSdk_C.so 后可用。
本地 Windows 不加载，is_available() 返回 False。

流程（官方）：
  NewSdk → Init(corpid, secret) → GetChatData(seq, limit) 取一批加密记录
  每条：RSA私钥解密 encrypt_random_key 得 AES key → DecryptData(key, encrypt_chat_msg) 得明文JSON
官方文档：https://developer.work.weixin.qq.com/document/path/91774
"""
import json
import base64
from typing import List, Dict, Any, Optional

from app.core.config import settings


def is_available() -> bool:
    return bool(settings.WX_ARCHIVE_SDK_PATH and settings.WX_ARCHIVE_SECRET
               and settings.WX_ARCHIVE_PRIVATE_KEY_PATH)


def _load_private_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    with open(settings.WX_ARCHIVE_PRIVATE_KEY_PATH, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _rsa_decrypt_key(private_key, encrypt_random_key: str) -> bytes:
    from cryptography.hazmat.primitives.asymmetric import padding
    cipher = base64.b64decode(encrypt_random_key)
    return private_key.decrypt(cipher, padding.PKCS1v15())


class WeWorkFinanceSDK:
    """对 libWeWorkFinanceSdk_C.so 的最小封装。"""

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self.lib = ctypes.cdll.LoadLibrary(settings.WX_ARCHIVE_SDK_PATH)
        self._setup_signatures()
        self.sdk = self.lib.NewSdk()
        corpid = (settings.WX_ARCHIVE_CORPID or settings.WX_CORP_ID).encode()
        ret = self.lib.Init(self.sdk, corpid, settings.WX_ARCHIVE_SECRET.encode())
        if ret != 0:
            raise RuntimeError(f"会话存档 Init 失败, code={ret}")
        self.private_key = _load_private_key()

    def _setup_signatures(self):
        c = self.ctypes
        self.lib.NewSdk.restype = c.c_void_p
        self.lib.Init.argtypes = [c.c_void_p, c.c_char_p, c.c_char_p]
        self.lib.Init.restype = c.c_int
        self.lib.GetChatData.argtypes = [c.c_void_p, c.c_ulonglong, c.c_uint,
                                         c.c_char_p, c.c_char_p, c.c_int, c.c_void_p]
        self.lib.GetChatData.restype = c.c_int
        self.lib.DecryptData.argtypes = [c.c_char_p, c.c_char_p, c.c_void_p]
        self.lib.DecryptData.restype = c.c_int
        self.lib.NewSlice.restype = c.c_void_p
        self.lib.FreeSlice.argtypes = [c.c_void_p]
        self.lib.GetContentFromSlice.argtypes = [c.c_void_p]
        self.lib.GetContentFromSlice.restype = c.c_void_p  # 裸指针，配合 GetSliceLen 按长度读，勿当NUL结尾字符串
        self.lib.GetSliceLen.argtypes = [c.c_void_p]
        self.lib.GetSliceLen.restype = c.c_int
        self.lib.DestroySdk.argtypes = [c.c_void_p]

    def _read_slice(self, slice_ptr) -> bytes:
        """按 Slice 的 len 精确读取 buf，避免把非 NUL 结尾的缓冲当字符串越界读。"""
        n = self.lib.GetSliceLen(slice_ptr)
        ptr = self.lib.GetContentFromSlice(slice_ptr)
        if not ptr or n <= 0:
            return b""
        return self.ctypes.string_at(ptr, n)

    def get_chat_data(self, seq: int, limit: int = 100) -> List[Dict[str, Any]]:
        slice_ptr = self.lib.NewSlice()
        try:
            ret = self.lib.GetChatData(self.sdk, seq, limit, b"", b"", 5, slice_ptr)
            if ret != 0:
                raise RuntimeError(f"GetChatData 失败, code={ret}")
            content = self._read_slice(slice_ptr)
            data = json.loads(content.decode("utf-8"))
        finally:
            self.lib.FreeSlice(slice_ptr)
        return data.get("chatdata", []) or []

    def decrypt_message(self, encrypt_random_key: str, encrypt_chat_msg: str) -> Dict[str, Any]:
        aes_key = _rsa_decrypt_key(self.private_key, encrypt_random_key)
        slice_ptr = self.lib.NewSlice()
        try:
            ret = self.lib.DecryptData(aes_key, encrypt_chat_msg.encode(), slice_ptr)
            if ret != 0:
                raise RuntimeError(f"DecryptData 失败, code={ret}")
            content = self._read_slice(slice_ptr)
            return json.loads(content.decode("utf-8"))
        finally:
            self.lib.FreeSlice(slice_ptr)

    def close(self):
        try:
            self.lib.DestroySdk(self.sdk)
        except Exception:
            pass
