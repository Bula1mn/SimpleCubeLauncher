"""Minecraft 原版与加载器安装。"""
import json
import os
import platform
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from .fsutil import write_json
from .java import CREATE_NO_WINDOW, choose_java, detect_java
from .net import download_file, fetch, fetch_json, fetch_json_candidates
from .tasks import Cancelled

MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
BMCL_MANIFEST = "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"
FABRIC_META = "https://meta.fabricmc.net/v2"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

FEATURES = {
    "has_custom_resolution": False,
    "is_demo_user": False,
    "has_quick_plays_support": False,
    "is_quick_play_singleplayer": False,
    "is_quick_play_multiplayer": False,
    "is_quick_play_realms": False,
}

_MACHINE = platform.machine().lower()
_IS_ARM64 = _MACHINE in ("arm64", "aarch64")
_IS_64 = ("64" in _MACHINE) or _MACHINE in ("amd64", "x86_64")


def native_allowed(name):
    """Mojang 的原版 JSON 里 natives-windows / -x86 / -arm64 往往共用同一条 OS 规则，
    需要按当前架构再筛一层，否则会把别的架构的 DLL 解压进来。"""
    text = str(name or "").lower()
    if ":natives-" not in text:
        return True
    if "arm64" in text or "aarch64" in text:
        return _IS_ARM64
    if text.endswith("-x86"):
        return not _IS_64
    return True


def _rule_matches(rule):
    os_rule = rule.get("os") or {}
    if os_rule:
        name = os_rule.get("name")
        if name and name != "windows":
            return False
        arch = os_rule.get("arch")
        if arch:
            machine = platform.machine().lower()
            is_64 = ("64" in machine) or machine in ("amd64", "x86_64")
            if arch == "x86" and is_64:
                return False
            if arch == "x86_64" and not is_64:
                return False
            if arch == "arm64":
                return False
        version = os_rule.get("version")
        if version:
            try:
                if not re.search(version, platform.version()):
                    return False
            except re.error:
                pass
    rule_features = rule.get("features") or {}
    for key, expected in rule_features.items():
        if bool(FEATURES.get(key)) != bool(expected):
            return False
    return True


def rules_allow(rules):
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if isinstance(rule, dict) and _rule_matches(rule):
            allowed = rule.get("action") == "allow"
    return allowed


def maven_path(name):
    ext = "jar"
    base = str(name or "")
    if "@" in base:
        base, ext = base.split("@", 1)
        ext = ext or "jar"
    parts = base.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else ""
    filename = f"{artifact}-{version}"
    if classifier:
        filename += f"-{classifier}"
    filename += f".{ext}"
    return "/".join(group.split(".")) + f"/{artifact}/{version}/{filename}"


def _lib_key(name):
    parts = str(name or "").split("@")[0].split(":")
    if len(parts) < 2:
        return None
    classifier = parts[3] if len(parts) > 3 else ""
    return f"{parts[0]}:{parts[1]}:{classifier}"


