"""文件写入小工具：兼容 Windows 沙箱下对已存在文件的替换限制。"""
import json
import os
import time


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    last = None
    for attempt in range(3):
        try:
            os.replace(tmp, path)
            return path
        except PermissionError as exc:
            last = exc
            time.sleep(0.15 * (attempt + 1))
    # 某些沙箱 ACL 禁止删除已有文件，退回直接覆盖
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return path
