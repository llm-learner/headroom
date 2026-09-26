"""Local, read-only headroom tray meter (Windows notification area or macOS
menu bar), with an optional desktop orb."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # e.g. Homebrew Python without python-tk
    tk = None


def ensure_tcl_library() -> None:
    """Point Tcl/Tk at their library directory before any Tk object exists.

    A venv interpreter normally resolves ``tcl_library`` from its base prefix.
    A process started detached (new session, no controlling terminal) can lose
    that and die with "Cannot find a usable init.tcl" — which looks like a
    missing Tk but is really a search-path problem. Setting the variables up
    front makes every launch path behave the same.
    """
    if sys.platform != "darwin" or tk is None:
        return
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return
    for prefix in (Path(sys.base_prefix), Path(sys.prefix)):
        lib = prefix / "lib"
        tcl = sorted(lib.glob("tcl[89].*"))
        tklib = sorted(lib.glob("tk[89].*"))
        if tcl and tklib:
            os.environ.setdefault("TCL_LIBRARY", str(tcl[-1]))
            os.environ.setdefault("TK_LIBRARY", str(tklib[-1]))
            return


ensure_tcl_library()

import headroom
from headroom_dashboard import ASSET_DIR, TEXT as WEB_TEXT


BALL = 64
CARD_W, CARD_H = 320, 306
KEY = "#ff00ff"
# Tk on macOS has no -transparentcolor; it draws "systemTransparent" instead.
TRANSPARENT = "systemTransparent" if sys.platform == "darwin" else KEY
if sys.platform == "darwin":
    UI_FONT, CJK_FONT = "Helvetica Neue", "PingFang SC"
else:
    UI_FONT, CJK_FONT = "Segoe UI", "Microsoft YaHei UI"
INK, BLUE, MUTED = "#14213d", "#2563eb", "#61708c"
#: Audio-only clips, the same ones the web dashboard's mood button plays.
MOOD_CLIPS = ("dog-dadada.m4a", "dog-industry-baby.m4a")
#: How far the mood image hops when clicked, in pixels.
MOOD_HOP = 7


def play_clip(name: str) -> None:
    """Play one bundled clip. macOS uses its own ``afplay``; elsewhere silent.

    Tk cannot decode video, so the tray card plays audio only — the animated
    clips stay in the web dashboard.
    """
    if sys.platform != "darwin":
        return
    path = ASSET_DIR / "audio" / name
    if not path.is_file():
        return
    try:
        subprocess.Popen(["afplay", str(path)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
TEXT = {
    "zh": {**WEB_TEXT["zh"], "open": "展开用量", "collapse": "收起",
           "exit": "退出 headroom", "language": "语言", "english": "英文", "chinese": "中文",
           "desktop_error": "暂时无法读取本机用量", "switch": "EN"},
    "en": {**WEB_TEXT["en"], "open": "Show usage", "collapse": "Collapse",
           "exit": "Exit headroom", "language": "Language", "english": "English", "chinese": "Chinese",
           "desktop_error": "Local usage is unavailable", "switch": "ZH"},
}


def read_usage(codex_home: Path, state_path: Path, adapters=None) -> dict:
    """No HTTP server, scorer, writes, or creation of a missing ledger."""
    selected = list(adapters) if adapters else [headroom.CodexAdapter(root=codex_home)]
    return headroom.usage(selected, datetime.now(headroom.SHANGHAI).date(), state_path)


def presentation(data: dict | None, lang: str) -> dict:
    labels = TEXT[lang]
    if data is not None:
        values = [data.get(key) for key in ("left_percent", "spent_points", "cap_points")]
        if (not all(type(v) in (int, float) and math.isfinite(v) for v in values)
                or not 0 <= values[0] <= 100 or values[1] < 0 or values[2] <= 0):
            data = None
    if data is None:
        return {"percent": None, "value": "--", "value_number": "--", "orb": "--",
                "color": MUTED, "meta": labels["desktop_error"], "image": None,
                "left_label": labels["left"], "mood": labels["mood_full"]}
    percent, spent, cap = values
    mood = ("brain-full.png" if percent >= 70 else
            "brain-low.png" if percent < 30 else "brain-declining.webp")
    mood_label = ("mood_full" if percent >= 70 else
                  "mood_low" if percent < 30 else "mood_declining")
    color = BLUE if percent >= 70 else "#c87918" if percent >= 30 else "#dc4a59"
    # Floor the compact number: 0.4% must not look like 1%, 99.9% like 100%.
    orb = "<1" if 0 < percent < 1 else str(math.floor(percent))
    return {"percent": percent, "value": f"{percent:.2f}%",
            # The card draws the "%" separately so it can be set smaller.
            "value_number": f"{percent:.2f}", "orb": orb,
            "color": color, "image": mood, "mood": labels[mood_label],
            "left_label": labels["left"],
            "meta": f"{labels['spent']} {spent:.2f} / {cap:g} {labels['points']}"}


def read_preferences(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        clean = {key: data[key] for key in ("x", "y")
                 if type(data.get(key)) is int and abs(data[key]) <= 100000}
        if data.get("lang") in ("zh", "en"):
            clean["lang"] = data["lang"]
        if type(data.get("muted")) is bool:
            clean["muted"] = data["muted"]
        return clean
    except (OSError, ValueError, UnicodeError):
        return {}


def save_preferences(path: Path, x: int, y: int, lang: str, muted: bool | None = None) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".headroom-desktop-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            data = {"x": int(x), "y": int(y), "lang": lang}
            muted = read_preferences(path).get("muted") if muted is None else muted
            if type(muted) is bool:
                data["muted"] = muted
            json.dump(data, handle)
        os.replace(temporary, path)
    except OSError:
        pass  # Display remains usable on read-only filesystems.
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def clamp_position(x, y, width, height, area):
    left, top, right, bottom = area
    return (max(left, min(int(x), right - width)),
            max(top, min(int(y), bottom - height)))


def tray_card_top(anchor_y, area):
    """Above a bottom taskbar; below a top bar such as the macOS menu bar."""
    top = anchor_y - CARD_H - 12
    return top if top >= area[1] else anchor_y + 12


def card_position(x, y, area):
    top = y - CARD_H - 12
    if top < area[1]:
        top = y + BALL + 12
    return clamp_position(x + BALL - CARD_W, top, CARD_W, CARD_H, area)


def mac_work_area():
    """Visible frame of the main screen (minus menu bar and Dock), top-left origin."""
    try:
        from AppKit import NSScreen
        # Cocoa's origin is the primary screen's bottom-left corner; Tk's is its top-left.
        primary = NSScreen.screens()[0].frame()
        visible = NSScreen.mainScreen().visibleFrame()
    except Exception:  # pyobjc is optional; pystray pulls it in on macOS.
        return None
    left = int(visible.origin.x)
    top = int(primary.size.height - visible.origin.y - visible.size.height)
    return left, top, left + int(visible.size.width), top + int(visible.size.height)


def work_area(root, x=0, y=0):
    if sys.platform == "darwin":
        area = mac_work_area()
        if area is not None:
            return area
    if sys.platform == "win32":
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user.MonitorFromPoint.restype = wintypes.HANDLE
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        monitor = user.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)
        if user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right, r.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def place_window(window, width, height, x, y):
    window.geometry(f"{width}x{height}")
    window.update_idletasks()
    if sys.platform == "win32":
        # Absolute desktop coordinates also work on monitors left of primary.
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        handle = user.GetAncestor(window.winfo_id(), 2)
        user.SetWindowPos(handle, None, int(x), int(y), width, height, 0x0010 | 0x0004)
    else:
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


class InstanceLock:
    """One display per ledger per login session; no open network port.

    Windows uses a named mutex. macOS/Linux use an advisory ``flock`` on a
    per-user file in the temp directory, released by the kernel on exit.
    """
    def __init__(self, state_path: Path):
        self.handle = None
        digest = hashlib.sha256(os.path.normcase(str(state_path.resolve())).encode()).hexdigest()[:24]
        self.name = "Local\\HeadroomDesktop-" + digest
        uid = os.getuid() if hasattr(os, "getuid") else "user"
        self.path = Path(tempfile.gettempdir()) / f"headroom-desktop-{uid}-{digest}.lock"

    def acquire(self):
        if sys.platform != "win32":
            return self.acquire_posix()
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            self.close()
            return False
        return True

    def acquire_posix(self):
        import fcntl
        handle = open(self.path, "a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def close(self):
        if self.handle:
            if sys.platform == "win32":
                self.kernel.CloseHandle(self.handle)
            else:
                self.handle.close()  # Releases the flock; keep the file to avoid races.
            self.handle = None


def flat_button(parent, command, **options):
    """A colored, borderless button.

    Aqua ``tk.Button`` ignores background colors (white text would vanish on
    the refresh button), so macOS gets a clickable label with ``invoke()``.
    """
    if sys.platform != "darwin":
        return tk.Button(parent, command=command, **options)
    for key in ("relief", "bd", "activebackground", "activeforeground"):
        options.pop(key, None)
    label = tk.Label(parent, **options)
    label.invoke = command
    label.bind("<ButtonRelease-1>", lambda _event: command())
    return label


def rounded(canvas, x1, y1, x2, y2, radius, **options):
    points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,
              x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)


class DesktopOrb:
    def __init__(self, root, codex_home, state_path, settings_path, lang=None, *,
                 visible=True, mode="orb", adapters=None):
        if mode not in ("tray", "orb"):
            raise ValueError("Display mode must be tray or orb")
        self.root, self.codex_home, self.state_path = root, codex_home, state_path
        self.adapters = list(adapters) if adapters else None
        self.settings_path, self.visible = settings_path, visible
        self.mode, self.tray, self.tray_anchor = mode, None, None
        self.actions = queue.Queue()
        saved = read_preferences(settings_path)
        self.lang = lang or saved.get("lang", "zh")
        self.data, self.updated, self.failed = None, "", False
        self.expanded, self.busy, self.closed = False, False, False
        self.results = queue.Queue(maxsize=1)
        self.images = {}
        self.menu = None
        self.poll_id = self.refresh_id = None
        self.press = None
        self.dragged = False
        # Mood-image click state: a hop that must survive a repaint, plus a
        # rotating clip so repeated clicks do not repeat the same sound.
        self.mood_hop_id = None
        self.mood_hop_token = 0
        self.mood_clip = 0
        area = work_area(root, saved.get("x", 0), saved.get("y", 0))
        self.x, self.y = clamp_position(saved.get("x", area[2]-BALL-24),
                                       saved.get("y", area[3]-BALL-32), BALL, BALL, area)
        self.setup_window(root, "headroom")
        self.orb = tk.Canvas(root, width=BALL, height=BALL, bg=TRANSPARENT, highlightthickness=0,
                             cursor="hand2", takefocus=True)
        self.orb.pack()
        self.orb.bind("<ButtonPress-1>", self.on_press)
        self.orb.bind("<B1-Motion>", self.on_drag)
        self.orb.bind("<ButtonRelease-1>", self.on_release)
        # Aqua Tk 8.6 reports the right button as Button-2; Control-click too.
        for sequence in (("<Button-2>", "<Control-Button-1>") if sys.platform == "darwin"
                         else ("<Button-3>",)):
            self.orb.bind(sequence, self.show_menu)
        self.orb.bind("<Return>", lambda _event: self.toggle())
        self.orb.bind("<space>", lambda _event: self.toggle())
        root.bind("<Escape>", lambda _event: self.collapse())
        root.protocol("WM_DELETE_WINDOW", self.close)
        if sys.platform == "darwin":
            root.createcommand("tk::mac::Quit", self.close)  # Cmd-Q / Dock Quit
        self.panel = tk.Toplevel(root)
        self.setup_window(self.panel, "headroom usage")
        self.panel.bind("<Escape>", lambda _event: self.collapse())
        self.panel.protocol("WM_DELETE_WINDOW", self.collapse)
        self.card = tk.Canvas(self.panel, width=CARD_W, height=CARD_H,
                              bg=TRANSPARENT, highlightthickness=0)
        self.card.pack()
        # Bound once; paint() re-tags the mood plate and image on every redraw.
        self.card.tag_bind("mood", "<ButtonRelease-1>", lambda _event: self.play_mood())
        self.card.tag_bind("mood", "<Enter>", lambda _event: self.card.configure(cursor="hand2"))
        self.card.tag_bind("mood", "<Leave>", lambda _event: self.card.configure(cursor=""))
        self.language_button = flat_button(self.panel, command=self.switch_language, relief="flat",
                                        bg="white", fg=MUTED, bd=0, cursor="hand2", font=(UI_FONT, 10))
        self.language_button.place(x=231, y=17, width=34, height=28)
        self.collapse_button = flat_button(self.panel, text="−", command=self.collapse, relief="flat",
                                       bg="white", fg=MUTED, bd=0, cursor="hand2", font=(UI_FONT, 17))
        self.collapse_button.place(x=271, y=15, width=28, height=30)
        self.refresh_button = flat_button(self.panel, command=self.request_refresh, relief="flat",
                                      bg=BLUE, fg="white", activebackground="#1d4ed8", activeforeground="white",
                                      bd=0, cursor="hand2", font=(UI_FONT, 12))
        # Inset by the drawn pill's corner radius so the label's square corners
        # stay inside the rounded shape.
        self.refresh_button.place(x=36, y=257, width=CARD_W-72, height=20)
        self.paint()
        if visible and mode == "orb":
            root.deiconify()
        if mode == "orb":
            place_window(root, BALL, BALL, self.x, self.y)
        self.panel.withdraw()

    @staticmethod
    def setup_window(window, title):
        window.withdraw()
        window.title(title)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=TRANSPARENT)
        if sys.platform == "win32":
            window.attributes("-transparentcolor", KEY)
            window.attributes("-toolwindow", True)
        elif sys.platform == "darwin":
            window.attributes("-transparent", True)

    def start(self):
        if self.mode == "tray":
            from headroom_tray import TrayIcon
            self.tray = TrayIcon(self.actions, TEXT[self.lang], presentation(self.data, self.lang))
            self.tray.start()
        self.request_refresh()
        self.poll_id = self.root.after(100, self.poll)
        self.refresh_id = self.root.after(10000, self.periodic_refresh)

    def request_refresh(self):
        if self.busy or self.closed:
            return
        self.busy = True
        # Show the click immediately: the number rarely changes between two
        # reads, so without this a refresh looks like nothing happened.
        self.refresh_button.configure(text=TEXT[self.lang]["loading"])

        def read():
            try:
                data = read_usage(self.codex_home, self.state_path, self.adapters)
            except Exception:  # a reader must never wedge the button
                data = None
            finally:
                # poll() clears busy only when a result arrives, so a reader
                # that raised something unexpected would otherwise leave the
                # button permanently inert. A full queue is also resolved here
                # rather than left to wedge the next refresh.
                try:
                    self.results.put_nowait((data, datetime.now().strftime("%H:%M:%S")))
                except queue.Full:
                    try:
                        self.results.get_nowait()
                        self.results.put_nowait((data, datetime.now().strftime("%H:%M:%S")))
                    except (queue.Empty, queue.Full):
                        pass

        threading.Thread(target=read, daemon=True, name="headroom-reader").start()

    def play_mood(self):
        """Hop the mood image and play a clip — the dashboard's click, in Tk.

        Tk cannot decode the bundled videos, so the card plays their audio and
        animates the still. The token guards against a repaint landing between
        the hop and the settle, which would otherwise leave the image offset.
        """
        self.mood_hop_token += 1
        token = self.mood_hop_token
        self.card.move("mood", 0, -MOOD_HOP)
        if self.mood_hop_id:
            self.root.after_cancel(self.mood_hop_id)
        self.mood_hop_id = self.root.after(180, lambda: self.settle_mood(token))
        name = MOOD_CLIPS[self.mood_clip % len(MOOD_CLIPS)]
        self.mood_clip += 1
        play_clip(name)

    def settle_mood(self, token):
        self.mood_hop_id = None
        if not self.closed and token == self.mood_hop_token:
            self.card.move("mood", 0, MOOD_HOP)

    def periodic_refresh(self):
        if not self.closed:
            self.request_refresh()
            self.refresh_id = self.root.after(10000, self.periodic_refresh)

    def poll(self):
        if self.closed:
            return
        self.drain_actions()
        if self.closed:
            return
        try:
            self.data, self.updated = self.results.get_nowait()
            self.failed = self.data is None
            self.busy = False
            self.paint()
            self.reposition()
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self.poll)

    def drain_actions(self):
        """Called on the Tk thread, never from a native tray callback."""
        while not self.closed:
            try:
                action = self.actions.get_nowait()
            except queue.Empty:
                return
            if action == "toggle":
                if not self.expanded:
                    self.tray_anchor = (self.root.winfo_pointerx(), self.root.winfo_pointery())
                self.toggle()
            elif action == "refresh":
                self.request_refresh()
            elif action in ("en", "zh"):
                self.switch_language(action)
            elif action == "exit":
                self.close()

    def update_tray(self):
        if self.tray is not None:
            self.tray.update(TEXT[self.lang], presentation(self.data, self.lang), self.expanded)

    def mood_image(self, filename):
        if filename not in self.images:
            try:
                from PIL import Image, ImageTk
                with Image.open(ASSET_DIR / filename) as source:
                    source = source.convert("RGBA")
                    source.thumbnail((54, 54), Image.Resampling.LANCZOS)
                    self.images[filename] = ImageTk.PhotoImage(source, master=self.root)
            except ImportError:
                try:
                    source = tk.PhotoImage(file=str(ASSET_DIR / filename), master=self.root)
                    factor = max(1, math.ceil(max(source.width(), source.height()) / 54))
                    self.images[filename] = source.subsample(factor)
                except tk.TclError:
                    self.images[filename] = None
            except (OSError, tk.TclError, ValueError):
                self.images[filename] = None
        return self.images[filename]

    def paint(self):
        labels, view = TEXT[self.lang], presentation(self.data, self.lang)
        self.orb.delete("all")
        self.orb.create_oval(2, 2, 62, 62, fill=INK, outline="#dae4f5", width=1)
        self.orb.create_oval(6, 6, 58, 58, outline="#34445f", width=3)
        if view["percent"]:
            if view["percent"] == 100:
                self.orb.create_oval(6, 6, 58, 58, outline="#58c7ab", width=3)
            else:
                self.orb.create_arc(6, 6, 58, 58, start=90, extent=-3.6*view["percent"],
                                    style="arc", outline="#58c7ab" if view["percent"] >= 70 else view["color"], width=3)
        self.orb.create_text(32, 27, text=view["orb"], fill="white", font=(UI_FONT, 16, "bold"))
        self.orb.create_text(32, 44, text="%", fill="#adc2e7", font=(UI_FONT, 9))

        card = self.card
        card.delete("all")
        rounded(card, 1, 1, CARD_W-1, CARD_H-1, 18, fill="white", outline="#e4e9f2")
        # Header, then a hairline so the number reads as its own block.
        card.create_text(24, 30, anchor="w", text=labels["heading"], fill=INK,
                         font=(CJK_FONT, 14, "bold"))
        card.create_line(24, 52, CARD_W-24, 52, fill="#eef1f6")

        # The number and its unit are sized separately: a full-size "%" competes
        # with the digits at this scale.
        number = card.create_text(24, 86, anchor="w", text=view["value_number"],
                                  fill=view["color"], font=(UI_FONT, 32, "bold"))
        box = card.bbox(number)
        if box:
            card.create_text(box[2] + 3, 86, anchor="w", text="%",
                             fill=view["color"], font=(UI_FONT, 17, "bold"))
        card.create_text(25, 128, anchor="w", text=view["left_label"], fill=MUTED,
                         font=(CJK_FONT, 11))

        # Mood thumbnail on a soft plate so a transparent PNG still reads.
        # Tagged "mood" so a click hops it and plays a clip.
        rounded(card, 236, 66, 296, 126, 14, fill="#f5f8fd", outline="", tags="mood")
        if view["image"]:
            picture = self.mood_image(view["image"])
            if picture:
                card.create_image(266, 96, image=picture, tags="mood")
            else:
                card.create_text(266, 96,
                                 text=":)" if view["percent"] >= 70 else ":(" if view["percent"] >= 30 else ":O",
                                 fill=view["color"], font=(UI_FONT, 24, "bold"), tags="mood")

        # A thin, rounded meter instead of the old heavy bar.
        card.create_line(28, 156, CARD_W-28, 156, width=6, fill="#e8edf6", capstyle="round")
        if view["percent"]:
            end = 28 + (CARD_W - 56) * min(100.0, view["percent"]) / 100
            card.create_line(28, 156, max(31, end), 156, width=6, fill=view["color"],
                             capstyle="round")

        meta = labels["loading"] if self.data is None and not self.failed else view["meta"]
        card.create_text(24, 182, anchor="w", text=meta,
                         fill=INK if not self.failed else "#b42318",
                         font=(CJK_FONT, 10), tags="usage")
        if self.updated and not self.failed:
            card.create_text(24, 202, anchor="w", text=labels["updated"]+self.updated,
                             fill=MUTED, font=(CJK_FONT, 9))
        if view.get("mood") and not self.failed:
            card.create_text(24, 222, anchor="w", text=view["mood"], fill=MUTED,
                             font=(CJK_FONT, 9))

        # The button is drawn here and the label sits inset by the corner radius,
        # so its square corners stay inside the rounded shape.
        rounded(card, 24, 245, CARD_W-24, 289, 12, fill=BLUE, outline="")
        self.language_button.configure(text=labels["switch"])
        self.refresh_button.configure(text=labels["refresh"])
        self.update_tray()

    def reposition(self):
        if self.mode == "tray":
            if self.expanded:
                ax, ay = self.tray_anchor or (self.x, self.y)
                area = work_area(self.root, ax, ay)
                x, y = clamp_position(ax-CARD_W, tray_card_top(ay, area), CARD_W, CARD_H, area)
                place_window(self.panel, CARD_W, CARD_H, x, y)
            return
        area = work_area(self.root, self.x+BALL//2, self.y+BALL//2)
        self.x, self.y = clamp_position(self.x, self.y, BALL, BALL, area)
        place_window(self.root, BALL, BALL, self.x, self.y)
        if self.expanded:
            x, y = card_position(self.x, self.y, area)
            place_window(self.panel, CARD_W, CARD_H, x, y)

    def toggle(self):
        if self.expanded:
            self.collapse()
        else:
            self.expanded = True
            if self.visible:
                self.panel.deiconify()
            self.reposition()
            self.request_refresh()
            if self.visible:
                self.refresh_button.focus_set()
            self.update_tray()

    def collapse(self):
        self.expanded = False
        self.panel.withdraw()
        self.update_tray()

    def on_press(self, event):
        self.press = event.x_root, event.y_root, self.x, self.y
        self.dragged = False

    def on_drag(self, event):
        if self.press is None:
            return
        sx, sy, ox, oy = self.press
        dx, dy = event.x_root-sx, event.y_root-sy
        if abs(dx)+abs(dy) > 5:
            self.dragged = True
        if self.dragged:
            self.x, self.y = ox+dx, oy+dy
            self.reposition()

    def on_release(self, _event):
        if self.press is None:
            return
        self.press = None
        if self.dragged:
            self.save()
        else:
            self.toggle()

    def switch_language(self, lang=None):
        self.lang = lang or ("en" if self.lang == "zh" else "zh")
        self.paint()
        self.save()

    def show_menu(self, event):
        labels = TEXT[self.lang]
        if self.menu is not None:
            self.menu.destroy()
        menu = tk.Menu(self.root, tearoff=False)
        self.menu = menu
        menu.add_command(label=labels["collapse"] if self.expanded else labels["open"], command=self.toggle)
        menu.add_command(label=labels["refresh"], command=self.request_refresh)
        languages = tk.Menu(menu, tearoff=False)
        languages.add_command(label=labels["english"], command=lambda: self.switch_language("en"))
        languages.add_command(label=labels["chinese"], command=lambda: self.switch_language("zh"))
        menu.add_cascade(label=labels["language"], menu=languages)
        menu.add_separator()
        menu.add_command(label=labels["exit"], command=self.close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def save(self):
        save_preferences(self.settings_path, self.x, self.y, self.lang)

    def close(self):
        if not self.closed:
            self.closed = True
            self.save()
            for timer in (self.poll_id, self.refresh_id):
                if timer:
                    self.root.after_cancel(timer)
            if self.tray is not None:
                self.tray.close()
            self.root.destroy()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    parser.add_argument("--codex-home", type=Path, default=home)
    parser.add_argument("--agent-home", action="append", metavar="NAME=PATH",
                        help="override one agent's root; repeatable")
    parser.add_argument("--agents", default=os.environ.get("HEADROOM_AGENTS", "auto"),
                        help="'auto' to discover every installed agent, or a comma list")
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--settings-path", type=Path)
    parser.add_argument("--lang", choices=TEXT, default=os.environ.get("HEADROOM_LANG"))
    parser.add_argument("--mode", choices=("tray", "orb"),
                        default=os.environ.get("HEADROOM_DESKTOP_MODE", "tray"))
    parser.add_argument("--renderer", choices=("webview", "tk"),
                        default="webview" if sys.platform == "win32" else "tk",
                        help="tray card renderer; tk is a static, low-dependency fallback "
                             "(the WebView2 card is Windows-only)")
    parser.add_argument("--show", action="store_true", help="expand the card on startup")
    args = parser.parse_args(argv)
    if args.lang is not None and args.lang not in TEXT:
        parser.error("HEADROOM_LANG must be zh or en")
    if args.mode not in ("tray", "orb"):
        parser.error("HEADROOM_DESKTOP_MODE must be tray or orb")
    args.state_path = args.state_path or headroom.default_state_path()
    args.settings_path = args.settings_path or args.state_path.with_name("desktop.json")
    protected = {args.state_path.resolve(), (args.codex_home / "thread_history_1.sqlite").resolve(),
                 (args.codex_home / "headroom" / "config.json").resolve()}
    if args.settings_path.resolve() in protected:
        parser.error("--settings-path must not overwrite the ledger, history, or scoring config")
    return args


def dashboard_command(args, lang=None):
    dashboard = Path(__file__).resolve().with_name("headroom_dashboard.py")
    command = [sys.executable, str(dashboard), "--codex-home", str(args.codex_home),
               "--state-path", str(args.state_path)]
    return command + ["--lang", lang] if lang else command


def fall_back_to_web(args, reason, port=8766):
    """Non-Windows only: replace this process with the loopback web dashboard."""
    lang = args.lang or read_preferences(args.settings_path).get("lang")
    url = f"http://127.0.0.1:{port}/" + (f"?lang={lang}" if lang else "")
    print(f"headroom: {reason}\nheadroom: using the web dashboard instead: {url}",
          file=sys.stderr, flush=True)
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            running = True
    except OSError:
        running = False
    if args.show:
        import webbrowser
        webbrowser.open(url)
    if running:
        return 0
    command = dashboard_command(args, lang)
    os.execv(command[0], command)


def main():
    args = parse_args()
    try:
        args.adapters = headroom.select_adapters(args.agents, args.agent_home, args.codex_home)
    except (headroom.UnknownAgentError, ValueError) as exc:
        raise SystemExit(str(exc))
    if sys.platform != "win32" and args.mode == "tray" and args.renderer == "webview":
        print("headroom: the animated WebView2 tray card is Windows-only; using the static "
              "Tk card (clips still play in the web dashboard).", file=sys.stderr)
        args.renderer = "tk"
    lock = InstanceLock(args.state_path)
    if not lock.acquire():
        return 0
    if tk is None:
        lock.close()
        if sys.platform == "win32":
            raise RuntimeError("The desktop display needs Python with Tk")
        return fall_back_to_web(args, "the desktop display needs Python with Tk "
                                      "(for Homebrew: brew install python-tk)")
    app = None
    root = None
    fallback = None
    try:
        if args.mode == "tray" and args.renderer == "webview":
            from headroom_webcard import run
            return run(args)
        try:
            root = tk.Tk()
            app = DesktopOrb(root, args.codex_home, args.state_path, args.settings_path,
                             args.lang, mode=args.mode, adapters=args.adapters)
            app.start()
        except (RuntimeError, tk.TclError) as exc:
            # Windows keeps its original behavior; elsewhere degrade to the browser UI.
            if sys.platform == "win32":
                raise
            fallback = str(exc)
        if fallback is None:
            if args.show:
                root.after(0, app.toggle)
            root.mainloop()
    finally:
        if app is not None:
            app.close()
        elif root is not None:
            root.destroy()
        lock.close()
    if fallback is not None:
        return fall_back_to_web(args, fallback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
