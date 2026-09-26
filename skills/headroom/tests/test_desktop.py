"""Desktop checks use withdrawn windows and temporary histories/ledgers only."""

import contextlib
import io
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import headroom as budget
import headroom_desktop as desktop
import headroom_hook as hook


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "ledger.sqlite3"
        self.settings = self.root / "desktop.json"
        today = datetime.now(budget.SHANGHAI).date()
        stamp = budget.day_start_ms(today - timedelta(days=1))
        with contextlib.closing(sqlite3.connect(self.root / "thread_history_1.sqlite")) as conn:
            conn.execute("CREATE TABLE thread_items (item_type TEXT, created_at_ms INTEGER)")
            conn.executemany("INSERT INTO thread_items VALUES (?, ?)", [("userMessage", stamp)] * 2)
            conn.commit()

    def test_direct_reader_never_scores_or_creates_ledger(self):
        with patch.object(budget, "score_event", side_effect=AssertionError("must not score")):
            self.assertEqual(desktop.read_usage(self.root, self.state)["left_percent"], 100)
            self.assertFalse(self.state.exists())
            day = datetime.now(budget.SHANGHAI).date()
            with contextlib.closing(budget.open_state(self.state, create=True)) as conn:
                conn.execute("INSERT INTO debits (event_id, local_day, points, provider) "
                             "VALUES (?, ?, ?, ?)",
                             ("fixture", day.isoformat(), 2.5, "fixture"))
                conn.commit()
            before = self.state.read_bytes()
            for _ in range(3):
                result = desktop.read_usage(self.root, self.state)
                self.assertEqual(result["cap_points"], 4)
                self.assertEqual(result["left_percent"], 37.5)
            self.assertEqual(self.state.read_bytes(), before)

    def test_language_moods_errors_and_compact_percentage(self):
        for lang in ("en", "zh"):
            for percent, filename in [(100, "brain-full.png"), (70, "brain-full.png"),
                                      (69.99, "brain-declining.webp"), (30, "brain-declining.webp"),
                                      (29.99, "brain-low.png"), (0, "brain-low.png")]:
                result = desktop.presentation({"left_percent": percent, "spent_points": 2.5, "cap_points": 10}, lang)
                self.assertEqual(result["image"], filename)
                self.assertEqual(result["value"], f"{percent:.2f}%")
                if lang == "en":
                    self.assertNotRegex(result["meta"], r"[\u3400-\u9fff]")
            for bad in (None, -1, 101, float("nan"), True, "70"):
                self.assertIsNone(desktop.presentation({"left_percent": bad}, lang)["percent"])
            self.assertIsNone(desktop.presentation(None, lang)["image"])
        data = {"left_percent": .4, "spent_points": 2, "cap_points": 10}
        self.assertEqual(desktop.presentation(data, "en")["orb"], "<1")

    def test_preferences_are_small_validated_and_roundtrip(self):
        self.assertEqual(desktop.read_preferences(self.settings), {})
        desktop.save_preferences(self.settings, -300, 250, "en")
        self.assertEqual(desktop.read_preferences(self.settings), {"x": -300, "y": 250, "lang": "en"})
        for raw in ('invalid', 'null', '[]', '{"x":true,"y":999999,"lang":"other","prompt":"private"}'):
            self.settings.write_text(raw, encoding="utf-8")
            self.assertEqual(desktop.read_preferences(self.settings), {})
        self.assertFalse(self.state.exists())

    def test_positions_keep_ball_and_card_in_work_area(self):
        for area in ((0, 0, 1920, 1040), (-1920, -300, 0, 900), (0, 0, 800, 600)):
            for x, y in ((-99999, -99999), (99999, 99999), (50, 50)):
                ox, oy = desktop.clamp_position(x, y, desktop.BALL, desktop.BALL, area)
                px, py = desktop.card_position(ox, oy, area)
                for ax, ay, w, h in ((ox, oy, desktop.BALL, desktop.BALL),
                                     (px, py, desktop.CARD_W, desktop.CARD_H)):
                    self.assertGreaterEqual(ax, area[0])
                    self.assertGreaterEqual(ay, area[1])
                    self.assertLessEqual(ax+w, area[2])
                    self.assertLessEqual(ay+h, area[3])

    def test_cli_environment_precedence(self):
        with patch.dict(os.environ, {"HEADROOM_LANG": "en", "CODEX_HOME": str(self.root),
                                     "HEADROOM_STATE_PATH": str(self.state)}):
            args = desktop.parse_args([])
            self.assertEqual((args.lang, args.codex_home, args.state_path), ("en", self.root, self.state))
            self.assertEqual(desktop.parse_args(["--lang", "zh"]).lang, "zh")
            self.assertEqual(args.settings_path, self.settings)
            self.assertEqual(args.mode, "tray")
            # The animated WebView2 card is Windows-only; elsewhere default to Tk.
            self.assertEqual(args.renderer, "webview" if sys.platform == "win32" else "tk")
            self.assertEqual(desktop.parse_args(["--renderer", "tk"]).renderer, "tk")
            self.assertEqual(desktop.parse_args(["--mode", "orb"]).mode, "orb")
        with patch.dict(os.environ, {"HEADROOM_DESKTOP_MODE": "orb"}):
            self.assertEqual(desktop.parse_args([]).mode, "orb")
            self.assertEqual(desktop.parse_args(["--mode", "tray"]).mode, "tray")
        with patch.dict(os.environ, {"HEADROOM_DESKTOP_MODE": "bad"}), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                desktop.parse_args([])
        with patch.dict(os.environ, {"HEADROOM_LANG": "bad"}), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                desktop.parse_args([])
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                desktop.parse_args(["--lang", "en", "--state-path", str(self.state), "--settings-path", str(self.state)])

    def test_session_display_modes_and_smoke_suppression(self):
        env = {"CODEX_HOME": str(self.root), "HEADROOM_STATE_PATH": str(self.state),
               "HEADROOM_DISABLE_DASHBOARD": "0", "HEADROOM_DISABLE_DESKTOP": "0"}
        with patch.dict(os.environ, env), patch.object(hook, "start_dashboard") as web, \
                patch.object(hook.subprocess, "Popen") as spawn:
            for mode, web_count, orb_count in [("desktop", 0, 1), ("web", 1, 0),
                                               ("both", 1, 1), ("off", 0, 0)]:
                web.reset_mock()
                spawn.reset_mock()
                with patch.dict(os.environ, {"HEADROOM_DISPLAY": mode}):
                    hook.start_display(None)
                self.assertEqual(web.call_count, web_count)
                self.assertEqual(spawn.call_count, orb_count)
                if orb_count:
                    command = spawn.call_args.args[0]
                    self.assertTrue(command[1].endswith("headroom_desktop.py"))
                    self.assertEqual(command[command.index("--codex-home")+1], str(self.root))
                    self.assertEqual(command[command.index("--state-path")+1], str(self.state))
            spawn.reset_mock()
            web.reset_mock()
            with patch.dict(os.environ, {"HEADROOM_DISABLE_DASHBOARD": "1", "HEADROOM_DISPLAY": "both"}):
                hook.start_display(None)
            spawn.assert_not_called()
            web.assert_not_called()
            with patch.dict(os.environ, {"HEADROOM_DISPLAY": "bad"}):
                with self.assertRaises(ValueError):
                    hook.start_display(None)

    def test_single_instance_released_and_duplicate_cli_exits(self):
        first, second = desktop.InstanceLock(self.state), desktop.InstanceLock(self.state)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            result = subprocess.run([sys.executable, desktop.__file__, "--state-path", str(self.state)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            first.close()
            self.assertTrue(second.acquire())
        finally:
            first.close()
            second.close()
        self.assertFalse(self.state.exists())

    @unittest.skipUnless(sys.platform in ("win32", "darwin"), "Windows/macOS Tk widget integration")
    def test_tray_keeps_orb_hidden_and_dispatches_on_tk_thread(self):
        root = desktop.tk.Tk()
        app = desktop.DesktopOrb(root, self.root, self.state, self.settings, "en", visible=False, mode="tray")
        self.addCleanup(lambda: None if app.closed else app.close())
        with patch("headroom_tray.TrayIcon") as factory, patch.object(app, "request_refresh") as refresh:
            app.start()
            tray = factory.return_value
            tray.start.assert_called_once()
            self.assertEqual(root.state(), "withdrawn")
            position = (app.x, app.y)
            app.actions.put("toggle")
            self.assertFalse(app.expanded)  # Native callbacks cannot manipulate Tk.
            app.drain_actions()
            self.assertTrue(app.expanded)
            self.assertEqual(root.state(), "withdrawn")
            app.reposition()
            self.assertEqual((app.x, app.y), position)
            app.actions.put("zh")
            app.actions.put("refresh")
            app.drain_actions()
            self.assertEqual(app.lang, "zh")
            self.assertEqual(refresh.call_count, 3)
            self.assertEqual(tray.update.call_args.args[0], desktop.TEXT["zh"])
            app.collapse_button.invoke()
            self.assertFalse(app.expanded)
            self.assertEqual(app.panel.state(), "withdrawn")
            app.actions.put("exit")
            app.drain_actions()
            self.assertTrue(app.closed)
            tray.close.assert_called_once()
            app.close()  # Cleanup is idempotent.
            tray.close.assert_called_once()
        self.assertFalse(self.state.exists())

    @unittest.skipUnless(sys.platform in ("win32", "darwin") and os.environ.get("HEADROOM_TEST_NATIVE_TRAY") == "1",
                         "opt-in smoke briefly opens a real tray icon and usage card")
    def test_native_tray_and_popup_lifecycle(self):
        root = desktop.tk.Tk()
        app = desktop.DesktopOrb(root, self.root, self.state, self.settings, "en", mode="tray")
        self.addCleanup(lambda: None if app.closed else app.close())
        app.start()
        until = time.monotonic() + 5
        while app.data is None and time.monotonic() < until:
            root.update()
            time.sleep(.01)
        self.assertIsNotNone(app.data)
        self.assertTrue(app.tray.icon.visible)
        # macOS runs the status item on Tk's main-thread loop, not a tray thread.
        native_thread = sys.platform == "win32"
        if native_thread:
            self.assertTrue(app.tray.thread.is_alive())
        self.assertEqual(app.tray.icon.title, "headroom · 100.00% left")
        self.assertEqual(root.state(), "withdrawn")
        # Exercise the application's own callback, not OS input automation.
        list(app.tray.icon.menu)[0](app.tray.icon)
        app.drain_actions()
        root.update()
        self.assertTrue(app.panel.winfo_ismapped())
        self.assertFalse(root.winfo_ismapped())
        list(app.tray.icon.menu)[0](app.tray.icon)
        app.drain_actions()
        root.update()
        self.assertFalse(app.panel.winfo_ismapped())
        list(app.tray.icon.menu)[-1](app.tray.icon)
        app.drain_actions()
        self.assertTrue(app.closed)
        if native_thread:
            self.assertFalse(app.tray.thread.is_alive())
        else:
            self.assertFalse(app.tray.icon.visible)
        self.assertFalse(self.state.exists())

    @unittest.skipUnless(sys.platform in ("win32", "darwin"), "Windows/macOS Tk widget integration")
    def test_widgets_toggle_drag_language_refresh_and_close(self):
        root = desktop.tk.Tk()
        app = desktop.DesktopOrb(root, self.root, self.state, self.settings, "zh", visible=False)
        self.addCleanup(lambda: None if app.closed else app.close())
        app.start()
        until = time.monotonic() + 5
        while (app.busy or app.data is None) and time.monotonic() < until:
            root.update()
            time.sleep(.01)
        self.assertIsNotNone(app.data)
        self.assertFalse(app.expanded)
        self.assertEqual(root.state(), "withdrawn")
        with patch.object(app, "request_refresh") as refresh:
            app.on_press(SimpleNamespace(x_root=app.x+20, y_root=app.y+20))
            app.on_release(None)
            self.assertTrue(app.expanded)
            refresh.assert_called_once()
            app.collapse_button.invoke()
            self.assertFalse(app.expanded)
            app.on_press(SimpleNamespace(x_root=app.x+20, y_root=app.y+20))
            app.on_drag(SimpleNamespace(x_root=app.x-30, y_root=app.y-30))
            app.on_release(None)
            self.assertFalse(app.expanded)  # Dragging must never become a click.
            app.language_button.invoke()
            self.assertEqual(app.lang, "en")
            self.assertEqual(app.refresh_button.cget("text"), "Refresh")
            for percent in (100, 50, 10):
                app.data = {"left_percent": percent, "spent_points": 2, "cap_points": 10}
                app.paint()
                for item in app.card.find_all():
                    if app.card.type(item) == "text":
                        self.assertNotRegex(app.card.itemcget(item, "text"), r"[\u3400-\u9fff]")
                        x1, y1, x2, y2 = app.card.bbox(item)
                        self.assertGreaterEqual(x1, 0)
                        self.assertLessEqual(x2, desktop.CARD_W)
            self.assertEqual(len(app.images), 3)
            if importlib.util.find_spec("PIL") is not None:
                self.assertTrue(all(app.images.values()))
            with patch.dict(sys.modules, {"PIL": None}):
                app.images.clear()
                app.data["left_percent"] = 50
                app.paint()  # A text mood still works if WebP support is absent.
            with patch.object(desktop.tk.Menu, "tk_popup"):
                app.show_menu(SimpleNamespace(x_root=10, y_root=10))
            self.assertTrue(app.menu.winfo_exists())
            self.assertEqual(app.menu.entrycget(4, "label"), "Exit headroom")
            app.data, app.failed = None, True
            app.paint()
            self.assertIn("unavailable", app.card.itemcget(app.card.find_withtag("usage")[0], "text"))
        app.close()
        self.assertTrue(app.closed)
        self.assertEqual(desktop.read_preferences(self.settings)["lang"], "en")
        self.assertFalse(self.state.exists())


class CardInteractionTests(unittest.TestCase):
    """The card's own clicks: refresh feedback and the mood hop."""

    @unittest.skipUnless(sys.platform in ("win32", "darwin"), "Tk card needs a display")
    def test_refresh_shows_progress_and_always_clears_busy(self):
        root = desktop.tk.Tk()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root_path = Path(temp.name)
        app = desktop.DesktopOrb(root, root_path, root_path / "l.sqlite3",
                                 root_path / "d.json", "zh", visible=False, mode="tray",
                                 adapters=None)
        self.addCleanup(lambda: None if app.closed else app.close())
        # A reader that raises something outside the caught set must still
        # release the button, or every later refresh would be a no-op.
        with patch.object(desktop, "read_usage", side_effect=KeyError("boom")):
            app.request_refresh()
            self.assertTrue(app.busy)
            self.assertEqual(app.refresh_button.cget("text"), desktop.TEXT["zh"]["loading"])
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                app.poll()  # start() is not called, so drive the drain directly
                root.update()
                time.sleep(0.01)
        self.assertFalse(app.busy)
        self.assertEqual(app.refresh_button.cget("text"), desktop.TEXT["zh"]["refresh"])
        self.assertFalse((root_path / "l.sqlite3").exists())

    @unittest.skipUnless(sys.platform in ("win32", "darwin"), "Tk card needs a display")
    def test_mood_click_hops_rotates_clips_and_settles(self):
        root = desktop.tk.Tk()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root_path = Path(temp.name)
        app = desktop.DesktopOrb(root, root_path, root_path / "l.sqlite3",
                                 root_path / "d.json", "zh", visible=False, mode="tray",
                                 adapters=None)
        self.addCleanup(lambda: None if app.closed else app.close())
        app.data = {"left_percent": 26.67, "spent_points": 154.0, "cap_points": 210}
        app.paint()
        item = app.card.find_withtag("mood")[-1]
        resting = app.card.bbox(item)[1]
        played = []
        with patch.object(desktop, "play_clip", side_effect=played.append):
            app.play_mood()
            self.assertEqual(app.card.bbox(item)[1], resting - desktop.MOOD_HOP)
            app.settle_mood(app.mood_hop_token)
            self.assertEqual(app.card.bbox(item)[1], resting)
            app.play_mood()
            app.play_mood()
        self.assertEqual(len(played), 3)
        self.assertNotEqual(played[0], played[1])   # clips rotate
        self.assertEqual(played[0], played[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
