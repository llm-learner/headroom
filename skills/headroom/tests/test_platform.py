"""Cross-platform installer, hook-launch, and macOS display logic.

Every test uses a temporary HOME/CODEX_HOME and fake native objects, so the
suite runs on Windows, macOS, and Linux without touching real Codex config.
"""

import contextlib
import importlib.util
import io
import json
import os
import queue
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "hooks"))
import headroom_desktop as desktop  # noqa: E402
import headroom_hook as hook  # noqa: E402
import headroom_tray as tray  # noqa: E402
import install_hooks as installer  # noqa: E402

FOREIGN = {"type": "command", "command": "echo keep-me", "timeout": 5}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "home with space"
        self.codex = self.home / ".codex"
        self.target = self.codex / "hooks.json"
        env = patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home),
                                      "CODEX_HOME": str(self.codex)})
        env.start()
        self.addCleanup(env.stop)

    def run_installer(self, *argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = installer.main(list(argv))
        return code, output.getvalue()

    def backups(self):
        return sorted(self.codex.glob("hooks.json.bak-*"))

    def test_posix_commands_are_quoted_python3_without_powershell(self):
        root = Path("/Users/me/My Repos/head'room/skills/headroom")
        hooks = installer.build_hooks(root, "/opt/homebrew/bin/python3", windows=False)
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit"})
        for event, flag in (("SessionStart", "--session-start"), ("UserPromptSubmit", "--user-prompt")):
            entry = hooks[event][0]["hooks"][0]
            self.assertNotIn("commandWindows", entry)
            self.assertNotIn("&", entry["command"])
            self.assertNotIn("powershell", entry["command"].lower())
            self.assertEqual(shlex.split(entry["command"]),
                             ["/opt/homebrew/bin/python3", str(root / "hooks" / "headroom_hook.py"), flag])
            self.assertTrue(entry["async"])
        self.assertEqual(hooks["SessionStart"][0]["matcher"], "startup|resume|clear|compact")
        self.assertNotIn("matcher", hooks["UserPromptSubmit"][0])
        shown = installer.build_hooks(root, "python3", display="desktop", windows=False)
        self.assertTrue(shown["SessionStart"][0]["hooks"][0]["command"].startswith(
            "HEADROOM_DISPLAY=desktop python3 "))
        self.assertNotIn("HEADROOM_DISPLAY", shown["UserPromptSubmit"][0]["hooks"][0]["command"])

    def test_windows_entries_match_the_powershell_installer_template(self):
        root, python = Path("C:/Users/me/headroom/skills/headroom"), "C:/Python312/python.exe"
        template = (SKILL / "hooks" / "hooks.json.template").read_text(encoding="utf-8")
        expected = json.loads(template.replace("__PLUGIN_ROOT__", str(root).replace("\\", "/"))
                              .replace("__PYTHON__", python))["hooks"]
        self.assertEqual(installer.build_hooks(root, python, windows=True), expected)

    def test_fresh_install_is_idempotent_and_creates_data_dir(self):
        code, output = self.run_installer()
        self.assertEqual(code, 0, output)
        data = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(data["description"], installer.DESCRIPTION)
        entry = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        if sys.platform == "win32":
            self.assertIn(installer.default_python().replace("\\", "/"), entry["commandWindows"])
        else:
            self.assertEqual(shlex.split(entry["command"])[0], installer.default_python())
        self.assertTrue((self.codex / "headroom").is_dir())
        before = self.target.read_bytes()
        code, output = self.run_installer()
        self.assertEqual(code, 0)
        self.assertIn("already up to date", output)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.backups(), [])

    def test_merge_keeps_other_hooks_backs_up_and_replaces_stale_entries(self):
        self.codex.mkdir(parents=True)
        stale = {"type": "command", "command": "python3 /old/place/hooks/headroom_hook.py --user-prompt"}
        original = {"hooks": {"UserPromptSubmit": [{"hooks": [FOREIGN]}, {"hooks": [stale]}],
                              "Stop": [{"hooks": [FOREIGN]}]}, "custom": 1}
        self.target.write_text(json.dumps(original), encoding="utf-8")
        code, output = self.run_installer("--python", sys.executable)
        self.assertEqual(code, 0, output)
        data = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(data["custom"], 1)
        self.assertNotIn("description", data)  # Never relabel a user's own file.
        self.assertEqual(data["hooks"]["Stop"], [{"hooks": [FOREIGN]}])
        prompt = data["hooks"]["UserPromptSubmit"]
        self.assertEqual(prompt[0], {"hooks": [FOREIGN]})
        self.assertEqual(len(prompt), 2)
        self.assertNotIn("/old/place", json.dumps(prompt))
        self.assertEqual(len(data["hooks"]["SessionStart"]), 1)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(json.loads(self.backups()[0].read_text(encoding="utf-8")), original)

        code, output = self.run_installer("--uninstall")
        self.assertEqual(code, 0, output)
        remaining = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(remaining, {"hooks": {"UserPromptSubmit": [{"hooks": [FOREIGN]}],
                                               "Stop": [{"hooks": [FOREIGN]}]}, "custom": 1})
        self.assertTrue((self.codex / "headroom").is_dir())  # Data is never deleted.

    def test_install_and_uninstall_preserve_commands_in_a_shared_hook_group(self):
        self.codex.mkdir(parents=True)
        stale = {"type": "command", "command": "python3 /old/hooks/headroom_hook.py --user-prompt"}
        shared = {"matcher": "*", "hooks": [FOREIGN, stale], "custom": "keep"}
        original = {"hooks": {"UserPromptSubmit": [shared]}}
        self.target.write_text(json.dumps(original), encoding="utf-8")
        code, output = self.run_installer()
        self.assertEqual(code, 0, output)
        installed = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(installed["hooks"]["UserPromptSubmit"][0],
                         {"matcher": "*", "hooks": [FOREIGN], "custom": "keep"})
        self.assertEqual(len(installed["hooks"]["UserPromptSubmit"]), 2)
        self.assertEqual(self.run_installer("--uninstall")[0], 0)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")),
                         {"hooks": {"UserPromptSubmit": [
                             {"matcher": "*", "hooks": [FOREIGN], "custom": "keep"}]}})

    def test_install_and_uninstall_keep_other_commands_that_mention_headroom(self):
        self.codex.mkdir(parents=True)
        lookalikes = [
            {"type": "command", "command": "echo /other/hooks/headroom_hook.py --user-prompt"},
            {"type": "command", "command": "python3 /other/hooks/headroom_hook.py --other"},
            {"type": "command", "command": "python3 /other/hooks/headroom_hook.py.bak --user-prompt"},
        ]
        stale = {"type": "command", "command": "python3 /old/hooks/headroom_hook.py --user-prompt"}
        original = {"hooks": {"UserPromptSubmit": [{"hooks": [*lookalikes, stale]}],
                              "Stop": [{"hooks": [stale]}]}}
        self.target.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(self.run_installer()[0], 0)
        installed = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(installed["hooks"]["UserPromptSubmit"][0]["hooks"], lookalikes)
        self.assertEqual(installed["hooks"]["Stop"], original["hooks"]["Stop"])
        self.assertEqual(self.run_installer("--uninstall")[0], 0)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")),
                         {"hooks": {"UserPromptSubmit": [{"hooks": lookalikes}],
                                    "Stop": [{"hooks": [stale]}]}})

    def test_replaces_stale_windows_command_without_removing_foreign_command(self):
        self.codex.mkdir(parents=True)
        stale = {"type": "command", "command": "echo placeholder",
                 "commandWindows": ('& "C:/Python Folder/python.exe" '
                                    '"C:/old/hooks/headroom_hook.py" --user-prompt')}
        foreign = {"type": "command", "command": "echo keep-me",
                   "commandWindows": "Write-Output headroom_hook.py"}
        self.target.write_text(json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [foreign, stale]}]}}), encoding="utf-8")
        self.assertEqual(self.run_installer()[0], 0)
        installed = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(installed["hooks"]["UserPromptSubmit"][0]["hooks"], [foreign])
        self.assertEqual(self.run_installer("--uninstall")[0], 0)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")),
                         {"hooks": {"UserPromptSubmit": [{"hooks": [foreign]}]}})

    def test_install_keeps_unrelated_empty_group_unchanged(self):
        self.codex.mkdir(parents=True)
        empty = {"matcher": "future", "hooks": [], "custom": "keep"}
        original = {"hooks": {"Stop": [empty]}}
        self.target.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(self.run_installer()[0], 0)
        installed = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(installed["hooks"]["Stop"], [empty])
        self.assertEqual(self.run_installer("--uninstall")[0], 0)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), original)

    def test_uninstall_removes_a_headroom_only_file_and_is_repeatable(self):
        self.assertEqual(self.run_installer()[0], 0)
        (self.codex / "headroom" / "ledger.sqlite3").write_bytes(b"keep")
        code, output = self.run_installer("--uninstall")
        self.assertEqual(code, 0, output)
        self.assertFalse(self.target.exists())
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual((self.codex / "headroom" / "ledger.sqlite3").read_bytes(), b"keep")
        code, output = self.run_installer("--uninstall")
        self.assertEqual(code, 0)
        self.assertIn("No headroom hooks", output)

    def test_dry_run_and_invalid_config_never_write(self):
        code, output = self.run_installer("--dry-run")
        self.assertEqual(code, 0, output)
        self.assertIn("headroom_hook.py", output)
        self.assertFalse(self.codex.exists())
        self.codex.mkdir(parents=True)
        self.target.write_text("{not json", encoding="utf-8")
        code, output = self.run_installer()
        self.assertEqual(code, 1)
        self.assertIn("error", output)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "{not json")
        self.assertEqual(self.backups(), [])

    def test_rejects_python_older_than_3_10(self):
        with patch.object(installer, "python_version", return_value=(3, 9)):
            code, output = self.run_installer("--python", "/usr/bin/python3")
        self.assertEqual(code, 1)
        self.assertIn("3.10+", output)
        self.assertFalse(self.target.exists())

    @unittest.skipIf(sys.platform == "win32", "symlinks need extra privileges on Windows")
    def test_optional_skill_link_is_created_and_removed(self):
        code, output = self.run_installer("--link-skill")
        self.assertEqual(code, 0, output)
        link = self.home / ".agents" / "skills" / "headroom"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), SKILL.resolve())
        self.assertEqual(self.run_installer("--link-skill")[0], 0)
        self.assertEqual(self.run_installer("--uninstall")[0], 0)
        self.assertFalse(link.exists() or link.is_symlink())

    @unittest.skipIf(sys.platform == "win32" or not shutil.which("sh"), "POSIX shell wrapper")
    def test_install_sh_wrapper_installs_into_temporary_home(self):
        env = {**os.environ, "HOME": str(self.home), "PYTHON": sys.executable}
        env.pop("CODEX_HOME")
        result = subprocess.run(["sh", str(SKILL / "hooks" / "install.sh"), "--display", "desktop"],
                                capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.target.read_text(encoding="utf-8"))
        start = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertTrue(start.startswith("HEADROOM_DISPLAY=desktop "))
        self.assertEqual(shlex.split(start)[1], sys.executable)

    @unittest.skipIf(sys.platform == "win32" or not shutil.which("sh"), "POSIX shell wrapper")
    def test_install_sh_uses_python_path_with_spaces_and_rejects_bad_override(self):
        chosen = self.home / "Python with spaces"
        chosen.parent.mkdir(parents=True)
        chosen.symlink_to(sys.executable)
        env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex),
               "PYTHON": str(chosen)}
        script = str(SKILL / "hooks" / "install.sh")
        result = subprocess.run(["sh", script], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.target.read_text(encoding="utf-8"))
        for event in ("SessionStart", "UserPromptSubmit"):
            command = data["hooks"][event][0]["hooks"][0]["command"]
            self.assertEqual(Path(shlex.split(command)[0]).resolve(), chosen.resolve())
        self.assertEqual(self.run_installer("--uninstall")[0], 0)
        self.assertFalse(self.target.exists())
        result = subprocess.run(["sh", script], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.target.read_bytes()
        env["PYTHON"] = str(self.home / "missing Python")
        bad = subprocess.run(["sh", script], capture_output=True, text=True, env=env, timeout=60)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("PYTHON must point", bad.stderr)
        self.assertEqual(self.target.read_bytes(), before)


@unittest.skipIf(sys.platform == "win32" or not shutil.which("sh"),
                 "installed POSIX hook commands run through /bin/sh")
class InstalledHooksEndToEndTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="headroom e2e ")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.codex = self.home / ".codex"
        self.codex.mkdir()
        self.ledger = self.codex / "headroom" / "ledger.sqlite3"
        self.debug = self.codex / "headroom" / "last-hook.json"
        yesterday = datetime.now(desktop.headroom.SHANGHAI).date() - timedelta(days=1)
        with contextlib.closing(sqlite3.connect(self.codex / "thread_history_1.sqlite")) as conn:
            conn.execute("CREATE TABLE thread_items (item_type TEXT, created_at_ms INTEGER)")
            conn.execute("INSERT INTO thread_items VALUES (?, ?)",
                         ("userMessage", desktop.headroom.day_start_ms(yesterday)))
            conn.commit()
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex),
                    "PYTHON": sys.executable, "HEADROOM_DISABLE_DASHBOARD": "1",
                    "HEADROOM_BACKEND": "mock", "HEADROOM_STATE_PATH": str(self.ledger),
                    "HEADROOM_DEBUG_PATH": str(self.debug)}
        self.env.pop("HEADROOM_PLUGIN_ROOT", None)
        self.env.pop("HEADROOM_HOOK_STRICT", None)

    def install(self, *args):
        return subprocess.run(["sh", str(SKILL / "hooks" / "install.sh"), *args],
                              capture_output=True, text=True, env=self.env, timeout=60)

    def run_hook(self, config, event, payload):
        command = config["hooks"][event][0]["hooks"][0]["command"]
        result = subprocess.run(["/bin/sh", "-c", command],
                                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                capture_output=True, env=self.env, timeout=35)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        return json.loads(self.debug.read_text(encoding="utf-8"))

    def debit_count(self):
        with contextlib.closing(sqlite3.connect(self.ledger)) as conn:
            return conn.execute("SELECT COUNT(*) FROM debits").fetchone()[0]

    def test_installed_commands_charge_once_skip_background_and_uninstall_cleanly(self):
        installed = self.install("--display", "off", "--link-skill")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        config_path = self.codex / "hooks.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        skill_link = self.home / ".agents" / "skills" / "headroom"
        self.assertEqual(skill_link.resolve(), SKILL.resolve())
        before = config_path.read_bytes()
        self.assertEqual(self.install("--display", "off", "--link-skill").returncode, 0)
        self.assertEqual(config_path.read_bytes(), before)

        session = {"session_id": "e2e-session", "cwd": str(self.home),
                   "hook_event_name": "SessionStart", "source": "startup"}
        self.assertEqual(self.run_hook(config, "SessionStart", session)["outcome"],
                         "display_ready_or_starting")
        self.assertFalse(self.ledger.exists())

        prompt = "端到端测试：你好？🧪"
        event = {"session_id": "e2e-session", "turn_id": "turn-1", "cwd": str(self.home),
                 "hook_event_name": "UserPromptSubmit", "permission_mode": "default",
                 "prompt": prompt}
        self.assertEqual(self.run_hook(config, "UserPromptSubmit", event)["outcome"], "charged")
        self.assertEqual(self.debit_count(), 1)
        self.assertEqual(self.run_hook(config, "UserPromptSubmit", event)["outcome"], "duplicate")
        self.assertEqual(self.debit_count(), 1)
        self.assertEqual(self.run_hook(config, "UserPromptSubmit", {**event, "turn_id": "turn-2",
                                                                      "permission_mode": "plan"})["outcome"],
                         "ineligible")
        self.assertEqual(self.run_hook(config, "UserPromptSubmit", {**event, "turn_id": "turn-3",
                                                                      "source": "scheduled"})["outcome"],
                         "ineligible")
        self.assertEqual(self.debit_count(), 1)
        status = subprocess.run([sys.executable, str(SKILL / "scripts" / "headroom.py"), "status"],
                                capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertGreater(json.loads(status.stdout)["spent_points"], 0)
        self.assertNotIn(prompt.encode("utf-8"), self.ledger.read_bytes())
        self.assertNotIn(prompt, self.debug.read_text(encoding="utf-8"))

        removed = self.install("--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(config_path.exists())
        self.assertFalse(skill_link.exists())
        self.assertEqual(self.debit_count(), 1)

    def test_browser_context_is_not_scored_as_user_text(self):
        installed = self.install("--display", "off")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        config = json.loads((self.codex / "hooks.json").read_text(encoding="utf-8"))
        context = ('<in-app-browser-context source="ambient-ui-state">\n'
                   + "Browser state? " * 30
                   + '\n</in-app-browser-context>\n\n## My request:\n')
        event = {"session_id": "browser-session", "turn_id": "turn-1",
                 "hook_event_name": "UserPromptSubmit", "permission_mode": "default",
                 "prompt": context + "现在呢？"}
        result = self.run_hook(config, "UserPromptSubmit", event)
        self.assertEqual(result["outcome"], "charged")
        self.assertEqual(result["charged_points"], 2.0)
        self.assertEqual(result["prompt_length"], len("现在呢？"))
        self.assertEqual(self.debit_count(), 1)

        event["turn_id"] = "turn-2"
        event["prompt"] = context + "  "
        self.assertEqual(self.run_hook(config, "UserPromptSubmit", event)["outcome"],
                         "ineligible")
        self.assertEqual(self.debit_count(), 1)


class HookLaunchTests(unittest.TestCase):
    def test_display_processes_are_detached_per_platform(self):
        with patch.object(hook.subprocess, "Popen") as spawn:
            hook.spawn_detached(["python3", "display.py"], None)
        options = spawn.call_args.kwargs
        if sys.platform == "win32":
            self.assertIn("creationflags", options)
            self.assertNotIn("start_new_session", options)
        else:
            self.assertTrue(options["start_new_session"])
            self.assertNotIn("creationflags", options)
        self.assertIs(options["stdin"], subprocess.DEVNULL)

    def test_default_display_is_web_outside_windows(self):
        env = {"HEADROOM_DISABLE_DASHBOARD": "0", "HEADROOM_DISABLE_DESKTOP": "0"}
        with patch.dict(os.environ, env), patch.object(hook, "start_dashboard") as web, \
                patch.object(hook, "spawn_detached") as spawn:
            os.environ.pop("HEADROOM_DISPLAY", None)
            hook.start_display(None)
        if sys.platform == "win32":
            spawn.assert_called_once()
            web.assert_not_called()
        else:
            web.assert_called_once()
            spawn.assert_not_called()


class TrayIconTests(unittest.TestCase):
    """A custom icon has to survive both menu bar appearances."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        try:
            import PIL  # noqa: F401 — Pillow is an optional desktop extra
            import headroom_tray
        except ImportError:
            self.skipTest("Pillow is not installed")
        self.tray = headroom_tray

    def test_dark_pixels_lighten_and_the_accent_survives(self):
        from PIL import Image
        image = Image.new("RGBA", (2, 1))
        image.putpixel((0, 0), (16, 32, 64, 255))    # dark navy
        image.putpixel((1, 0), (32, 96, 240, 255))   # bright accent
        out = self.tray.lighten_for_dark(image)
        navy = out.getpixel((0, 0))
        accent = out.getpixel((1, 0))
        self.assertGreater(sum(navy[:3]), sum((16, 32, 64)))
        self.assertEqual(accent[:3], (32, 96, 240))
        self.assertEqual(out.getpixel((0, 0))[3], 255)

    def test_transparent_pixels_stay_transparent(self):
        from PIL import Image
        image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        self.assertEqual(self.tray.lighten_for_dark(image).getpixel((0, 0)), (0, 0, 0, 0))

    def test_a_dark_sibling_wins_in_dark_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            light = Path(temp) / "menubar-icon.png"
            dark = Path(temp) / "menubar-icon-dark.png"
            light.write_bytes(b"x")
            env = {"HEADROOM_ICON": str(light)}
            with patch.dict(os.environ, env, clear=False):
                self.assertEqual(self.tray.custom_icon_path(False), light)
                # No sibling yet: the light file is reused.
                self.assertEqual(self.tray.custom_icon_path(True), light)
                dark.write_bytes(b"x")
                self.assertEqual(self.tray.custom_icon_path(True), dark)

    def test_appearance_probe_never_raises(self):
        self.assertIn(self.tray.system_is_dark(), (True, False))

    def test_a_per_user_icon_outranks_the_bundled_default(self):
        """Shipping a default icon must not shadow the per-user one.

        custom_icon_path returns the first file that exists, so a bundled
        default listed first would make ~/.headroom/icon.png unreachable.
        """
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            env = {"HOME": str(home), "USERPROFILE": str(home)}
            with patch.dict(os.environ, env, clear=True):
                bundled = self.tray.custom_icon_path(False)
                self.assertEqual(bundled.name, "menubar-icon.png")
                self.assertEqual(bundled.parent.name, "assets")
                (home / ".headroom").mkdir()
                mine = home / ".headroom" / "icon.png"
                mine.write_bytes(b"x")
                self.assertEqual(self.tray.custom_icon_path(False), mine)


class TclLibraryTests(unittest.TestCase):
    """A detached venv process loses Tcl's search path; headroom sets it."""

    def test_missing_variables_are_derived_from_a_prefix(self):
        import headroom_desktop as desktop
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp)
            for name in ("tcl9.0", "tk9.0"):
                (prefix / "lib" / name).mkdir(parents=True)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("TCL_LIBRARY", "TK_LIBRARY")}
            with patch.dict(os.environ, env, clear=True),                     patch.object(desktop.sys, "base_prefix", str(prefix)),                     patch.object(desktop.sys, "prefix", str(prefix)),                     patch.object(desktop.sys, "platform", "darwin"):
                desktop.ensure_tcl_library()
                self.assertEqual(os.environ["TCL_LIBRARY"], str(prefix / "lib" / "tcl9.0"))
                self.assertEqual(os.environ["TK_LIBRARY"], str(prefix / "lib" / "tk9.0"))

    def test_existing_variables_are_left_alone(self):
        import headroom_desktop as desktop
        env = {"TCL_LIBRARY": "/mine/tcl", "TK_LIBRARY": "/mine/tk"}
        with patch.dict(os.environ, env, clear=False):
            desktop.ensure_tcl_library()
            self.assertEqual(os.environ["TCL_LIBRARY"], "/mine/tcl")
            self.assertEqual(os.environ["TK_LIBRARY"], "/mine/tk")

    def test_non_darwin_is_untouched(self):
        import headroom_desktop as desktop
        env = {k: v for k, v in os.environ.items()
               if k not in ("TCL_LIBRARY", "TK_LIBRARY")}
        with patch.dict(os.environ, env, clear=True),                 patch.object(desktop.sys, "platform", "linux"):
            desktop.ensure_tcl_library()
            self.assertNotIn("TCL_LIBRARY", os.environ)


