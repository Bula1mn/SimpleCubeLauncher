"""构建启动参数并启动游戏。"""
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import zipfile

from . import __version__
from .java import CREATE_NO_WINDOW, choose_java, detect_java
from .minecraft import maven_path, native_allowed, rules_allow

RUNNING = {}
_RUNNING_LOCK = threading.Lock()


class LaunchError(Exception):
    pass


def offline_uuid(name):
    digest = hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).hexdigest()
    return "-".join((digest[0:8], digest[8:12], digest[12:16], digest[16:20], digest[20:32]))


def read_log(instance_dir, max_chars=6000):
    logs_dir = os.path.join(instance_dir, "logs")
    candidates = []
    for name in ("latest.log", "launcher.log"):
        path = os.path.join(logs_dir, name)
        if os.path.isfile(path):
            try:
                candidates.append((os.path.getmtime(path), path))
            except OSError:
                pass
    if not candidates:
        return ""
    path = max(candidates)[1]
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_chars * 4))
            data = f.read()
        return data.decode("utf-8", "replace")[-max_chars:]
    except OSError:
        return ""


def stop_game(instance_id):
    with _RUNNING_LOCK:
        info = RUNNING.get(instance_id)
    if not info:
        return False
    proc = info.get("proc")
    if proc is None or proc.poll() is not None:
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        return False
    with _RUNNING_LOCK:
        info["alive"] = False
        info["exit_code"] = proc.returncode
    return True


def running_snapshot():
    with _RUNNING_LOCK:
        result = {}
        for iid, info in RUNNING.items():
            proc = info.get("proc")
            alive = bool(info.get("alive"))
            if proc is not None:
                alive = alive and proc.poll() is None
            result[iid] = {
                "pid": proc.pid if proc else None,
                "alive": alive,
                "started_at": info.get("started"),
                "exit_code": info.get("exit_code"),
                "log": info.get("log"),
            }
        return result


