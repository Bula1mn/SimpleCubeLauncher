"""Build a portable .mrpack from an installed instance."""
import json
import os
import re
import zipfile


def _safe(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "")).strip().strip(".")[:100]


def _loader_dependency(instance):
    loader = str(instance.get("loader") or "").lower()
    version_id = str(instance.get("version_id") or "")
    major = str(instance.get("mc_version") or "")
    key = None
    if "neoforge" in loader or "neoforge" in version_id.lower():
        key = "neoforge"
        match = re.search(r"neoforge[-_ ]([0-9][0-9A-Za-z.\-+]*)", version_id, re.I)
    elif "forge" in loader or "forge" in version_id.lower():
        key = "forge"
        match = re.search(r"forge[-_ ]([0-9][0-9A-Za-z.\-+]*)", version_id, re.I)
    elif "fabric" in loader or "fabric" in version_id.lower():
        key = "fabric-loader"
        match = re.search(r"fabric[-_ ]loader[-_ ]([0-9][0-9A-Za-z.\-+]*)", version_id, re.I)
        if not match:
            match = re.search(r"fabric[-_ ]([0-9][0-9A-Za-z.\-+]*)", version_id, re.I)
    if not key:
        return {}
    value = match.group(1) if match else ""
    if key == "fabric-loader" and value and major and value.endswith("-" + major):
        value = value[:-(len(major) + 1)]
    return {key: value} if value else {}


def pack_instance(instance, output_path, name, version, include_saves=False, progress=None):
    instance_dir = instance.get("dir")
    if not instance_dir or not os.path.isdir(instance_dir):
        raise RuntimeError("实例目录不存在")
    output_path = str(output_path or "").strip()
    if not output_path.lower().endswith(".mrpack"):
        output_path += ".mrpack"
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    name = str(name or instance.get("name") or "SCL Pack").strip()
    version = str(version or "1.0.0").strip()
    mc_version = str(instance.get("mc_version") or "1.20.1")
    dependencies = {"minecraft": mc_version}
    dependencies.update(_loader_dependency(instance))
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": version,
        "name": name,
        "summary": "Packed by Simple Cube Launcher",
        "files": [],
        "dependencies": dependencies,
    }

    include_dirs = ["mods", "config", "resourcepacks", "shaderpacks"]
    if include_saves:
        include_dirs.append("saves")
    entries = []
    for directory in include_dirs:
        root = os.path.join(instance_dir, directory)
        if not os.path.isdir(root):
            continue
        for base, _, files in os.walk(root):
            for filename in files:
                full = os.path.join(base, filename)
                rel = os.path.relpath(full, instance_dir).replace("\\", "/")
                entries.append((full, rel))
    for filename in ("options.txt", "servers.dat"):
        full = os.path.join(instance_dir, filename)
        if os.path.isfile(full):
            entries.append((full, filename))
    icon = str(instance.get("icon") or "")
    if icon and os.path.isfile(icon):
        entries.append((icon, "icon.png"))

    total = len(entries)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("modrinth.index.json",
                         json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
        for index_no, (full, rel) in enumerate(entries, 1):
            archive.write(full, "overrides/" + rel)
            if progress:
                progress(index_no, total)
    return output_path, total, dependencies
