"""Tray adapter (Windows notification area, macOS menu bar).

Native callbacks only enqueue actions for the card controller.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

#: Size the icon is authored at, in pixels. The menu bar draws it near 18pt.
ICON_PX = 64
#: Menu bar items are tiny; this is the widest the ring may get.
RING_INSET = 5


def hide_dock_icon():
    """Keep a menu-bar-only app out of the macOS Dock; harmless if AppKit is absent."""
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(1)  # Accessory
    except Exception:
        pass


def draw_icon(percent, color):
    """The built-in icon: a gauge ring around a bold H.

    Everything is drawn with thick strokes on a transparent background so it
    survives being scaled down to a menu bar, where a 1px detail is invisible.
    """
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (ICON_PX, ICON_PX), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outer = (1, 1, ICON_PX - 2, ICON_PX - 2)
    # A dark disc keeps the mark legible on light *and* dark menu bars.
    draw.ellipse(outer, fill="#14213d")
    ring = (RING_INSET, RING_INSET, ICON_PX - RING_INSET - 1, ICON_PX - RING_INSET - 1)
    width = 5
    draw.arc(ring, 0, 360, fill="#3d5273", width=width)
    if percent:
        draw.arc(ring, -90, -90 + 3.6 * min(100.0, percent), fill=color, width=width)
    # A legible H without depending on installed fonts: two stems and a bar.
    left, right = 22, 42
    top, bottom, mid = 21, 43, 32
    for x in (left, right):
        draw.line((x, top, x, bottom), fill="white", width=7)
    draw.line((left, mid, right, mid), fill="white", width=7)
    return image


def custom_icon_path(dark: bool = False) -> Path | None:
    """A user-supplied icon, if one is installed.

    Checked before the drawn icon so a generated image can be dropped in
    without touching code. ``HEADROOM_ICON`` wins, then a per-user
    ``~/.headroom/icon.png``, then the bundled default. A ``-dark`` sibling is
    used on a dark menu bar when present; otherwise the light one is recoloured.
    """
    import os
    configured = os.environ.get("HEADROOM_ICON")
    assets = Path(__file__).resolve().parents[1] / "assets"
    stems = ([Path(configured).expanduser()] if configured else [])
    # The per-user file comes before the bundled one: a shipped default would
    # otherwise shadow it, because the first existing file wins.
    stems += [Path.home() / ".headroom" / "icon.png", assets / "menubar-icon.png"]
    for stem in stems:
        if dark:
            variant = stem.with_name(stem.stem + "-dark" + stem.suffix)
            if variant.is_file():
                return variant
        if stem.is_file():
            return stem
    return None


def system_is_dark() -> bool:
    """Is the system in dark appearance? False when it cannot be determined."""
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSApp, NSAppearanceNameDarkAqua, NSApplication
        NSApplication.sharedApplication()
        appearance = NSApp.effectiveAppearance()
        if appearance is None:
            return False
        matched = appearance.bestMatchFromAppearancesWithNames_([NSAppearanceNameDarkAqua])
        return matched == NSAppearanceNameDarkAqua
    except Exception:
        pass
    try:
        import subprocess
        result = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                capture_output=True, text=True, timeout=3)
        return result.stdout.strip().lower() == "dark"
    except Exception:
        return False


#: What dark parts of a custom icon become on a dark menu bar.
DARK_REPLACEMENT = (201, 212, 232)


def lighten_for_dark(image):
    """Lift a custom icon's dark areas so they read on a dark menu bar.

    A hand-drawn icon usually pairs a dark accent with one bright accent; the
    dark half disappears against a dark menu bar. Pixels below the accent's
    brightness are blended toward a light slate, which keeps the shape and
    leaves the bright accent untouched. Run this after downscaling — it walks
    every pixel.
    """
    out = image.copy()
    pixels = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            level = max(r, g, b)
            if level >= 120:
                continue  # the bright accent colour stays as it is
            weight = (120 - level) / 120
            pixels[x, y] = (
                int(r + (DARK_REPLACEMENT[0] - r) * weight),
                int(g + (DARK_REPLACEMENT[1] - g) * weight),
                int(b + (DARK_REPLACEMENT[2] - b) * weight),
                a,
            )
    return out


def icon_image(percent, color, path: Path | None = None, dark: bool = False):
    """The icon to hand pystray: a custom file when present, else the drawn one."""
    explicit_dark = path is not None and path.stem.endswith("-dark")
    resolved = path if path is not None else custom_icon_path(dark)
    if resolved is not None:
        try:
            from PIL import Image
            with Image.open(resolved) as source:
                image = source.convert("RGBA")
            # Menu bar slots are square; letterbox rather than distort.
            image.thumbnail((ICON_PX, ICON_PX), Image.Resampling.LANCZOS)
            if dark and not explicit_dark:
                image = lighten_for_dark(image)
            canvas = Image.new("RGBA", (ICON_PX, ICON_PX), (0, 0, 0, 0))
            canvas.paste(image, ((ICON_PX - image.width) // 2,
                                 (ICON_PX - image.height) // 2), image)
            return canvas
        except (OSError, ValueError):
            pass  # A broken custom icon must not take the tray down.
    return draw_icon(percent, color)


class TrayIcon:
    def __init__(self, actions, labels, view):
        try:
            import pystray
            from PIL import Image  # noqa: F401 — check both dependencies up front
        except ImportError as exc:
            raise RuntimeError(
                "Tray mode requires pystray and Pillow. Install requirements-desktop.txt "
                "or launch with --mode orb."
            ) from exc
        self.actions = actions
        self.labels, self.expanded = labels, False
        self.ready, self.stopped = threading.Event(), threading.Event()
        self.error = None
        self.thread = None
        self.dark = system_is_dark()
        self.custom = custom_icon_path(self.dark)
        self.icon_key = (view["orb"], view["color"], self.dark)
        item, menu = pystray.MenuItem, pystray.Menu
        self.icon = pystray.Icon(
            "headroom", icon_image(view["percent"], view["color"], self.custom, self.dark),
            self.title(view),
            menu(
                item(lambda _: self.labels["collapse"] if self.expanded else self.labels["open"],
                     self.action("toggle"), default=True),
                item(lambda _: self.labels["refresh"], self.action("refresh")),
                item(lambda _: self.labels["language"], menu(
                    item(lambda _: self.labels["english"], self.action("en")),
                    item(lambda _: self.labels["chinese"], self.action("zh")))),
                menu.SEPARATOR,
                item(lambda _: self.labels["exit"], self.action("exit")),
            ),
        )

    def title(self, view):
        """Hover text. Uses the card's own labels so it follows the language."""
        if view["percent"] is None:
            return "headroom · " + self.labels["desktop_error"]
        return f"headroom · {view['value']} {self.labels['left']}"

    def action(self, name):
        def enqueue(_icon, _item):
            self.actions.put(name)
        return enqueue

    def start(self):
        if sys.platform == "darwin":
            self.start_detached()
            return

        def setup(icon):
            try:
                if not self.stopped.is_set():
                    icon.visible = True
            except Exception as exc:
                self.error = exc
            finally:
                self.ready.set()

        def run():
            try:
                self.icon.run(setup=setup)
            except Exception as exc:
                self.error = exc
            finally:
                self.ready.set()

        self.thread = threading.Thread(target=run, daemon=True, name="headroom-tray")
        self.thread.start()
        if not self.ready.wait(3) or self.error or not self.icon.visible:
            self.close()
            raise RuntimeError("Could not start the Windows headroom tray icon") from self.error

    def start_detached(self):
        """AppKit status items must live on the main thread.

        Call this from the Tk thread after ``tk.Tk()`` exists: Tk's Aqua event
        loop already pumps the shared NSApplication, so no extra thread runs.
        """
        try:
            hide_dock_icon()
            self.icon.run_detached(setup=lambda _icon: None)
            if not self.stopped.is_set():
                self.icon.visible = True
        except Exception as exc:
            self.error = exc
        finally:
            self.ready.set()
        if self.error or not self.icon.visible:
            self.close()
            raise RuntimeError("Could not start the macOS headroom menu bar icon") from self.error

    def update(self, labels, view, expanded):
        menu_changed = labels != self.labels or expanded != self.expanded
        self.labels, self.expanded = labels, expanded
        self.icon.title = self.title(view)
        # Re-check the appearance so the icon follows a light/dark switch.
        self.dark = system_is_dark()
        key = (view["orb"], view["color"], self.dark)
        if key != self.icon_key:
            self.custom = custom_icon_path(self.dark)
            self.icon.icon = icon_image(view["percent"], view["color"], self.custom, self.dark)
            self.icon_key = key
        if menu_changed:
            self.icon.update_menu()

    def close(self):
        self.stopped.set()
        if self.thread is None and sys.platform == "darwin":
            # NSApplication belongs to Tk here; only remove our status item.
            try:
                self.icon.visible = False
            except Exception:
                pass
            return
        self.icon.stop()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