def _write_json(path, data):
    write_json(path, data)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class Minecraft:
    def __init__(self, config, tasks):
        self.config = config
        self.tasks = tasks

    # ---------- 路径 ----------
    def version_dir(self, vid):
        return self.config.path_in("versions", vid)

    def marker(self, vid):
        return os.path.join(self.version_dir(vid), ".mcl-installed")

    def is_installed(self, vid):
        return os.path.isfile(self.marker(vid))

    # ---------- 清单 ----------
    def manifest(self, refresh=False):
        path = self.config.path_in("meta", "version_manifest_v2.json")
        if not refresh and os.path.isfile(path):
            try:
                if time.time() - os.path.getmtime(path) < 1800:
                    return _read_json(path)
            except Exception:
                pass
        urls = []
        if self.config.source != "official":
            urls.append(BMCL_MANIFEST)
        urls.append(MANIFEST_URL)
        data = fetch_json_candidates(urls)
        _write_json(path, data)
        return data

    def manifest_versions(self, kind="all", refresh=False):
        data = self.manifest(refresh=refresh)
        items = data.get("versions") or []
        if kind in ("release", "snapshot"):
            items = [item for item in items if item.get("type") == kind]
        return items

    def _version_entry(self, vid):
        for item in self.manifest_versions():
            if item.get("id") == vid:
                return item
        raise RuntimeError(f"版本 {vid} 不在官方清单中")

    def installed_version_ids(self):
        root = self.config.path_in("versions")
        result = []
        if not os.path.isdir(root):
            return result
        for name in os.listdir(root):
            if os.path.isfile(os.path.join(root, name, name + ".json")):
                result.append(name)
        return sorted(result)

    def version_json(self, vid, refresh=False):
        local = os.path.join(self.version_dir(vid), vid + ".json")
        if not refresh and os.path.isfile(local):
            try:
                return _read_json(local)
            except Exception:
                pass
        cached = self.config.path_in("meta", "versions", vid + ".json")
        if not refresh and os.path.isfile(cached):
            try:
                return _read_json(cached)
            except Exception:
                pass
        entry = self._version_entry(vid)
        urls = []
        if self.config.source != "official":
            urls.append(f"https://bmclapi2.bangbang93.com/version/{vid}/json")
        if entry.get("url"):
            urls.append(entry["url"])
        data = fetch_json_candidates(urls)
        if isinstance(data, dict) and not data.get("id"):
            data["id"] = vid
        _write_json(cached, data)
        return data

    def _save_version_json(self, vid, data):
        _write_json(os.path.join(self.version_dir(vid), vid + ".json"), data)
        _write_json(self.config.path_in("meta", "versions", vid + ".json"), data)

    # ---------- 安装原版 ----------
    def install(self, vid, task, force=False):
        marker = self.marker(vid)
        if not force and os.path.isfile(marker) and os.path.isfile(os.path.join(self.version_dir(vid), vid + ".jar")):
            task.log(f"{vid} 已安装，跳过下载")
            try:
                return self.version_json(vid)
            except Exception:
                pass
        task.log(f"开始安装 Minecraft {vid}")
        task.set_stage("获取版本信息")
        data = self.version_json(vid)
        self._save_version_json(vid, data)
        task.set_stage("下载游戏核心")
        self._install_client(data, vid, task)
        task.set_stage("下载运行库")
        self._install_libraries(data, task)
        task.set_stage("下载游戏资源")
        self._install_assets(data, task)
        task.set_stage("下载日志配置")
        self._install_logging(data, task)
        _write_json(marker, {"version_id": vid, "time": int(time.time())})
        task.log(f"{vid} 安装完成")
        return data

    def _install_client(self, data, vid, task):
        info = (data.get("downloads") or {}).get("client")
        if not info:
            return
        dest = os.path.join(self.version_dir(vid), vid + ".jar")
        official = info.get("url")
        if not official:
            return
        urls = []
        if self.config.source != "official":
            urls.append(f"https://bmclapi2.bangbang93.com/version/{vid}/client")
        urls.append(official)
        task.add_total(info.get("size") or 0)
        download_file(
            urls[0], dest, task=task, sha1=info.get("sha1"), size=info.get("size"),
            source="official", alt_urls=urls[1:], label=os.path.basename(dest),
            parallel_chunks=8,
        )

    def _library_entries(self, data):
        entries = []
        seen = set()
        for lib in data.get("libraries") or []:
            if not isinstance(lib, dict) or not rules_allow(lib.get("rules")):
                continue
            if not native_allowed(lib.get("name")):
                continue
            downloads = lib.get("downloads") or {}
            artifact = downloads.get("artifact") or {}
            added = False
            if artifact.get("path") and artifact.get("url"):
                entry = (artifact["path"], artifact["url"], artifact.get("sha1"), artifact.get("size"))
                if entry[0] not in seen:
                    seen.add(entry[0])
                    entries.append(entry)
                    added = True
            if not added and lib.get("name"):
                path = maven_path(lib["name"])
                if path and path not in seen:
                    base = lib.get("url") or "https://libraries.minecraft.net/"
                    seen.add(path)
                    entries.append((path, base.rstrip("/") + "/" + path, None, None))
            natives = lib.get("natives") or {}
            classifier_key = natives.get("windows")
            if classifier_key:
                classifier = str(classifier_key).replace("$" + "{arch}", "64")
                info = (downloads.get("classifiers") or {}).get(classifier)
                if info and info.get("path") and info.get("url") and info["path"] not in seen:
                    seen.add(info["path"])
                    entries.append((info["path"], info["url"], info.get("sha1"), info.get("size")))
        return entries

    def _install_libraries(self, data, task, stage=None):
        entries = self._library_entries(data)
        if not entries:
            return
        self._download_entries(entries, "libraries", task, stage or "下载运行库")

    def _install_assets(self, data, task):
        info = data.get("assetIndex") or {}
        if not info.get("url"):
            return
        index_path = self.config.path_in("assets", "indexes", str(info.get("id") or "legacy") + ".json")
        self._download_single(info["url"], index_path, task, info.get("sha1"), info.get("size"))
        try:
            index = _read_json(index_path)
        except Exception:
            raise RuntimeError("资源索引解析失败")
        entries = []
        seen = set()
        for obj in (index.get("objects") or {}).values():
            if not isinstance(obj, dict):
                continue
            digest = obj.get("hash")
            if not digest or digest in seen:
                continue
            seen.add(digest)
            entries.append((f"{digest[:2]}/{digest}", f"https://resources.download.minecraft.net/{digest[:2]}/{digest}",
                            digest, obj.get("size") or 0))
        task.log(f"资源文件：{len(entries)} 个")
        self._download_entries(entries, os.path.join("assets", "objects"), task, "下载游戏资源")

    def _install_logging(self, data, task):
        client = (data.get("logging") or {}).get("client") or {}
        info = client.get("file") or {}
        if not info.get("url"):
            return
        name = info.get("id") or "client.xml"
        dest = self.config.path_in("assets", "log_configs", name)
        self._download_single(info["url"], dest, task, info.get("sha1"), info.get("size"))

    def _download_single(self, url, dest, task, sha1=None, size=None, alt_urls=None):
        if size:
            task.add_total(size)
        download_file(url, dest, task=task, sha1=sha1, size=size,
                      source=self.config.source, alt_urls=alt_urls)

    def _download_entries(self, entries, root_rel, task, stage):
        if not entries:
            return
        total = sum(int(item[3] or 0) for item in entries)
        task.add_total(total)
        task.set_stage(stage)
        root = self.config.path_in(root_rel) if root_rel else self.config.game_root

        def work(entry):
            task.check_cancel()
            rel, url, sha1, size = entry
            dest = os.path.join(root, rel)
            chunks = 4 if int(size or 0) >= 8 * 1024 * 1024 else 0
            download_file(url, dest, task=task, sha1=sha1, size=size,
                          source=self.config.source, label=os.path.basename(rel),
                          parallel_chunks=chunks)

        with ThreadPoolExecutor(max_workers=24) as pool:
            futures = [pool.submit(work, entry) for entry in entries]
            for future in as_completed(futures):
                future.result()

    # ---------- 合并版本 ----------
    def merge_version(self, vid, _depth=0):
        if _depth > 8:
            raise RuntimeError("版本继承层级过深")
        raw = self.version_json(vid)
        parent_id = raw.get("inheritsFrom")
        if not parent_id:
            merged = dict(raw)
            merged.setdefault("id", vid)
            merged["_base"] = vid
            return merged
        parent = self.merge_version(parent_id, _depth + 1)
        merged = dict(parent)
        for key, value in raw.items():
            if key in ("libraries", "arguments", "minecraftArguments", "id", "inheritsFrom"):
                continue
            merged[key] = value
        merged["id"] = vid
        merged["libraries"] = self._merge_libraries(parent.get("libraries") or [], raw.get("libraries") or [])
        merged["arguments"] = self._merge_arguments(parent.get("arguments"), raw.get("arguments"))
        if "minecraftArguments" in raw:
            merged["minecraftArguments"] = raw["minecraftArguments"]
        merged["_base"] = parent.get("_base") or parent_id
        return merged

    @staticmethod
    def _merge_libraries(parent_libs, child_libs):
        result = {}
        order = []
        for lib in list(parent_libs) + list(child_libs):
            if not isinstance(lib, dict):
                continue
            key = _lib_key(lib.get("name")) or f"__{len(order)}"
            if key not in result:
                order.append(key)
            result[key] = lib
        return [result[key] for key in order]

    @staticmethod
    def _merge_arguments(parent_args, child_args):
        if not parent_args and not child_args:
            return None
        left = parent_args or {}
        right = child_args or {}
        return {
            "game": list(left.get("game") or []) + list(right.get("game") or []),
            "jvm": list(left.get("jvm") or []) + list(right.get("jvm") or []),
        }

    # ---------- 加载器 ----------
    def fabric_loaders(self, mc):
        return fetch_json(f"{FABRIC_META}/versions/loader/{mc}")

    def install_fabric(self, mc, loader_version=None, task=None):
        self.install(mc, task)
        task.set_stage("获取 Fabric 版本")
        loaders = self.fabric_loaders(mc)
        if not loaders:
            raise RuntimeError(f"Minecraft {mc} 没有可用的 Fabric 加载器")
        pick = None
        if loader_version:
            for item in loaders:
                if item.get("loader", {}).get("version") == loader_version:
                    pick = item
                    break
        if pick is None:
            stable = [item for item in loaders if item.get("loader", {}).get("stable")]
            pick = (stable or loaders)[0]
        lv = pick["loader"]["version"]
        fid = f"fabric-loader-{lv}-{mc}"
        if self.is_installed(fid):
            task.log(f"{fid} 已安装，跳过")
            return fid, lv
        task.set_stage("下载 Fabric 启动配置")
        profile = fetch_json(f"{FABRIC_META}/versions/loader/{mc}/{lv}/profile/json")
        profile["id"] = fid
        profile["inheritsFrom"] = mc
        self._save_version_json(fid, profile)
        task.set_stage("下载 Fabric 运行库")
        self._install_libraries(profile, task, stage="下载 Fabric 运行库")
        _write_json(self.marker(fid), {"version_id": fid, "time": int(time.time()), "loader": lv})
        task.log(f"Fabric {lv} 安装完成")
        return fid, lv

    def forge_version(self, mc):
        data = fetch_json(FORGE_PROMOS)
        promos = data.get("promos") or {}
        return promos.get(f"{mc}-recommended") or promos.get(f"{mc}-latest")

    def install_forge(self, mc, loader_version=None, task=None):
        self.install(mc, task)
        task.set_stage("获取 Forge 版本")
        fv = loader_version
        if not fv:
            fv = self.forge_version(mc)
        if not fv:
            raise RuntimeError(f"Minecraft {mc} 没有可用的 Forge 版本")
        target = f"{mc}-forge-{fv}"
        if os.path.isfile(os.path.join(self.version_dir(target), target + ".json")):
            task.log(f"{target} 已安装，跳过")
            return target, fv
        jar = self.config.path_in("meta", "installers", f"forge-{mc}-{fv}-installer.jar")
        url = f"{FORGE_MAVEN}/{mc}-{fv}/forge-{mc}-{fv}-installer.jar"
        task.set_stage("下载 Forge 安装器")
        download_file(url, jar, task=task, source=self.config.source, label="Forge 安装器")
        self._run_installer(jar, task, "安装 Forge")
        found = self._find_loader_version(mc, "forge", fv)
        if not found:
            raise RuntimeError("Forge 安装器执行完成，但没有找到版本文件")
        _write_json(self.marker(found), {"version_id": found, "time": int(time.time()), "loader": fv})
        task.log(f"Forge {fv} 安装完成")
        return found, fv

    def _neoforge_versions(self, mc):
        raw = fetch(f"{NEOFORGE_MAVEN}/maven-metadata.xml")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []
        if mc == "1.20.1":
            prefix = "47.1."
        else:
            parts = mc.split(".")
            if len(parts) < 3:
                return []
            prefix = f"{parts[1]}.{parts[2]}."
        values = []
        for node in root.iter():
            if node.tag.endswith("version") and node.text:
                value = node.text.strip()
                if value.startswith(prefix):
                    values.append(value)
        return values

    def install_neoforge(self, mc, loader_version=None, task=None):
        self.install(mc, task)
        task.set_stage("获取 NeoForge 版本")
        versions = self._neoforge_versions(mc)
        if loader_version:
            value = loader_version
        elif versions:
            value = versions[-1]
        else:
            raise RuntimeError(f"Minecraft {mc} 没有可用的 NeoForge 版本")
        target = f"neoforge-{value}"
        if os.path.isfile(os.path.join(self.version_dir(target), target + ".json")):
            task.log(f"{target} 已安装，跳过")
            return target, value
        jar = self.config.path_in("meta", "installers", f"neoforge-{value}-installer.jar")
        url = f"{NEOFORGE_MAVEN}/{value}/neoforge-{value}-installer.jar"
        task.set_stage("下载 NeoForge 安装器")
        download_file(url, jar, task=task, source=self.config.source, label="NeoForge 安装器")
        self._run_installer(jar, task, "安装 NeoForge")
        found = self._find_loader_version(mc, "neoforge", value)
        if not found:
            raise RuntimeError("NeoForge 安装器执行完成，但没有找到版本文件")
        _write_json(self.marker(found), {"version_id": found, "time": int(time.time()), "loader": value})
        task.log(f"NeoForge {value} 安装完成")
        return found, value

    def _find_loader_version(self, mc, loader, loader_version):
        root = self.config.path_in("versions")
        names = []
        if os.path.isdir(root):
            names = os.listdir(root)
        expected = [
            f"{mc}-{loader}-{loader_version}",
            f"{loader}-{loader_version}",
            f"{mc}-{loader}-{loader_version}-client",
        ]
        for name in expected:
            if os.path.isfile(os.path.join(root, name, name + ".json")):
                return name
        for name in names:
            if loader in name.lower() and os.path.isfile(os.path.join(root, name, name + ".json")):
                return name
        return None

    def _run_installer(self, jar, task, label):
        javas = detect_java(self.config.game_root, self.config.data.get("java_path", ""))
        java = choose_java(javas, 8, self.config.data.get("java_path", ""))
        if not java:
            raise RuntimeError(f"{label}需要 Java，请先在设置中指定 Java 路径")
        task.set_stage(label)
        task.log(f"使用 Java {java['version']}：{java['path']}")
        # Forge / NeoForge 安装器会检查启动器配置文件
        profiles = os.path.join(self.config.game_root, "launcher_profiles.json")
        if not os.path.isfile(profiles):
            _write_json(profiles, {"profiles": {}, "settings": {}, "version": 3})
        proc = subprocess.Popen(
            [java["path"], "-jar", jar, "--installClient", self.config.game_root],
            cwd=self.config.game_root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        try:
            while True:
                if task.cancel_event.is_set():
                    proc.kill()
                    raise Cancelled()
                line = proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").strip()
                if text:
                    task.log(text)
            code = proc.wait()
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if code != 0:
            raise RuntimeError(f"{label}失败（退出码 {code}），详情见任务日志")

    def install_loader(self, mc, loader_type, loader_version=None, task=None):
        loader_type = (loader_type or "vanilla").lower()
        if loader_type in ("", "vanilla", "none"):
            self.install(mc, task)
            return mc, None
        if loader_type == "fabric":
            return self.install_fabric(mc, loader_version, task)
        if loader_type == "forge":
            return self.install_forge(mc, loader_version, task)
        if loader_type == "neoforge":
            return self.install_neoforge(mc, loader_version, task)
        raise RuntimeError(f"暂不支持 {loader_type} 加载器")

    # ---------- Java 需求 ----------
    def required_java(self, version_id):
        data = None
        try:
            data = self.version_json(version_id)
        except Exception:
            data = None
        guard = 0
        while data is not None and "javaVersion" not in data and data.get("inheritsFrom") and guard < 6:
            try:
                data = self.version_json(data["inheritsFrom"])
            except Exception:
                data = None
            guard += 1
        if data and data.get("javaVersion"):
            try:
                return int(data["javaVersion"].get("majorVersion") or 0)
            except (TypeError, ValueError):
                pass
        return self._fallback_java(version_id)

    @staticmethod
    def _fallback_java(version_id):
        match = re.search(r"1\.(\d+)(?:\.(\d+))?", str(version_id))
        if not match:
            return 21
        minor = int(match.group(1))
        patch = int(match.group(2) or 0)
        if minor >= 21 or (minor == 20 and patch >= 5):
            return 21
        if minor >= 18:
            return 17
        if minor == 17:
            return 16
        return 8
