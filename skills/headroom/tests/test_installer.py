"""Installing the same hook into each agent's own config format.

test_platform.py covers the Codex contract the installer has always had. This
file covers what the other agents add: their own config paths, event names and
schema quirks, plus an end-to-end check that drives the real hook script with a
documented Claude Code payload and a documented Gemini CLI payload and asserts
both land in the same ledger with the same score.

Every test uses a temporary HOME, so the suite never touches a real agent's
settings.
"""

import contextlib
import io
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "hooks"))
import install_hooks as installer  # noqa: E402

FOREIGN = {"type": "command", "command": "echo keep-me", "timeout": 5}

#: A Claude Code UserPromptSubmit payload and a Gemini CLI BeforeAgent one, cut
#: down to the fields each product documents.
CLAUDE_PROMPT = {
    "session_id": "3f0c8b1e-0f5a-4d6e-9a11-7c2d4b6a8e10",
    "prompt_id": "b1d4e7f0-2a35-4c68-9b0c-1e2f3a4b5c6d",
    "transcript_path": "/Users/me/.claude/projects/-Users-me-src/x.jsonl",
    "cwd": "/Users/me/src", "permission_mode": "default",
    "hook_event_name": "UserPromptSubmit",
    "prompt": "Explain how the daily cap window is derived, and why today is excluded.",
}
GEMINI_PROMPT = {
    "session_id": "9d2a5c7e-1b3f-4a60-8e92-3c5d7f9a1b20",
    "transcript_path": "/Users/me/.gemini/tmp/abc/chats/session-2026-09-25.json",
    "cwd": "/Users/me/src", "hook_event_name": "BeforeAgent",
    "timestamp": "2026-09-25T02:00:00Z",
    "prompt": "Explain how the daily cap window is derived, and why today is excluded.",
}


