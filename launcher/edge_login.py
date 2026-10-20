"""通过 Microsoft Edge 远程调试捕获微软 OAuth 回调 code。"""
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from urllib.parse import parse_qs, urlparse

try:
    import websocket
except Exception:
    websocket = None


class EdgeLoginError(Exception):
    pass


def find_edge():
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    found = shutil.which("msedge.exe")
    if found:
        candidates.append(found)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _get_json(url, timeout=1.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean_profile_locks(profile_dir):
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        path = os.path.join(profile_dir, name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _browser_from_pid(pid):
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=0x08000000, timeout=10)
    except Exception:
        pass


def _extract_callback_code(url):
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if parsed.hostname != "login.live.com":
        return ""
    if parsed.path.rstrip("/") != "/oauth20_desktop.srf":
        return ""
    return (parse_qs(parsed.query).get("code") or [""])[0]


def capture_auth_code(auth_url, profile_dir, timeout=300):
    if websocket is None:
        raise EdgeLoginError("缺少 websocket-client，无法启动 Edge 登录。")
    edge = find_edge()
    if not edge:
        raise EdgeLoginError("没有找到 Microsoft Edge，无法完成自动登录。")
    os.makedirs(profile_dir, exist_ok=True)
    _clean_profile_locks(profile_dir)
    port = _free_port()
    args = [
        edge,
        "--remote-debugging-port=%d" % port,
        "--user-data-dir=%s" % profile_dir,
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeFirstRunExperience",
        "--new-window",
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0)
    ws = None
    try:
        deadline = time.time() + 20
        targets = []
        while time.time() < deadline:
            if proc.poll() is not None:
                raise EdgeLoginError("Edge 启动失败，请确认 Microsoft Edge 已安装。")
            try:
                targets = _get_json("http://127.0.0.1:%d/json/list" % port, 1)
                if targets:
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if not targets:
            raise EdgeLoginError("Edge 调试端口没有响应。")
        page = next((item for item in targets if item.get("type") == "page"), targets[0])
        ws_url = page.get("webSocketDebuggerUrl")
        if not ws_url:
            raise EdgeLoginError("Edge 页面没有调试地址。")
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
        ws.send(json.dumps({"id": 3, "method": "Page.navigate",
                            "params": {"url": auth_url}}))
        ws.settimeout(1.0)
        deadline = time.time() + max(30, int(timeout))
        while time.time() < deadline:
            if proc.poll() is not None:
                raise EdgeLoginError("Edge 已被关闭，登录未完成。")
            try:
                message = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:
                raise EdgeLoginError("Edge 调试连接已关闭。") from exc
            if not message:
                continue
            if isinstance(message, bytes):
                message = message.decode("utf-8", "replace")
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                continue
            method = event.get("method") or ""
            params = event.get("params") or {}
            urls = []
            if method == "Network.requestWillBeSent":
                urls.append(((params.get("request") or {}).get("url") or ""))
            elif method == "Network.responseReceived":
                urls.append(((params.get("response") or {}).get("url") or ""))
            elif method == "Page.frameNavigated":
                urls.append((((params.get("frame") or {}).get("url")) or ""))
            elif method == "Page.frameRequestedNavigation":
                urls.append((params.get("url") or ""))
            for url in urls:
                code = _extract_callback_code(url)
                if code:
                    return code
        raise EdgeLoginError("微软登录超时，请重新点击登录。")
    finally:
        try:
            if ws is not None:
                ws.close()
        except Exception:
            pass
        _browser_from_pid(proc.pid)