class Launcher:
    def __init__(self, config, tasks, minecraft):
        self.config = config
        self.tasks = tasks
        self.minecraft = minecraft

    def launch(self, instance_id, task, account=None):
        inst = self.config.get_instance(instance_id)
        version_id = inst.get("version_id") or inst.get("mc_version")
        task.set_stage("检查版本", version_id)
        merged = self.minecraft.merge_version(version_id)
        required = self.minecraft.required_java(version_id)
        configured = inst.get("java_path") or self.config.data.get("java_path") or ""
        javas = detect_java(self.config.game_root, configured)
        java = choose_java(javas, required, configured)
        if not java:
            raise LaunchError("没有找到 Java，请先在设置页指定 Java 路径")
        if java["major"] and java["major"] < required:
            raise LaunchError("该版本需要 Java %s 或更高，当前为 %s" % (required, java["major"]))
        game_dir = inst["dir"]
        for sub in ("mods", "shaderpacks", "resourcepacks", "saves", "logs"):
            os.makedirs(os.path.join(game_dir, sub), exist_ok=True)
        task.set_stage("准备运行库")
        natives = self._prepare_natives(merged, game_dir)
        classpath, missing = self._classpath(merged)
        if missing:
            raise LaunchError("缺少运行库：" + "、".join(missing[:3]) + (" 等" if len(missing) > 3 else ""))
        task.set_stage("生成启动参数")
        command = self._build_command(merged, java, classpath, natives, game_dir, account,
                                      memory_mb=inst.get("memory_mb"))
        log_path = os.path.join(game_dir, "logs", "launcher.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            log_file.write("Java: " + java["path"] + "\n")
            log_file.write("Version: " + version_id + "\n")
            log_file.write("Command: " + subprocess.list2cmdline(command) + "\n\n")
            log_file.flush()
            proc = subprocess.Popen(
                command, cwd=game_dir, stdout=log_file, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        task.log("已启动，进程 PID %s" % proc.pid)
        task.log("Java：%s" % java["path"])
        with _RUNNING_LOCK:
            RUNNING[instance_id] = {"proc": proc, "started": time.time(), "log": log_path, "alive": True}
        threading.Thread(target=self._watch, args=(instance_id, proc), daemon=True).start()
        self.config.update_instance(instance_id, last_played=int(time.time()))
        time.sleep(1.5)
        code = proc.poll()
        if code is not None and code != 0:
            tail = read_log(game_dir, 2000)
            raise LaunchError("游戏启动后立即退出（代码 %s）。\n%s" % (code, tail))
        task.set_stage("游戏运行中")

    @staticmethod
    def _watch(instance_id, proc):
        code = proc.wait()
        with _RUNNING_LOCK:
            info = RUNNING.get(instance_id)
            if info:
                info["alive"] = False
                info["exit_code"] = code
                info["ended"] = time.time()
        time.sleep(120)
        with _RUNNING_LOCK:
            info = RUNNING.get(instance_id)
            if info and not info.get("alive"):
                RUNNING.pop(instance_id, None)

    def _prepare_natives(self, merged, game_dir):
        natives = os.path.join(game_dir, "natives")
        if os.path.isdir(natives):
            try:
                shutil.rmtree(natives)
            except OSError:
                # 上一个进程可能还占用着 DLL，换一个目录
                natives = os.path.join(game_dir, "natives-%d" % int(time.time()))
        os.makedirs(natives, exist_ok=True)
        for name in os.listdir(game_dir):
            if name.startswith("natives-"):
                old = os.path.join(game_dir, name)
                if os.path.abspath(old) != os.path.abspath(natives):
                    shutil.rmtree(old, ignore_errors=True)
        libs_root = self.config.path_in("libraries")
        for lib in merged.get("libraries") or []:
            if not isinstance(lib, dict) or not rules_allow(lib.get("rules")):
                continue
            if not native_allowed(lib.get("name")):
                continue
            downloads = lib.get("downloads") or {}
            rel = None
            natives_map = lib.get("natives") or {}
            key = natives_map.get("windows")
            if key:
                info = (downloads.get("classifiers") or {}).get(str(key).replace("$" + "{arch}", "64"))
                if info:
                    rel = info.get("path")
            if not rel:
                name = lib.get("name") or ""
                if ":natives-windows" in name:
                    rel = (downloads.get("artifact") or {}).get("path")
            if not rel:
                continue
            jar = os.path.join(libs_root, rel)
            if not os.path.isfile(jar):
                continue
            try:
                with zipfile.ZipFile(jar) as zf:
                    for item in zf.namelist():
                        low = item.lower()
                        if item.endswith("/") or low.startswith("meta-inf/"):
                            continue
                        if not low.endswith((".dll", ".so", ".dylib")):
                            continue
                        target = os.path.join(natives, os.path.basename(item))
                        with zf.open(item) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            except zipfile.BadZipFile:
                continue
        return natives

    def _classpath(self, merged):
        libs_root = self.config.path_in("libraries")
        entries, seen, missing = [], set(), []
        for lib in merged.get("libraries") or []:
            if not isinstance(lib, dict) or not rules_allow(lib.get("rules")):
                continue
            name = lib.get("name") or ""
            if re.search(r":natives-[^:]+", name):
                continue
            art = (lib.get("downloads") or {}).get("artifact") or {}
            rel = art.get("path") or maven_path(name)
            if not rel:
                continue
            path = os.path.join(libs_root, rel)
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            if os.path.isfile(path):
                entries.append(path)
            else:
                missing.append(rel)
        base = merged.get("_base") or merged.get("id")
        jar = os.path.join(self.config.path_in("versions", base), base + ".jar")
        if os.path.isfile(jar):
            entries.append(jar)
        else:
            missing.append(base + ".jar")
        return entries, missing

    def _build_command(self, merged, java, classpath, natives, game_dir, account=None,
                       memory_mb=None):
        cfg = self.config
        data = cfg.public()
        memory = int(memory_mb or data.get("memory_mb") or 4096)
        base = merged.get("_base") or merged.get("id")
        asset_index = (merged.get("assetIndex") or {}).get("id") or "legacy"
        account = account or {}
        player_name = str(account.get("name") or cfg.player_name)
        account_uuid = str(account.get("uuid") or offline_uuid(player_name))
        access_token = str(account.get("access_token") or "0")
        user_type = str(account.get("user_type") or "legacy")
        xuid = str(account.get("xuid") or "0")
        client_id = str(account.get("client_id") or "0")
        ctx = {
            "auth_player_name": player_name,
            "version_name": merged.get("id") or base,
            "game_directory": game_dir,
            "assets_root": cfg.path_in("assets"),
            "assets_index_name": asset_index,
            "auth_uuid": account_uuid,
            "auth_access_token": access_token,
            "clientid": client_id,
            "auth_xuid": xuid,
            "user_type": user_type,
            "version_type": merged.get("type") or "release",
            "natives_directory": natives,
            "launcher_name": "Simple Cube Launcher",
            "launcher_version": __version__,
            "classpath": os.pathsep.join(classpath),
            "classpath_separator": os.pathsep,
            "library_directory": cfg.path_in("libraries"),
            "resolution_width": str(data.get("width") or 960),
            "resolution_height": str(data.get("height") or 540),
            "user_properties": "{}",
            "game_assets": "",
        }
        jvm_args = ["-Xms%dM" % min(512, memory), "-Xmx%dM" % memory]
        if java["major"] >= 9:
            jvm_args.append("-XX:+UseG1GC")
        jvm_args.extend(["-Dfile.encoding=UTF-8", "-Dminecraft.launcher.brand=SimpleCubeLauncher",
                         "-Dminecraft.launcher.version=" + __version__])
        arguments = merged.get("arguments")
        if isinstance(arguments, dict) and (arguments.get("game") or arguments.get("jvm")):
            jvm_args.extend(self._resolve(arguments.get("jvm") or [], ctx))
            game_args = self._resolve(arguments.get("game") or [], ctx)
        else:
            game_args = self._legacy_args(merged.get("minecraftArguments") or "", ctx)
            jvm_args.extend([
                "-Djava.library.path=" + natives,
                "-cp", ctx["classpath"],
            ])
        if not any(arg in ("-cp", "-classpath") for arg in jvm_args):
            jvm_args.extend(["-cp", ctx["classpath"]])
        if not any(str(arg).startswith("-Djava.library.path=") for arg in jvm_args):
            jvm_args.append("-Djava.library.path=" + natives)
        logging = (merged.get("logging") or {}).get("client") or {}
        argument = logging.get("argument")
        file_id = (logging.get("file") or {}).get("id")
        if argument and file_id:
            path = cfg.path_in("assets", "log_configs", file_id)
            if os.path.isfile(path):
                jvm_args.append(str(argument).replace("${path}", path))
        jvm_args.extend(["-Dlog4j2.formatMsgNoLookups=true",
                         "-Dfml.ignoreInvalidMinecraftCertificates=true",
                         "-Dfml.ignorePatchDiscrepancies=true"])
        if "--width" not in game_args:
            game_args.extend(["--width", str(data.get("width") or 960)])
        if "--height" not in game_args:
            game_args.extend(["--height", str(data.get("height") or 540)])
        main_class = merged.get("mainClass")
        if not main_class:
            raise LaunchError("版本缺少 mainClass，无法启动")
        # Forge / NeoForge 的 BootstrapLauncher 会把 classpath 上的原版 jar 也当成模块，
        # 导致 "module minecraft contains package ..." 冲突；把原版 jar 加入 ignoreList。
        if "bootstraplauncher" in str(main_class).lower():
            base_jar = (merged.get("_base") or base) + ".jar"
            for index, arg in enumerate(jvm_args):
                if isinstance(arg, str) and arg.startswith("-DignoreList="):
                    if base_jar not in arg:
                        jvm_args[index] = arg + "," + base_jar
                    break
        return [java["path"]] + jvm_args + [main_class] + game_args

    def _resolve(self, args, ctx):
        out = []
        for item in args:
            if isinstance(item, str):
                out.append(self._sub(item, ctx))
            elif isinstance(item, dict):
                if not rules_allow(item.get("rules")):
                    continue
                value = item.get("value")
                if isinstance(value, str):
                    value = [value]
                for part in value or []:
                    out.append(self._sub(str(part), ctx))
        return out

    def _legacy_args(self, text, ctx):
        if not text:
            return []
        replaced = self._sub(text, ctx)
        try:
            parts = shlex.split(replaced, posix=False)
        except ValueError:
            parts = replaced.split()
        return [part.strip('"') for part in parts]

    @staticmethod
    def _sub(text, ctx):
        for key, value in ctx.items():
            text = text.replace("$" + "{" + key + "}", str(value))
        return text
