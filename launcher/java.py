"""Java 运行时探测。"""
import os
import re
import shutil
import subprocess
import threading
import time

CREATE_NO_WINDOW = 0x08000000

_CACHE = {"time": 0.0, "items": []}
_LOCK = threading.Lock()


def _parse_version(text):
    match = re.search(r'version "([^"]+)"', text)
    version = match.group(1) if match else ""
    if not version:
        match = re.search(r"version (\S+)", text)
        version = match.group(1) if match else ""
    major = 0
    if version.startswith("1."):
        try:
            major = int(version.split(".")[1])
        except (IndexError, ValueError):
            major = 0
    else:
        match = re.match(r"(\d+)", version)
        if match:
            major = int(match.group(1))
    return version, major


def inspect_java(path):
    try:
        proc = subprocess.run(
            [path, "-version"], capture_output=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        text = (proc.stderr or b"").decode("utf-8", "replace") + \
               (proc.stdout or b"").decode("utf-8", "replace")
        version, major = _parse_version(text)
        if not version:
            return None
        arch = "x86_64" if "64-Bit" in text else "x86"
        first = text.strip().splitlines()[0] if text.strip() else ""
        return {
            "path": os.path.abspath(path),
            "version": version,
            "major": major,
            "arch": arch,
            "vendor": first[:160],
        }
    except Exception:
        return None


def _glob_candidates(game_root, configured):
    seen = []
    if configured:
        seen.append(configured)
    which = shutil.which("java")
    if which:
        seen.append(which)
    home = os.environ.get("JAVA_HOME")
    if home:
        seen.append(os.path.join(home, "bin", "java.exe"))
    env = os.environ
    roots = [
        env.get("ProgramFiles"),
        env.get("ProgramFiles(x86)"),
        env.get("LOCALAPPDATA"),
        os.path.join(env.get("LOCALAPPDATA", ""), "Programs"),
    ]
    patterns = [
        "Java/*/bin/java.exe",
        "Eclipse Adoptium/*/bin/java.exe",
        "Eclipse/*/bin/java.exe",
        "Microsoft/jdk-*/bin/java.exe",
        "Zulu/*/bin/java.exe",
        "BellSoft/*/bin/java.exe",
        "Amazon Corretto/*/bin/java.exe",
        "Programs/Eclipse Adoptium/*/bin/java.exe",
    ]
    for root in roots:
        if not root:
            continue
        for pattern in patterns:
            import glob
            for item in glob.glob(os.path.join(root, pattern)):
                seen.append(item)
    if game_root:
        import glob
        for item in glob.glob(os.path.join(game_root, "runtime", "*", "bin", "java.exe")):
            seen.append(item)
    result = []
    visited = set()
    for item in seen:
        if not item:
            continue
        path = os.path.abspath(os.path.expanduser(str(item)))
        key = path.lower()
        if key in visited or not os.path.isfile(path):
            continue
        visited.add(key)
        result.append(path)
    return result


def detect_java(game_root="", configured="", force=False):
    with _LOCK:
        now = time.time()
        if not force and _CACHE["items"] and now - _CACHE["time"] < 45:
            return [dict(item) for item in _CACHE["items"]]
    items = []
    for path in _glob_candidates(game_root, configured):
        info = inspect_java(path)
        if info:
            items.append(info)
    items.sort(key=lambda i: (i["major"], i["path"]), reverse=True)
    with _LOCK:
        _CACHE["items"] = items
        _CACHE["time"] = time.time()
    return [dict(item) for item in items]


def choose_java(items, required_major, configured=""):
    if configured:
        for item in items:
            if os.path.abspath(item["path"]).lower() == os.path.abspath(configured).lower():
                return item
        inspected = inspect_java(configured)
        if inspected:
            return inspected
    eligible = [i for i in items if i["major"] >= required_major]
    if eligible:
        return sorted(eligible, key=lambda i: i["major"])[0]
    if items:
        return sorted(items, key=lambda i: i["major"], reverse=True)[0]
    return None
