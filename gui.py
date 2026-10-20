"""SCL - 原生 Tk 桌面界面。"""
import os
import sys
import threading
import time
import shutil
import queue
import hashlib
import zipfile
import subprocess
import urllib.parse
import ctypes
import datetime
import webbrowser
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

if getattr(sys, "frozen", False):
    CODE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    CODE_DIR = os.path.dirname(os.path.abspath(__file__))
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)


def _pick_data_dir():
    if not getattr(sys, "frozen", False):
        return CODE_DIR
    if os.path.isdir(os.path.join(CODE_DIR, "game")) or \
            os.path.isfile(os.path.join(CODE_DIR, "portable.txt")):
        return CODE_DIR
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, "SimpleCubeLauncher")


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", CODE_DIR)
    return os.path.join(base, *parts)


DATA_DIR = _pick_data_dir()
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    pass

from launcher.config import Config
from launcher.tasks import TaskManager
from launcher.minecraft import Minecraft
from launcher.modrinth import Modrinth
from launcher.launch import Launcher, read_log, running_snapshot, stop_game
from launcher.java import detect_java, choose_java
from launcher.accounts import AccountManager, AccountError
from launcher import microsoft
from launcher.microsoft import MicrosoftError
from launcher import edge_login
from launcher import __version__ as SCL_VERSION
from launcher.pack import pack_instance
from launcher.update import check_update, download_update, apply_update
from launcher.net import fetch as http_fetch
try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    Image = None
    ImageDraw = None
    ImageTk = None
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
except Exception:
    pygame = None

BG = "#F5F7F9"
PANEL = "#FFFFFF"
INK = "#141C17"
MUTED = "#6E7B73"
LINE = "#E2E8E4"
SIDEBAR = "#0D1511"
ACCENT = "#1F9D6A"
ACCENT_DARK = "#147A50"
DANGER = "#D9534F"
FONT_NAME = "Microsoft YaHei UI"

def ft(size=9, bold=False):
    return (FONT_NAME, size, "bold") if bold else (FONT_NAME, size)

def fmt_bytes(value):
    value = float(value or 0)
    if value < 1024:
        return "%d B" % value
    if value < 1024 * 1024:
        return "%.1f KB" % (value / 1024)
    if value < 1024 * 1024 * 1024:
        return "%.1f MB" % (value / 1024 / 1024)
    return "%.2f GB" % (value / 1024 / 1024 / 1024)

def fmt_speed(value):
    return fmt_bytes(value) + "/s" if value else ""

def fmt_num(value):
    value = int(value or 0)
    if value >= 1000000:
        return "%.1fM" % (value / 1000000)
    if value >= 1000:
        return "%.1fk" % (value / 1000)
    return str(value)

def fmt_date(iso):
    return str(iso or "")[:10]

def loader_name(loader):
    if not loader:
        return "原版"
    kind = loader.get("type") if isinstance(loader, dict) else loader
    return {"fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge",
            "quilt": "Quilt", "vanilla": "原版"}.get(kind, kind or "原版")

class ImageStore:
    def __init__(self, app):
        self.app = app
        self.cache = {}
        self.refs = {}
        self.failed = set()
        self.dir = os.path.join(DATA_DIR, "cache", "images")
        try:
            os.makedirs(self.dir, exist_ok=True)
        except OSError:
            pass

    def _load(self, url, size):
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        path = os.path.join(self.dir, digest)
        if not os.path.isfile(path):
            data = http_fetch(url, timeout=40, retries=2)
            with open(path, "wb") as handle:
                handle.write(data)
        image = Image.open(path).convert("RGBA")
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        image.thumbnail(size, resample)
        return image

    def _photo(self, image):
        return ImageTk.PhotoImage(image)

    def set_label(self, label, url, size, letter="?"):
        try:
            label.configure(text=letter or "?")
        except Exception:
            return
        if not url or Image is None or ImageTk is None:
            return
        key = (url, tuple(size))
        if key in self.cache:
            try:
                label.configure(image=self.cache[key], text="")
            except Exception:
                pass
            return
        if url in self.failed:
            return

        def work():
            return key, self._load(url, size)

        def done(result):
            key2, image = result
            try:
                photo = self._photo(image)
            except Exception:
                return
            self.cache[key2] = photo
            self.refs[key2] = photo
            try:
                if label.winfo_exists():
                    label.configure(image=photo, text="")
            except Exception:
                pass

        self.app.background(work, done, lambda exc: self.failed.add(url))

    def set_file(self, label, path, size, letter="?"):
        if not path or Image is None or ImageTk is None:
            return
        if not os.path.isfile(path):
            return
        try:
            key = ("file", os.path.abspath(path), os.path.getmtime(path), tuple(size))
            if key in self.cache:
                label.configure(image=self.cache[key], text="")
                return
            image = Image.open(path).convert("RGBA")
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
            image.thumbnail(size, resample)
            photo = ImageTk.PhotoImage(image)
            self.cache[key] = photo
            self.refs[key] = photo
            label.configure(image=photo, text="")
        except Exception:
            pass

    def photo(self, url, size, callback):
        key = (url, tuple(size))
        if key in self.cache:
            callback(self.cache[key])
            return

        def work():
            return key, self._load(url, size)

        def done(result):
            key2, image = result
            try:
                photo = self._photo(image)
            except Exception:
                return
            self.cache[key2] = photo
            self.refs[key2] = photo
            callback(photo)

        self.app.background(work, done, lambda exc: None)


class MusicPlayer:
    def __init__(self, config):
        self.config = config
        self.available = pygame is not None
        self.ready = False
        self.playing = False
        self.path = ""
        self.volume = int(config.data.get("music_volume") or 55) / 100.0

    def _ensure(self):
        if not self.available:
            return False
        if not self.ready:
            try:
                pygame.mixer.init()
                self.ready = True
            except Exception:
                self.available = False
        return self.ready

    def load(self, path, play=False):
        if not self._ensure() or not path or not os.path.isfile(path):
            return False
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            self.path = path
            if play:
                self.play()
            return True
        except Exception:
            return False

    def play(self):
        if not self._ensure() or not self.path:
            return
        try:
            pygame.mixer.music.play(-1)
            self.playing = True
        except Exception:
            self.playing = False

    def pause(self):
        if not self.ready:
            return
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass
        self.playing = False

    def unpause(self):
        if not self.ready:
            return
        try:
            pygame.mixer.music.unpause()
            self.playing = True
        except Exception:
            self.playing = False

    def toggle(self):
        if self.playing:
            self.pause()
        elif self.path:
            self.unpause() if pygame and pygame.mixer.music.get_busy() else self.play()

    def set_volume(self, percent):
        self.volume = max(0.0, min(1.0, float(percent) / 100.0))
        if self.ready:
            try:
                pygame.mixer.music.set_volume(self.volume)
            except Exception:
                pass

    def stop(self):
        if self.ready:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self.playing = False