class CliTests(unittest.TestCase):
    def test_status_cli_honors_codex_home_like_the_hook_and_dashboard(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            with contextlib.closing(sqlite3.connect(home / "thread_history_1.sqlite")) as conn:
                conn.execute("CREATE TABLE thread_items (item_type TEXT, created_at_ms INTEGER)")
                conn.commit()
            env = {**os.environ, "CODEX_HOME": str(home), "HOME": str(home / "elsewhere")}
            env.pop("HEADROOM_STATE_PATH", None)
            result = subprocess.run([sys.executable, str(SKILL / "scripts" / "headroom.py"), "status"],
                                    capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["left_percent"], 100)
            self.assertFalse((home / "headroom" / "ledger.sqlite3").exists())


class DesktopPlatformTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_tray_card_opens_above_bottom_taskbar_and_below_top_menu_bar(self):
        area = (0, 25, 1440, 900)
        self.assertEqual(desktop.tray_card_top(880, area), 880 - desktop.CARD_H - 12)
        self.assertEqual(desktop.tray_card_top(12, area), 24)
        x, y = desktop.clamp_position(1200 - desktop.CARD_W, desktop.tray_card_top(12, area),
                                      desktop.CARD_W, desktop.CARD_H, area)
        self.assertGreaterEqual(y, area[1])
        self.assertLessEqual(y + desktop.CARD_H, area[3])

    @unittest.skipIf(sys.platform == "win32", "POSIX flock lock")
    def test_posix_instance_lock_is_per_ledger_and_released(self):
        first = desktop.InstanceLock(self.root / "a.sqlite3")
        second = desktop.InstanceLock(self.root / "a.sqlite3")
        other = desktop.InstanceLock(self.root / "b.sqlite3")
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            self.assertTrue(other.acquire())
            first.close()
            self.assertTrue(second.acquire())
        finally:
            for lock in (first, second, other):
                lock.close()

    def test_fallback_starts_web_dashboard_or_reuses_running_one(self):
        args = SimpleNamespace(codex_home=self.root, state_path=self.root / "ledger.sqlite3",
                               settings_path=self.root / "desktop.json", lang="en", show=False)
        stderr = io.StringIO()
        with patch.object(desktop.os, "execv") as execv, patch("socket.create_connection",
                                                                side_effect=OSError), \
                contextlib.redirect_stderr(stderr):
            desktop.fall_back_to_web(args, "no tray here")
        command = execv.call_args.args[1]
        self.assertTrue(command[1].endswith("headroom_dashboard.py"))
        self.assertEqual(command[command.index("--state-path") + 1], str(args.state_path))
        self.assertEqual(command[command.index("--lang") + 1], "en")
        self.assertIn("no tray here", stderr.getvalue())
        self.assertIn("http://127.0.0.1:8766/?lang=en", stderr.getvalue())
        with patch.object(desktop.os, "execv") as execv, patch("socket.create_connection"), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(desktop.fall_back_to_web(args, "no tray here"), 0)
        execv.assert_not_called()

    def test_windows_only_webview_renderer_is_not_the_default_elsewhere(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root)}):
            args = desktop.parse_args([])
        self.assertEqual(args.renderer, "webview" if sys.platform == "win32" else "tk")


