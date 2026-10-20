"""配置与实例管理。"""
import json
import os
import re
import shutil
import threading
import time
import uuid

from .fsutil import write_json

DEFAULT_CONFIG = {
    "game_root": "",
    "java_path": "",
    "memory_mb": 4096,
    "download_source": "auto",
    "download_dir": "",
    "update_url": "",
    "update_auto": True,
    "player_name": "Steve",
    "width": 960,
    "height": 540,
    "close_on_launch": False,
    "home_background": "forest",
    "background_image": "",
    "music_path": "",
    "music_volume": 55,
    "music_autoplay": False,
    "window_alpha": 1.0,
    "show_home_log": True,
    "minimize_on_launch": False,
    "accent": "green",
}


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, base_dir):
        self.base_dir = os.path.abspath(base_dir)
        self.path = os.path.join(self.base_dir, "config.json")
        self._lock = threading.RLock()
        self.data = dict(DEFAULT_CONFIG)
        self._load()
        if not self.data.get("game_root"):
            self.data["game_root"] = os.path.join(self.base_dir, "game")
        root = os.path.expanduser(str(self.data["game_root"]))
        if not os.path.isabs(root):
            root = os.path.join(self.base_dir, root)
        self.data["game_root"] = os.path.abspath(root)
        self._ensure_tree()
        self._repair_instances()
        self._migrate_instance_names()
        self.save()

    def _migrate_instance_names(self):
        root = os.path.join(self.game_root, "instances")
        if not os.path.isdir(root):
            return
        for folder in list(os.listdir(root)):
            if not folder.startswith("inst-"):
                continue
            old_dir = os.path.join(root, folder)
            meta = os.path.join(old_dir, "instance.json")
            if not os.path.isfile(meta):
                continue
            try:
                with open(meta, "r", encoding="utf-8") as handle:
                    inst = json.load(handle)
            except Exception:
                continue
            name = str(inst.get("name") or folder).strip()
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")[:48] or folder
            target = safe
            suffix = 2
            while os.path.exists(os.path.join(root, target)) and os.path.abspath(os.path.join(root, target)) != os.path.abspath(old_dir):
                target = "%s-%d" % (safe, suffix)
                suffix += 1
            if target == folder:
                continue
            new_dir = os.path.join(root, target)
            try:
                os.rename(old_dir, new_dir)
                inst["id"] = target
                write_json(os.path.join(new_dir, "instance.json"), inst)
            except Exception:
                continue

    def _repair_instances(self):
        """进程被杀后可能留下 installing=true，启动时清掉。"""
        root = os.path.join(self.game_root, "instances")
        if not os.path.isdir(root):
            return
        for name in os.listdir(root):
            meta = os.path.join(root, name, "instance.json")
            if not os.path.isfile(meta):
                continue
            try:
                with open(meta, "r", encoding="utf-8") as f:
                    inst = json.load(f)
                if not inst.get("installing"):
                    continue
                inst["installing"] = False
                write_json(meta, inst)
            except Exception:
                continue

    # ---------- 基础 ----------
    def _load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for key, value in loaded.items():
                        if key in DEFAULT_CONFIG:
                            self.data[key] = value
            except Exception:
                pass
        for key, value in DEFAULT_CONFIG.items():
            self.data.setdefault(key, value)

    def save(self):
        with self._lock:
            data = dict(self.data)
            default_root = os.path.join(self.base_dir, "game")
            if os.path.abspath(data.get("game_root", "")) == os.path.abspath(default_root):
                data["game_root"] = "game"
            write_json(self.path, data)

    def update(self, **kwargs):
        with self._lock:
            if "game_root" in kwargs and kwargs["game_root"]:
                root = os.path.abspath(os.path.expanduser(str(kwargs["game_root"]).strip()))
                self.data["game_root"] = root
            if "memory_mb" in kwargs:
                try:
                    self.data["memory_mb"] = max(512, min(65536, int(kwargs["memory_mb"])))
                except (TypeError, ValueError):
                    pass
            for key in ("java_path", "download_source", "player_name",
                        "download_dir", "update_url"):
                if key in kwargs:
                    self.data[key] = str(kwargs[key] or "").strip()
            if "player_name" in kwargs and not self.data["player_name"]:
                self.data["player_name"] = "Steve"
            if "download_source" in kwargs and self.data["download_source"] not in ("auto", "official", "mirror"):
                self.data["download_source"] = "auto"
            if "width" in kwargs:
                try:
                    self.data["width"] = max(320, min(7680, int(kwargs["width"])))
                except (TypeError, ValueError):
                    pass
            if "height" in kwargs:
                try:
                    self.data["height"] = max(240, min(4320, int(kwargs["height"])))
                except (TypeError, ValueError):
                    pass
            for key in ("home_background", "background_image", "music_path"):
                if key in kwargs:
                    self.data[key] = str(kwargs[key] or "").strip()
            if "home_background" in kwargs and self.data["home_background"] not in (
                    "forest", "dawn", "night", "minimal", "custom"):
                self.data["home_background"] = "forest"
            if "accent" in kwargs:
                self.data["accent"] = str(kwargs["accent"] or "green")
                if self.data["accent"] not in ("green", "blue", "purple"):
                    self.data["accent"] = "green"
            if "music_volume" in kwargs:
                try:
                    self.data["music_volume"] = max(0, min(100, int(kwargs["music_volume"])))
                except (TypeError, ValueError):
                    pass
            if "window_alpha" in kwargs:
                try:
                    self.data["window_alpha"] = max(0.75, min(1.0, float(kwargs["window_alpha"])))
                except (TypeError, ValueError):
                    pass
            for key in ("music_autoplay", "show_home_log", "minimize_on_launch",
                        "update_auto"):
                if key in kwargs:
                    self.data[key] = bool(kwargs[key])
            self._ensure_tree()
            self.save()
        return self.public()

    def public(self):
        with self._lock:
            data = dict(self.data)
        data["memory_mb"] = int(data.get("memory_mb") or 4096)
        data["music_volume"] = int(data.get("music_volume") or 0)
        data["window_alpha"] = float(data.get("window_alpha") or 1.0)
        data["game_root"] = self.data["game_root"]
        return data

    @property
    def game_root(self):
        return self.data["game_root"]

    @property
    def source(self):
        return self.data.get("download_source") or "auto"

    @property
    def download_root(self):
        raw = str(self.data.get("download_dir") or "").strip()
        if raw:
            return os.path.abspath(os.path.expanduser(raw))
        return os.path.join(self.base_dir, "downloads")

    @property
    def player_name(self):
        name = str(self.data.get("player_name") or "Steve").strip()
        return name[:16] or "Steve"

    def path_in(self, *parts):
        return os.path.join(self.game_root, *parts)

    def _ensure_tree(self):
        for rel in ("instances", "versions", "libraries", "assets", "logs", "meta"):
            try:
                os.makedirs(os.path.join(self.game_root, rel), exist_ok=True)
            except OSError:
                pass

    # ---------- 实例 ----------
    def instance_dir(self, iid):
        iid = str(iid or "")
        if (not iid or iid in (".", "..") or len(iid) > 80
                or any(ch in iid for ch in ("/", "\\", ":", "*", "?", '"', "<", ">", "|"))):
            raise ConfigError("实例 ID 不合法")
        return os.path.join(self.game_root, "instances", iid)

    def list_instances(self):
        result = []
        root = os.path.join(self.game_root, "instances")
        if not os.path.isdir(root):
            return result
        for name in os.listdir(root):
            meta = os.path.join(root, name, "instance.json")
            if not os.path.isfile(meta):
                continue
            try:
                with open(meta, "r", encoding="utf-8") as f:
                    inst = json.load(f)
            except Exception:
                continue
            if not isinstance(inst, dict):
                continue
            inst.setdefault("id", name)
            inst["dir"] = os.path.join(root, name)
            result.append(inst)
        result.sort(key=lambda i: i.get("last_played") or i.get("created") or 0, reverse=True)
        return result

    def get_instance(self, iid):
        path = self.instance_dir(iid)
        meta = os.path.join(path, "instance.json")
        if not os.path.isfile(meta):
            raise ConfigError("实例不存在")
        with open(meta, "r", encoding="utf-8") as f:
            inst = json.load(f)
        inst.setdefault("id", iid)
        inst["dir"] = path
        return inst

    def create_instance(self, name, mc_version, version_id=None, loader=None, icon=None, summary=None, installing=False):
        name = (name or "").strip() or mc_version
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")[:48] or mc_version
        iid = safe
        suffix = 2
        while os.path.exists(self.instance_dir(iid)):
            iid = "%s-%d" % (safe, suffix)
            suffix += 1
        path = self.instance_dir(iid)
        for sub in ("mods", "shaderpacks", "resourcepacks", "saves", "logs"):
            os.makedirs(os.path.join(path, sub), exist_ok=True)
        inst = {
            "id": iid,
            "name": name[:48],
            "mc_version": mc_version,
            "version_id": version_id or mc_version,
            "loader": loader or None,
            "icon": icon,
            "summary": summary,
            "created": int(time.time()),
            "last_played": 0,
            "installing": bool(installing),
        }
        self._write_instance(inst)
        return dict(inst, dir=path)

    def update_instance(self, iid, **fields):
        inst = self.get_instance(iid)
        for key in ("name", "version_id", "loader", "icon", "summary", "last_played",
                    "mc_version", "installing", "java_path", "memory_mb"):
            if key in fields:
                inst[key] = fields[key]
        self._write_instance(inst)
        return inst

    def _write_instance(self, inst):
        inst = dict(inst)
        inst.pop("dir", None)
        path = self.instance_dir(inst["id"])
        os.makedirs(path, exist_ok=True)
        write_json(os.path.join(path, "instance.json"), inst)

    def delete_instance(self, iid):
        path = self.instance_dir(iid)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
