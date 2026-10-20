"""Windows DPAPI 加密，用于保存微软账号令牌。"""
import base64
import ctypes
import os
from ctypes import wintypes

if os.name == "nt":
    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _crypt32.CryptProtectData.argtypes = [
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def protect(text):
    text = str(text or "")
    if not text:
        return ""
    if os.name != "nt":
        return "plain:" + base64.b64encode(text.encode("utf-8")).decode("ascii")
    try:
        source = _blob(text.encode("utf-8"))
        target = _Blob()
        if not _crypt32.CryptProtectData(ctypes.byref(source), "SCL",
                                         None, None, None, 0x1, ctypes.byref(target)):
            raise OSError("CryptProtectData failed")
        try:
            raw = ctypes.string_at(target.pbData, target.cbData)
        finally:
            _kernel32.LocalFree(target.pbData)
        return "dpapi:" + base64.b64encode(raw).decode("ascii")
    except Exception:
        return "plain:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def unprotect(value):
    value = str(value or "")
    if not value:
        return ""
    if value.startswith("plain:"):
        try:
            return base64.b64decode(value[6:]).decode("utf-8")
        except Exception:
            return ""
    if value.startswith("dpapi:") and os.name == "nt":
        try:
            raw = base64.b64decode(value[6:])
            source = _blob(raw)
            target = _Blob()
            if not _crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None,
                                               None, 0x1, ctypes.byref(target)):
                return ""
            try:
                return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
            finally:
                _kernel32.LocalFree(target.pbData)
        except Exception:
            return ""
    return ""
