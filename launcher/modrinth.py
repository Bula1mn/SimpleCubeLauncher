"""Modrinth 搜索、Mod/光影/整合包安装。"""
import json
import os
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode

from .net import download_file, fetch_json

API = "https://api.modrinth.com/v2"
HEADERS = {"User-Agent": "SimpleCubeLauncher/0.2 (Minecraft launcher)"}


class Modrinth:
    def __init__(self, config, tasks, minecraft):
        self.config = config
        self.tasks = tasks
        self.minecraft = minecraft

    # ---------- 查询 ----------
    def _get(self, path, params=None):
        url = API + path
        if params:
            url += "?" + urlencode(params, doseq=True)
        return fetch_json(url, headers=HEADERS, timeout=30)

    def search(self, kind, query="", game_version=None, loader=None, limit=20, offset=0):
        if kind in ("shader", "shaders"):
            kind = "shader"
        elif kind in ("modpack", "modpacks"):
            kind = "modpack"
        elif kind in ("resourcepack", "resourcepacks"):
            kind = "resourcepack"
        else:
            kind = "mod"
        facets = [["project_type:" + kind]]
        if game_version and game_version != "all":
            facets.append(["versions:" + game_version])
        loader = (loader or "").lower()
        if loader and loader not in ("all", "vanilla") and kind in ("mod", "modpack"):
            facets.append(["categories:" + loader])
        params = {
            "query": query or "",
            "limit": max(1, min(40, int(limit or 20))),
            "offset": max(0, int(offset or 0)),
            "index": "relevance" if query else "downloads",
            "facets": json.dumps(facets, separators=(",", ":")),
        }
        data = self._get("/search", params)
        return {
            "hits": data.get("hits") or [],
            "total": data.get("total_hits") or 0,
            "offset": data.get("offset") or 0,
            "limit": data.get("limit") or params["limit"],
        }

    def project(self, project_id):
        return self._get("/project/" + project_id)

    def versions(self, project_id, game_version=None, loader=None):
        loader = (loader or "").lower()
        params = {}
        if game_version and game_version != "all":
            params["game_versions"] = json.dumps([game_version])
        if loader and loader not in ("all", "vanilla"):
            params["loaders"] = json.dumps([loader])
        data = self._get("/project/" + project_id + "/version", params or None)
        return data if isinstance(data, list) else []

    @staticmethod
    def pick_version(versions, version_id=None):
        if version_id:
            for item in versions:
                if item.get("id") == version_id:
                    return item
            raise RuntimeError("找不到所选的版本文件")
        for item in versions:
            if item.get("files"):
                return item
        raise RuntimeError("没有找到可下载的文件")

    @staticmethod
    def primary_file(version):
        files = version.get("files") or []
        for item in files:
            if item.get("primary"):
                return item
        return files[0] if files else None

    # ---------- 安装 Mod / 光影 ----------
    def install_content(self, project_id, version_id, instance_id, kind, task):
        instance = self.config.get_instance(instance_id)
        loader = instance.get("loader") or {}
        loader_type = loader.get("type") if isinstance(loader, dict) else (loader or "")
        if kind == "mod" and not loader_type:
            raise RuntimeError("这个实例是原版，没有 Mod 加载器，无法安装 Mod")
        game_version = instance.get("mc_version")
        versions = self.versions(project_id, game_version,
                                 None if kind in ("shader", "resourcepack") else loader_type)
        version = self.pick_version(versions, version_id)
        file = self.primary_file(version)
        if not file:
            raise RuntimeError("该版本没有可下载的文件")
        folder = {"shader": "shaderpacks", "resourcepack": "resourcepacks"}.get(kind, "mods")
        dest_dir = os.path.join(instance["dir"], folder)
        os.makedirs(dest_dir, exist_ok=True)
        filename = os.path.basename(str(file.get("filename") or "download.jar"))
        dest = os.path.join(dest_dir, filename)
        task.set_stage("下载 " + filename)
        download_file(
            file["url"], dest, task=task,
            sha1=(file.get("hashes") or {}).get("sha1"),
            size=file.get("size"), source="official", label=filename,
        )
        task.log("已下载到 " + folder + "/" + filename)
        return {"file": filename, "version": version.get("version_number")}

    # ---------- 安装整合包 ----------
    def install_modpack(self, project_id, version_id, name, task):
        project = self.project(project_id)
        versions = self.versions(project_id)
        version = self.pick_version(versions, version_id)
        file = self.primary_file(version)
        if not file:
            raise RuntimeError("整合包没有可下载的文件")
        filename = os.path.basename(str(file.get("filename") or "pack.mrpack"))
        pack_path = self.config.path_in("meta", "modpacks", filename)
        task.set_stage("下载整合包")
        download_file(
            file["url"], pack_path, task=task,
            sha1=(file.get("hashes") or {}).get("sha1"),
            size=file.get("size"), source="official", label=filename,
        )
        return self.install_modpack_file(pack_path, name, task, project=project)

    def install_modpack_file(self, pack_path, name, task, project=None):
        project = project or {}
        task.set_stage("解析整合包")
        try:
            with zipfile.ZipFile(pack_path) as zf:
                index = json.loads(zf.read("modrinth.index.json").decode("utf-8"))
        except KeyError:
            raise RuntimeError("不是有效的 Modrinth 整合包（缺少 modrinth.index.json）")
        except zipfile.BadZipFile:
            raise RuntimeError("整合包文件损坏")
        deps = index.get("dependencies") or {}
        mc = str(deps.get("minecraft") or "")
        if not mc:
            raise RuntimeError("整合包没有声明 Minecraft 版本")
        loader_type, loader_version = "vanilla", None
        if deps.get("fabric-loader"):
            loader_type, loader_version = "fabric", str(deps["fabric-loader"])
        elif deps.get("forge"):
            loader_type, loader_version = "forge", str(deps["forge"])
        elif deps.get("neoforge"):
            loader_type, loader_version = "neoforge", str(deps["neoforge"])
        elif deps.get("quilt-loader"):
            raise RuntimeError("暂不支持 Quilt 整合包")
        title = (name or project.get("title") or index.get("name")
                 or os.path.splitext(os.path.basename(pack_path))[0] or "整合包").strip()
        icon = project.get("icon_url") or index.get("icon") or ""
        instance = self.config.create_instance(
            title, mc, loader=None, icon=icon,
            summary=(index.get("summary") or project.get("description") or "")[:200],
        )
        task.log("创建实例：" + title)
        try:
            self.config.update_instance(instance["id"], installing=True)
            task.set_stage("安装游戏与加载器")
            resolved_version, resolved_loader = self.minecraft.install_loader(mc, loader_type, loader_version, task)
            self.config.update_instance(
                instance["id"], version_id=resolved_version,
                loader={"type": loader_type, "version": resolved_loader} if resolved_loader else None,
            )
            entries = []
            for item in index.get("files") or []:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").replace("\\", "/")
                if not path or path.startswith("/") or ".." in path.split("/"):
                    continue
                env = item.get("env") or {}
                if env.get("client") == "unsupported":
                    continue
                urls = item.get("downloads") or []
                if not urls:
                    continue
                entries.append((path, urls[0], (item.get("hashes") or {}).get("sha1"), item.get("fileSize") or 0))
            task.log("整合包文件：%d 个" % len(entries))
            self._download_pack_files(entries, instance["dir"], task)
            task.set_stage("解压覆盖文件")
            self._extract_overrides(pack_path, instance["dir"], "overrides/")
            self._extract_overrides(pack_path, instance["dir"], "client-overrides/")
            self.config.update_instance(instance["id"], installing=False)
            task.log("整合包安装完成")
            return {"instance_id": instance["id"], "name": title, "minecraft": mc, "loader": loader_type}
        except Exception:
            self.config.delete_instance(instance["id"])
            raise

    def _download_pack_files(self, entries, root, task):
        total = sum(int(item[3] or 0) for item in entries)
        task.add_total(total)
        task.set_stage("下载整合包内容")
        base = os.path.normpath(root)

        def work(entry):
            task.check_cancel()
            rel, url, sha1, size = entry
            target = os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))
            if not (target == base or target.startswith(base + os.sep)):
                return
            download_file(url, target, task=task, sha1=sha1, size=size,
                          source="official", label=os.path.basename(rel))

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(work, entry) for entry in entries]
            for future in as_completed(futures):
                future.result()

    def install_zip_modpack(self, pack_path, name, task):
        """CurseForge-style zip: manifest.json + overrides."""
        with zipfile.ZipFile(pack_path) as zf:
            if "manifest.json" not in zf.namelist():
                raise RuntimeError("zip 中没有 manifest.json")
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        mc = str(((manifest.get("minecraft") or {}).get("version") or ""))
        if not mc:
            raise RuntimeError("整合包没有声明 Minecraft 版本")
        loader_type, loader_version = "vanilla", None
        for item in (manifest.get("minecraft") or {}).get("modLoaders") or []:
            raw = str(item.get("id") or "")
            if "-" not in raw:
                continue
            kind, version = raw.split("-", 1)
            kind = kind.lower()
            if kind == "forge":
                loader_type, loader_version = "forge", version
            elif kind == "fabric":
                loader_type, loader_version = "fabric", version
            elif kind == "neoforge":
                loader_type, loader_version = "neoforge", version
            if item.get("primary"):
                break
        title = (name or manifest.get("name")
                 or os.path.splitext(os.path.basename(pack_path))[0] or "整合包").strip()
        instance = self.config.create_instance(
            title, mc, loader=None,
            summary=("CurseForge 整合包 " + str(manifest.get("version") or ""))[:200],
        )
        task.log("创建实例：" + title)
        try:
            self.config.update_instance(instance["id"], installing=True)
            task.set_stage("安装游戏与加载器")
            resolved_version, resolved_loader = self.minecraft.install_loader(
                mc, loader_type, loader_version, task)
            self.config.update_instance(
                instance["id"], version_id=resolved_version,
                loader={"type": loader_type, "version": resolved_loader} if resolved_loader else None,
            )
            task.set_stage("解压整合包")
            overrides = str(manifest.get("overrides") or "overrides").strip("/") + "/"
            with zipfile.ZipFile(pack_path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    member = info.filename.replace("\\", "/")
                    if member.startswith(overrides):
                        rel = member[len(overrides):]
                    elif member.startswith(("mods/", "config/", "resourcepacks/", "shaderpacks/")):
                        rel = member
                    else:
                        continue
                    self._extract_member(zf, info, instance["dir"], rel)
            task.log("CurseForge 外部文件需要 CurseForge 下载，当前已导入 overrides")
            self.config.update_instance(instance["id"], installing=False)
            return {"instance_id": instance["id"], "name": title, "minecraft": mc, "loader": loader_type}
        except Exception:
            self.config.delete_instance(instance["id"])
            raise

    def install_plain_zip(self, pack_path, name, task, mc_version="1.20.1"):
        """A plain zip of an instance/game directory."""
        title = (name or os.path.splitext(os.path.basename(pack_path))[0] or "整合包").strip()
        instance = self.config.create_instance(title, mc_version, loader=None,
                                               summary="从 zip 导入")
        task.log("创建实例：" + title)
        try:
            self.config.update_instance(instance["id"], installing=True)
            task.set_stage("安装原版")
            resolved_version, _ = self.minecraft.install_loader(mc_version, "vanilla", None, task)
            self.config.update_instance(instance["id"], version_id=resolved_version)
            task.set_stage("解压 zip")
            with zipfile.ZipFile(pack_path) as zf:
                names = [i.filename.replace("\\", "/") for i in zf.infolist() if not i.is_dir()]
                top = sorted(set(n.split("/", 1)[0] for n in names if "/" in n))
                prefix = top[0] + "/" if len(top) == 1 and all("/" in n for n in names) else ""
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    member = info.filename.replace("\\", "/")
                    if member in ("manifest.json", "modrinth.index.json"):
                        continue
                    if prefix and member.startswith(prefix):
                        rel = member[len(prefix):]
                    elif prefix and "/" not in member:
                        rel = member
                    else:
                        rel = member
                    self._extract_member(zf, info, instance["dir"], rel)
            self.config.update_instance(instance["id"], installing=False)
            return {"instance_id": instance["id"], "name": title, "minecraft": mc_version}
        except Exception:
            self.config.delete_instance(instance["id"])
            raise

    @staticmethod
    def _extract_member(zf, info, dest, rel):
        rel = rel.replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/"):
            return
        target = os.path.normpath(os.path.join(dest, rel.replace("/", os.sep)))
        base = os.path.normpath(dest)
        if not (target == base or target.startswith(base + os.sep)):
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)

    @staticmethod
    def _extract_overrides(zip_path, dest, prefix):
        base = os.path.normpath(dest)
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                name = info.filename
                if info.is_dir() or not name.startswith(prefix):
                    continue
                rel = name[len(prefix):]
                if not rel:
                    continue
                target = os.path.normpath(os.path.join(dest, rel))
                if not (target == base or target.startswith(base + os.sep)):
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