class RoundedButton(tk.Canvas):
    """A flat, rounded button rendered on a Canvas."""
    def __init__(self, master=None, cnf=None, **kwargs):
        cnf = dict(cnf or {})
        cnf.update(kwargs)
        self._text = str(cnf.pop("text", ""))
        self._fg = cnf.pop("fg", cnf.pop("foreground", INK))
        self._bg = cnf.pop("bg", cnf.pop("background", None))
        if not self._bg:
            try:
                self._bg = master.cget("bg")
            except Exception:
                self._bg = PANEL
        self._active_bg = cnf.pop("activebackground", self._bg)
        self._active_fg = cnf.pop("activeforeground", self._fg)
        self._disabled_fg = cnf.pop("disabledforeground", "#9aa79e")
        self._font_spec = cnf.pop("font", ft(9))
        self._padx = int(cnf.pop("padx", 8) or 0)
        self._pady = int(cnf.pop("pady", 4) or 0)
        self._width_chars = cnf.pop("width", None)
        self._height_chars = cnf.pop("height", None)
        self._anchor = cnf.pop("anchor", "center")
        self._command = cnf.pop("command", None)
        self._state = cnf.pop("state", "normal")
        self._cursor = cnf.pop("cursor", "hand2")
        self._radius = int(cnf.pop("radius", 9))
        for key in ("relief", "bd", "borderwidth", "highlightbackground", "highlightcolor",
                    "highlightthickness", "activebackground", "activeforeground",
                    "overrelief", "takefocus", "justify", "wraplength", "compound",
                    "image", "textvariable", "underline", "default", "offvalue", "onvalue",
                    "indicatoron", "selectcolor", "selectimage", "troughcolor"):
            cnf.pop(key, None)
        try:
            self._font = tkfont.Font(font=self._font_spec)
        except Exception:
            self._font = tkfont.Font(family="Segoe UI", size=9)
        self._hover = False
        cnf.pop("state", None)
        super().__init__(master, bg=self._bg, bd=0, highlightthickness=0,
                         cursor=self._cursor, **cnf)
        self._requested = self._natural_size()
        self.configure(width=self._requested[0], height=self._requested[1])
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _natural_size(self):
        text_w = self._font.measure(self._text) if self._text else 0
        line_h = self._font.metrics("linespace")
        char_w = self._font.measure("0") or 7
        width = text_w + self._padx * 2 + 8
        height = line_h + self._pady * 2 + 6
        if self._width_chars:
            try:
                width = max(width, int(self._width_chars) * char_w + self._padx * 2)
            except Exception:
                pass
        if self._height_chars:
            try:
                height = max(height, int(self._height_chars) * line_h + self._pady * 2)
            except Exception:
                pass
        return max(28, int(width)), max(24, int(height))

    def _draw(self):
        try:
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            self.delete("all")
            fill = self._active_bg if (self._hover and self._state != "disabled") else self._bg
            radius = max(3, min(self._radius, height // 2))
            x1, y1, x2, y2 = 1, 1, width - 1, height - 1
            points = [
                x1 + radius, y1, x2 - radius, y1, x2, y1 + radius,
                x2, y2 - radius, x2 - radius, y2, x1 + radius, y2,
                x1, y2 - radius, x1, y1 + radius,
            ]
            self.create_polygon(points, smooth=True, splinesteps=18,
                                fill=fill, outline="")
            fg = self._disabled_fg if self._state == "disabled" else (
                self._active_fg if self._hover else self._fg)
            if self._anchor == "w":
                tx, anchor = self._padx, "w"
            elif self._anchor == "e":
                tx, anchor = width - self._padx, "e"
            else:
                tx, anchor = width // 2, "center"
            self.create_text(tx, height // 2, text=self._text, fill=fg,
                             font=self._font_spec, anchor=anchor)
        except Exception:
            pass

    def _on_enter(self, event=None):
        self._hover = True
        self._draw()

    def _on_leave(self, event=None):
        self._hover = False
        self._draw()

    def _on_press(self, event=None):
        if self._state != "disabled":
            self._hover = True
            self._draw()

    def _on_release(self, event=None):
        inside = True
        if event is not None:
            try:
                inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
            except Exception:
                inside = False
        self._hover = inside
        self._draw()
        if inside and self._state != "disabled" and callable(self._command):
            try:
                self._command()
            except Exception:
                pass

    def configure(self, cnf=None, **kwargs):
        cnf = dict(cnf or {})
        cnf.update(kwargs)
        redraw = False
        if "text" in cnf:
            self._text = str(cnf.pop("text") or "")
            redraw = True
        if "fg" in cnf or "foreground" in cnf:
            self._fg = cnf.pop("fg", cnf.pop("foreground", self._fg))
            redraw = True
        if "bg" in cnf or "background" in cnf:
            self._bg = cnf.pop("bg", cnf.pop("background", self._bg))
            try:
                super().configure(bg=self._bg)
            except Exception:
                pass
            redraw = True
        if "activebackground" in cnf:
            self._active_bg = cnf.pop("activebackground")
            redraw = True
        if "activeforeground" in cnf:
            self._active_fg = cnf.pop("activeforeground")
            redraw = True
        if "state" in cnf:
            self._state = cnf.pop("state")
            redraw = True
        if "font" in cnf:
            self._font_spec = cnf.pop("font")
            try:
                self._font = tkfont.Font(font=self._font_spec)
            except Exception:
                pass
            redraw = True
        if "command" in cnf:
            self._command = cnf.pop("command")
        if "cursor" in cnf:
            self._cursor = cnf.pop("cursor")
            try:
                super().configure(cursor=self._cursor)
            except Exception:
                pass
        for key in ("relief", "bd", "borderwidth", "highlightbackground", "highlightthickness",
                    "overrelief", "takefocus", "justify", "wraplength", "compound", "image",
                    "textvariable"):
            cnf.pop(key, None)
        if cnf:
            try:
                super().configure(**cnf)
            except Exception:
                pass
        if redraw:
            req = self._natural_size()
            self.configure(width=req[0], height=req[1])
            self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        if key in ("bg", "background"):
            return self._bg
        if key in ("fg", "foreground"):
            return self._fg
        return super().cget(key)

    def __setitem__(self, key, value):
        self.configure({key: value})

    def invoke(self):
        if self._state != "disabled" and callable(self._command):
            self._command()

    def flash(self):
        self._on_press()
        self.after(90, self._on_leave)

    def lift(self, aboveThis=None):
        try:
            if aboveThis is None:
                self.tk.call("raise", self._w)
            else:
                self.tk.call("raise", self._w, aboveThis)
        except Exception:
            pass


NativeButton = tk.Button
tk.Button = RoundedButton


class InlineDialog(tk.Frame):
    """An in-app modal card; never creates another OS window."""
    def __init__(self, app, width=640, height=560):
        self.app = app
        self._alive = True
        existing = getattr(app, "inline_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.destroy()
            except Exception:
                pass
        app.inline_dialog = self
        self._card_w = int(width)
        self._card_h = int(height)
        self.layer = tk.Frame(app, bg=BG)
        self.layer.place(relx=0, rely=0, relwidth=1, relheight=1)
        super().__init__(self.layer, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        self.place(relx=0.5, rely=0.5, anchor="center")
        self._apply_size()
        self.title_text = ""
        self.close_button = tk.Button(
            self, text="×", command=self.destroy, bg="#111512", fg="white",
            activebackground="#c0392b", activeforeground="white", relief="flat", bd=0,
            highlightthickness=0, padx=6, pady=0, cursor="hand2",
            font=("Segoe UI", 12, "bold"))
        self.close_button.place(relx=1.0, x=-8, y=8, anchor="ne")
        self.close_button.lift()
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_set()
        self._animate_pop()

    def _animate_pop(self):
        if not hasattr(self, "_full_w"):
            return
        steps = 5

        def step(index):
            if not self._alive:
                return
            ratio = 0.92 + 0.08 * index / steps
            try:
                self.place_configure(width=int(self._full_w * ratio),
                                     height=int(self._full_h * ratio))
            except Exception:
                return
            if index < steps:
                self.after(10, lambda: step(index + 1))
        step(0)

    def _apply_size(self):
        try:
            aw = max(520, self.app.winfo_width())
            ah = max(420, self.app.winfo_height())
        except Exception:
            aw, ah = 1180, 780
        width = min(self._card_w, aw - 36)
        height = min(self._card_h, ah - 36)
        self._full_w = max(320, width)
        self._full_h = max(260, height)
        self.place_configure(width=self._full_w, height=self._full_h)

    def geometry(self, spec=None):
        if not spec:
            return ""
        text = str(spec).split("+")[0]
        if "x" in text:
            try:
                width, height = text.split("x", 1)
                self._card_w = int(width)
                self._card_h = int(height)
                self._apply_size()
            except Exception:
                pass
        return ""

    def title(self, text=None):
        if text is not None:
            self.title_text = str(text)
        return self.title_text

    def transient(self, *args, **kwargs):
        return None

    def grab_set(self, *args, **kwargs):
        return None

    def grab_release(self, *args, **kwargs):
        return None

    def resizable(self, *args, **kwargs):
        return None

    def protocol(self, *args, **kwargs):
        return None

    def attributes(self, *args, **kwargs):
        return None

    def wm_attributes(self, *args, **kwargs):
        return None

    def iconphoto(self, *args, **kwargs):
        return None

    def wait_window(self, *args, **kwargs):
        return None

    def winfo_exists(self):
        return 1 if self._alive else 0

    def destroy(self):
        if not self._alive:
            return
        self._alive = False
        try:
            self.layer.destroy()
        except Exception:
            pass
        if getattr(self.app, "inline_dialog", None) is self:
            self.app.inline_dialog = None


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simple Cube Launcher")
        self.geometry("1180x780")
        if "--debug" in sys.argv:
            self.geometry("1180x780+40+40")
        self.minsize(900, 600)
        self.overrideredirect(True)
        self._zoomed = False
        self._resize_origin = None
        self._fade_busy = False
        self._startup_done = False
        self._startup_geom = None
        self._startup_animating = False
        self._settings_loading = False
        self._settings_after = None
        self.update_manifest = None
        self._resize_job = None
        self._edge_mode = None
        self._edge_origin = None
        self._edge_target = None
        self._edge_job = None
        self._edge_cursor = ""
        self.configure(bg=BG)
        self._setup_styles()
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        try:
            self._icon_image = tk.PhotoImage(file=resource_path("assets", "icon.png"))
            self.iconphoto(True, self._icon_image)
        except Exception:
            self._icon_image = None

        self.config_obj = Config(DATA_DIR)
        global ACCENT, ACCENT_DARK
        accents = {"green": ("#1F9D6A", "#147A50"),
                   "blue": ("#2D6BEA", "#1F4FC0"),
                   "purple": ("#7A57D1", "#5A3EAD")}
        ACCENT, ACCENT_DARK = accents.get(self.config_obj.data.get("accent"), accents["green"])
        self.accounts = AccountManager(DATA_DIR, self.config_obj)
        self.images = ImageStore(self)
        self.music = MusicPlayer(self.config_obj)
        self.tasks = TaskManager()
        self.minecraft = Minecraft(self.config_obj, self.tasks)
        self.modrinth = Modrinth(self.config_obj, self.tasks, self.minecraft)
        self.launcher = Launcher(self.config_obj, self.tasks, self.minecraft)

        self.ui_queue = queue.Queue()
        self.instances = []
        self.javas = []
        self.java_map = {}
        self.running = {}
        self.selected_id = ""
        self.required_cache = {}
        self.instance_sig = None
        self.version_cache = {}
        self.release_versions = []
        self.versions_loading = False
        self.seen_tasks = set()
        self.active_task_id = None
        self.current_page = "home"
        self.task_win = None
        self.account_dialog_ref = None
        self._hero_after = None
        self._hero_widgets = []
        self.settings_canvas = None
        self.device_window = None
        self.device_data = None
        self.device_polling = False
        self.last_log = ""
        self.log_target = None
        self.poll_count = 0
        self.last_disk_check = 0
        self.free_gb = None

        self._build_style()
        self._build_shell()
        self._build_home()
        self._build_download()
        self._build_settings()
        if not self.config_obj.data.get("show_home_log", True):
            self.log_box.grid_remove()
        self.update_account_display()
        self.show_page("home")
        self.refresh_instances()
        self.reload_javas()
        self.load_versions()
        try:
            self.attributes("-alpha", float(self.config_obj.data.get("window_alpha") or 1.0))
        except Exception:
            pass
        self.report_callback_exception = self._on_callback_exception
        self.after(200, self._apply_borderless)

        self.after(500, self.enable_file_drop)
        self.after(250, self._bind_edge_resize)
        self.after(2200, self._auto_check_updates)
        self.after(60000, self._tick_greeting)
        self.after(900, self.autoplay_music)
        self.after(300, self.poll_loop)
        if "--debug" in sys.argv:
            self.after(1500, self._print_rect)
        if "--debug-download" in sys.argv:
            self.after(1300, self._debug_download)
        if "--debug-settings" in sys.argv:
            self.after(1300, self._debug_settings)
        if "--debug-home" in sys.argv:
            self.after(1300, self._debug_home)
        if "--debug-settings-bottom" in sys.argv:
            self.after(1300, self._debug_settings_bottom)
        if "--debug-account" in sys.argv:
            self.after(1300, self._debug_account)
        if "--debug-login" in sys.argv:
            self.after(1300, lambda: self.device_login_dialog())
        if "--selftest" in sys.argv:
            self.withdraw()
            self.after(1200, self._selftest_start)
            self.after(7500, self._selftest_report)
        if "--selftest-ui" in sys.argv:
            self.withdraw()
            self.after(1200, self._ui_selftest_start)
            self.after(12000, self._ui_selftest_report)

    def _on_callback_exception(self, exc, value, tb):
        try:
            with open(os.path.join(DATA_DIR, "gui-error.log"), "a", encoding="utf-8") as handle:
                import traceback
                handle.write(time.strftime("%Y-%m-%d %H:%M:%S") + chr(10))
                handle.write("".join(traceback.format_exception(exc, value, tb)) + chr(10))
        except Exception:
            pass
        try:
            self.task_label.configure(text="操作失败：%s" % str(value)[:100])
        except Exception:
            pass

    def _print_rect(self):
        print("RECT", self.winfo_rootx(), self.winfo_rooty(),
              self.winfo_width(), self.winfo_height(), flush=True)

    def _debug_download(self):
        self.show_page("download")
        self.notebook.select(1)
        self.lift()
        self.attributes("-topmost", False)
        self.focus_force()
        self.after(1500, self._print_rect)

    def _debug_home(self):
        self.show_page("home")
        self.lift()
        self.attributes("-topmost", False)
        self.focus_force()
        self.after(1500, self._print_rect)

    def _debug_settings_bottom(self):
        self.show_page("settings")
        self.after(800, lambda: self.settings_canvas.yview_moveto(1.0))
        self.lift()
        self.attributes("-topmost", False)
        self.focus_force()
        self.after(1800, self._print_rect)

    def _debug_account(self):
        self.lift()
        self.attributes("-topmost", False)
        self.focus_force()
        self.account_dialog()
        self.after(1000, self._print_rect)

    def _debug_settings(self):
        self.show_page("settings")
        self.lift()
        self.attributes("-topmost", False)
        self.focus_force()
        self.after(1500, self._print_rect)

    def _ui_selftest_start(self):
        self.show_page("download")
        self.notebook.select(1)

    def _ui_selftest_report(self):
        panel = self.content_panels.get("mod")
        cache = 0
        try:
            cache = len(os.listdir(self.images.dir))
        except Exception:
            pass
        settings_ok = True
        settings_error = ""
        try:
            self.show_page("settings")
            self.fill_settings()
        except Exception as exc:
            settings_ok = False
            settings_error = str(exc)[:120]
        report = "SELFTEST-UI hits=%d preview=%s image=%s hero=%s cache=%d music=%s settings=%s %s\n" % (
            len(panel.hits) if panel else -1,
            bool(panel.preview_title.cget("text")) if panel else False,
            bool(panel.preview_image.cget("image")) if panel else False,
            bool(getattr(self, "_hero_photo", None)), cache,
            bool(self.music.available), settings_ok, settings_error)
        try:
            print(report, end="", flush=True)
        except Exception:
            pass
        if "--selftest-file" in sys.argv:
            index = sys.argv.index("--selftest-file")
            if index + 1 < len(sys.argv):
                try:
                    with open(sys.argv[index + 1], "w", encoding="utf-8") as handle:
                        handle.write(report)
                except Exception:
                    pass
        self.destroy()

    def _selftest_start(self):
        self.show_page("download")
        self.notebook.select(1)

    def _selftest_report(self):
        report = "SELFTEST instances=%d versions=%d mods=%d status=%s" % (
            len(self.instances), len(self.version_tree.get_children()),
            len(self.content_panels["mod"].tree.get_children()),
            self.version_status.cget("text")) + chr(10)
        try:
            print(report, end="", flush=True)
        except Exception:
            pass
        if "--selftest-file" in sys.argv:
            index = sys.argv.index("--selftest-file")
            if index + 1 < len(sys.argv):
                try:
                    with open(sys.argv[index + 1], "w", encoding="utf-8") as handle:
                        handle.write(report)
                except Exception:
                    pass
        self.destroy()

    def _setup_styles(self):
        try:
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure(
                "Minimal.Vertical.TScrollbar",
                gripcount=0,
                background="#c7d2c9",
                darkcolor="#c7d2c9",
                lightcolor="#c7d2c9",
                troughcolor=BG,
                bordercolor=BG,
                arrowcolor=BG,
                arrowsize=1,
                relief="flat",
                borderwidth=0,
                width=8,
            )
            style.map(
                "Minimal.Vertical.TScrollbar",
                background=[("active", "#9fb3a5"), ("pressed", "#7f9885")],
            )
            style.configure("TNotebook", background=BG, borderwidth=0)
            style.configure("TNotebook.Tab", padding=(14, 7), background=BG,
                            foreground=MUTED, font=ft(8))
            style.map("TNotebook.Tab", background=[("selected", PANEL)],
                      foreground=[("selected", ACCENT_DARK)])
            style.configure("TCombobox", padding=4)
            style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                            foreground=INK, rowheight=34, font=ft(8), borderwidth=0)
            style.configure("Treeview.Heading", background="#F7FAF8",
                            foreground="#526158", font=ft(8, True), relief="flat",
                            borderwidth=0, padding=6)
            style.map("Treeview", background=[("selected", "#DDF3E7")],
                      foreground=[("selected", "#0E5C39")])
            style.map("Treeview.Heading", background=[("active", "#EFF5F1")])
            style.configure(
                "Flat.TCheckbutton",
                background=PANEL,
                foreground="#5d6a61",
                font=ft(8),
                padding=0,
                relief="flat",
                focuscolor=PANEL,
                indicatorcolor=PANEL,
            )
            style.map(
                "Flat.TCheckbutton",
                background=[("active", PANEL)],
                indicatorcolor=[("selected", ACCENT), ("!selected", PANEL)],
            )
        except Exception:
            pass

    def _bind_edge_resize(self):
        for sequence, handler in (("<Motion>", self._on_edge_motion),
                                  ("<ButtonPress-1>", self._on_edge_press),
                                  ("<B1-Motion>", self._on_edge_drag),
                                  ("<ButtonRelease-1>", self._on_edge_release)):
            try:
                self.bind_all(sequence, handler, add="+")
            except Exception:
                pass

    def _edge_at(self, x, y):
        if self._zoomed or getattr(self, "inline_dialog", None) is not None:
            return ""
        left = self.winfo_rootx()
        top = self.winfo_rooty()
        right = left + self.winfo_width()
        bottom = top + self.winfo_height()
        margin = 7
        horizontal = "w" if x <= left + margin else ("e" if x >= right - margin else "")
        vertical = "n" if y <= top + margin else ("s" if y >= bottom - margin else "")
        return vertical + horizontal

    @staticmethod
    def _edge_cursor_for(mode):
        if mode in ("nw", "se"):
            return "size_nw_se"
        if mode in ("ne", "sw"):
            return "size_ne_sw"
        if mode in ("n", "s"):
            return "sb_v_double_arrow"
        if mode in ("e", "w"):
            return "sb_h_double_arrow"
        return ""

    def _on_edge_motion(self, event=None):
        if event is None:
            return
        mode = self._edge_at(event.x_root, event.y_root)
        cursor = self._edge_cursor_for(mode)
        if cursor != self._edge_cursor:
            self._edge_cursor = cursor
            try:
                self.configure(cursor=cursor or "")
            except Exception:
                pass

    def _on_edge_press(self, event=None):
        if event is None:
            return
        mode = self._edge_at(event.x_root, event.y_root)
        if not mode:
            return
        self._edge_mode = mode
        self._edge_origin = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y(),
                             self.winfo_width(), self.winfo_height())
        self._edge_target = None
        return "break"

    def _on_edge_drag(self, event=None):
        if event is None or not self._edge_mode or not self._edge_origin:
            return
        x0, y0, wx, wy, w0, h0 = self._edge_origin
        dx, dy = event.x_root - x0, event.y_root - y0
        mode = self._edge_mode
        x, y, w, h = wx, wy, w0, h0
        if "e" in mode:
            w = max(900, w0 + dx)
        if "s" in mode:
            h = max(600, h0 + dy)
        if "w" in mode:
            w = max(900, w0 - dx)
            x = wx + (w0 - w)
        if "n" in mode:
            h = max(600, h0 - dy)
            y = wy + (h0 - h)
        self._edge_target = (x, y, w, h)
        if self._edge_job is None:
            self._edge_job = self.after(8, self._apply_edge_resize)
        return "break"

    def _apply_edge_resize(self):
        self._edge_job = None
        if not self._edge_target:
            return
        x, y, w, h = self._edge_target
        try:
            self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        except Exception:
            pass

    def _on_edge_release(self, event=None):
        self._edge_mode = None
        self._edge_origin = None
        self._edge_target = None

    def _apply_window_theme(self):
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            dwm = ctypes.windll.dwmapi
            hwnd = user32.GetAncestor(self.winfo_id(), 2)
            if not hwnd:
                return
            for attr, value in ((20, 1), (35, 0x0020281A), (36, 0x00FFFFFF), (34, 0x0020281A)):
                data = ctypes.c_int(int(value))
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(data), ctypes.sizeof(data))
        except Exception:
            pass

    def _hwnd(self):
        try:
            return ctypes.windll.user32.GetAncestor(self.winfo_id(), 2)
        except Exception:
            return 0

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
        widget.bind("<B1-Motion>", self._drag_window, add="+")
        widget.bind("<ButtonRelease-1>", self._end_window_drag, add="+")
        widget.bind("<Double-Button-1>", lambda e: self._toggle_maximize(), add="+")

    def _start_window_drag(self, event=None):
        if self._zoomed or event is None:
            return
        self._drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_window(self, event=None):
        if event is None or self._zoomed or getattr(self, "_drag_offset", None) is None:
            return
        dx, dy = self._drag_offset
        x = int(event.x_root - dx)
        y = int(event.y_root - dy)
        hwnd = self._hwnd()
        if hwnd:
            try:
                ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)
                return
            except Exception:
                pass
        self.geometry("+%d+%d" % (x, y))

    def _end_window_drag(self, event=None):
        self._drag_offset = None

    def _apply_borderless(self):
        if os.name != "nt":
            return
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, -20)
            style = (style | 0x00040000) & ~0x00000080
            user32.SetWindowLongW(hwnd, -20, style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            pass
        try:
            dwm = ctypes.windll.dwmapi
            corner = ctypes.c_int(2)
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
            border = ctypes.c_int(0x0020281A)
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
        except Exception:
            pass

    def _toggle_maximize(self):
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            if user32.IsZoomed(hwnd):
                user32.ShowWindow(hwnd, 9)
                self._zoomed = False
                self.win_max.configure(text="□")
            else:
                user32.ShowWindow(hwnd, 3)
                self._zoomed = True
                self.win_max.configure(text="❐")
        except Exception:
            pass

    def _minimize_window(self):
        hwnd = self._hwnd()
        if hwnd:
            try:
                ctypes.windll.user32.ShowWindow(hwnd, 6)
            except Exception:
                pass

    def _resize_start(self, event):
        if self._zoomed:
            return
        self._resize_origin = (event.x_root, event.y_root,
                               self.winfo_width(), self.winfo_height())

    def _resize_drag(self, event):
        if not self._resize_origin or self._zoomed:
            return
        x0, y0, w0, h0 = self._resize_origin
        width = max(900, w0 + (event.x_root - x0))
        height = max(600, h0 + (event.y_root - y0))
        self.geometry("%dx%d+%d+%d" % (width, height, self.winfo_x(), self.winfo_y()))

    # ------------------------------------------------------------------ 样式

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 8), font=ft(9),
                        background="#e9ede6", foreground="#536158", borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", "#dff0e4"), ("active", "#eef2ec")],
                  foreground=[("selected", ACCENT_DARK), ("active", "#3f5345")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=INK, rowheight=29, font=ft(9), borderwidth=0)
        style.configure("Treeview.Heading", font=ft(9, True), background="#f0f3ee",
                        foreground="#4c5a51", relief="flat", padding=4)
        style.map("Treeview", background=[("selected", "#dff0e4")],
                  foreground=[("selected", INK)])
        style.configure("TCombobox", padding=4)
        style.configure("Horizontal.TProgressbar", troughcolor="#e9ede6",
                        background=ACCENT, borderwidth=0, thickness=6)

    # ------------------------------------------------------------------ 框架
    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=214)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        brand = tk.Frame(self.sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=18, pady=(22, 28))
        tk.Label(brand, text="S", bg=ACCENT, fg="#0d2114", width=2, height=1,
                 font=ft(16, True)).pack(side="left")
        text_box = tk.Frame(brand, bg=SIDEBAR)
        text_box.pack(side="left", padx=10)
        tk.Label(text_box, text="SCL", bg=SIDEBAR, fg="#e7efe9",
                 font=ft(12, True)).pack(anchor="w")
        tk.Label(text_box, text="MINECRAFT LAUNCHER", bg=SIDEBAR, fg="#8fa096",
                 font=ft(6)).pack(anchor="w")

        self.nav_buttons = {}
        for key, label, symbol in (("home", "主页", "▦"), ("download", "下载", "⬇"),
                                   ("settings", "设置", "⚙")):
            button = tk.Button(
                self.sidebar, text="  %s   %s" % (symbol, label), anchor="w",
                bg=SIDEBAR, fg="#b7c5bc", activebackground="#223027",
                activeforeground="#ffffff", relief="flat", bd=0,
                highlightthickness=0, cursor="hand2", font=ft(10),
                padx=12, pady=9, command=lambda k=key: self.show_page(k),
            )
            button.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[key] = button

        foot = tk.Frame(self.sidebar, bg=SIDEBAR)
        foot.pack(side="bottom", fill="x", padx=14, pady=(0, 14))
        status_line = tk.Frame(foot, bg=SIDEBAR)
        status_line.pack(fill="x", padx=6, pady=(0, 8))
        self.side_dot = tk.Label(status_line, text="●", bg=SIDEBAR, fg="#5bcf83", font=ft(8))
        self.side_dot.pack(side="left")
        self.side_status = tk.Label(status_line, text="就绪", bg=SIDEBAR, fg="#9daaa2", font=ft(8))
        self.side_status.pack(side="left", padx=7)
        tk.Label(foot, text="SCL v0.2.8", bg=SIDEBAR, fg="#65736b",
                 font=ft(7)).pack(anchor="w", padx=6, pady=(0, 8))
        tk.Button(foot, text="退出 SCL", anchor="w", bg=SIDEBAR, fg="#93a29a",
                  activebackground="#223027", activeforeground="#ffffff",
                  relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                  font=ft(8), padx=6, pady=4, command=self.on_close).pack(fill="x")

        account_box = tk.Frame(self.sidebar, bg="#1a2820", highlightbackground="#2d3e33",
                               highlightthickness=1)
        account_box.pack(side="bottom", fill="x", padx=12, pady=(0, 10))
        tk.Label(account_box, text="账号", bg="#1a2820", fg="#8fa096", font=ft(7)).pack(
            anchor="w", padx=10, pady=(8, 0))
        self.side_account_name = tk.Label(account_box, text="离线 · Steve", bg="#1a2820",
                                          fg="#e7efe9", font=ft(9, True), anchor="w")
        self.side_account_name.pack(fill="x", padx=10, pady=(1, 5))
        self.side_account_btn = tk.Button(account_box, text="登录正版", bg=ACCENT, fg="white",
                                          activebackground=ACCENT_DARK, activeforeground="white",
                                          relief="flat", bd=0, highlightthickness=0, padx=8,
                                          pady=5, cursor="hand2", font=ft(8),
                                          command=self.sidebar_account_action)
        self.side_account_btn.pack(fill="x", padx=8, pady=(0, 8))

        self.main = tk.Frame(self, bg=BG)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self.main, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 10))
        header.grid_columnconfigure(0, weight=1)
        self.title_label = tk.Label(header, text="主页", bg=BG, fg=INK, font=ft(20, True))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = tk.Label(header, text="选择一个实例，开始你的世界", bg=BG,
                                       fg=MUTED, font=ft(9))
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        right = tk.Frame(header, bg=BG)
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self.account_btn = tk.Button(right, text="离线 · Steve", bg="#e9f5ed", fg=ACCENT_DARK,
                                     activebackground="#dff0e4", activeforeground=ACCENT_DARK,
                                     relief="flat", bd=0, highlightthickness=0,
                                     padx=11, pady=5, cursor="hand2", font=ft(8),
                                     command=self.account_dialog)
        self.account_btn.pack(side="left", padx=(0, 7))
        self.music_btn = tk.Button(right, text="♪", bg=PANEL, fg="#4b7a5d",
                                   activebackground="#eef4ee", activeforeground=ACCENT_DARK,
                                   relief="flat", bd=0, highlightbackground=LINE,
                                   highlightthickness=1, padx=8, pady=4,
                                   cursor="hand2", font=ft(10), command=self.toggle_music)
        self.music_btn.pack(side="left", padx=(0, 7))
        self.pill_java = tk.Label(right, text="Java 检测中…", bg=PANEL, fg="#536058",
                                  font=ft(8), padx=11, pady=5, highlightbackground=LINE,
                                  highlightthickness=1)
        self.pill_java.pack(side="left", padx=(0, 7))
        self.pill_disk = tk.Label(right, text="磁盘 —", bg=PANEL, fg="#536058",
                                  font=ft(8), padx=11, pady=5, highlightbackground=LINE,
                                  highlightthickness=1)
        self.pill_disk.pack(side="left", padx=(0, 7))
        tk.Button(right, text="刷新", bg=PANEL, fg="#536058", activebackground="#f7f9f6",
                  relief="flat", bd=0, highlightbackground=LINE, highlightthickness=1,
                  padx=12, pady=5, cursor="hand2", font=ft(8),
                  command=self.refresh_all).pack(side="left")
        self.update_btn = tk.Button(right, text="发现更新", bg="#e9f5ed", fg=ACCENT_DARK,
                                    activebackground="#dff0e4", padx=10, pady=5,
                                    cursor="hand2", font=ft(8),
                                    command=self.show_update_dialog)
        self.update_btn.pack_forget()

        controls = tk.Frame(header, bg=BG, highlightthickness=0, bd=0)
        controls.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(10, 0), pady=(0, 2))
        for text, command, close in (("—", self._minimize_window, False),
                                     ("□", self._toggle_maximize, False),
                                     ("×", self.on_close, True)):
            button = tk.Button(controls, text=text, command=command,
                               bg=BG, fg="#111511",
                               activebackground="#f3d7d3" if close else "#e7ece7",
                               activeforeground="#c0392b" if close else "#111511",
                               relief="flat", bd=0, highlightthickness=0,
                               padx=9, pady=5, width=3, cursor="hand2",
                               font=("Segoe UI", 14, "bold"))
            button.pack(side="left", padx=1)
            if text == "—":
                self.win_min = button
            elif text == "□":
                self.win_max = button
            else:
                self.win_close = button

        for widget in (brand, text_box, self.title_label, self.subtitle_label, header):
            self._bind_drag(widget)
        for parent in (brand, text_box):
            for child in parent.winfo_children():
                self._bind_drag(child)

        self.body = tk.Frame(self.main, bg=BG)
        self.body.grid(row=1, column=0, sticky="nsew", padx=28)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for key in ("home", "download", "settings"):
            frame = tk.Frame(self.body, bg=BG)
            frame.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = frame

        bar = tk.Frame(self.main, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        bar.grid(row=2, column=0, sticky="ew", padx=28, pady=(10, 16))
        bar.grid_columnconfigure(1, weight=1)
        self.task_label = tk.Label(bar, text="就绪", bg=PANEL, fg="#5b6a60", font=ft(9), anchor="w")
        self.task_label.grid(row=0, column=0, sticky="w", padx=(12, 10), pady=9)
        self.progress = ttk.Progressbar(bar, mode="determinate", maximum=100, value=0)
        self.progress.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=9)
        self.task_pct = tk.Label(bar, text="", bg=PANEL, fg=MUTED, font=ft(8), width=26, anchor="e")
        self.task_pct.grid(row=0, column=2, sticky="e", padx=(0, 10))
        self.cancel_btn = tk.Button(bar, text="取消", bg="#f6f8f4", fg="#6a776e",
                                    relief="flat", bd=0, highlightthickness=0,
                                    padx=10, pady=4, cursor="hand2", font=ft(8),
                                    state="disabled", command=self.cancel_task)
        self.cancel_btn.grid(row=0, column=3, padx=(0, 8), pady=7)
        tk.Button(bar, text="任务", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightthickness=0, padx=8, pady=4, cursor="hand2", font=ft(8),
                  command=self.show_tasks_window).grid(row=0, column=4, padx=(0, 10), pady=7)

    # ------------------------------------------------------------------ 主页
    def _build_home(self):
        page = self.pages["home"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=0)
        page.grid_rowconfigure(2, weight=1)

        self.hero = tk.Canvas(page, height=186, bg="#15251a", highlightthickness=0)
        self.hero.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.hero.bind("<Configure>", self.on_hero_resize)

        head = tk.Frame(page, bg=BG)
        head.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        head.grid_columnconfigure(0, weight=1)
        tk.Label(head, text="我的实例", bg=BG, fg=INK, font=ft(13, True)).grid(row=0, column=0, sticky="w")
        self.instance_count = tk.Label(head, text="", bg=BG, fg=MUTED, font=ft(8))
        self.instance_count.grid(row=1, column=0, sticky="w")
        tk.Button(head, text="＋ 新建实例", bg=ACCENT, fg="white", activebackground=ACCENT_DARK,
                  activeforeground="white", relief="flat", bd=0, highlightthickness=0,
                  padx=14, pady=7, cursor="hand2", font=ft(9),
                  command=self.new_instance_dialog).grid(row=0, column=1, rowspan=2, sticky="e")

        self.home_canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        self.home_canvas.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(page, style="Minimal.Vertical.TScrollbar", orient="vertical", command=self.home_canvas.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.home_canvas.configure(yscrollcommand=scroll.set)
        self.home_inner = tk.Frame(self.home_canvas, bg=BG)
        self.home_window = self.home_canvas.create_window((0, 0), window=self.home_inner, anchor="nw")
        self.home_inner.bind("<Configure>", lambda e: self.home_canvas.configure(scrollregion=self.home_canvas.bbox("all")))
        self.home_canvas.bind("<Configure>", lambda e: self.home_canvas.itemconfigure(self.home_window, width=e.width))
        self.bind_all("<MouseWheel>", self.on_mousewheel)

        log_box = tk.Frame(page, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        log_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.log_box = log_box
        log_box.grid_columnconfigure(0, weight=1)
        log_head = tk.Frame(log_box, bg=PANEL)
        log_head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 4))
        log_head.grid_columnconfigure(0, weight=1)
        self.log_title = tk.Label(log_head, text="运行日志", bg=PANEL, fg=INK, font=ft(9, True))
        self.log_title.grid(row=0, column=0, sticky="w")
        tk.Button(log_head, text="刷新", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2", font=ft(8),
                  command=lambda: self.refresh_log(True)).grid(row=0, column=1, padx=4)
        tk.Button(log_head, text="打开文件夹", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2", font=ft(8),
                  command=self.open_selected_folder).grid(row=0, column=2, padx=4)
        self.log_text = tk.Text(log_box, height=9, bg="#0f1712", fg="#cfe8d6",
                                insertbackground="#cfe8d6", relief="flat", bd=0,
                                font=("Consolas", 9), wrap="word", state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        log_scroll = ttk.Scrollbar(log_box, style="Minimal.Vertical.TScrollbar", orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 10), padx=(0, 8))
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def on_mousewheel(self, event):
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            return
        canvas = None
        if self.current_page == "home":
            canvas = self.home_canvas
        elif self.current_page == "settings":
            canvas = self.settings_canvas
        if canvas is None:
            return
        node = widget
        while node is not None:
            if node is canvas:
                canvas.yview_scroll(int(-event.delta / 120), "units")
                return
            node = getattr(node, "master", None)

    def refresh_instances(self):
        self.instances = self.config_obj.list_instances()
        ids = [item["id"] for item in self.instances]
        if self.selected_id not in ids:
            self.selected_id = ids[0] if ids else ""
        self.instance_sig = None
        self.build_cards()
        self.refresh_log(True)
        self.render_hero()

    def build_cards(self):
        for child in self.home_inner.winfo_children():
            child.destroy()
        self.instance_count.configure(text="%d 个实例" % len(self.instances) if self.instances else "还没有实例")
        if not self.instances:
            empty = tk.Frame(self.home_inner, bg=BG, highlightbackground="#d5ded4",
                             highlightthickness=1)
            empty.pack(fill="x", pady=(8, 0), ipady=24)
            tk.Label(empty, text="还没有任何实例", bg=BG, fg=INK, font=ft(14, True)).pack(pady=(10, 4))
            tk.Label(empty, text="先安装一个原版游戏，或者直接装一个整合包。", bg=BG,
                     fg=MUTED, font=ft(9)).pack(pady=(0, 12))
            row = tk.Frame(empty, bg=BG)
            row.pack()
            tk.Button(row, text="安装原版", bg=ACCENT, fg="white", relief="flat", bd=0,
                      padx=14, pady=7, cursor="hand2", font=ft(9),
                      command=lambda: self.show_page("download")).pack(side="left", padx=5)
            tk.Button(row, text="浏览整合包", bg=PANEL, fg=INK, relief="flat", bd=0,
                      highlightbackground=LINE, highlightthickness=1, padx=14, pady=7,
                      cursor="hand2", font=ft(9),
                      command=lambda: self.show_page("download")).pack(side="left", padx=5)
            return

        for instance in self.instances:
            self.build_card(instance)

    def build_card(self, instance):
        iid = instance["id"]
        running = bool((self.running.get(iid) or {}).get("alive"))
        selected = iid == self.selected_id
        card = tk.Frame(self.home_inner, bg=PANEL,
                        highlightbackground=ACCENT if selected else LINE,
                        highlightthickness=2 if selected else 1)
        card.pack(fill="x", pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)

        icon_frame = tk.Frame(card, bg="#dff1e4", width=52, height=52)
        icon_frame.grid(row=0, column=0, rowspan=2, padx=(14, 12), pady=14)
        icon_frame.grid_propagate(False)
        letter = (instance.get("name") or "M").strip()[:1].upper() or "M"
        icon_label = tk.Label(icon_frame, text=letter, bg="#dff1e4", fg="#2c6b42",
                              font=ft(17, True))
        icon_label.place(relx=0.5, rely=0.5, anchor="center")
        icon_value = instance.get("icon") or ""
        if icon_value and os.path.isfile(icon_value):
            self.images.set_file(icon_label, icon_value, (52, 52), letter)
        elif icon_value:
            self.images.set_label(icon_label, icon_value, (52, 52), letter)

        name = tk.Label(card, text=instance.get("name") or iid, bg=PANEL, fg=INK,
                        font=ft(11, True), anchor="w")
        name.grid(row=0, column=1, sticky="w", pady=(12, 0))
        meta = tk.Label(card, text="%s  ·  %s" % (instance.get("mc_version") or "?",
                                                  loader_name(instance.get("loader"))),
                        bg=PANEL, fg=MUTED, font=ft(8), anchor="w")
        meta.grid(row=1, column=1, sticky="w", pady=(0, 12))

        required = self.required_for(instance)
        java = choose_java(self.javas, required,
                           instance.get("java_path") or self.config_obj.data.get("java_path", ""))
        if instance.get("installing"):
            status_text, status_color = "正在安装…", "#a56b18"
        elif java is None:
            status_text, status_color = "未找到 Java", DANGER
        elif java["major"] < required:
            status_text, status_color = "需要 Java %d+" % required, DANGER
        else:
            status_text, status_color = "Java %d" % java["major"], ACCENT_DARK
        status = tk.Label(card, text=status_text, bg=PANEL, fg=status_color, font=ft(8))
        status.grid(row=0, column=2, rowspan=2, sticky="e", padx=10)

        actions = tk.Frame(card, bg=PANEL)
        actions.grid(row=0, column=3, rowspan=2, padx=(0, 14))
        if instance.get("installing"):
            tk.Label(actions, text="安装中…", bg=PANEL, fg="#a56b18", font=ft(8)).pack(side="left", padx=6)
        elif running:
            tk.Button(actions, text="停止", bg="#fff6f5", fg=DANGER, activebackground="#fdeeed",
                      relief="flat", bd=0, highlightbackground="#efd3d1", highlightthickness=1,
                      padx=12, pady=6, cursor="hand2", font=ft(8),
                      command=lambda: self.stop_instance(iid)).pack(side="left", padx=4)
        else:
            tk.Button(actions, text="启动", bg=ACCENT, fg="white", activebackground=ACCENT_DARK,
                      activeforeground="white", relief="flat", bd=0, highlightthickness=0,
                      padx=14, pady=6, cursor="hand2", font=ft(8),
                      command=lambda: self.launch_instance(iid)).pack(side="left", padx=4)
        tk.Button(actions, text="详情", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=9, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.open_instance_details(instance)).pack(side="left", padx=4)
        tk.Button(actions, text="目录", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=9, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.open_folder(instance.get("dir"))).pack(side="left", padx=4)
        tk.Button(actions, text="删除", bg=PANEL, fg="#8b978f", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=9, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.delete_instance(instance)).pack(side="left", padx=4)

        for widget in (card, icon_frame, name, meta, status):
            widget.bind("<Button-1>", lambda e, x=iid: self.select_instance(x))

    def select_instance(self, iid):
        if self.selected_id == iid:
            return
        self.selected_id = iid
        self.build_cards()
        self.refresh_log(True)
        self.render_hero()

    def required_for(self, instance):
        version_id = instance.get("version_id") or instance.get("mc_version")
        if version_id not in self.required_cache:
            try:
                self.required_cache[version_id] = self.minecraft.required_java(version_id)
            except Exception:
                self.required_cache[version_id] = 21
        return self.required_cache[version_id]

    def refresh_log(self, force=False):
        iid = self.selected_id
        if not iid:
            alive = [key for key, value in self.running.items() if value.get("alive")]
            iid = alive[0] if alive else ""
        instance = next((item for item in self.instances if item["id"] == iid), None)
        if not instance:
            return
        text = read_log(instance["dir"], 9000)
        running = bool((self.running.get(iid) or {}).get("alive"))
        self.log_title.configure(text="运行日志 · " + (instance.get("name") or iid) +
                                 ("（运行中）" if running else ""))
        if not force and text == self.last_log and self.log_target == iid:
            return
        self.last_log = text
        self.log_target = iid
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", text or "（暂无日志，启动游戏后会显示）")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------ 启停
    def launch_instance(self, iid):
        self.select_instance(iid)
        self.show_page("home")

        def job(task):
            account = self.accounts.launch_account(task)
            task.log("账号：%s（%s）" % (account.get("name"), "正版" if account.get("type") == "msa" else "离线"))
            self.launcher.launch(iid, task, account)

        self.start_task("启动游戏", job, "launch")

    def stop_instance(self, iid):
        self.background(lambda: stop_game(iid), self.after_stop)

    def after_stop(self, ok):
        if ok:
            self.task_label.configure(text="已结束游戏")
        else:
            messagebox.showinfo("结束游戏", "没有找到正在运行的游戏进程。", parent=self)
        self.poll_once()

    def _launch_external(self, args, hidden=False):
        try:
            flags = 0x08000000 if (hidden and os.name == "nt") else 0
            subprocess.Popen(args, close_fds=True, creationflags=flags)
            return True
        except Exception:
            return False

    def open_url(self, url):
        if not url:
            return False
        # 不要用 cmd start 打开带 & 的 URL：cmd 会把 & 当成命令分隔符，
        # 浏览器只拿到 client_id，导致 AADSTS900144 缺少 scope。
        try:
            if webbrowser.open(url, new=2):
                return True
        except Exception:
            pass
        try:
            os.startfile(url)
            return True
        except Exception:
            pass
        try:
            if self._launch_external(["explorer.exe", url]):
                return True
        except Exception:
            pass
        return False

    def open_folder(self, path):
        if not path:
            messagebox.showinfo("打开目录", "目录不存在。", parent=self)
            return
        path = os.path.normpath(path)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        # Explorer 直接打开，避免 os.startfile 在当前权限下抛 WinError 5。
        if self._launch_external(["explorer.exe", path]):
            return
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("打开目录失败",
                                 "无法打开目录：\n%s\n\n%s" % (path, exc), parent=self)

    def open_selected_folder(self):
        instance = next((item for item in self.instances if item["id"] == self.selected_id), None)
        if instance:
            self.open_folder(instance.get("dir"))

    def open_instance_details(self, instance):
        iid = instance.get("id")
        try:
            inst = self.config_obj.get_instance(iid)
        except Exception as exc:
            messagebox.showerror("实例详情", str(exc), parent=self)
            return
        dialog = InlineDialog(self, 680, 650)
        dialog.title("实例详情 / 存档设置")
        dialog.geometry("680x650")
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(dialog, text="实例详情 / 存档设置", bg=PANEL, fg=INK, font=ft(15, True)).pack(
            anchor="w", padx=22, pady=(16, 2))
        tk.Label(dialog, text="%s · %s · %s" % (
            inst.get("mc_version") or "?", loader_name(inst.get("loader")), iid),
            bg=PANEL, fg=MUTED, font=ft(8)).pack(anchor="w", padx=22, pady=(0, 10))

        top = tk.Frame(dialog, bg=PANEL)
        top.pack(fill="x", padx=22)
        icon_holder = tk.Frame(top, bg="#e9f5ed", width=84, height=84)
        icon_holder.pack(side="left")
        icon_holder.pack_propagate(False)
        icon_label = tk.Label(icon_holder, text=(inst.get("name") or "M")[:1].upper(),
                              bg="#e9f5ed", fg="#2c6b42", font=ft(18, True))
        icon_label.place(relx=0.5, rely=0.5, anchor="center")
        icon_var = tk.StringVar(value=inst.get("icon") or "")
        if icon_var.get() and os.path.isfile(icon_var.get()):
            self.images.set_file(icon_label, icon_var.get(), (84, 84), "?")
        elif icon_var.get():
            self.images.set_label(icon_label, icon_var.get(), (84, 84), "?")

        right = tk.Frame(top, bg=PANEL)
        right.pack(side="left", fill="x", expand=True, padx=(14, 0))
        tk.Label(right, text="名称", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w")
        name_var = tk.StringVar(value=inst.get("name") or "")
        tk.Entry(right, textvariable=name_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).pack(
            fill="x", ipady=4, pady=(2, 8))
        tk.Label(right, text="自定义存档图片", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w")
        image_row = tk.Frame(right, bg=PANEL)
        image_row.pack(fill="x", pady=(2, 0))
        image_text = tk.Label(image_row, text=(os.path.basename(icon_var.get()) if icon_var.get() else "未选择"),
                              bg=PANEL, fg=MUTED, font=ft(8), anchor="w")
        image_text.pack(side="left", fill="x", expand=True)
        def choose_image():
            path = filedialog.askopenfilename(
                parent=dialog, title="选择实例图片",
                filetypes=[("图片", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")])
            if not path:
                return
            target = os.path.join(inst["dir"], "icon.png")
            try:
                shutil.copy2(path, target)
            except Exception as exc:
                messagebox.showerror("图片", str(exc), parent=dialog)
                return
            icon_var.set(target)
            image_text.configure(text=os.path.basename(target))
            self.images.set_file(icon_label, target, (84, 84), "?")
        tk.Button(image_row, text="选择图片", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=8, pady=3,
                  cursor="hand2", font=ft(8), command=choose_image).pack(side="right")

        tk.Label(dialog, text="Java 设置", bg=PANEL, fg=INK, font=ft(10, True)).pack(
            anchor="w", padx=22, pady=(14, 2))
        java_row = tk.Frame(dialog, bg=PANEL)
        java_row.pack(fill="x", padx=22)
        tk.Label(java_row, text="Java 路径", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w")
        java_var = tk.StringVar(value=inst.get("java_path") or "")
        tk.Entry(java_row, textvariable=java_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(8)).pack(
            side="left", fill="x", expand=True, ipady=4, pady=(2, 0))
        def choose_java_path():
            path = filedialog.askopenfilename(
                parent=dialog, title="选择 Java",
                filetypes=[("Java", "javaw.exe java.exe"), ("所有文件", "*.*")])
            if path:
                java_var.set(path)
        tk.Button(java_row, text="浏览", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=8, pady=3,
                  cursor="hand2", font=ft(8), command=choose_java_path).pack(side="left", padx=(6, 0), pady=(2, 0))
        mem_row = tk.Frame(dialog, bg=PANEL)
        mem_row.pack(fill="x", padx=22, pady=(5, 0))
        tk.Label(mem_row, text="内存 MB", bg=PANEL, fg="#65736a", font=ft(8)).pack(side="left")
        memory_var = tk.StringVar(value=str(inst.get("memory_mb") or self.config_obj.data.get("memory_mb") or 4096))
        tk.Entry(mem_row, textvariable=memory_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(8), width=10).pack(
            side="left", padx=(8, 0), ipady=4)
        tk.Label(mem_row, text="留空使用全局设置", bg=PANEL, fg=MUTED, font=ft(7)).pack(side="left", padx=8)

        tk.Label(dialog, text="Mod 管理", bg=PANEL, fg=INK, font=ft(10, True)).pack(
            anchor="w", padx=22, pady=(14, 4))
        mods_frame = tk.Frame(dialog, bg=PANEL)
        mods_frame.pack(fill="both", expand=True, padx=22)
        mods_list = tk.Listbox(mods_frame, bg="#fbfcfa", fg=INK, relief="flat",
                               highlightbackground=LINE, highlightthickness=1,
                               font=ft(8), height=6, selectmode="single")
        mods_list.pack(side="left", fill="both", expand=True)
        mods_scroll = ttk.Scrollbar(mods_frame, style="Minimal.Vertical.TScrollbar", orient="vertical", command=mods_list.yview)
        mods_scroll.pack(side="right", fill="y")
        mods_list.configure(yscrollcommand=mods_scroll.set)
        mods_dir = os.path.join(inst["dir"], "mods")
        def refresh_mods():
            mods_list.delete(0, "end")
            try:
                names = sorted(os.listdir(mods_dir))
            except OSError:
                names = []
            for name in names:
                if name.endswith(".jar") or name.endswith(".jar.disabled"):
                    mods_list.insert("end", name)
        refresh_mods()

        def selected_mod():
            selection = mods_list.curselection()
            if not selection:
                return ""
            return str(mods_list.get(selection[0]))
        def toggle_mod():
            name = selected_mod()
            if not name:
                return
            source = os.path.join(mods_dir, name)
            target = source[:-9] if source.endswith(".disabled") else source + ".disabled"
            try:
                os.replace(source, target)
                refresh_mods()
            except OSError as exc:
                messagebox.showerror("Mod 管理", str(exc), parent=dialog)
        def delete_mod():
            name = selected_mod()
            if not name:
                return
            if not messagebox.askyesno("删除 Mod", "确定删除 %s 吗？" % name, parent=dialog):
                return
            try:
                os.remove(os.path.join(mods_dir, name))
                refresh_mods()
            except OSError as exc:
                messagebox.showerror("Mod 管理", str(exc), parent=dialog)
        mod_buttons = tk.Frame(dialog, bg=PANEL)
        mod_buttons.pack(fill="x", padx=22, pady=(5, 0))
        for text, command in (("启用/禁用", toggle_mod), ("删除", delete_mod),
                              ("打开 mods", lambda: self.open_folder(mods_dir))):
            tk.Button(mod_buttons, text=text, bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                      highlightbackground=LINE, highlightthickness=1, padx=8, pady=4,
                      cursor="hand2", font=ft(8), command=command).pack(side="left", padx=(0, 6))

        bottom = tk.Frame(dialog, bg=PANEL)
        bottom.pack(fill="x", padx=22, pady=(12, 14))
        def save_details():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("保存", "名称不能为空。", parent=dialog)
                return
            memory = None
            raw_memory = memory_var.get().strip()
            if raw_memory:
                try:
                    memory = max(512, min(65536, int(raw_memory)))
                except ValueError:
                    messagebox.showerror("保存", "内存必须是数字。", parent=dialog)
                    return
            try:
                self.config_obj.update_instance(
                    iid, name=name, java_path=java_var.get().strip(),
                    memory_mb=memory, icon=icon_var.get().strip())
            except Exception as exc:
                messagebox.showerror("保存", str(exc), parent=dialog)
                return
            self.instance_sig = None
            self.refresh_instances()
            self.task_label.configure(text="实例设置已保存")
            dialog.destroy()
        tk.Button(bottom, text="保存", bg=ACCENT, fg="white", relief="flat", bd=0,
                  highlightthickness=0, padx=18, pady=7, cursor="hand2", font=ft(9),
                  command=save_details).pack(side="left")
        tk.Button(bottom, text="打开实例目录", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=12, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.open_folder(inst["dir"])).pack(side="left", padx=8)
        tk.Button(bottom, text="取消", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=12, pady=6,
                  cursor="hand2", font=ft(8), command=dialog.destroy).pack(side="right")

    def delete_instance(self, instance):
        if (self.running.get(instance["id"]) or {}).get("alive"):
            messagebox.showinfo("删除实例", "游戏正在运行，请先结束游戏。", parent=self)
            return
        if not messagebox.askyesno("删除实例",
                                   "确定删除“%s”吗？\n只会删除这个实例的 Mod、光影和存档。" % instance.get("name"),
                                   parent=self):
            return
        self.config_obj.delete_instance(instance["id"])
        self.required_cache.clear()
        self.refresh_instances()
        self.task_label.configure(text="实例已删除")

    # ------------------------------------------------------------------ 下载
    def enable_file_drop(self):
        if os.name != "nt" or getattr(self, "_drop_proc", None) is not None:
            return
        try:
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            hwnd = user32.GetAncestor(self.winfo_id(), 2)
            if not hwnd:
                return
            GWLP_WNDPROC = -4
            WM_DROPFILES = 0x0233
            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                         wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.GetWindowLongPtrW.restype = ctypes.c_void_p
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.CallWindowProcW.restype = ctypes.c_ssize_t
            user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                               wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                               wintypes.LPWSTR, wintypes.UINT]
            shell32.DragQueryFileW.restype = wintypes.UINT
            shell32.DragFinish.argtypes = [wintypes.HANDLE]
            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            old = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

            def wndproc(h, msg, wparam, lparam):
                if msg == WM_DROPFILES:
                    hdrop = wintypes.HANDLE(wparam)
                    try:
                        paths = []
                        count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                        for index in range(count):
                            length = shell32.DragQueryFileW(hdrop, index, None, 0)
                            buffer = ctypes.create_unicode_buffer(length + 1)
                            shell32.DragQueryFileW(hdrop, index, buffer, length + 1)
                            paths.append(buffer.value)
                        self.after(0, lambda p=paths: self.on_drop_files(p))
                    except Exception:
                        pass
                    finally:
                        try:
                            shell32.DragFinish(hdrop)
                        except Exception:
                            pass
                    return 0
                return user32.CallWindowProcW(old, h, msg, wparam, lparam)

            self._drop_proc = WNDPROC(wndproc)
            self._drop_old = old
            self._drop_hwnd = hwnd
            user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                                     ctypes.cast(self._drop_proc, ctypes.c_void_p))
            shell32.DragAcceptFiles(hwnd, True)
        except Exception:
            self._drop_proc = None

    def on_drop_files(self, paths):
        packs = [p for p in paths if str(p).lower().endswith((".mrpack", ".zip"))]
        if not packs:
            self.task_label.configure(text="只支持 .mrpack / .zip 整合包")
            return
        try:
            self.install_local_modpack(packs[0])
        except Exception as exc:
            self.task_label.configure(text="整合包识别失败：%s" % str(exc)[:80])

    def choose_modpack(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择整合包",
            filetypes=[("整合包", "*.mrpack *.zip"), ("所有文件", "*.*")])
        if path:
            self.install_local_modpack(path)

    def install_local_modpack(self, path):
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            messagebox.showinfo("安装整合包", "文件不存在。", parent=self)
            return
        lower = path.lower()
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
        except Exception as exc:
            self.task_label.configure(text="整合包损坏：%s" % str(exc)[:80])
            return
        if lower.endswith(".mrpack") or "modrinth.index.json" in names:
            runner = lambda task: self.modrinth.install_modpack_file(path, None, task)
        elif "manifest.json" in names:
            runner = lambda task: self.modrinth.install_zip_modpack(path, None, task)
        else:
            selected = next((item for item in self.instances
                             if item.get("id") == self.selected_id), None)
            mc_version = (selected or {}).get("mc_version") or "1.20.1"
            runner = lambda task: self.modrinth.install_plain_zip(
                path, None, task, mc_version=mc_version)
        self.start_task("安装整合包", runner, "modpack")

    def _build_download(self):
        if not self.instances:
            self.instances = self.config_obj.list_instances()
            if self.instances and not self.selected_id:
                self.selected_id = self.instances[0]["id"]
        page = self.pages["download"]
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        drop_bar = tk.Frame(page, bg=BG)
        drop_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Label(drop_bar, text="提示：把 .mrpack / .zip 整合包拖入窗口即可识别并安装，或",
                 bg=BG, fg=MUTED, font=ft(8)).pack(side="left")
        tk.Button(drop_bar, text="选择整合包文件", bg=PANEL, fg="#4b7a5d", relief="flat",
                  bd=0, highlightbackground=LINE, highlightthickness=1, padx=10, pady=4,
                  cursor="hand2", font=ft(8), command=self.choose_modpack).pack(side="left", padx=6)
        tk.Label(drop_bar, text="来源：", bg=BG, fg=MUTED, font=ft(7)).pack(side="left", padx=(12, 2))
        tk.Button(drop_bar, text="MC百科", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=8, pady=4,
                  cursor="hand2", font=ft(7), command=lambda: self.search_external("mcmod")).pack(side="left", padx=2)
        tk.Button(drop_bar, text="CurseForge", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=8, pady=4,
                  cursor="hand2", font=ft(7), command=lambda: self.search_external("curseforge")).pack(side="left", padx=2)
        notebook = ttk.Notebook(page)
        notebook.grid(row=1, column=0, sticky="nsew")
        self.notebook = notebook

        version_tab = tk.Frame(notebook, bg=BG)
        notebook.add(version_tab, text="游戏版本")
        self._build_versions(version_tab)

        self.content_panels = {}
        for kind, title in (("mod", "Mod"), ("shader", "光影"),
                            ("resourcepack", "资源包"), ("modpack", "整合包")):
            tab = tk.Frame(notebook, bg=BG)
            notebook.add(tab, text=title)
            panel = ContentPanel(self, tab, kind)
            panel.build()
            self.content_panels[kind] = panel

        notebook.bind("<<NotebookTabChanged>>", self.on_download_tab)

    def search_external(self, source):
        try:
            index = self.notebook.index("current")
        except Exception:
            index = 0
        kind = {1: "mod", 2: "shader", 3: "resourcepack", 4: "modpack"}.get(index, "mod")
        panel = self.content_panels.get(kind)
        query = panel.query.get().strip() if panel else ""
        if not query:
            messagebox.showinfo("外部搜索", "先在当前标签页输入要搜索的名称。", parent=self)
            return
        quoted = urllib.parse.quote_plus(query)
        if source == "mcmod":
            self.open_url("https://search.mcmod.cn/s?key=" + quoted)
        else:
            self.open_url("https://www.curseforge.com/minecraft/search?search=" + quoted)

    def _build_versions(self, parent):
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        top = tk.Frame(parent, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top.grid_columnconfigure(2, weight=1)
        self.version_kind = tk.StringVar(value="release")
        for index, (value, label) in enumerate((("release", "正式版"), ("snapshot", "快照"))):
            tk.Radiobutton(top, text=label, value=value, variable=self.version_kind,
                           bg=BG, fg="#4f5e54", selectcolor=PANEL, activebackground=BG,
                           font=ft(9), command=self.load_versions).grid(row=0, column=index, padx=(0, 8))
        self.version_filter = tk.StringVar()
        self.version_filter.trace_add("write", lambda *a: self.render_versions())
        tk.Entry(top, textvariable=self.version_filter, bg=PANEL, fg=INK,
                 relief="flat", highlightbackground=LINE, highlightthickness=1,
                 font=ft(9)).grid(row=0, column=2, sticky="ew", padx=(4, 8), ipady=5)
        tk.Button(top, text="刷新清单", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.load_versions(True)).grid(row=0, column=3)

        self.version_status = tk.Label(parent, text="选择版本后点“安装所选版本”。", bg=BG,
                                       fg=MUTED, font=ft(8), anchor="w")
        self.version_status.grid(row=1, column=0, sticky="ew", padx=12)

        table = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        table.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 8))
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)
        self.version_tree = ttk.Treeview(table, columns=("id", "type", "date", "state"),
                                         show="headings", height=13)
        for key, label, width in (("id", "版本", 260), ("type", "类型", 90),
                                  ("date", "发布日期", 130), ("state", "状态", 100)):
            self.version_tree.heading(key, text=label)
            self.version_tree.column(key, width=width, anchor="w")
        self.version_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, style="Minimal.Vertical.TScrollbar", orient="vertical", command=self.version_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.version_tree.configure(yscrollcommand=scroll.set)
        self.version_tree.bind("<Double-1>", lambda e: self.install_selected_version())

        bottom = tk.Frame(parent, bg=BG)
        bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        tk.Button(bottom, text="安装所选版本", bg=ACCENT, fg="white", activebackground=ACCENT_DARK,
                  activeforeground="white", relief="flat", bd=0, highlightthickness=0,
                  padx=14, pady=7, cursor="hand2", font=ft(9),
                  command=self.install_selected_version).pack(side="left")
        self.version_hint = tk.Label(bottom, text="", bg=BG, fg=MUTED, font=ft(8))
        self.version_hint.pack(side="left", padx=10)

    def on_download_tab(self, event=None):
        try:
            index = self.notebook.index("current")
        except Exception:
            return
        if index == 1:
            self.content_panels["mod"].ensure_loaded()
        elif index == 2:
            self.content_panels["shader"].ensure_loaded()
        elif index == 3:
            self.content_panels["resourcepack"].ensure_loaded()
        elif index == 4:
            self.content_panels["modpack"].ensure_loaded()


    def load_versions(self, force=False):
        kind = self.version_kind.get()
        if kind in self.version_cache and not force:
            self.render_versions()
            return
        if self.versions_loading:
            return
        self.versions_loading = True
        self.version_status.configure(text="正在获取版本清单…")
        self.background(lambda: self.minecraft.manifest_versions(kind),
                        self.on_versions, self.on_versions_error)

    def on_versions(self, versions):
        self.versions_loading = False
        kind = self.version_kind.get()
        self.version_cache[kind] = versions
        if kind == "release":
            self.release_versions = versions
        self.render_versions()
        self.version_status.configure(text="共 %d 个版本。" % len(versions))
        self.update_version_choices()

    def on_versions_error(self, exc):
        self.versions_loading = False
        self.version_status.configure(text="获取版本失败：%s" % exc)

    def render_versions(self):
        if not hasattr(self, "version_tree"):
            return
        versions = self.version_cache.get(self.version_kind.get(), [])
        keyword = self.version_filter.get().strip().lower()
        self.version_tree.delete(*self.version_tree.get_children())
        for item in versions:
            if keyword and keyword not in str(item.get("id", "")).lower():
                continue
            installed = any(inst.get("version_id") == item.get("id") and not inst.get("loader")
                            for inst in self.instances)
            self.version_tree.insert("", "end", iid=item.get("id"), values=(
                item.get("id"),
                "正式版" if item.get("type") == "release" else "快照",
                fmt_date(item.get("releaseTime")),
                "已安装" if installed else "",
            ))

    def install_selected_version(self):
        selection = self.version_tree.selection()
        if not selection:
            messagebox.showinfo("安装版本", "请先在列表里选择一个版本。", parent=self)
            return
        version_id = selection[0]
        if any(inst.get("version_id") == version_id and not inst.get("loader") for inst in self.instances):
            messagebox.showinfo("安装版本", "这个版本已经有原版实例了。", parent=self)
            return
        instance = self.config_obj.create_instance(version_id, version_id,
                                                   version_id=version_id, installing=True)

        def job(task):
            try:
                self.minecraft.install(version_id, task)
                self.config_obj.update_instance(instance["id"], installing=False)
            except Exception:
                self.config_obj.delete_instance(instance["id"])
                raise

        self.start_task("安装 Minecraft %s" % version_id, job, "install")
        self.version_hint.configure(text="已开始安装，进度见底部。")
        self.required_cache.clear()
        self.refresh_instances()

    # ------------------------------------------------------------------ 设置
    # ------------------------------------------------------------------ 更新
    def _update_url(self):
        url = str(self.config_obj.data.get("update_url") or "").strip()
        if not url and hasattr(self, "update_url_var"):
            url = self.update_url_var.get().strip()
        if url:
            return url
        # Release zip ships update_url.txt next to the exe so a published
        # build can auto-check without every player editing settings.
        for base in (CODE_DIR, DATA_DIR):
            try:
                path = os.path.join(base, "update_url.txt")
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as handle:
                        candidate = handle.readline().strip()
                    if candidate:
                        return candidate
            except Exception:
                pass
        return ""

    def _auto_check_updates(self):
        if "--selftest" in sys.argv or "--selftest-ui" in sys.argv:
            return
        try:
            if not bool(self.config_obj.data.get("update_auto", True)):
                return
            if not self._update_url():
                return
            self.check_updates(False)
        except Exception:
            pass

    def check_updates(self, manual=False):
        url = self._update_url()
        if not url:
            if manual:
                self.task_label.configure(text="先在设置里填写更新清单 URL")
            return
        if manual:
            self.task_label.configure(text="正在检查更新…")

        def done(manifest):
            self.update_manifest = manifest if manifest.get("available") else None
            if manifest.get("available"):
                self.update_btn.configure(text="更新 v%s" % manifest.get("version"))
                try:
                    self.update_btn.pack(side="left", padx=(0, 7), before=self.win_min.master)
                except Exception:
                    try:
                        self.update_btn.pack(side="left", padx=(0, 7))
                    except Exception:
                        pass
                if manual:
                    self.show_update_dialog()
            else:
                try:
                    self.update_btn.pack_forget()
                except Exception:
                    pass
                if manual:
                    self.task_label.configure(text="当前已是最新版本")
        self.background(lambda: check_update(url, SCL_VERSION), done,
                        lambda exc: self.task_label.configure(
                            text="检查更新失败：%s" % str(exc)[:80]) if manual else None)

    def show_update_dialog(self):
        manifest = self.update_manifest
        if not manifest:
            self.check_updates(True)
            return
        dialog = InlineDialog(self, 620, 470)
        dialog.title("发现新版本")
        dialog.geometry("620x470")
        tk.Label(dialog, text="发现新版本", bg=PANEL, fg=INK, font=ft(15, True)).pack(
            anchor="w", padx=22, pady=(16, 2))
        tk.Label(dialog, text="当前 %s → 最新 %s" % (SCL_VERSION, manifest.get("version")),
                 bg=PANEL, fg=MUTED, font=ft(8)).pack(anchor="w", padx=22)
        notes = tk.Text(dialog, height=9, wrap="word", bg="#fbfcfa", fg=INK,
                        relief="flat", highlightbackground=LINE, highlightthickness=1,
                        font=ft(8), padx=8, pady=6)
        notes.pack(fill="both", expand=True, padx=22, pady=(10, 8))
        notes.insert("1.0", manifest.get("notes") or "本次更新没有填写说明。")
        notes.configure(state="disabled")
        status = tk.Label(dialog, text="", bg=PANEL, fg=MUTED, font=ft(8), wraplength=560,
                          justify="left")
        status.pack(anchor="w", padx=22, pady=(0, 6))

        def start():
            if not getattr(sys, "frozen", False):
                status.configure(text="开发模式不会替换源码；请在打包版中测试更新。")
                return
            status.configure(text="正在下载更新…")
            self.background(
                lambda: download_update(manifest, self.config_obj.download_root),
                lambda result: _finish_update(result, status),
                lambda exc: status.configure(text="更新失败：%s" % str(exc)[:160]))

        def _finish_update(result, label):
            staging, archive = result
            label.configure(text="下载完成，正在启动替换并退出…")
            try:
                apply_update(staging, CODE_DIR)
            except Exception as exc:
                label.configure(text="替换失败：%s" % str(exc)[:160])
                return
            self.after(500, self.on_close)

        bottom = tk.Frame(dialog, bg=PANEL)
        bottom.pack(fill="x", padx=22, pady=(0, 14))
        tk.Button(bottom, text="立即更新", bg=ACCENT, fg="white", padx=16, pady=7,
                  font=ft(9), command=start).pack(side="left")
        tk.Button(bottom, text="稍后", bg=PANEL, fg="#5d6a61", padx=14, pady=6,
                  font=ft(8), command=dialog.destroy).pack(side="left", padx=8)

    # ------------------------------------------------------------------ 整合包发布
    def open_pack_dialog(self):
        instances = self.config_obj.list_instances()
        dialog = InlineDialog(self, 660, 560)
        dialog.title("整合包发布")
        dialog.geometry("660x560")
        tk.Label(dialog, text="整合包发布", bg=PANEL, fg=INK, font=ft(15, True)).pack(
            anchor="w", padx=22, pady=(16, 2))
        tk.Label(dialog, text="把实例整理成可安装的 .mrpack，Mod、配置、资源包和光影会放进 overrides。",
                 bg=PANEL, fg=MUTED, font=ft(8), wraplength=610, justify="left").pack(
            anchor="w", padx=22, pady=(0, 10))
        if not instances:
            tk.Label(dialog, text="还没有实例。", bg=PANEL, fg=MUTED, font=ft(9)).pack(
                anchor="w", padx=22)
            return
        labels = ["%s (%s)" % (item.get("name") or item.get("id"), item.get("id")) for item in instances]
        instance_var = tk.StringVar(value=labels[0])
        tk.Label(dialog, text="实例", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w", padx=22)
        ttk.Combobox(dialog, textvariable=instance_var, values=labels, state="readonly",
                     font=ft(9)).pack(fill="x", padx=22, pady=(3, 8), ipady=3)
        first = instances[0]
        name_var = tk.StringVar(value=first.get("name") or "SCL Pack")
        version_var = tk.StringVar(value="1.0.0")
        output_var = tk.StringVar(value=os.path.join(
            self.config_obj.download_root,
            "%s-%s.mrpack" % (first.get("name") or "SCL-Pack", "1.0.0")))
        for title_text, variable in (("整合包名称", name_var), ("版本号", version_var),
                                     ("输出文件", output_var)):
            tk.Label(dialog, text=title_text, bg=PANEL, fg="#65736a", font=ft(8)).pack(
                anchor="w", padx=22, pady=(3, 2))
            tk.Entry(dialog, textvariable=variable, bg="#fbfcfa", fg=INK, relief="flat",
                     highlightbackground=LINE, highlightthickness=1, font=ft(9)).pack(
                fill="x", padx=22, ipady=4)
        include_saves = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="包含存档 saves/（体积可能很大）",
                        variable=include_saves, style="Flat.TCheckbutton").pack(
            anchor="w", padx=18, pady=(6, 4))
        status = tk.Label(dialog, text="输出到下载目录，也可以手动修改。", bg=PANEL,
                          fg=MUTED, font=ft(8), wraplength=610, justify="left")
        status.pack(anchor="w", padx=22, pady=(0, 6))

        def browse():
            path = filedialog.asksaveasfilename(
                parent=dialog, title="保存整合包", defaultextension=".mrpack",
                initialfile=os.path.basename(output_var.get()),
                filetypes=[("Modrinth 整合包", "*.mrpack")])
            if path:
                output_var.set(path)

        def start():
            selected = labels.index(instance_var.get()) if instance_var.get() in labels else 0
            instance = instances[selected]
            output = output_var.get().strip()
            if not output:
                status.configure(text="请选择输出文件。")
                return
            status.configure(text="正在打包…")
            self.background(
                lambda: pack_instance(instance, output, name_var.get(), version_var.get(),
                                      bool(include_saves.get())),
                lambda result: _done(result, status),
                lambda exc: status.configure(text="打包失败：%s" % str(exc)[:180]))

        def _done(result, label):
            path, count, deps = result
            label.configure(text="完成：%s（%d 个文件，依赖 %s）" % (
                path, count, ", ".join("%s=%s" % item for item in deps.items())))

        bottom = tk.Frame(dialog, bg=PANEL)
        bottom.pack(fill="x", padx=22, pady=(6, 12))
        tk.Button(bottom, text="开始打包", bg=ACCENT, fg="white", padx=16, pady=7,
                  font=ft(9), command=start).pack(side="left")
        tk.Button(bottom, text="选择输出", bg=PANEL, fg="#4b7a5d", padx=12, pady=6,
                  font=ft(8), command=browse).pack(side="left", padx=8)
        tk.Button(bottom, text="打开下载目录", bg=PANEL, fg="#4b7a5d", padx=12, pady=6,
                  font=ft(8), command=lambda: self.open_folder(self.config_obj.download_root)).pack(
            side="left")

    def _build_settings(self):
        page = self.pages["settings"]
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(page, style="Minimal.Vertical.TScrollbar", orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        wrap = tk.Frame(canvas, bg=BG)
        inner = canvas.create_window((0, 0), window=wrap, anchor="nw")
        wrap.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner, width=e.width))
        self.settings_canvas = canvas
        wrap.grid_columnconfigure(0, weight=1, uniform="settings")
        wrap.grid_columnconfigure(1, weight=1, uniform="settings")

        def make_card(row, column, title, desc, columnspan=1):
            box = tk.Frame(wrap, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            padx = (0, 6) if column == 0 else (6, 0)
            if columnspan == 2:
                padx = 0
            box.grid(row=row, column=column, columnspan=columnspan, sticky="nsew",
                     padx=padx, pady=(0, 10))
            box.grid_columnconfigure(0, weight=1)
            tk.Label(box, text=title, bg=PANEL, fg=INK, font=ft(10, True)).grid(
                row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 0))
            if desc:
                tk.Label(box, text=desc, bg=PANEL, fg=MUTED, font=ft(8),
                         wraplength=520, justify="left").grid(
                    row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))
            return box

        game_card = make_card(0, 0, "游戏目录", "所有版本、实例和资源都保存在这里。", 2)
        self.game_var = tk.StringVar()
        tk.Entry(game_card, textvariable=self.game_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).grid(
            row=2, column=0, sticky="ew", padx=(14, 8), pady=(0, 13), ipady=5)
        tk.Button(game_card, text="浏览", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8), command=self.browse_game_dir).grid(
            row=2, column=1, padx=(0, 14), pady=(0, 13))
        tk.Label(game_card, text="下载目录", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=3, column=0, sticky="w", padx=14)
        tk.Label(game_card, text="更新包、整合包输出和临时下载文件保存在这里。",
                 bg=PANEL, fg=MUTED, font=ft(7)).grid(row=4, column=0, sticky="w", padx=14,
                                                     pady=(0, 3))
        self.download_var = tk.StringVar()
        tk.Entry(game_card, textvariable=self.download_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).grid(
            row=5, column=0, sticky="ew", padx=(14, 8), pady=(0, 13), ipady=5)
        tk.Button(game_card, text="浏览", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8), command=self.browse_download_dir).grid(
            row=5, column=1, padx=(0, 14), pady=(0, 13))

        java_card = make_card(1, 0, "Java 运行时", "SCL 会自动探测，也可以手动指定。")
        self.java_var = tk.StringVar(value="自动选择")
        self.java_combo = ttk.Combobox(java_card, textvariable=self.java_var,
                                       state="readonly", font=ft(8))
        self.java_combo.grid(row=2, column=0, sticky="ew", padx=(14, 8), pady=(0, 8))
        tk.Button(java_card, text="重新检测", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8), command=self.reload_javas).grid(
            row=2, column=1, padx=(0, 14), pady=(0, 8))
        self.java_custom = tk.StringVar()
        tk.Entry(java_card, textvariable=self.java_custom, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12), ipady=5)

        memory_card = make_card(1, 1, "内存分配", "大型整合包建议 6144 – 8192 MB。")
        self.memory_label = tk.Label(memory_card, text="4096 MB", bg=PANEL, fg=ACCENT_DARK,
                                     font=ft(9, True))
        self.memory_label.grid(row=2, column=0, columnspan=2, sticky="e", padx=14)
        self.memory_var = tk.IntVar(value=4096)
        tk.Scale(memory_card, from_=1024, to=16384, resolution=512, orient="horizontal",
                 variable=self.memory_var, showvalue=False, bg=PANEL, fg=INK,
                 highlightthickness=0, troughcolor="#e9ede6", activebackground=ACCENT,
                 command=self.on_memory).grid(row=3, column=0, columnspan=2, sticky="ew",
                                              padx=10, pady=(0, 12))

        source_card = make_card(2, 0, "下载源", "自动优先使用镜像，失败回退官方源。")
        self.source_var = tk.StringVar(value="自动")
        ttk.Combobox(source_card, textvariable=self.source_var, state="readonly",
                     values=("自动", "官方", "镜像"), font=ft(9), width=16).grid(
            row=2, column=0, sticky="w", padx=14, pady=(0, 12))

        player_card = make_card(2, 1, "玩家", "离线模式使用的玩家名。")
        self.player_var = tk.StringVar(value="Steve")
        tk.Entry(player_card, textvariable=self.player_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).grid(
            row=2, column=0, sticky="ew", padx=14, pady=(0, 12), ipady=5)

        personal = tk.Frame(wrap, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        personal.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        personal.grid_columnconfigure(1, weight=1)
        tk.Label(personal, text="个性化", bg=PANEL, fg=INK, font=ft(10, True)).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 2))
        tk.Label(personal, text="主页背景、强调色、透明度和启动行为。", bg=PANEL, fg=MUTED,
                 font=ft(8)).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))
        tk.Label(personal, text="主页背景", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=2, column=0, sticky="w", padx=14, pady=3)
        self.bg_var = tk.StringVar(value="森林")
        ttk.Combobox(personal, textvariable=self.bg_var, state="readonly",
                     values=("森林", "晨曦", "夜色", "简约", "自定义"), width=12,
                     font=ft(8)).grid(row=2, column=1, sticky="w", padx=10, pady=3)
        self.bg_path_var = tk.StringVar()
        bg_row = tk.Frame(personal, bg=PANEL)
        bg_row.grid(row=3, column=1, sticky="ew", padx=10, pady=3)
        tk.Entry(bg_row, textvariable=self.bg_path_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(8)).pack(
            side="left", fill="x", expand=True, ipady=4)
        tk.Button(bg_row, text="选图", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=8, pady=4,
                  cursor="hand2", font=ft(8), command=self.browse_background).pack(side="left", padx=(6, 0))
        tk.Label(personal, text="强调色（重启生效）", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=4, column=0, sticky="w", padx=14, pady=3)
        self.accent_var = tk.StringVar(value="绿色")
        ttk.Combobox(personal, textvariable=self.accent_var, state="readonly",
                     values=("绿色", "蓝色", "紫色"), width=12, font=ft(8)).grid(
            row=4, column=1, sticky="w", padx=10, pady=3)
        tk.Label(personal, text="窗口透明度", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=5, column=0, sticky="w", padx=14, pady=3)
        alpha_row = tk.Frame(personal, bg=PANEL)
        alpha_row.grid(row=5, column=1, sticky="ew", padx=10, pady=3)
        self.alpha_var = tk.DoubleVar(value=1.0)
        self.alpha_label = tk.Label(alpha_row, text="100%", bg=PANEL, fg=ACCENT_DARK,
                                    font=ft(8, True), width=5, anchor="e")
        self.alpha_label.pack(side="right")
        tk.Scale(alpha_row, from_=0.75, to=1.0, resolution=0.01, orient="horizontal",
                 variable=self.alpha_var, showvalue=False, bg=PANEL, highlightthickness=0,
                 troughcolor="#e9ede6", activebackground=ACCENT,
                 command=self.on_alpha).pack(side="left", fill="x", expand=True)
        self.show_log_var = tk.BooleanVar(value=True)
        self.minimize_var = tk.BooleanVar(value=False)
        checks = tk.Frame(personal, bg=PANEL)
        checks.grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(3, 12))
        ttk.Checkbutton(checks, text="主页显示运行日志", variable=self.show_log_var,
                        style="Flat.TCheckbutton").pack(side="left", padx=(0, 16))
        ttk.Checkbutton(checks, text="启动游戏后最小化 SCL", variable=self.minimize_var,
                        style="Flat.TCheckbutton").pack(side="left")

        music_card = tk.Frame(wrap, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        music_card.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        music_card.grid_columnconfigure(1, weight=1)
        tk.Label(music_card, text="背景音乐", bg=PANEL, fg=INK, font=ft(10, True)).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 2))
        tk.Label(music_card, text="支持 mp3 / ogg / wav，播放时循环。", bg=PANEL, fg=MUTED,
                 font=ft(8)).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))
        tk.Label(music_card, text="音乐文件", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=2, column=0, sticky="w", padx=14, pady=3)
        music_row = tk.Frame(music_card, bg=PANEL)
        music_row.grid(row=2, column=1, sticky="ew", padx=10, pady=3)
        self.music_path_var = tk.StringVar()
        tk.Entry(music_row, textvariable=self.music_path_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(8)).pack(
            side="left", fill="x", expand=True, ipady=4)
        tk.Button(music_row, text="选择", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=8, pady=4,
                  cursor="hand2", font=ft(8), command=self.browse_music).pack(side="left", padx=(6, 0))
        self.music_settings_btn = tk.Button(music_row, text="试听", bg=PANEL, fg="#4b7a5d",
                                            relief="flat", bd=0, highlightbackground=LINE,
                                            highlightthickness=1, padx=8, pady=4,
                                            cursor="hand2", font=ft(8),
                                            command=self.toggle_music_settings)
        self.music_settings_btn.pack(side="left", padx=(6, 0))
        tk.Label(music_card, text="音量", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=3, column=0, sticky="w", padx=14, pady=3)
        volume_row = tk.Frame(music_card, bg=PANEL)
        volume_row.grid(row=3, column=1, sticky="ew", padx=10, pady=3)
        self.music_volume_var = tk.IntVar(value=55)
        self.music_volume_label = tk.Label(volume_row, text="55%", bg=PANEL, fg=ACCENT_DARK,
                                           font=ft(8, True), width=5, anchor="e")
        self.music_volume_label.pack(side="right")
        tk.Scale(volume_row, from_=0, to=100, resolution=1, orient="horizontal",
                 variable=self.music_volume_var, showvalue=False, bg=PANEL,
                 highlightthickness=0, troughcolor="#e9ede6", activebackground=ACCENT,
                 command=self.on_music_volume).pack(side="left", fill="x", expand=True)
        self.music_autoplay_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(music_card, text="启动 SCL 时自动播放",
                        variable=self.music_autoplay_var,
                        style="Flat.TCheckbutton").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(3, 12))

        release = make_card(5, 0, "发布与更新", "发布整合包，或从静态清单检查启动器更新。", 2)
        self.update_url_var = tk.StringVar()
        tk.Label(release, text="更新清单 URL", bg=PANEL, fg="#65736a", font=ft(8)).grid(
            row=2, column=0, sticky="w", padx=14, pady=(2, 3))
        tk.Entry(release, textvariable=self.update_url_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(8)).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 6), ipady=5)
        self.update_auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(release, text="启动时自动检查更新",
                        variable=self.update_auto_var,
                        style="Flat.TCheckbutton").grid(
            row=4, column=0, sticky="w", padx=12, pady=(0, 8))
        release_actions = tk.Frame(release, bg=PANEL)
        release_actions.grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 12))
        tk.Button(release_actions, text="整合包发布", bg=PANEL, fg="#4b7a5d", relief="flat",
                  bd=0, highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8), command=self.open_pack_dialog).pack(side="left",
                                                                                  padx=(0, 6))
        tk.Button(release_actions, text="检查更新", bg=PANEL, fg="#4b7a5d", relief="flat",
                  bd=0, highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8), command=lambda: self.check_updates(True)).pack(
            side="left")

        actions = tk.Frame(wrap, bg=BG)
        actions.grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 8))
        tk.Button(actions, text="打开游戏目录", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=12, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.open_folder(self.game_var.get())).pack(side="left", padx=(0, 8))
        self.settings_hint = tk.Label(actions, text="修改后自动保存", bg=BG, fg=MUTED, font=ft(8))
        self.settings_hint.pack(side="left", padx=8)
        self._setup_settings_autosave()

    def on_memory(self, value):
        self.memory_label.configure(text="%d MB" % int(float(value)))

    def browse_download_dir(self):
        path = filedialog.askdirectory(parent=self, initialdir=self.download_var.get() or DATA_DIR)
        if path:
            self.download_var.set(path)

    def browse_game_dir(self):
        path = filedialog.askdirectory(parent=self, initialdir=self.game_var.get() or DATA_DIR)
        if path:
            self.game_var.set(path)

    def reload_javas(self):
        self.pill_java.configure(text="Java 检测中…")
        configured = self.config_obj.data.get("java_path", "")
        self.background(lambda: detect_java(self.config_obj.game_root, configured, force=True),
                        self.on_javas)

    def on_javas(self, javas):
        self.javas = javas or []
        self.java_map = {}
        values = ["自动选择"]
        for java in self.javas:
            label = "Java %d · %s" % (java["major"], java["path"])
            values.append(label)
            self.java_map[label] = java["path"]
        self.java_combo.configure(values=values)
        configured = self.config_obj.data.get("java_path", "")
        if configured:
            matched = next((label for label, path in self.java_map.items()
                            if path.lower() == configured.lower()), None)
            if matched:
                self.java_var.set(matched)
                self.java_custom.set("")
            else:
                self.java_var.set("自动选择")
                self.java_custom.set(configured)
        else:
            self.java_var.set("自动选择")
        if self.javas:
            best = self.javas[0]
            self.pill_java.configure(text="Java %d · %d 个" % (best["major"], len(self.javas)))
        else:
            self.pill_java.configure(text="未检测到 Java")
        self.instance_sig = None
        self.build_cards()
        self.render_hero()

    def fill_settings(self):
        self._settings_loading = True
        data = self.config_obj.public()
        self.game_var.set(data["game_root"])
        self.download_var.set(data.get("download_dir") or self.config_obj.download_root)
        self.update_url_var.set(data.get("update_url") or "")
        self.update_auto_var.set(bool(data.get("update_auto", True)))
        self.memory_var.set(int(data["memory_mb"]))
        self.memory_label.configure(text="%d MB" % int(data["memory_mb"]))
        self.player_var.set(self.accounts.offline_name())
        source = data.get("download_source", "auto")
        self.source_var.set({"auto": "自动", "official": "官方", "mirror": "镜像"}.get(source, "自动"))
        bg_name = {"forest": "森林", "dawn": "晨曦", "night": "夜色",
                   "minimal": "简约", "custom": "自定义"}.get(data.get("home_background"), "森林")
        self.bg_var.set(bg_name)
        self.bg_path_var.set(data.get("background_image") or "")
        self.accent_var.set({"green": "绿色", "blue": "蓝色", "purple": "紫色"}.get(
            data.get("accent"), "绿色"))
        alpha = float(data.get("window_alpha") or 1.0)
        self.alpha_var.set(alpha)
        self.alpha_label.configure(text="%d%%" % round(alpha * 100))
        self.show_log_var.set(bool(data.get("show_home_log", True)))
        self.minimize_var.set(bool(data.get("minimize_on_launch", False)))
        self.music_path_var.set(data.get("music_path") or "")
        volume = int(data.get("music_volume") or 55)
        self.music_volume_var.set(volume)
        self.music_volume_label.configure(text="%d%%" % volume)
        self.music_autoplay_var.set(bool(data.get("music_autoplay", False)))
        if hasattr(self, "music_settings_btn"):
            self.music_settings_btn.configure(text="暂停" if self.music.playing else "试听")
        if not self.java_var.get():
            self.java_var.set("自动选择")
        self._settings_loading = False

    def browse_background(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择主页背景",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")])
        if path:
            self.bg_path_var.set(path)
            self.bg_var.set("自定义")

    def browse_music(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择背景音乐",
            filetypes=[("音频", "*.mp3 *.ogg *.wav *.flac"), ("所有文件", "*.*")])
        if path:
            self.music_path_var.set(path)

    def on_alpha(self, value):
        try:
            alpha = float(value)
        except Exception:
            return
        self.alpha_label.configure(text="%d%%" % round(alpha * 100))
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            pass

    def on_music_volume(self, value):
        try:
            volume = int(float(value))
        except Exception:
            return
        self.music_volume_label.configure(text="%d%%" % volume)
        self.music.set_volume(volume)

    def toggle_music_settings(self):
        if not self.music.available:
            messagebox.showinfo("背景音乐", "当前环境没有可用的音频组件（pygame）。", parent=self)
            return
        path = self.music_path_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showinfo("背景音乐", "请先选择一个音乐文件。", parent=self)
            return
        if self.music.path != path:
            if not self.music.load(path):
                messagebox.showinfo("背景音乐", "这个音频文件无法播放。", parent=self)
                return
        self.music.toggle()
        self.update_music_button()
        self.music_settings_btn.configure(text="暂停" if self.music.playing else "试听")

    def _setup_settings_autosave(self):
        variables = [
            getattr(self, "game_var", None), getattr(self, "memory_var", None),
            getattr(self, "player_var", None), getattr(self, "source_var", None),
            getattr(self, "bg_var", None), getattr(self, "bg_path_var", None),
            getattr(self, "accent_var", None), getattr(self, "alpha_var", None),
            getattr(self, "show_log_var", None), getattr(self, "minimize_var", None),
            getattr(self, "music_path_var", None), getattr(self, "music_volume_var", None),
            getattr(self, "music_autoplay_var", None), getattr(self, "java_var", None),
            getattr(self, "java_custom", None), getattr(self, "download_var", None),
            getattr(self, "update_url_var", None), getattr(self, "update_auto_var", None),
        ]
        for variable in variables:
            if variable is None:
                continue
            try:
                variable.trace_add("write", self._schedule_settings_save)
            except Exception:
                pass

    def _schedule_settings_save(self, *args):
        if getattr(self, "_settings_loading", False):
            return
        if self._settings_after is not None:
            try:
                self.after_cancel(self._settings_after)
            except Exception:
                pass
        self._settings_after = self.after(350, self._auto_save_settings)

    def _auto_save_settings(self):
        self._settings_after = None
        try:
            self.save_settings(silent=True)
        except Exception:
            self.settings_hint.configure(text="自动保存失败")

    def save_settings(self, silent=False):
        path = self.game_var.get().strip()
        if not path:
            if not silent:
                messagebox.showerror("保存设置", "游戏目录不能为空。", parent=self)
            return
        source = {"自动": "auto", "官方": "official", "镜像": "mirror"}.get(self.source_var.get(), "auto")
        java_path = self.java_map.get(self.java_var.get(), "")
        if not java_path:
            java_path = self.java_custom.get().strip()
        bg_key = {"森林": "forest", "晨曦": "dawn", "夜色": "night",
                  "简约": "minimal", "自定义": "custom"}.get(self.bg_var.get(), "forest")
        accent_key = {"绿色": "green", "蓝色": "blue", "紫色": "purple"}.get(self.accent_var.get(), "green")
        old_accent = self.config_obj.data.get("accent")
        alpha = float(self.alpha_var.get())
        music_path = self.music_path_var.get().strip()
        volume = int(self.music_volume_var.get())
        autoplay = bool(self.music_autoplay_var.get())
        show_log = bool(self.show_log_var.get())
        minimize = bool(self.minimize_var.get())
        try:
            self.config_obj.update(
                game_root=path, memory_mb=int(self.memory_var.get()),
                download_dir=self.download_var.get().strip(),
                update_url=self.update_url_var.get().strip(),
                update_auto=bool(self.update_auto_var.get()),
                download_source=source, player_name=self.player_var.get().strip() or "Steve",
                java_path=java_path, home_background=bg_key,
                background_image=self.bg_path_var.get().strip(), accent=accent_key,
                window_alpha=alpha, music_path=music_path, music_volume=volume,
                music_autoplay=autoplay, show_home_log=show_log,
                minimize_on_launch=minimize,
            )
        except Exception as exc:
            if silent:
                self.settings_hint.configure(text="保存失败：%s" % str(exc)[:40])
            else:
                messagebox.showerror("保存设置", str(exc), parent=self)
            return
        self.accounts.set_offline_name(self.player_var.get().strip() or "Steve")
        self.attributes("-alpha", alpha)
        if show_log:
            self.log_box.grid()
        else:
            self.log_box.grid_remove()
        self.music.set_volume(volume)
        if music_path and os.path.isfile(music_path):
            self.music.load(music_path, play=autoplay)
        elif self.music.playing:
            self.music.stop()
        self.update_music_button()
        self.update_account_display()
        self.settings_hint.configure(text="已自动保存")
        self.after(2200, lambda: self.settings_hint.configure(text="修改后自动保存"))
        self.selected_id = ""
        self.required_cache.clear()
        self.refresh_instances()
        self.render_hero()
        self.update_header()
        if accent_key != old_accent and not silent:
            messagebox.showinfo("强调色", "强调色会在下次启动 SCL 时生效。", parent=self)

    # ------------------------------------------------------------------ 新建实例
    def new_instance_dialog(self):
        dialog = InlineDialog(self, 560, 430)
        dialog.title("新建实例")
        dialog.geometry("460x330")
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        tk.Label(dialog, text="新建实例", bg=PANEL, fg=INK, font=ft(14, True)).pack(
            anchor="w", padx=20, pady=(18, 4))
        tk.Label(dialog, text="选择游戏版本与加载器。", bg=PANEL, fg=MUTED, font=ft(8)).pack(
            anchor="w", padx=20)
        body = tk.Frame(dialog, bg=PANEL)
        body.pack(fill="both", expand=True, padx=20, pady=12)
        tk.Label(body, text="实例名称", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w")
        name_var = tk.StringVar(value="我的世界")
        tk.Entry(body, textvariable=name_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).pack(
            fill="x", pady=(4, 10), ipady=5)
        tk.Label(body, text="游戏版本", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w")
        versions = [item.get("id") for item in self.version_cache.get("release", [])[:80]]
        if not versions:
            versions = ["1.20.1"]
        version_var = tk.StringVar(value=versions[0])
        ttk.Combobox(body, textvariable=version_var, values=versions, state="readonly",
                     font=ft(9)).pack(fill="x", pady=(4, 10))
        tk.Label(body, text="加载器", bg=PANEL, fg="#65736a", font=ft(8)).pack(anchor="w")
        loader_var = tk.StringVar(value="Fabric")
        ttk.Combobox(body, textvariable=loader_var, values=("原版", "Fabric", "Forge", "NeoForge"),
                     state="readonly", font=ft(9)).pack(fill="x", pady=(4, 4))
        tk.Label(body, text="Forge / NeoForge 首次安装需要下载安装器，耗时较长。",
                 bg=PANEL, fg=MUTED, font=ft(7)).pack(anchor="w", pady=(2, 0))
        row = tk.Frame(dialog, bg=PANEL)
        row.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(row, text="取消", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=14, pady=6,
                  cursor="hand2", font=ft(9), command=dialog.destroy).pack(side="right")
        create = tk.Button(row, text="创建并安装", bg=ACCENT, fg="white", relief="flat", bd=0,
                           padx=16, pady=6, cursor="hand2", font=ft(9))
        create.pack(side="right", padx=8)

        def do_create():
            name = name_var.get().strip() or version_var.get()
            mc_version = version_var.get()
            loader_key = {"原版": "vanilla", "Fabric": "fabric",
                          "Forge": "forge", "NeoForge": "neoforge"}.get(loader_var.get(), "fabric")
            create.configure(state="disabled")
            dialog.destroy()
            instance = self.config_obj.create_instance(name, mc_version, version_id=mc_version,
                                                       installing=True)

            def job(task):
                try:
                    version_id, resolved = self.minecraft.install_loader(mc_version, loader_key, None, task)
                    self.config_obj.update_instance(
                        instance["id"], version_id=version_id,
                        loader={"type": loader_key, "version": resolved} if resolved else None,
                        installing=False,
                    )
                except Exception:
                    self.config_obj.delete_instance(instance["id"])
                    raise

            self.start_task("创建实例 %s" % name, job, "install")
            self.required_cache.clear()
            self.refresh_instances()
            self.show_page("home")

        create.configure(command=do_create)

    # ------------------------------------------------------------------ 搜索与安装
    def version_choices(self):
        values = []
        for instance in self.instances:
            value = instance.get("mc_version")
            if value and value not in values:
                values.append(value)
        for item in self.release_versions[:60]:
            value = item.get("id")
            if value and value not in values:
                values.append(value)
        return values or ["1.20.1"]

    def update_version_choices(self):
        values = self.version_choices()
        for panel in getattr(self, "content_panels", {}).values():
            panel.set_versions(values)
        if hasattr(self, "version_tree"):
            self.render_versions()

    def open_project(self, kind, project_id, game_version, loader):
        loader = (loader or "").lower() or None
        dialog = InlineDialog(self, 700, 640)
        dialog.title("项目详情")
        dialog.geometry("700x640")
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()
        tk.Label(dialog, text="正在从 Modrinth 获取项目详情…", bg=PANEL, fg=MUTED,
                 font=ft(10)).pack(expand=True)

        def load():
            project = self.modrinth.project(project_id)
            versions = self.modrinth.versions(
                project_id, None if kind == "modpack" else game_version,
                None if kind in ("shader", "modpack", "resourcepack") else loader)
            return project, versions

        self.background(load, lambda data: self.fill_project_dialog(dialog, kind, data),
                        lambda exc: self.project_error(dialog, exc))

    def project_error(self, dialog, exc):
        if not dialog.winfo_exists():
            return
        for child in dialog.winfo_children():
            child.destroy()
        tk.Label(dialog, text="加载失败", bg=PANEL, fg=DANGER, font=ft(12, True)).pack(pady=(60, 6))
        tk.Label(dialog, text=str(exc), bg=PANEL, fg=MUTED, font=ft(9), wraplength=600).pack()
        tk.Button(dialog, text="关闭", command=dialog.destroy, bg=PANEL, fg=INK,
                  relief="flat", bd=0, highlightbackground=LINE, highlightthickness=1,
                  padx=14, pady=6, cursor="hand2", font=ft(9)).pack(pady=20)

    def fill_project_dialog(self, dialog, kind, data):
        if not dialog.winfo_exists():
            return
        for child in dialog.winfo_children():
            child.destroy()
        project, versions = data
        header = tk.Frame(dialog, bg=PANEL)
        header.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(header, text=project.get("title") or "", bg=PANEL, fg=INK,
                 font=ft(15, True)).pack(anchor="w")
        type_name = {"shader": "光影", "modpack": "整合包", "resourcepack": "资源包"}.get(kind, "Mod")
        tk.Label(header, text="%s · %s 次下载 · %s" % (
            type_name, fmt_num(project.get("downloads")), project.get("author") or ""),
            bg=PANEL, fg=MUTED, font=ft(8)).pack(anchor="w", pady=(2, 0))

        desc = tk.Text(dialog, height=7, bg="#fbfcfa", fg="#4f5e54", relief="flat",
                       highlightbackground=LINE, highlightthickness=1, font=ft(8),
                       wrap="word", padx=8, pady=6)
        desc.pack(fill="x", padx=20, pady=(8, 10))
        body_text = str(project.get("body") or project.get("description") or "")
        body_text = body_text.replace("#", "").replace("*", "").replace(chr(96), "")
        desc.insert("1.0", body_text[:3000])
        desc.configure(state="disabled")

        table_box = tk.Frame(dialog, bg=PANEL)
        table_box.pack(fill="both", expand=True, padx=20)
        table = ttk.Treeview(table_box, columns=("ver", "gv", "loader"),
                             show="headings", height=8)
        for key, label, width in (("ver", "版本", 230), ("gv", "游戏版本", 180),
                                  ("loader", "加载器", 160)):
            table.heading(key, text=label)
            table.column(key, width=width, anchor="w")
        table.pack(fill="both", expand=True)
        for version in versions:
            table.insert("", "end", iid=str(version.get("id")), values=(
                version.get("version_number"),
                " / ".join((version.get("game_versions") or [])[-3:]),
                " / ".join((version.get("loaders") or [])[:3]),
            ))
        children = table.get_children()
        if children:
            table.selection_set(children[0])

        extra = tk.Frame(dialog, bg=PANEL)
        extra.pack(fill="x", padx=20, pady=(10, 4))
        instance_var = tk.StringVar()
        instance_map = {}
        name_var = tk.StringVar(value=project.get("title") or "整合包")
        if kind in ("mod", "shader", "resourcepack"):
            candidates = self.instances
            if kind == "mod":
                candidates = [item for item in self.instances if item.get("loader")]
            if candidates:
                labels = []
                for item in candidates:
                    label = "%s（%s · %s）" % (item.get("name"), item.get("mc_version"),
                                               loader_name(item.get("loader")))
                    labels.append(label)
                    instance_map[label] = item["id"]
                default = next((label for label in labels
                                if instance_map[label] == self.selected_id), labels[0])
                instance_var.set(default)
                tk.Label(extra, text="安装到实例", bg=PANEL, fg="#65736a",
                         font=ft(8)).pack(anchor="w")
                ttk.Combobox(extra, textvariable=instance_var, values=labels,
                             state="readonly", font=ft(9)).pack(fill="x", pady=(3, 2))
            else:
                tk.Label(extra, text="没有可安装的实例，请先在主页创建一个带加载器的实例。",
                         bg=PANEL, fg=DANGER, font=ft(8)).pack(anchor="w")
            if kind == "shader":
                tk.Label(extra, text="光影需要 Iris 或 OptiFine 才能生效。", bg=PANEL,
                         fg=MUTED, font=ft(7)).pack(anchor="w", pady=(2, 0))
            if kind == "resourcepack":
                tk.Label(extra, text="资源包会安装到实例的 resourcepacks/。", bg=PANEL,
                         fg=MUTED, font=ft(7)).pack(anchor="w", pady=(2, 0))
        else:
            tk.Label(extra, text="整合包会创建新实例", bg=PANEL, fg="#65736a",
                     font=ft(8)).pack(anchor="w")
            tk.Entry(extra, textvariable=name_var, bg="#fbfcfa", fg=INK, relief="flat",
                     highlightbackground=LINE, highlightthickness=1, font=ft(9)).pack(
                fill="x", pady=(3, 0), ipady=4)

        buttons = tk.Frame(dialog, bg=PANEL)
        buttons.pack(fill="x", padx=20, pady=(12, 16))
        tk.Button(buttons, text="取消", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=14, pady=6,
                  cursor="hand2", font=ft(9), command=dialog.destroy).pack(side="right")
        install = tk.Button(buttons, text="开始安装", bg=ACCENT, fg="white", relief="flat",
                            bd=0, padx=16, pady=6, cursor="hand2", font=ft(9))
        install.pack(side="right", padx=8)

        def do_install():
            selection = table.selection()
            if not selection:
                messagebox.showinfo("安装", "请选择一个版本。", parent=dialog)
                return
            version_id = selection[0]
            install.configure(state="disabled")
            if kind == "modpack":
                name = name_var.get().strip() or project.get("title") or "整合包"
                dialog.destroy()
                self.start_task("安装整合包 %s" % name,
                                lambda task: self.modrinth.install_modpack(
                                    project.get("id"), version_id, name, task), "modpack")
                self.required_cache.clear()
                return
            if not instance_map:
                messagebox.showerror("安装", "没有可用的实例。", parent=dialog)
                install.configure(state="normal")
                return
            instance_id = instance_map.get(instance_var.get())
            if not instance_id:
                messagebox.showerror("安装", "请选择目标实例。", parent=dialog)
                install.configure(state="normal")
                return
            instance = next((item for item in self.instances if item["id"] == instance_id), None)
            if kind == "mod" and instance and not instance.get("loader"):
                messagebox.showerror("安装", "这个实例没有 Mod 加载器，无法安装 Mod。", parent=dialog)
                install.configure(state="normal")
                return
            dialog.destroy()
            label = {"shader": "光影", "resourcepack": "资源包"}.get(kind, "Mod")
            self.start_task("安装 %s" % label,
                            lambda task: self.modrinth.install_content(
                                project.get("id"), version_id, instance_id, kind, task), kind)

        install.configure(command=do_install)

    def open_image_preview(self, url, title=""):
        if not url:
            return
        win = InlineDialog(self, 900, 620)
        win.title(title or "图片预览")
        win.geometry("900x620")
        win.configure(bg="#101612")
        win.transient(self)
        label = tk.Label(win, text="正在加载大图…", bg="#101612", fg="#cfe8d6", font=ft(9))
        label.pack(fill="both", expand=True, padx=10, pady=10)
        self.images.photo(url, (860, 560), lambda photo: label.configure(image=photo, text="") if win.winfo_exists() else None)

    def background_path(self):
        key = self.config_obj.data.get("home_background") or "forest"
        if key == "custom":
            custom = self.config_obj.data.get("background_image") or ""
            if custom and os.path.isfile(custom):
                return custom
            key = "forest"
        return resource_path("assets", "bg-%s.png" % key)

    def on_hero_resize(self, event=None):
        if self._hero_after is not None:
            try:
                self.after_cancel(self._hero_after)
            except Exception:
                pass
        self._hero_after = self.after(180, self.render_hero)

    def render_hero(self):
        if not hasattr(self, "hero") or not self.hero.winfo_exists():
            return
        self._hero_after = None
        for widget in getattr(self, "_hero_widgets", []):
            try:
                widget.destroy()
            except Exception:
                pass
        self._hero_widgets = []
        self.hero.delete("all")
        width = max(900, int(self.hero.winfo_width() or 1180))
        height = 186
        photo = None
        if Image is not None and ImageDraw is not None and ImageTk is not None:
            try:
                image = Image.open(self.background_path()).convert("RGB")
                scale = max(width / image.width, height / image.height)
                image = image.resize((max(1, int(image.width * scale)),
                                      max(1, int(image.height * scale))),
                                     getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS))
                left = (image.width - width) // 2
                top = (image.height - height) // 2
                image = image.crop((left, top, left + width, top + height)).convert("RGBA")
                overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                draw.rectangle([0, 0, width, height], fill=(5, 12, 8, 100))
                for x in range(0, width):
                    ratio = x / max(1, width - 1)
                    alpha = int(170 * (1 - ratio) ** 1.4)
                    draw.line([(x, 0), (x, height)], fill=(5, 12, 8, alpha))
                image = Image.alpha_composite(image, overlay).convert("RGB")
                photo = ImageTk.PhotoImage(image)
                self.hero.create_image(0, 0, anchor="nw", image=photo)
                self._hero_photo = photo
            except Exception:
                photo = None
        if photo is None:
            self.hero.configure(bg="#15251a")
        info = self.accounts.active_info()
        account_name = info.get("name") or "Steve"
        prefix = "正版" if info.get("type") == "msa" else "离线"
        instance = next((item for item in self.instances if item.get("id") == self.selected_id), None)
        china_hour = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).hour
        if china_hour < 6 or china_hour >= 23:
            greeting = "凌晨好"
        elif china_hour < 9:
            greeting = "早上好"
        elif china_hour < 12:
            greeting = "上午好"
        elif china_hour < 14:
            greeting = "中午好"
        elif china_hour < 18:
            greeting = "下午好"
        else:
            greeting = "晚上好"
        self.hero.create_text(28, 24, anchor="nw", text="%s · %s" % (prefix, account_name),
                              fill="#cfe8d6", font=ft(9))
        if instance:
            self.hero.create_text(28, 48, anchor="nw", text="%s，%s" % (greeting, account_name),
                                  fill="#ffffff", font=ft(19, True))
            self.hero.create_text(28, 92, anchor="nw", text=instance.get("name") or "",
                                  fill="#eaf5ec", font=ft(12, True))
            required = self.required_for(instance)
            java = choose_java(self.javas, required, self.config_obj.data.get("java_path", ""))
            java_text = "Java %d" % java["major"] if java else "未找到 Java"
            meta = "%s  ·  %s  ·  %s" % (instance.get("mc_version") or "?",
                                          loader_name(instance.get("loader")), java_text)
            self.hero.create_text(28, 120, anchor="nw", text=meta, fill="#b7c9bc", font=ft(8))
            running = bool((self.running.get(instance["id"]) or {}).get("alive"))
            if running:
                button = tk.Button(self.hero, text="游戏运行中", bg="#2f5d40", fg="#dff5e6",
                                   relief="flat", bd=0, highlightthickness=0, padx=18,
                                   pady=9, font=ft(9, True), state="disabled")
            else:
                button = tk.Button(self.hero, text="启动游戏", bg=ACCENT, fg="white",
                                   activebackground=ACCENT_DARK, activeforeground="white",
                                   relief="flat", bd=0, highlightthickness=0, padx=20,
                                   pady=9, cursor="hand2", font=ft(9, True),
                                   command=lambda iid=instance["id"]: self.launch_instance(iid))
            self.hero.create_window(width - 190, height - 64, anchor="nw", window=button)
            self._hero_widgets.append(button)
        else:
            self.hero.create_text(28, 48, anchor="nw", text="欢迎使用 SCL",
                                  fill="#ffffff", font=ft(19, True))
            self.hero.create_text(28, 92, anchor="nw", text="先创建一个实例，开始你的世界。",
                                  fill="#cfe8d6", font=ft(9))
            button = tk.Button(self.hero, text="新建实例", bg=ACCENT, fg="white",
                               activebackground=ACCENT_DARK, activeforeground="white",
                               relief="flat", bd=0, highlightthickness=0, padx=20,
                               pady=9, cursor="hand2", font=ft(9, True),
                               command=self.new_instance_dialog)
            self.hero.create_window(width - 190, height - 64, anchor="nw", window=button)
            self._hero_widgets.append(button)
        self.update_music_button()

    def _tick_greeting(self):
        self.render_hero()
        self.after(60000, self._tick_greeting)

    def toggle_music(self):
        if not self.music.available:
            messagebox.showinfo("背景音乐", "当前环境没有可用的音频组件（pygame）。", parent=self)
            return
        if not self.music.path:
            path = self.config_obj.data.get("music_path") or ""
            if not path or not os.path.isfile(path):
                messagebox.showinfo("背景音乐", "请先在设置里选择音乐文件。", parent=self)
                return
            if not self.music.load(path):
                messagebox.showinfo("背景音乐", "这个音频文件无法播放。", parent=self)
                return
        self.music.toggle()
        self.update_music_button()

    def autoplay_music(self):
        path = self.config_obj.data.get("music_path") or ""
        if self.config_obj.data.get("music_autoplay") and path and os.path.isfile(path):
            if self.music.load(path, play=True):
                self.update_music_button()

    def update_music_button(self):
        if hasattr(self, "music_btn"):
            self.music_btn.configure(text="❚❚" if self.music.playing else "♪")

    # ------------------------------------------------------------------ 账号
    def update_account_display(self):
        try:
            info = self.accounts.active_info()
        except Exception:
            return
        prefix = "正版" if info.get("type") == "msa" else "离线"
        name = str(info.get("name") or "")
        if len(name) > 10:
            name = name[:10] + "…"
        if hasattr(self, "account_btn"):
            self.account_btn.configure(text="%s · %s" % (prefix, name))
        if hasattr(self, "side_account_name"):
            self.side_account_name.configure(text="%s · %s" % (prefix, name))
            self.side_account_btn.configure(text="切换账号" if info.get("type") == "msa" else "登录正版")
        self.render_hero()

    def sidebar_account_action(self):
        try:
            is_offline = self.accounts.active_info().get("type") == "offline"
        except Exception:
            is_offline = True
        if is_offline:
            self.device_login_dialog(self)
        else:
            self.account_dialog()

    def account_dialog(self):
        if self.account_dialog_ref is not None and self.account_dialog_ref.winfo_exists():
            self.account_dialog_ref.lift()
            return
        dialog = InlineDialog(self, 580, 530)
        dialog.title("SCL 账号")
        dialog.geometry("580x530")
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        self.account_dialog_ref = dialog
        self._render_account_dialog(dialog)
        dialog.close_button.lift()

    def _render_account_dialog(self, dialog):
        for child in dialog.winfo_children():
            if child is getattr(dialog, "close_button", None):
                continue
            child.destroy()
        tk.Label(dialog, text="账号", bg=PANEL, fg=INK, font=ft(15, True)).pack(
            anchor="w", padx=22, pady=(18, 2))
        tk.Label(dialog, text="登录正版后自动保存，和离线账号随时切换。", bg=PANEL,
                 fg=MUTED, font=ft(8)).pack(anchor="w", padx=22, pady=(0, 8))
        tk.Button(dialog, text="登录微软正版", bg=ACCENT, fg="white", relief="flat", bd=0,
                  activebackground=ACCENT_DARK, activeforeground="white",
                  highlightthickness=0, padx=14, pady=8, cursor="hand2", font=ft(9, True),
                  command=lambda: self.device_login_dialog(dialog)).pack(
            fill="x", padx=22, pady=(0, 10))

        selected = tk.StringVar(value=self.accounts.active_key())
        rows = tk.Frame(dialog, bg=PANEL)
        rows.pack(fill="x", padx=22)
        current = self.accounts.active_key()
        for item in self.accounts.list_accounts():
            row = tk.Frame(rows, bg="#fbfcfa" if item["key"] == current else PANEL,
                           highlightbackground=LINE, highlightthickness=1)
            row.pack(fill="x", pady=3)
            radio = tk.Radiobutton(
                row, text=item.get("name") or "账号", variable=selected, value=item["key"],
                bg=row.cget("bg"), fg=INK, selectcolor=row.cget("bg"), activebackground=row.cget("bg"),
                font=ft(9, True), anchor="w", padx=8, pady=6)
            radio.pack(side="left", fill="x", expand=True)
            detail = "微软正版" if item.get("type") == "msa" else "离线账号"
            tk.Label(row, text=detail, bg=row.cget("bg"), fg=ACCENT_DARK if item.get("type") == "msa" else MUTED,
                     font=ft(8)).pack(side="right", padx=10)

        tk.Label(dialog, text="离线玩家名", bg=PANEL, fg="#65736a", font=ft(8)).pack(
            anchor="w", padx=22, pady=(12, 3))
        name_var = tk.StringVar(value=self.accounts.offline_name())
        name_row = tk.Frame(dialog, bg=PANEL)
        name_row.pack(fill="x", padx=22)
        tk.Entry(name_row, textvariable=name_var, bg="#fbfcfa", fg=INK, relief="flat",
                 highlightbackground=LINE, highlightthickness=1, font=ft(9)).pack(
            side="left", fill="x", expand=True, ipady=5)
        tk.Button(name_row, text="保存", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8),
                  command=lambda: self._save_offline_name(dialog, name_var.get())).pack(side="left", padx=(6, 0))

        tk.Label(dialog, text="Microsoft 登录会打开浏览器，输入一次性代码；"
                              "令牌只保存在本机，并使用 Windows DPAPI 加密。",
                 bg=PANEL, fg=MUTED, font=ft(7), wraplength=520, justify="left").pack(
            anchor="w", padx=22, pady=(12, 0))

        buttons = tk.Frame(dialog, bg=PANEL)
        buttons.pack(fill="x", padx=22, pady=(16, 14))
        tk.Button(buttons, text="使用所选账号", bg=ACCENT, fg="white", relief="flat", bd=0,
                  highlightthickness=0, padx=14, pady=7, cursor="hand2", font=ft(9),
                  command=lambda: self._use_account(dialog, selected.get())).pack(side="left")
        tk.Button(buttons, text="删除所选", bg="#fff8f7", fg=DANGER, relief="flat", bd=0,
                  highlightbackground="#efd3d1", highlightthickness=1, padx=10, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self._delete_account(dialog, selected.get())).pack(side="right")

    def _save_offline_name(self, dialog, name):
        try:
            self.accounts.set_offline_name(name)
            self.update_account_display()
            self.fill_settings()
            self.task_label.configure(text="离线玩家名已保存")
            self._render_account_dialog(dialog)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=dialog)

    def _use_account(self, dialog, key):
        try:
            self.accounts.set_active(key)
            self.update_account_display()
            self.task_label.configure(text="已切换到 " + self.accounts.active_info().get("name", ""))
            dialog.destroy()
        except Exception as exc:
            messagebox.showerror("切换账号", str(exc), parent=dialog)

    def _delete_account(self, dialog, key):
        if key == "offline":
            messagebox.showinfo("删除账号", "离线账号不能删除。", parent=dialog)
            return
        if not messagebox.askyesno("删除账号", "确定从 SCL 移除这个正版账号吗？", parent=dialog):
            return
        self.accounts.remove(key)
        self.update_account_display()
        self._render_account_dialog(dialog)

    # ------------------------------------------------------------------ 微软登录
    def device_login_dialog(self, parent=None):
        if self.device_window is not None and self.device_window.winfo_exists():
            self.device_window.lift()
            return
        win = tk.Toplevel(self)
        win.title("SCL · 微软正版登录")
        win.geometry("560x360")
        win.configure(bg=PANEL)
        win.transient(parent or self)
        win.grab_set()
        win.resizable(False, False)
        self.device_window = win
        self.login_busy = False
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_device_window(win))

        tk.Label(win, text="微软正版登录", bg=PANEL, fg=INK, font=ft(15, True)).pack(
            anchor="w", padx=22, pady=(18, 2))
        tk.Label(win, text="启动器会打开 Microsoft Edge。请在浏览器中完成微软登录，"
                          "启动器会自动读取授权，不需要复制回调地址。",
                 bg=PANEL, fg=MUTED, font=ft(8), wraplength=510, justify="left").pack(
            anchor="w", padx=22)
        tk.Label(win, text="微软会从回调页地址栏移除 code，手动复制会得到 removed=true；"
                          "所以这里由启动器监听 Edge 的跳转。",
                 bg="#f4f8f3", fg="#4b6a56", font=ft(8), wraplength=510, justify="left").pack(
            fill="x", padx=22, pady=(12, 8), ipady=6)
        self.device_status = tk.Label(win, text="点击下方按钮启动 Edge 登录。",
                                      bg=PANEL, fg=MUTED, font=ft(8), wraplength=510,
                                      justify="left")
        self.device_status.pack(anchor="w", padx=22, pady=(4, 10))
        self.device_login_btn = tk.Button(
            win, text="打开 Microsoft Edge 登录", bg=ACCENT, fg="white",
            relief="flat", bd=0, highlightthickness=0, padx=16, pady=8,
            cursor="hand2", font=ft(9, True),
            command=lambda: self._start_edge_login(win))
        self.device_login_btn.pack(anchor="w", padx=22)
        tk.Button(win, text="取消", bg=PANEL, fg="#5d6a61", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=12, pady=6,
                  cursor="hand2", font=ft(8),
                  command=lambda: self._close_device_window(win)).pack(anchor="w", padx=22, pady=(8, 12))

    def _start_edge_login(self, win):
        if self.login_busy:
            return
        self.login_busy = True
        self.device_login_btn.configure(state="disabled")
        self.device_status.configure(text="正在启动 Microsoft Edge，请稍候…")
        profile_dir = os.path.join(DATA_DIR, "edge-profile")

        def job():
            code = edge_login.capture_auth_code(
                microsoft.build_auth_url(), profile_dir, timeout=300)
            tokens = microsoft.exchange_code(code)
            return microsoft.build_account(tokens)

        self.background(job,
                        lambda account: self._device_account(win, account),
                        lambda exc: self._device_login_error(win, exc))

    def _device_account(self, win, account):
        if not win.winfo_exists():
            return
        try:
            self.accounts.add_msa(account)
        except Exception as exc:
            self._device_login_error(win, exc)
            return
        self.update_account_display()
        if self.account_dialog_ref is not None and self.account_dialog_ref.winfo_exists():
            self._render_account_dialog(self.account_dialog_ref)
        self.task_label.configure(text="正版账号已添加：" + str(account.get("name")))
        self._close_device_window(win)
        messagebox.showinfo("微软登录", "登录成功：%s" % account.get("name"), parent=self)

    def _device_login_error(self, win, exc):
        if not win.winfo_exists():
            return
        self.login_busy = False
        self.device_login_btn.configure(state="normal")
        self.device_status.configure(text=str(exc))

    def _close_device_window(self, win):
        if win.winfo_exists():
            win.destroy()
        self.device_window = None

    # ------------------------------------------------------------------ 任务与轮询
    def background(self, func, done=None, error=None):
        def runner():
            try:
                result = func()
            except Exception as exc:
                callback = error if error is not None else self.default_error
                self.ui_queue.put((callback, exc))
                return
            if done is not None:
                self.ui_queue.put((done, result))
        threading.Thread(target=runner, daemon=True).start()

    def default_error(self, exc):
        messagebox.showerror("出错", str(exc), parent=self)

    def drain_queue(self):
        while True:
            try:
                callback, value = self.ui_queue.get_nowait()
            except queue.Empty:
                return
            try:
                callback(value)
            except Exception:
                pass

    def start_task(self, title, fn, kind):
        task = self.tasks.start(kind, title, fn)
        self.active_task_id = task.id
        self.task_label.configure(text="%s · 准备中" % title)
        self.progress.configure(mode="determinate", value=0)
        self.cancel_btn.configure(state="normal")
        self.poll_once()

    def cancel_task(self):
        if self.active_task_id:
            self.tasks.cancel(self.active_task_id)
            self.task_label.configure(text="正在取消…")

    def poll_once(self):
        self.drain_queue()
        self.running = running_snapshot()
        self.update_header()
        self.update_tasks()
        self.maybe_refresh_instances()
        self.poll_count += 1
        if self.poll_count % 4 == 0 and self.current_page == "home":
            self.refresh_log(False)
        if self.task_win is not None and self.task_win.winfo_exists():
            self.refresh_task_window()

    def poll_loop(self):
        try:
            self.poll_once()
        except Exception:
            pass
        self.after(800, self.poll_loop)

    def update_header(self):
        running_count = sum(1 for info in self.running.values() if info.get("alive"))
        self.side_status.configure(text="%d 个实例运行中" % running_count if running_count else "就绪")
        self.side_dot.configure(fg="#5bcf83" if running_count else "#7f8c84")
        now = time.time()
        if now - self.last_disk_check > 12:
            self.last_disk_check = now
            try:
                self.free_gb = shutil.disk_usage(self.config_obj.game_root).free / (1024 ** 3)
            except Exception:
                self.free_gb = None
        self.pill_disk.configure(text="剩余 %.1f GB" % self.free_gb
                                 if self.free_gb is not None else "磁盘 —")

    def update_tasks(self):
        snapshots = self.tasks.snapshot_all()
        for task in snapshots:
            if task["status"] == "running" or task["id"] in self.seen_tasks:
                continue
            self.seen_tasks.add(task["id"])
            if task["status"] == "error":
                self.task_label.configure(text="失败：%s" % task["title"])
                messagebox.showerror("任务失败",
                                     "%s\n\n%s" % (task["title"], task.get("error") or ""),
                                     parent=self)
            elif task["status"] == "success":
                self.task_label.configure(text="完成：%s" % task["title"])
                if task.get("kind") == "modpack":
                    self.show_page("home")
                if task.get("kind") == "launch" and self.config_obj.data.get("minimize_on_launch"):
                    self.after(800, self.iconify)
            else:
                self.task_label.configure(text="已取消：%s" % task["title"])
            self.required_cache.clear()
            self.refresh_instances()
            if task.get("kind") == "install":
                self.version_cache.pop(self.version_kind.get(), None)
                if self.current_page == "download":
                    self.load_versions(True)

        running = [task for task in snapshots if task["status"] == "running"]
        if running:
            task = running[-1]
            self.active_task_id = task["id"]
            self.task_label.configure(text="%s · %s" % (task["title"], task["stage"]))
            if task["total"]:
                self.progress.stop()
                self.progress.configure(mode="determinate", value=task["progress"] * 100)
                self.task_pct.configure(text="%s / %s · %s" % (
                    fmt_bytes(task["current"]), fmt_bytes(task["total"]),
                    fmt_speed(task["speed"])))
            else:
                if str(self.progress.cget("mode")) != "indeterminate":
                    self.progress.configure(mode="indeterminate")
                    self.progress.start(12)
                self.task_pct.configure(text=fmt_bytes(task["current"]))
            self.cancel_btn.configure(state="normal")
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.task_pct.configure(text="")
            self.cancel_btn.configure(state="disabled")
            self.active_task_id = None

    def maybe_refresh_instances(self):
        signature = []
        for instance in self.instances:
            signature.append((instance.get("id"), instance.get("name"), instance.get("version_id"),
                              instance.get("installing"),
                              bool((self.running.get(instance.get("id")) or {}).get("alive"))))
        if repr(signature) != self.instance_sig:
            self.instance_sig = repr(signature)
            self.build_cards()
            self.refresh_log(False)

    def refresh_all(self):
        self.required_cache.clear()
        self.refresh_instances()
        self.reload_javas()
        self.version_cache.clear()
        self.load_versions(True)
        self.update_header()
        self.task_label.configure(text="已刷新")

    def _alpha_target(self):
        try:
            return max(0.75, min(1.0, float(self.config_obj.data.get("window_alpha") or 1.0)))
        except Exception:
            return 1.0

    def _prepare_startup(self):
        if "--selftest" in sys.argv or "--selftest-ui" in sys.argv:
            return
        try:
            self.update_idletasks()
            x, y = self.winfo_x(), self.winfo_y()
            width, height = self.winfo_width(), self.winfo_height()
            if width < 400 or height < 300:
                return
            self._startup_geom = (x, y, width, height)
            self._startup_animating = True
            sw = int(width * 0.78)
            sh = int(height * 0.78)
            self.geometry("%dx%d+%d+%d" % (
                sw, sh, x + (width - sw) // 2, y + (height - sh) // 2))
            self.attributes("-alpha", 0.0)
        except Exception:
            self._startup_geom = None

    def _on_window_configure(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(16, self._refresh_after_resize)

    def _refresh_after_resize(self):
        self._resize_job = None
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _startup_open(self):
        if "--selftest" in sys.argv or "--selftest-ui" in sys.argv or self._startup_done:
            self._startup_animating = False
            return
        self._startup_done = True
        if not self.winfo_viewable():
            return
        try:
            target = self._alpha_target()
            self.update_idletasks()
            if self._startup_geom:
                x, y, width, height = self._startup_geom
            else:
                x, y = self.winfo_x(), self.winfo_y()
                width, height = self.winfo_width(), self.winfo_height()
            if width < 400 or height < 300:
                return
            start_scale = 0.82
            self.attributes("-alpha", 0.0)

            def step(index):
                if index > 6:
                    self.geometry("%dx%d+%d+%d" % (width, height, x, y))
                    self.attributes("-alpha", target)
                    self._startup_animating = False
                    return
                ratio = start_scale + (1.0 - start_scale) * index / 6.0
                w = int(width * ratio)
                h = int(height * ratio)
                gx = x + (width - w) // 2
                gy = y + (height - h) // 2
                self.geometry("%dx%d+%d+%d" % (w, h, gx, gy))
                self.attributes("-alpha", target * (index / 6.0))
                self.after(12, lambda: step(index + 1))
            step(0)
        except Exception:
            try:
                self.attributes("-alpha", self._alpha_target())
            except Exception:
                pass

    def _grab_main(self):
        if ImageGrab is None:
            return None
        try:
            self.update_idletasks()
            x = self.main.winfo_rootx()
            y = self.main.winfo_rooty()
            w = self.main.winfo_width()
            h = self.main.winfo_height()
            if w < 50 or h < 50:
                return None
            image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            if image.size != (w, h):
                image = image.resize((w, h), Image.LANCZOS)
            return image
        except Exception:
            return None

    def _content_overlay(self, image):
        if image is None or ImageTk is None:
            return None
        try:
            photo = ImageTk.PhotoImage(image)
            self._fade_photo = photo
            overlay = tk.Label(self.main, image=photo, bd=0, bg=BG,
                               highlightthickness=0)
            overlay.place(x=0, y=0, width=self.main.winfo_width(),
                          height=self.main.winfo_height())
            overlay.lift()
            return overlay
        except Exception:
            return None

    def _fade_content_switch(self, name):
        if (not self.winfo_viewable() or self._fade_busy
                or "--selftest" in sys.argv or getattr(self, "_startup_animating", False)
                or getattr(self, "inline_dialog", None) is not None):
            self._apply_page(name)
            return
        old = self._grab_main()
        self._apply_page(name)
        self.update_idletasks()
        new = self._grab_main()
        if old is None or new is None:
            return
        self._fade_busy = True
        overlay = self._content_overlay(old)
        if overlay is None:
            self._fade_busy = False
            return
        steps = 6

        def step(index):
            nonlocal overlay
            if index > steps:
                try:
                    overlay.destroy()
                except Exception:
                    pass
                self._fade_busy = False
                return
            try:
                blended = Image.blend(old, new, index / float(steps))
                photo = ImageTk.PhotoImage(blended)
                self._fade_photo = photo
                overlay.configure(image=photo)
            except Exception:
                pass
            self.after(16, lambda: step(index + 1))
        step(0)

    def _fade_content_in(self):
        if (not self.winfo_viewable() or self._fade_busy
                or "--selftest" in sys.argv or getattr(self, "_startup_animating", False)
                or getattr(self, "inline_dialog", None) is not None):
            return
        image = self._grab_main()
        if image is None:
            return
        self._fade_busy = True
        base = Image.new("RGB", image.size, BG)
        overlay = self._content_overlay(base)
        if overlay is None:
            self._fade_busy = False
            return
        steps = 5

        def step(index):
            nonlocal overlay
            if index > steps:
                try:
                    overlay.destroy()
                except Exception:
                    pass
                self._fade_busy = False
                return
            try:
                blended = Image.blend(base, image, index / float(steps))
                photo = ImageTk.PhotoImage(blended)
                self._fade_photo = photo
                overlay.configure(image=photo)
            except Exception:
                pass
            self.after(14, lambda: step(index + 1))
        step(0)

    def _transition(self, callback):
        callback()

    def show_page(self, name):
        self._apply_page(name)

    def _apply_page(self, name):
        self.current_page = name
        for page in self.pages.values():
            page.grid_remove()
        self.pages[name].grid()
        titles = {
            "home": ("主页", "选择一个实例，开始你的世界"),
            "download": ("下载", "原版、Mod、光影与整合包，都在这里"),
            "settings": ("设置", "调整 Java、内存与下载源"),
        }
        title, subtitle = titles.get(name, titles["home"])
        self.title_label.configure(text=title)
        self.subtitle_label.configure(text=subtitle)
        for key, button in self.nav_buttons.items():
            active = key == name
            button.configure(bg="#1C3A2B" if active else SIDEBAR,
                             fg="#E6FFF2" if active else "#B7C5BC")
        if name == "home":
            self.refresh_instances()
            self.render_hero()
        elif name == "settings":
            self.fill_settings()

    # ------------------------------------------------------------------ 任务窗口
    def show_tasks_window(self):
        if self.task_win is not None and self.task_win.winfo_exists():
            self.task_win.lift()
            return
        win = InlineDialog(self, 760, 540)
        win.title("任务详情")
        win.geometry("760x520")
        win.configure(bg=PANEL)
        win.transient(self)
        self.task_win = win
        text = tk.Text(win, bg="#0f1712", fg="#cfe8d6", insertbackground="#cfe8d6",
                       relief="flat", bd=0, font=("Consolas", 9), wrap="word")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        self.task_text = text
        self.refresh_task_window()

    def refresh_task_window(self):
        if self.task_win is None or not self.task_win.winfo_exists():
            return
        text = getattr(self, "task_text", None)
        if text is None or not text.winfo_exists():
            return
        lines = []
        for task in reversed(self.tasks.snapshot_all()):
            lines.append("[%s] %s · %s" % (task["status"], task["title"], task["stage"]))
            if task.get("error"):
                lines.append("  " + task["error"])
            for log in (task.get("logs") or [])[-6:]:
                lines.append("  | " + log)
            lines.append("")
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("end", "\n".join(lines) or "暂无任务")
        text.configure(state="disabled")
        text.see("end")
        if self.task_win is not None and self.task_win.winfo_exists():
            self.task_win.after(900, self.refresh_task_window)

    # ------------------------------------------------------------------ 退出
    def on_close(self):
        self.destroy()

class ContentPanel:
    def __init__(self, app, parent, kind):
        self.app = app
        self.parent = parent
        self.kind = kind
        self.hits = []
        self.offset = 0
        self.total = 0
        self.page = 1
        self.page_size = 20
        self.size_cache = {}
        self.preview_id = ""
        self.preview_slug = ""
        self.loaded = False
        self.hit_by_id = {}
        self.project_cache = {}
        self.loader_var = tk.StringVar(value="全部")
        self.gv_var = tk.StringVar()

    def build(self):
        self.parent.grid_rowconfigure(2, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)
        top = tk.Frame(self.parent, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self.query = tk.Entry(top, bg=PANEL, fg=INK, relief="flat",
                              highlightbackground=LINE, highlightthickness=1,
                              font=ft(9), width=32)
        self.query.pack(side="left", ipady=5)
        self.query.bind("<Return>", lambda e: self.search(False))
        tk.Button(top, text="搜索", bg=PANEL, fg="#4b7a5d", relief="flat", bd=0,
                  highlightbackground=LINE, highlightthickness=1, padx=10, pady=5,
                  cursor="hand2", font=ft(8),
                  command=lambda: self.search(False)).pack(side="left", padx=6)
        tk.Label(top, text="游戏版本", bg=BG, fg=MUTED, font=ft(8)).pack(side="left", padx=(8, 3))
        self.gv_combo = ttk.Combobox(top, textvariable=self.gv_var, width=11, font=ft(8))
        self.gv_combo.pack(side="left", padx=(0, 6))
        self.loader_combo = None
        if self.kind in ("mod", "modpack"):
            tk.Label(top, text="加载器", bg=BG, fg=MUTED, font=ft(8)).pack(side="left", padx=(4, 3))
            self.loader_combo = ttk.Combobox(
                top, textvariable=self.loader_var,
                values=("Fabric", "Forge", "NeoForge", "全部"),
                width=9, state="readonly", font=ft(8))
            self.loader_combo.pack(side="left")
            self.loader_var.set("全部")
        self.set_versions(self.app.version_choices())

        self.status = tk.Label(self.parent, text="点搜索查看热门内容；选中项目后右侧显示图片预览。",
                               bg=BG, fg=MUTED, font=ft(8), anchor="w")
        self.status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))

        body = tk.Frame(self.parent, bg=BG)
        body.grid(row=2, column=0, sticky="nsew", padx=12)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        table = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        table.grid(row=0, column=0, sticky="nsew")
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("title", "author", "downloads"),
                                 show="headings", height=13)
        for key, label, width in (("title", "名称", 300), ("author", "作者", 130),
                                  ("downloads", "下载量", 90)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, style="Minimal.Vertical.TScrollbar", orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.preview_selected())
        self.tree.bind("<Double-1>", lambda e: self.open_selected())

        preview = tk.Frame(body, bg=PANEL, width=292, highlightbackground=LINE,
                           highlightthickness=1)
        preview.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        preview.pack_propagate(False)
        icon_holder = tk.Frame(preview, bg="#e9f5ed", width=72, height=72)
        icon_holder.pack(anchor="w", padx=14, pady=(10, 6))
        icon_holder.pack_propagate(False)
        self.preview_icon = tk.Label(icon_holder, text="?", bg="#e9f5ed", fg="#2c6b42",
                                     font=ft(22, True))
        self.preview_icon.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_title = tk.Label(preview, text="选择项目", bg=PANEL, fg=INK,
                                      font=ft(10, True), wraplength=252, justify="left",
                                      anchor="w")
        self.preview_title.pack(fill="x", padx=14)
        self.preview_meta = tk.Label(preview, text="", bg=PANEL, fg=MUTED, font=ft(8),
                                     wraplength=252, justify="left", anchor="w")
        self.preview_meta.pack(fill="x", padx=14, pady=(2, 2))
        self.preview_size = tk.Label(preview, text="大小 —", bg=PANEL, fg="#4b7a5d",
                                     font=ft(8), anchor="w")
        self.preview_size.pack(fill="x", padx=14, pady=(0, 6))
        image_holder = tk.Frame(preview, bg="#f4f8f3", width=252, height=108)
        image_holder.pack(anchor="w", padx=14)
        image_holder.pack_propagate(False)
        self.preview_image = tk.Label(image_holder, text="图片预览", bg="#f4f8f3", fg=MUTED,
                                      font=ft(8), cursor="hand2")
        self.preview_image.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_image.bind("<Button-1>", lambda e: self.open_preview_image())
        self.preview_url = ""
        desc_frame = tk.Frame(preview, bg=PANEL)
        desc_frame.pack(fill="x", expand=False, padx=14, pady=(8, 4))
        self.preview_desc = tk.Text(desc_frame, height=3, wrap="word", bg=PANEL, fg="#5d6a61",
                                    relief="flat", bd=0, highlightthickness=0,
                                    font=ft(8), cursor="arrow")
        self.preview_desc.pack(side="left", fill="both", expand=True)
        desc_scroll = ttk.Scrollbar(desc_frame, style="Minimal.Vertical.TScrollbar", orient="vertical", command=self.preview_desc.yview)
        desc_scroll.pack(side="right", fill="y")
        self.preview_desc.configure(yscrollcommand=desc_scroll.set, state="disabled")

        button_row = tk.Frame(preview, bg=PANEL)
        button_row.pack(fill="x", padx=14, pady=(0, 12))
        self.source_btn = tk.Menubutton(button_row, text="Modrinth", bg=PANEL, fg="#4b7a5d",
                                        activebackground="#eef4ee", activeforeground=ACCENT_DARK,
                                        relief="flat", bd=0, highlightbackground=LINE,
                                        highlightthickness=1, padx=7, pady=6,
                                        cursor="hand2", font=ft(8))
        self.source_btn.pack(side="left")
        source_menu = tk.Menu(self.source_btn, tearoff=0)
        source_menu.add_command(label="打开 Modrinth", command=lambda: self._open_source("modrinth"))
        source_menu.add_command(label="搜索 MC百科", command=lambda: self._open_source("mcmod"))
        source_menu.add_command(label="搜索 CurseForge", command=lambda: self._open_source("curseforge"))
        self.source_btn.configure(menu=source_menu)
        self.source_menu = source_menu
        self.install_btn = tk.Button(button_row, text="安装", bg=ACCENT, fg="white",
                                     activebackground=ACCENT_DARK, activeforeground="white",
                                     relief="flat", bd=0, highlightthickness=0, padx=9, pady=6,
                                     cursor="hand2", font=ft(8),
                                     command=self.open_selected)
        self.install_btn.pack(side="left", padx=5)
        self.copy_btn = tk.Button(button_row, text="复制昵称", bg=PANEL, fg="#5d6a61",
                                  activebackground="#eef4ee", relief="flat", bd=0,
                                  highlightbackground=LINE, highlightthickness=1,
                                  padx=7, pady=6, cursor="hand2", font=ft(8),
                                  command=self._copy_preview_title)
        self.copy_btn.pack(side="left")
        button_row.pack_forget()
        button_row.pack(fill="x", padx=14, pady=(4, 4), before=desc_frame)

        bottom = tk.Frame(self.parent, bg=BG)
        bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 10))
        self.pager = tk.Frame(bottom, bg=BG)
        self.pager.pack(side="left")
        tk.Label(bottom, text="每页 20 条", bg=BG, fg=MUTED, font=ft(7)).pack(side="right")

    def set_versions(self, values):
        self.gv_combo.configure(values=values)
        if not self.gv_var.get() and values:
            instance = next((item for item in self.app.instances
                             if item.get("id") == self.app.selected_id), None)
            preferred = instance.get("mc_version") if instance else values[0]
            self.gv_var.set(preferred if preferred in values else values[0])

    def ensure_loaded(self):
        if not self.loaded:
            self.loaded = True
            self.search(False)

    def loader_key(self):
        raw = self.loader_var.get()
        if raw == "全部":
            return None
        return {"Fabric": "fabric", "Forge": "forge", "NeoForge": "neoforge"}.get(
            raw, str(raw).lower())

    def search(self, more=False, page=None):
        if page is not None:
            self.page = max(1, int(page))
        elif not more:
            self.page = 1
        query = self.query.get().strip()
        game_version = self.gv_var.get() or None
        loader = None if self.kind in ("shader", "resourcepack") else self.loader_key()
        self.hits = []
        self.hit_by_id = {}
        self.tree.delete(*self.tree.get_children())
        self.status.configure(text="搜索中…")
        self.page = max(1, self.page)
        offset = (self.page - 1) * self.page_size
        self.app.background(
            lambda: self.app.modrinth.search(self.kind, query, game_version, loader,
                                             self.page_size, offset),
            lambda data: self.render(data, more),
            lambda exc: self.status.configure(text="搜索失败：%s" % exc),
        )

    def go_page(self, page):
        if page < 1:
            return
        self.search(False, page=page)

    def build_pager(self):
        for child in self.pager.winfo_children():
            child.destroy()
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page = min(max(1, self.page), pages)
        if pages <= 1:
            return

        def button(text, page, current=False):
            return tk.Button(
                self.pager, text=text, bg=ACCENT if current else PANEL,
                fg="white" if current else "#5d6a61", activebackground=ACCENT_DARK if current else "#eef4ee",
                activeforeground="white" if current else INK, relief="flat", bd=0,
                highlightbackground=LINE, highlightthickness=1, padx=8, pady=4,
                cursor="hand2", font=ft(8), command=lambda p=page: self.go_page(p))

        button("‹", self.page - 1).pack(side="left", padx=(0, 4))
        start_page = max(1, self.page - 3)
        end_page = min(pages, start_page + 6)
        start_page = max(1, end_page - 6)
        if start_page > 1:
            button("1", 1).pack(side="left", padx=2)
            if start_page > 2:
                tk.Label(self.pager, text="…", bg=BG, fg=MUTED, font=ft(8)).pack(side="left", padx=2)
        for number in range(start_page, end_page + 1):
            button(str(number), number, number == self.page).pack(side="left", padx=2)
        if end_page < pages:
            if end_page < pages - 1:
                tk.Label(self.pager, text="…", bg=BG, fg=MUTED, font=ft(8)).pack(side="left", padx=2)
            button(str(pages), pages).pack(side="left", padx=2)
        button("›", self.page + 1).pack(side="left", padx=(4, 0))

    def render(self, data, more=False):
        hits = data.get("hits") or []
        self.hits = hits
        self.hit_by_id = {}
        self.tree.delete(*self.tree.get_children())
        self.total = int(data.get("total") or 0)
        self.offset = (self.page - 1) * self.page_size
        for hit in hits:
            project_id = hit.get("project_id")
            self.hit_by_id[project_id] = hit
            self.tree.insert("", "end", iid=project_id, values=(
                hit.get("title"), hit.get("author") or "",
                fmt_num(hit.get("downloads")),
            ))
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.status.configure(text="找到 %d 个结果 · 第 %d/%d 页" % (self.total, self.page, pages))
        self.build_pager()
        if hits and not self.tree.selection():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.preview_selected()

    def _set_preview_desc(self, text):
        self.preview_desc.configure(state="normal")
        self.preview_desc.delete("1.0", "end")
        self.preview_desc.insert("1.0", text or "")
        self.preview_desc.configure(state="disabled")

    def _copy_preview_title(self):
        title = self.preview_title.cget("text")
        if title and title != "选择项目":
            self.clipboard_clear()
            self.clipboard_append(title)
            self.app.task_label.configure(text="已复制：" + title)

    def _open_source(self, target):
        title = self.preview_title.cget("text")
        if not title or title == "选择项目":
            return
        query = urllib.parse.quote_plus(title)
        if target == "modrinth" and getattr(self, "preview_slug", ""):
            type_name = {"mod": "mod", "shader": "shader", "resourcepack": "resourcepack",
                         "modpack": "modpack"}.get(self.kind, "mod")
            url = "https://modrinth.com/%s/%s" % (type_name, self.preview_slug)
        elif target == "mcmod":
            url = "https://search.mcmod.cn/s?key=" + query
        else:
            url = "https://www.curseforge.com/minecraft/search?search=" + query
        self.app.open_url(url)

    def load_size(self, project_id):
        cached = self.size_cache.get(project_id)
        if cached is not None:
            if self.preview_id == project_id:
                self.preview_size.configure(text="大小 " + (fmt_bytes(cached) if cached else "未知"))
            return
        self.preview_id = project_id
        self.preview_size.configure(text="大小 …")

        def load():
            return self.app.modrinth.versions(project_id)

        def done(versions):
            size = 0
            try:
                if versions:
                    file = self.app.modrinth.primary_file(versions[0])
                    if file:
                        size = int(file.get("size") or 0)
            except Exception:
                size = 0
            self.size_cache[project_id] = size
            if self.preview_id == project_id:
                self.preview_size.configure(text="大小 " + (fmt_bytes(size) if size else "未知"))

        self.app.background(load, done, lambda exc: None)

    def preview_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        project_id = selection[0]
        hit = self.hit_by_id.get(project_id)
        if not hit:
            return
        self.preview_id = project_id
        title = hit.get("title") or "项目"
        self.preview_title.configure(text=title)
        self.preview_meta.configure(text="%s · %s 次下载" % (
            hit.get("author") or "", fmt_num(hit.get("downloads"))))
        self.preview_slug = hit.get("slug") or ""
        self._set_preview_desc(str(hit.get("description") or ""))
        self.load_size(project_id)
        self.app.images.set_label(self.preview_icon, hit.get("icon_url"), (68, 68),
                                  (title[:1] or "?").upper())
        self.app.images.set_label(self.preview_image, hit.get("icon_url"), (248, 104), "")
        cached = self.project_cache.get(project_id)
        if cached:
            self._apply_preview(project_id, cached)
            return

        def load():
            return self.app.modrinth.project(project_id)

        def done(project):
            self.project_cache[project_id] = project
            self._apply_preview(project_id, project)

        self.app.background(load, done, lambda exc: None)

    def _apply_preview(self, project_id, project):
        gallery = project.get("gallery") or []
        url = ""
        if gallery:
            url = gallery[0].get("url") or gallery[0].get("raw_url") or ""
        if not url:
            url = project.get("icon_url") or ""
        self.preview_url = url
        self.preview_slug = project.get("slug") or self.preview_slug
        if url:
            self.app.images.set_label(self.preview_image, url, (248, 104), "")
        else:
            self.preview_image.configure(text="暂无预览图")
        description = str(project.get("description") or "")
        self._set_preview_desc(description)

    def open_preview_image(self):
        if getattr(self, "preview_url", ""):
            self.app.open_image_preview(self.preview_url, self.preview_title.cget("text"))

    def open_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("安装", "请先选择一个项目。", parent=self.app)
            return
        loader = None if self.kind in ("shader", "resourcepack") else self.loader_key()
        self.app.open_project(self.kind, selection[0], self.gv_var.get(), loader)



def main():
    try:
        app = LauncherApp()
        app.mainloop()
    except Exception:
        import traceback
        log_path = os.path.join(DATA_DIR, "gui-error.log")
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(time.strftime("%Y-%m-%d %H:%M:%S") + chr(10))
                handle.write(traceback.format_exc())
                handle.write(chr(10))
        except Exception:
            pass
        try:
            messagebox.showerror("SCL 错误", "SCL 遇到错误，详情见 gui-error.log")
        except Exception:
            pass

if __name__ == "__main__":
    main()
