"""HTTP 与下载。"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .tasks import Cancelled

UA = "SimpleCubeLauncher/0.2 (Minecraft launcher)"

# Mojang 资源镜像（BMCLAPI）
_MIRROR_MAP = (
    ("https://resources.download.minecraft.net/", "https://bmclapi2.bangbang93.com/assets/"),
    ("https://libraries.minecraft.net/", "https://bmclapi2.bangbang93.com/maven/"),
)


def mirror_url(url):
    for src, dst in _MIRROR_MAP:
        if url.startswith(src):
            return dst + url[len(src):]
    return None


def candidates(url, source="auto"):
    mirrored = mirror_url(url)
    if source == "official" or not mirrored:
        return [url]
    if source == "mirror":
        return [mirrored, url]
    return [mirrored, url]


def _request(url, headers=None, timeout=30, data=None):
    merged = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        merged.update(headers)
    return urllib.request.Request(url, data=data, headers=merged)


def fetch(url, headers=None, timeout=30, retries=3):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(_request(url, headers, timeout), timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (400, 401, 403, 404, 410):
                break
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"请求失败：{url}（{last}）")


def fetch_json(url, headers=None, timeout=30, retries=3):
    raw = fetch(url, headers=headers, timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8", "replace"))


def fetch_json_candidates(urls, headers=None, timeout=30):
    last = None
    for url in urls:
        if not url:
            continue
        try:
            return fetch_json(url, headers=headers, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"无法获取数据（{last}）")


def sha1_file(path):
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _parallel_ranges(url, part, size, task, timeout, chunks):
    """Download one big file with several Range connections."""
    chunks = max(2, int(chunks))
    chunk_size = (size + chunks - 1) // chunks
    ranges = []
    for index in range(chunks):
        start = index * chunk_size
        if start >= size:
            break
        ranges.append((index, start, min(size - 1, start + chunk_size - 1)))
    def work(item):
        index, start, end = item
        if task is not None:
            task.check_cancel()
        headers = {"Range": "bytes=%d-%d" % (start, end), "Accept-Encoding": "identity"}
        with urllib.request.urlopen(_request(url, headers=headers, timeout=timeout),
                                    timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 206:
                raise IOError("服务器不支持分段下载")
            data = resp.read()
        if len(data) != end - start + 1:
            raise IOError("分段长度不符")
        path = "%s.%d" % (part, index)
        with open(path, "wb") as out:
            out.write(data)
        if task is not None:
            task.add_progress(len(data))
        return path

    with ThreadPoolExecutor(max_workers=len(ranges)) as pool:
        futures = [pool.submit(work, item) for item in ranges]
        for future in futures:
            future.result()
    # merge in index order
    with open(part, "wb") as out:
        for index, _, _ in ranges:
            path = "%s.%d" % (part, index)
            with open(path, "rb") as src:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
            try:
                os.remove(path)
            except OSError:
                pass


def download_file(url, dest, task=None, sha1=None, size=None, source="auto",
                  label=None, retries=3, timeout=60, alt_urls=None, parallel_chunks=0):
    """下载到 dest；带缓存命中、镜像回退、哈希校验。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest):
        if (size is None or os.path.getsize(dest) == size) and not sha1:
            if task is not None and size:
                task.add_progress(size)
            return dest
        if size is None or os.path.getsize(dest) == size:
            if sha1_file(dest) == sha1:
                if task is not None and size:
                    task.add_progress(size)
                return dest
        try:
            os.remove(dest)
        except OSError:
            pass

    last = None
    urls = candidates(url, source)
    for extra in (alt_urls or []):
        if extra and extra not in urls:
            urls.append(extra)
    part = dest + ".part"
    if parallel_chunks and size and size >= 8 * 1024 * 1024:
        for candidate in urls[:1]:
            try:
                if task is not None:
                    task.check_cancel()
                    if label:
                        task.set_stage(task.stage, label)
                _parallel_ranges(candidate, part, size, task, max(timeout, 90),
                                 parallel_chunks)
                if os.path.getsize(part) != size:
                    raise IOError("文件大小不符")
                if sha1 and sha1_file(part) != sha1:
                    raise IOError("文件 SHA1 校验失败")
                os.replace(part, dest)
                return dest
            except Cancelled:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise
            except Exception:
                for path in [part] + [part + "." + str(i) for i in range(8)]:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
    for attempt in range(retries):
        for candidate in urls:
            if task is not None:
                task.check_cancel()
                if label:
                    task.set_stage(task.stage, label)
            try:
                with urllib.request.urlopen(_request(candidate, timeout=timeout), timeout=timeout) as resp, \
                        open(part, "wb") as out:
                    while True:
                        if task is not None:
                            task.check_cancel()
                        chunk = resp.read(512 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        if task is not None:
                            task.add_progress(len(chunk))
                if size is not None and os.path.getsize(part) != size:
                    raise IOError(f"文件大小不符：{os.path.getsize(part)} != {size}")
                if sha1 and sha1_file(part) != sha1:
                    raise IOError("文件 SHA1 校验失败")
                os.replace(part, dest)
                return dest
            except Cancelled:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise
            except Exception as exc:  # noqa: BLE001
                last = exc
                try:
                    os.remove(part)
                except OSError:
                    pass
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"下载失败：{os.path.basename(dest)}（{last}）")


def get_json(url, headers=None, timeout=30):
    return fetch_json(url, headers=headers, timeout=timeout)
