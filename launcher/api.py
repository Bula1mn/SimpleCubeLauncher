"""本地 HTTP API 与静态页面。"""
import json
import mimetypes
import os
import shutil
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .java import choose_java, detect_java
from .launch import LaunchError, Launcher, read_log, running_snapshot, stop_game
from .minecraft import Minecraft
from .modrinth import Modrinth
from .tasks import TaskManager

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class App:
    def __init__(self, config):
        self.config = config
        self.tasks = TaskManager()
        self.minecraft = Minecraft(config, self.tasks)
        self.modrinth = Modrinth(config, self.tasks, self.minecraft)
        self.launcher = Launcher(config, self.tasks, self.minecraft)
        self.started = time.time()

    def state(self):
        cfg = self.config
        configured = cfg.data.get("java_path") or ""
        javas = detect_java(cfg.game_root, configured)
        instances = cfg.list_instances()
        for instance in instances:
            required = 21
            try:
                required = self.minecraft.required_java(instance.get("version_id") or instance.get("mc_version"))
            except Exception:
                pass
            chosen = choose_java(javas, required, configured)
            instance["required_java"] = required
            instance["java"] = {"path": chosen["path"], "major": chosen["major"]} if chosen else None
            instance["java_ok"] = bool(chosen and chosen["major"] >= required)
        try:
            free_gb = round(shutil.disk_usage(cfg.game_root).free / (1024 ** 3), 1)
        except Exception:
            free_gb = None
        return {
            "config": cfg.public(),
            "instances": instances,
            "javas": javas,
            "running": running_snapshot(),
            "tasks": self.tasks.snapshot_all(),
            "version": __version__,
            "base_dir": cfg.base_dir,
            "game_root": cfg.game_root,
            "free_gb": free_gb,
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "SimpleCubeLauncher/" + __version__

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        pass

    # ---------- 基础 ----------
    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            raise ApiError("请求格式错误")
        return data if isinstance(data, dict) else {}

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self._api(method, path, query)
            elif method == "GET":
                self._static(path)
            else:
                self._json({"error": "not found"}, 404)
        except ApiError as exc:
            self._json({"error": str(exc)}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc) or exc.__class__.__name__}, 500)

    def _q(self, query, key, default=""):
        values = query.get(key)
        return values[0] if values else default

    # ---------- API ----------
    def _api(self, method, path, query):
        app = self.app
        cfg = app.config
        if method == "GET" and path == "/api/state":
            return self._json(app.state())
        if method == "GET" and path == "/api/versions":
            kind = self._q(query, "type", "release")
            refresh = self._q(query, "refresh", "0") == "1"
            versions = app.minecraft.manifest_versions(kind, refresh=refresh)
            installed = set(app.minecraft.installed_version_ids())
            items = []
            for item in versions:
                items.append({
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "releaseTime": item.get("releaseTime"),
                    "installed": item.get("id") in installed,
                })
            latest = app.minecraft.manifest().get("latest") or {}
            return self._json({"versions": items, "latest": latest})
        if method == "GET" and path == "/api/search":
            kind = self._q(query, "kind", "mod")
            result = app.modrinth.search(
                kind,
                self._q(query, "q", ""),
                self._q(query, "game_version", "") or None,
                self._q(query, "loader", "") or None,
                int(self._q(query, "limit", "20") or 20),
                int(self._q(query, "offset", "0") or 0),
            )
            return self._json(result)
        if method == "GET" and path == "/api/project":
            project_id = self._q(query, "id")
            if not project_id:
                raise ApiError("缺少项目 ID")
            project = app.modrinth.project(project_id)
            versions = app.modrinth.versions(
                project_id,
                self._q(query, "game_version", "") or None,
                self._q(query, "loader", "") or None,
            )
            return self._json({"project": project, "versions": versions[:120]})
        if method == "GET" and path == "/api/logs":
            instance_id = self._q(query, "instance_id")
            instance = cfg.get_instance(instance_id)
            return self._json({"log": read_log(instance["dir"], 12000)})
        if method == "GET" and path == "/api/tasks":
            return self._json({"tasks": app.tasks.snapshot_all()})

        if method == "POST" and path == "/api/config":
            body = self._body()
            return self._json({"config": cfg.update(**body)})
        if method == "POST" and path == "/api/instance/create":
            body = self._body()
            mc_version = str(body.get("mc_version") or "").strip()
            if not mc_version:
                raise ApiError("请选择 Minecraft 版本")
            loader_type = str(body.get("loader") or "vanilla").lower()
            loader_version = body.get("loader_version") or None
            name = str(body.get("name") or "").strip() or mc_version
            instance = cfg.create_instance(name, mc_version, version_id=mc_version, installing=True)
            task = app.tasks.start("install", "创建实例 " + name, lambda t: self._create_instance_job(instance, mc_version, loader_type, loader_version, t))
            return self._json({"instance": instance, "task": task.id})
        if method == "POST" and path == "/api/instance/delete":
            body = self._body()
            iid = str(body.get("id") or "")
            running = running_snapshot().get(iid) or {}
            if running.get("alive"):
                raise ApiError("游戏正在运行，无法删除")
            cfg.delete_instance(iid)
            return self._json({"ok": True})
        if method == "POST" and path == "/api/instance/update":
            body = self._body()
            iid = str(body.get("id") or "")
            fields = {}
            if body.get("name"):
                fields["name"] = str(body["name"]).strip()[:48]
            cfg.update_instance(iid, **fields)
            return self._json({"ok": True})
        if method == "POST" and path == "/api/install/vanilla":
            body = self._body()
            version_id = str(body.get("version_id") or "").strip()
            if not version_id:
                raise ApiError("缺少版本")
            existing = None
            for inst in cfg.list_instances():
                if inst.get("version_id") == version_id and not inst.get("loader"):
                    existing = inst
                    break
            if existing and app.minecraft.is_installed(version_id):
                return self._json({"instance": existing, "task": None, "existing": True})
            if existing:
                cfg.update_instance(existing["id"], installing=True)
                task = app.tasks.start(
                    "install", "安装 " + version_id,
                    lambda t: self._vanilla_job(existing, version_id, t, False),
                )
                return self._json({"instance": existing, "task": task.id})
            name = str(body.get("name") or version_id).strip()
            instance = cfg.create_instance(name, version_id, version_id=version_id, installing=True)
            task = app.tasks.start("install", "安装 " + version_id, lambda t: self._vanilla_job(instance, version_id, t, True))
            return self._json({"instance": instance, "task": task.id})
        if method == "POST" and path == "/api/install/mod":
            body = self._body()
            iid = str(body.get("instance_id") or "")
            pid = str(body.get("project_id") or "")
            if not iid or not pid:
                raise ApiError("缺少实例或项目")
            task = app.tasks.start("mod", "安装 Mod", lambda t: app.modrinth.install_content(pid, body.get("version_id"), iid, "mod", t))
            return self._json({"task": task.id})
        if method == "POST" and path == "/api/install/shader":
            body = self._body()
            iid = str(body.get("instance_id") or "")
            pid = str(body.get("project_id") or "")
            if not iid or not pid:
                raise ApiError("缺少实例或项目")
            task = app.tasks.start("shader", "安装光影", lambda t: app.modrinth.install_content(pid, body.get("version_id"), iid, "shader", t))
            return self._json({"task": task.id})
        if method == "POST" and path == "/api/install/modpack":
            body = self._body()
            pid = str(body.get("project_id") or "")
            if not pid:
                raise ApiError("缺少整合包项目")
            task = app.tasks.start("modpack", "安装整合包", lambda t: app.modrinth.install_modpack(pid, body.get("version_id"), body.get("name"), t))
            return self._json({"task": task.id})
        if method == "POST" and path == "/api/kill":
            body = self._body()
            iid = str(body.get("instance_id") or "")
            return self._json({"ok": stop_game(iid)})
        if method == "POST" and path == "/api/launch":
            body = self._body()
            iid = str(body.get("instance_id") or "")
            if not iid:
                raise ApiError("缺少实例")
            if (running_snapshot().get(iid) or {}).get("alive"):
                raise ApiError("该实例已经在运行")
            task = app.tasks.start("launch", "启动游戏", lambda t: app.launcher.launch(iid, t))
            return self._json({"task": task.id})
        if method == "POST" and path == "/api/task/cancel":
            body = self._body()
            return self._json({"ok": app.tasks.cancel(str(body.get("task_id") or ""))})
        if method == "POST" and path == "/api/open-folder":
            body = self._body()
            target = os.path.abspath(str(body.get("path") or cfg.game_root))
            root = os.path.abspath(cfg.game_root)
            base = os.path.abspath(cfg.base_dir)
            allowed = target == root or target.startswith(root + os.sep) or target == base or target.startswith(base + os.sep)
            if not allowed:
                raise ApiError("不允许打开该路径", 403)
            if not os.path.exists(target):
                raise ApiError("路径不存在")
            os.startfile(target)
            return self._json({"ok": True})
        if method == "POST" and path == "/api/shutdown":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return self._json({"ok": True})
        raise ApiError("接口不存在", 404)

    def _vanilla_job(self, instance, version_id, task, delete_on_error=True):
        try:
            self.app.minecraft.install(version_id, task)
            self.app.config.update_instance(instance["id"], installing=False)
        except Exception:
            if delete_on_error:
                self.app.config.delete_instance(instance["id"])
            else:
                self.app.config.update_instance(instance["id"], installing=False)
            raise

    def _create_instance_job(self, instance, mc_version, loader_type, loader_version, task):
        try:
            version_id, resolved = self.app.minecraft.install_loader(mc_version, loader_type, loader_version, task)
            self.app.config.update_instance(
                instance["id"], version_id=version_id,
                loader={"type": loader_type, "version": resolved} if resolved else None,
                installing=False,
            )
        except Exception:
            self.app.config.delete_instance(instance["id"])
            raise

    # ---------- 静态文件 ----------
    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = urllib.parse.unquote(path.lstrip("/"))
        full = os.path.abspath(os.path.join(WEB_DIR, rel))
        if not (full == WEB_DIR or full.startswith(WEB_DIR + os.sep)):
            return self._json({"error": "forbidden"}, 403)
        if not os.path.isfile(full):
            return self._json({"error": "not found"}, 404)
        mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
            mime += "; charset=utf-8"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(config, host="127.0.0.1", port=17871):
    app = App(config)
    last = None
    for candidate in range(port, port + 40):
        try:
            server = Server((host, candidate), Handler)
            server.app = app
            return server
        except OSError as exc:
            last = exc
    raise RuntimeError("没有可用端口：%s" % last)
