"""后台任务：进度、日志、取消。"""
import threading
import time
import traceback
import uuid
from collections import deque


class Cancelled(Exception):
    pass


class Task:
    def __init__(self, kind, title):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.status = "running"
        self.stage = "准备中"
        self.message = ""
        self.current = 0
        self.total = 0
        self.unit = "bytes"
        self.logs = deque(maxlen=400)
        self.result = None
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._samples = deque(maxlen=40)

    # ---------- 更新 ----------
    def set_stage(self, stage, message=""):
        with self._lock:
            self.stage = str(stage)
            if message:
                self.message = str(message)

    def set_total(self, total):
        with self._lock:
            self.total = max(0, int(total))

    def add_total(self, delta):
        with self._lock:
            self.total = max(0, self.total + int(delta))

    def set_progress(self, current, total=None):
        with self._lock:
            self.current = max(0, int(current))
            if total is not None:
                self.total = max(0, int(total))
            self._samples.append((time.time(), self.current))

    def add_progress(self, n):
        with self._lock:
            self.current += max(0, int(n))
            self._samples.append((time.time(), self.current))
            while len(self._samples) > 2 and time.time() - self._samples[0][0] > 4:
                self._samples.popleft()

    def log(self, line):
        text = str(line).rstrip()
        if not text:
            return
        with self._lock:
            self.logs.append(text[:600])

    def check_cancel(self):
        if self.cancel_event.is_set():
            raise Cancelled()

    def cancel(self):
        self.cancel_event.set()

    def finish(self, status="success", error=None):
        with self._lock:
            self.status = status
            self.error = error
            self.finished_at = time.time()

    # ---------- 序列化 ----------
    def _speed_locked(self):
        if len(self._samples) >= 2:
            t0, c0 = self._samples[0]
            t1, c1 = self._samples[-1]
            if t1 - t0 > 0.35:
                return max(0.0, (c1 - c0) / (t1 - t0))
        return 0.0

    def snapshot(self):
        with self._lock:
            progress = (self.current / self.total) if self.total else 0.0
            return {
                "id": self.id,
                "kind": self.kind,
                "title": self.title,
                "status": self.status,
                "stage": self.stage,
                "message": self.message,
                "current": self.current,
                "total": self.total,
                "unit": self.unit,
                "progress": min(1.0, max(0.0, progress)),
                "speed": self._speed_locked(),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed": (self.finished_at or time.time()) - self.started_at,
                "error": self.error,
                "result": self.result if isinstance(self.result, (dict, list, str, int, float, bool, type(None))) else None,
                "logs": list(self.logs)[-20:],
            }


class TaskManager:
    def __init__(self):
        self._tasks = {}
        self._order = []
        self._lock = threading.Lock()

    def create(self, kind, title):
        task = Task(kind, title)
        with self._lock:
            self._tasks[task.id] = task
            self._order.append(task.id)
            self._prune_locked()
        return task

    def start(self, kind, title, fn):
        task = self.create(kind, title)

        def runner():
            try:
                task.check_cancel()
                result = fn(task)
                task.result = result
                if task.cancel_event.is_set():
                    task.finish("canceled")
                else:
                    task.finish("success")
            except Cancelled:
                task.log("任务已取消")
                task.finish("canceled")
            except Exception as exc:  # noqa: BLE001
                task.log(traceback.format_exc())
                task.finish("error", str(exc) or exc.__class__.__name__)

        threading.Thread(target=runner, name=f"task-{task.id}", daemon=True).start()
        return task

    def get(self, task_id):
        with self._lock:
            return self._tasks.get(task_id)

    def cancel(self, task_id):
        task = self.get(task_id)
        if task and task.status == "running":
            task.cancel()
            return True
        return False

    def snapshot_all(self):
        with self._lock:
            tasks = [self._tasks[i] for i in self._order if i in self._tasks]
        return [t.snapshot() for t in tasks]

    def _prune_locked(self):
        now = time.time()
        keep = []
        for i in self._order:
            t = self._tasks.get(i)
            if not t:
                continue
            if t.status != "running" and t.finished_at and now - t.finished_at > 3600:
                self._tasks.pop(i, None)
                continue
            keep.append(i)
        while len(keep) > 50:
            drop = keep.pop(0)
            self._tasks.pop(drop, None)
        self._order = keep