class MultiAgentInstallerTests(unittest.TestCase):
    """The same installer, merged into Claude Code's and Gemini CLI's configs."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "home with space"
        self.codex = self.home / ".codex"
        self.claude = self.home / ".claude"
        self.gemini = self.home / ".gemini"
        self.target = self.codex / "hooks.json"
        env = {key: value for key, value in os.environ.items()
               if key not in ("CLAUDE_CONFIG_DIR", "GEMINI_DIR", "CODEX_HOME",
                              "HEADROOM_AGENT", "HEADROOM_STATE_PATH")}
        env.update({"HOME": str(self.home), "USERPROFILE": str(self.home),
                    "CODEX_HOME": str(self.codex)})
        env = patch.dict(os.environ, env, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def run_installer(self, *argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = installer.main(list(argv))
        return code, output.getvalue()

    #: Each product's name for "the user just submitted a prompt".
    PROMPT_EVENT = {"claude": "UserPromptSubmit", "gemini": "BeforeAgent"}

    def foreign_config(self, agent):
        """A settings file that already has a hook on both events headroom uses."""
        return {"model": "keep-me", "hooks": {
            self.PROMPT_EVENT[agent]: [{"hooks": [FOREIGN]}],
            "Stop": [{"hooks": [FOREIGN]}]}}

    def settings_path(self, agent):
        return getattr(self, agent) / "settings.json"

    def install_everything(self):
        for agent in self.PROMPT_EVENT:
            directory = getattr(self, agent)
            directory.mkdir(parents=True)
            self.settings_path(agent).write_text(json.dumps(self.foreign_config(agent)),
                                                 encoding="utf-8")
        self.codex.mkdir(parents=True, exist_ok=True)
        code, output = self.run_installer("--python", sys.executable)
        self.assertEqual(code, 0, output)
        return output

    def test_auto_wires_codex_and_every_other_agent_that_is_installed(self):
        # Nothing but Codex exists yet, so nothing but Codex is touched: the
        # installer never creates ~/.claude or ~/.gemini for a tool you do not use.
        code, output = self.run_installer("--python", sys.executable)
        self.assertEqual(code, 0, output)
        self.assertTrue(self.target.is_file())
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.gemini.exists())

        self.install_everything()
        for agent in self.PROMPT_EVENT:
            data = json.loads(self.settings_path(agent).read_text(encoding="utf-8"))
            self.assertEqual(data["model"], "keep-me")        # Other keys survive.
            self.assertEqual(data["hooks"]["Stop"], [{"hooks": [FOREIGN]}])
            self.assertNotIn("description", data)             # Codex's label stays Codex's.
            blocks = data["hooks"][self.PROMPT_EVENT[agent]]
            self.assertEqual(blocks[0], {"hooks": [FOREIGN]})  # Appended, not replaced.
            self.assertEqual(len(blocks), 2)
            self.assertEqual(len(data["hooks"]["SessionStart"]), 1)

    def test_codex_entries_are_unchanged_when_other_agents_are_present(self):
        self.install_everything()
        data = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(data["description"], installer.DESCRIPTION)
        self.assertEqual(set(data["hooks"]), {"SessionStart", "UserPromptSubmit"})
        entry = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertTrue(entry["async"])
        self.assertNotIn("HEADROOM_AGENT", entry["command"])   # Codex needs no variable.
        self.assertEqual(shlex.split(entry["command"])[-1], "--user-prompt")

    def test_claude_entries_match_claude_s_code_hook_schema(self):
        root = Path("/Users/me/My Repos/head'room/skills/headroom")
        hooks = installer.build_hooks(root, "/opt/homebrew/bin/python3",
                                      display="desktop", windows=False, agent="claude")
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit"})
        start = hooks["SessionStart"][0]["hooks"][0]
        self.assertEqual(shlex.split(start["command"]),
                         ["HEADROOM_AGENT=claude", "HEADROOM_DISPLAY=desktop",
                          "/opt/homebrew/bin/python3",
                          str(root / "hooks" / "headroom_hook.py"), "--session-start"])
        self.assertEqual(start["timeout"], 3)                 # Seconds, like Codex.
        self.assertEqual(start["statusMessage"], "Starting headroom dashboard")
        self.assertNotIn("commandWindows", start)             # That field is Codex-only.
        self.assertNotIn("async", start)                      # Never invented for another product.
        self.assertEqual(hooks["SessionStart"][0]["matcher"], "startup|resume|clear|compact")
        prompt = hooks["UserPromptSubmit"][0]["hooks"][0]
        self.assertNotIn("HEADROOM_DISPLAY", prompt["command"])   # Only SessionStart reads it.
        self.assertNotIn("matcher", hooks["UserPromptSubmit"][0])

    def test_gemini_entries_use_milliseconds_and_the_antigravity_agent_id(self):
        root = Path("/tmp/skills/headroom")
        hooks = installer.build_hooks(root, "/usr/bin/python3", windows=False, agent="gemini")
        # Gemini CLI has no UserPromptSubmit; BeforeAgent is its prompt event.
        self.assertEqual(set(hooks), {"SessionStart", "BeforeAgent"})
        self.assertEqual(shlex.split(hooks["BeforeAgent"][0]["hooks"][0]["command"])[0],
                         "HEADROOM_AGENT=antigravity")
        self.assertEqual(hooks["BeforeAgent"][0]["hooks"][0]["timeout"], 30000)
        self.assertEqual(hooks["SessionStart"][0]["hooks"][0]["timeout"], 3000)
        self.assertEqual(hooks["BeforeAgent"][0]["hooks"][0]["name"], "headroom")
        self.assertNotIn("statusMessage", hooks["BeforeAgent"][0]["hooks"][0])
        self.assertNotIn("matcher", hooks["SessionStart"][0])

    def test_an_explicit_agent_list_installs_exactly_those(self):
        code, output = self.run_installer("--python", sys.executable, "--agents", "claude,gemini")
        self.assertEqual(code, 0, output)
        self.assertFalse(self.target.exists())
        self.assertTrue((self.claude / "settings.json").is_file())
        self.assertTrue((self.gemini / "settings.json").is_file())
        code, output = self.run_installer("--agents", "nope")
        self.assertEqual(code, 1)
        self.assertIn("unknown agent", output)

    def test_uninstall_removes_every_agents_blocks_and_keeps_foreign_ones(self):
        self.install_everything()
        code, output = self.run_installer("--uninstall")
        self.assertEqual(code, 0, output)
        self.assertFalse(self.target.exists())   # Codex's file held nothing else.
        for agent in self.PROMPT_EVENT:
            remaining = json.loads(self.settings_path(agent).read_text(encoding="utf-8"))
            self.assertEqual(remaining, self.foreign_config(agent))  # Byte-for-byte back.
        self.assertTrue((self.codex / "headroom").is_dir())   # The ledger is never deleted.

    def test_one_scorer_charges_every_agent_into_the_shared_ledger(self):
        """The claim the installer exists to make.

        HEADROOM_AGENT is what the installed command line sets, so setting it in
        the environment is exactly what the real hook sees.
        """
        state = self.codex / "headroom" / "ledger.sqlite3"
        self.charge(CLAUDE_PROMPT, "claude", state)
        self.charge(GEMINI_PROMPT, "antigravity", state)
        with contextlib.closing(sqlite3.connect(state)) as conn:
            rows = conn.execute(
                "SELECT agent, points, provider FROM debits ORDER BY agent").fetchall()
        self.assertEqual([row[0] for row in rows], ["antigravity", "claude"])
        self.assertEqual({row[2] for row in rows}, {"jev-mock-local"})
        self.assertGreater(rows[0][1], 0)
        # Identical text, identical score: the standard did not change per agent.
        self.assertEqual(rows[0][1], rows[1][1])

    def test_a_duplicate_hook_delivery_charges_once(self):
        state = self.codex / "headroom" / "ledger.sqlite3"
        self.charge(CLAUDE_PROMPT, "claude", state)
        self.charge(CLAUDE_PROMPT, "claude", state, outcome="duplicate")
        with contextlib.closing(sqlite3.connect(state)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM debits").fetchone()[0], 1)

    def charge(self, payload, agent, state, outcome="charged"):
        env = {**os.environ, "HEADROOM_AGENT": agent, "HEADROOM_STATE_PATH": str(state),
               "HEADROOM_DISABLE_DASHBOARD": "1"}
        result = subprocess.run(
            [sys.executable, str(SKILL / "hooks" / "headroom_hook.py"), "--user-prompt"],
            input=json.dumps(payload).encode("utf-8"), capture_output=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((state.parent / "last-hook.json").read_text(encoding="utf-8"))
        self.assertEqual(record["outcome"], outcome, record)
        self.assertEqual(record["agent"], agent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
