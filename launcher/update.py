"""Static-manifest update checker and one-click updater."""
import hashlib
import json
import os
import re
import subprocess
import zipfile

from .net import download_file, fetch_json


def version_tuple(value):
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts[:4])


def check_update(manifest_url, current_version):
    data = fetch_json(manifest_url, timeout=15)
    if not isinstance(data, dict):
        raise RuntimeError("更新清单格式不正确")
    latest = str(data.get("version") or "").strip()
    if not latest:
        raise RuntimeError("更新清单缺少 version")
    return {
        "version": latest,
        "notes": str(data.get("notes") or ""),
        "url": str(data.get("url") or ""),
        "sha256": str(data.get("sha256") or "").lower(),
        "mandatory": bool(data.get("mandatory")),
        "available": version_tuple(latest) > version_tuple(current_version),
    }


def _safe_extract(archive, target):
    root = os.path.abspath(target)
    for member in archive.infolist():
        dest = os.path.abspath(os.path.join(root, member.filename))
        if not dest.startswith(root + os.sep) and dest != root:
            raise RuntimeError("更新包包含非法路径")
    archive.extractall(root)


def download_update(manifest, download_root, progress=None):
    version = str(manifest.get("version") or "new")
    url = str(manifest.get("url") or "")
    if not url:
        raise RuntimeError("更新清单没有下载地址")
    updates = os.path.join(download_root, "updates")
    os.makedirs(updates, exist_ok=True)
    archive_path = os.path.join(updates, "SCL-%s.zip" % re.sub(r"[^0-9A-Za-z._-]", "_", version))
    download_file(url, archive_path, parallel_chunks=4, timeout=120, label="SCL 更新包")
    expected = str(manifest.get("sha256") or "").lower()
    if expected:
        digest = hashlib.sha256()
        with open(archive_path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        if digest.hexdigest().lower() != expected:
            try:
                os.remove(archive_path)
            except OSError:
                pass
            raise RuntimeError("更新包 SHA256 校验失败")
    staging = os.path.join(updates, "staging-%s" % re.sub(r"[^0-9A-Za-z._-]", "_", version))
    if os.path.isdir(staging):
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        _safe_extract(archive, staging)
    if progress:
        progress(1, 1)
    return staging, archive_path


def apply_update(staging, app_dir, exe_name="SimpleCubeLauncher.exe"):
    source = os.path.join(staging, "SimpleCubeLauncher")
    if not os.path.isdir(source):
        source = staging
    bat_path = os.path.join(staging, "apply-update.bat")
    lines = [
        "@echo off",
        "timeout /t 2 /nobreak >nul",
        "taskkill /f /im %s >nul 2>&1" % exe_name,
        'robocopy "%s" "%s" /E /NFL /NDL /NJH /NJS /NP >nul' % (source, app_dir),
        'start "" "%s"' % os.path.join(app_dir, exe_name),
        'del "%%~f0"',
    ]
    with open(bat_path, "w", encoding="gbk", errors="replace") as handle:
        handle.write("\r\n".join(lines) + "\r\n")
    subprocess.Popen(
        ["cmd", "/c", "start", "", "/min", bat_path],
        creationflags=0x08000000,
        close_fds=True,
    )
    return bat_path
