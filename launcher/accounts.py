"""账号管理：离线账号 + 微软正版账号。"""
import hashlib
import os
import threading
import time

from . import dpapi, microsoft
from .fsutil import write_json


def offline_uuid(name):
    digest = hashlib.md5(("OfflinePlayer:" + str(name)).encode("utf-8")).hexdigest()
    return "-".join((digest[0:8], digest[8:12], digest[12:16], digest[16:20], digest[20:32]))


class AccountError(Exception):
    pass


class AccountManager:
    def __init__(self, base_dir, config):
        self.base_dir = base_dir
        self.config = config
        self.path = os.path.join(base_dir, "accounts.json")
        self.lock = threading.RLock()
        self.data = self._load()
        offline_name = str(self.data.get("offline_name") or self.config.player_name or "Steve").strip()
        if not offline_name:
            offline_name = "Steve"
        self.data["offline_name"] = offline_name[:16]
        self.data.setdefault("active", "offline")
        self.data.setdefault("accounts", [])
        self._save()

    # ---------- 存储 ----------
    def _load(self):
        if os.path.isfile(self.path):
            try:
                import json
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {"active": "offline", "offline_name": self.config.player_name, "accounts": []}

    def _save(self):
        with self.lock:
            write_json(self.path, self.data)

    def _store_account(self, account):
        stored = dict(account)
        stored["key"] = "msa:" + str(account.get("uuid"))
        stored["access_token"] = dpapi.protect(account.get("access_token", ""))
        stored["refresh_token"] = dpapi.protect(account.get("refresh_token", ""))
        stored.pop("ms_refresh_token", None)
        stored["type"] = "msa"
        return stored

    def _open_account(self, stored):
        account = dict(stored)
        account["access_token"] = dpapi.unprotect(stored.get("access_token", ""))
        account["refresh_token"] = dpapi.unprotect(stored.get("refresh_token", ""))
        return account

    # ---------- 查询/切换 ----------
    def list_accounts(self):
        with self.lock:
            items = [{
                "key": "offline",
                "type": "offline",
                "name": self.data.get("offline_name") or "Steve",
                "uuid": offline_uuid(self.data.get("offline_name") or "Steve"),
                "detail": "离线账号",
            }]
            for stored in self.data.get("accounts") or []:
                items.append({
                    "key": stored.get("key") or ("msa:" + stored.get("uuid", "")),
                    "type": "msa",
                    "name": stored.get("name") or "正版账号",
                    "uuid": stored.get("uuid") or "",
                    "detail": "微软正版",
                })
            return items

    def active_key(self):
        with self.lock:
            key = self.data.get("active") or "offline"
            if key != "offline" and not any(item.get("key") == key for item in self.data.get("accounts") or []):
                key = "offline"
                self.data["active"] = key
            return key

    def active_info(self):
        key = self.active_key()
        for item in self.list_accounts():
            if item["key"] == key:
                return item
        return self.list_accounts()[0]

    def set_active(self, key):
        keys = {item["key"] for item in self.list_accounts()}
        if key not in keys:
            raise AccountError("账号不存在")
        with self.lock:
            self.data["active"] = key
            self._save()

    def offline_name(self):
        return self.data.get("offline_name") or "Steve"

    def set_offline_name(self, name):
        name = (name or "Steve").strip()[:16] or "Steve"
        with self.lock:
            self.data["offline_name"] = name
            self._save()
        self.config.update(player_name=name)

    def add_msa(self, account):
        stored = self._store_account(account)
        with self.lock:
            accounts = self.data.setdefault("accounts", [])
            accounts[:] = [item for item in accounts if item.get("uuid") != stored.get("uuid")]
            accounts.append(stored)
            self.data["active"] = stored["key"]
            self._save()
        return stored["key"]

    def remove(self, key):
        if key == "offline":
            raise AccountError("离线账号不能删除")
        with self.lock:
            self.data["accounts"] = [item for item in self.data.get("accounts") or []
                                     if item.get("key") != key]
            if self.data.get("active") == key:
                self.data["active"] = "offline"
            self._save()

    # ---------- 启动账号 ----------
    def launch_account(self, task=None):
        key = self.active_key()
        if key == "offline":
            name = self.offline_name()
            return {
                "type": "offline",
                "name": name,
                "uuid": offline_uuid(name),
                "access_token": "0",
                "user_type": "legacy",
                "xuid": "",
                "client_id": "",
            }
        with self.lock:
            stored = next((item for item in self.data.get("accounts") or []
                           if item.get("key") == key), None)
        if not stored:
            raise AccountError("正版账号不存在，请重新登录")
        account = self._open_account(stored)
        if int(account.get("expires_at") or 0) > int(time.time()) + 90:
            return {
                "type": "msa",
                "name": account.get("name"),
                "uuid": account.get("uuid"),
                "access_token": account.get("access_token"),
                "user_type": "msa",
                "xuid": account.get("xuid") or "",
                "client_id": "",
            }
        if task is not None:
            try:
                task.set_stage("刷新微软令牌")
                task.log("正版令牌已过期，正在刷新…")
            except Exception:
                pass
        refreshed = microsoft.refresh_account(account)
        self.add_msa(refreshed)
        return {
            "type": "msa",
            "name": refreshed.get("name"),
            "uuid": refreshed.get("uuid"),
            "access_token": refreshed.get("access_token"),
            "user_type": "msa",
            "xuid": refreshed.get("xuid") or "",
            "client_id": "",
        }