class FakeDetachedIcon:
    def __init__(self, name, icon, title, menu):
        self.name, self.icon, self.title, self.menu = name, icon, title, menu
        self.visible = False
        self.detached = 0

    def run(self, setup=None):
        raise AssertionError("macOS must not start a separate AppKit loop")

    def run_detached(self, setup=None):
        self.detached += 1

    def stop(self):
        raise AssertionError("macOS must not stop Tk's NSApplication")

    def update_menu(self):
        pass


def tray_dependencies_importable():
    if not (importlib.util.find_spec("pystray") and importlib.util.find_spec("PIL")):
        return False
    try:
        import pystray  # noqa: F401  (backend selection needs a desktop session)
    except Exception:
        return False
    return True


@unittest.skipUnless(tray_dependencies_importable(), "optional tray dependencies")
class MacMenuBarTests(unittest.TestCase):
    def test_macos_status_item_runs_detached_on_the_calling_thread(self):
        view = desktop.presentation({"left_percent": 80, "spent_points": 2, "cap_points": 10}, "en")
        events = queue.Queue()
        with patch("pystray.Icon", FakeDetachedIcon), patch.object(tray.sys, "platform", "darwin"), \
                patch.object(tray, "hide_dock_icon") as hide_dock:
            icon = tray.TrayIcon(events, desktop.TEXT["en"], view)
            icon.start()
            self.assertIsNone(icon.thread)
            self.assertEqual(icon.icon.detached, 1)
            self.assertTrue(icon.icon.visible)
            hide_dock.assert_called_once()
            list(icon.icon.menu)[0](icon.icon)
            self.assertEqual(events.get_nowait(), "toggle")
            icon.close()
            self.assertFalse(icon.icon.visible)


if __name__ == "__main__":
    unittest.main(verbosity=2)
