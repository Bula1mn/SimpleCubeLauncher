"""Simple Cube Launcher 入口。"""
import argparse
import os
import subprocess
import sys
import time
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from launcher.api import create_server
from launcher.config import Config


def find_edge():
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ]
    for item in candidates:
        if item and os.path.isfile(item):
            return item
    return None


def open_window(url):
    edge = find_edge()
    if edge:
        try:
            subprocess.Popen([edge, "--app=" + url, "--window-size=1200,820"], close_fds=True)
            return True
        except Exception:
            pass
    webbrowser.open(url)
    return False


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Simple Cube Launcher")
    parser.add_argument("--port", type=int, default=17871)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    config = Config(BASE_DIR)
    server = create_server(config, port=args.port)
    port = server.server_address[1]
    url = "http://127.0.0.1:%d" % port
    print("=" * 58)
    print("  Simple Cube Launcher (SCL) 0.2.8")
    print("  界面地址：%s" % url)
    print("  游戏目录：%s" % config.game_root)
    print("  关闭此窗口即可退出启动器（游戏不受影响）")
    print("=" * 58)
    if not args.no_browser:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("启动器已退出")


if __name__ == "__main__":
    main()
