#!/usr/bin/env python3
"""Cross-platform, non-destructive installer for headroom's agent hooks.

Every supported agent stores lifecycle hooks as JSON, and every one of them
calls the same ``headroom_hook.py``, so one turn is scored by the same local
scorer no matter which tool you typed into:

| Agent | Config file | Hook events |
| --- | --- | --- |
| Codex | ``$CODEX_HOME/hooks.json`` | ``SessionStart``, ``UserPromptSubmit`` |
| Claude Code | ``$CLAUDE_CONFIG_DIR/settings.json`` | ``SessionStart``, ``UserPromptSubmit`` |
| Gemini CLI | ``$GEMINI_DIR/settings.json`` | ``SessionStart``, ``BeforeAgent`` |

The merge keeps every other hook in the file, is idempotent, and backs up each
changed file before writing. Use ``--uninstall`` to remove only headroom's
entries. Runtime data (the shared ledger, preferences) stays in
``$CODEX_HOME/headroom`` and is never deleted.

The installer itself runs on Python 3.8+, so it can explain an interpreter
that is too old (e.g. macOS's /usr/bin/python3) instead of crashing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HOOK_SCRIPT = "headroom_hook.py"
DESCRIPTION = "headroom: I need a reset."
DISPLAYS = ("desktop", "web", "both", "off")
MIN_PYTHON = (3, 10)
#: A python executable name, with or without a version, and with or without .exe.
PYTHON_NAME = re.compile(r"pythonw?(?:\d+(?:\.\d+)*)?(?:\.exe)?$", re.IGNORECASE)
#: A leading ``NAME=value`` environment assignment in a command line.
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
#: The statusMessage values headroom writes; a fallback for a bare `python3`.
HOOK_STATUSES = ("Starting headroom dashboard", "Charging headroom")
#: Claude Code's and Codex's SessionStart matcher, in each product's own syntax.
SESSION_START = "startup|resume|clear|compact"


@dataclass(frozen=True)
class Event:
    """One lifecycle event, described in the agent's own vocabulary."""

    name: str                    # the agent's event name
    flag: str                    # the flag headroom_hook.py reads
    timeout: int                 # in the agent's own unit (seconds or ms)
    matcher: str | None = None   # omitted when the schema has no such field
    status: str | None = None    # spinner text; omitted where unsupported
    display: bool = False        # accepts HEADROOM_DISPLAY (POSIX only)
    asynchronous: bool = False   # never blocks the turn
    named: bool = False          # the schema identifies hooks by name


@dataclass(frozen=True)
class Agent:
    """Where one agent keeps its hooks, and what its schema accepts."""

    key: str          # the --agents value
    label: str
    agent: str        # HEADROOM_AGENT, and the ledger's agent id
    home_env: str     # variable that overrides the home directory
    home_dir: str     # default home, relative to the user's home
    config: str       # config file inside that home
    review: str       # how the user trusts the hooks afterwards
    description: bool = False   # stamp a top-level description on a new file
    windows: bool = False       # writes the PowerShell commandWindows field
    events: tuple[Event, ...] = ()


#: Every agent the installer knows, in the order it reports them.
#:
#: The timeout unit is per product and getting it wrong is silent: a hook killed
#: at the wrong scale simply stops charging. Codex and Claude Code count
#: seconds; Gemini CLI counts milliseconds.
AGENTS: dict[str, Agent] = {
    "codex": Agent(
        key="codex", label="Codex", agent="codex",
        home_env="CODEX_HOME", home_dir=".codex", config="hooks.json",
        review="run /hooks in Codex",
        description=True, windows=True,
        events=(
            Event("SessionStart", "--session-start", 3, SESSION_START,
                  "Starting headroom dashboard", display=True, asynchronous=True),
            Event("UserPromptSubmit", "--user-prompt", 30, None,
                  "Charging headroom", asynchronous=True),
        ),
    ),
    "claude": Agent(
        key="claude", label="Claude Code", agent="claude",
        home_env="CLAUDE_CONFIG_DIR", home_dir=".claude", config="settings.json",
        review="run /hooks in Claude Code",
        events=(
            Event("SessionStart", "--session-start", 3, SESSION_START,
                  "Starting headroom dashboard", display=True),
            Event("UserPromptSubmit", "--user-prompt", 30, None, "Charging headroom"),
        ),
    ),
    "gemini": Agent(
        # Gemini CLI and Antigravity share ~/.gemini, and the adapter registry
        # counts both under the one id "antigravity".
        key="gemini", label="Gemini CLI", agent="antigravity",
        home_env="GEMINI_DIR", home_dir=".gemini", config="settings.json",
        review="run /hooks panel in Gemini CLI",
        events=(
            Event("SessionStart", "--session-start", 3000, None, display=True, named=True),
            Event("BeforeAgent", "--user-prompt", 30000, None, named=True),
        ),
    ),
}

#: event name -> the hook flags headroom installs there, derived from AGENTS.
#: Used to recognize our own entries without matching incidental mentions.
HOOK_FLAGS: dict[str, set[str]] = {}
for _spec in AGENTS.values():
    for _event in _spec.events:
        HOOK_FLAGS.setdefault(_event.name, set()).add(_event.flag)


def skill_root() -> Path:
    configured = os.environ.get("HEADROOM_PLUGIN_ROOT")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[1]


def default_home(spec: Agent) -> Path:
    configured = os.environ.get(spec.home_env)
    return Path(configured).expanduser() if configured else Path.home() / spec.home_dir


def default_codex_home() -> Path:
    return default_home(AGENTS["codex"])


def default_python() -> str:
    """The interpreter running the installer; never pythonw for hooks."""
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return str(executable)


def python_version(python: str) -> tuple[int, int] | None:
    if python == sys.executable:
        return sys.version_info[:2]
    try:
        result = subprocess.run([python, "-c", "import sys; print(*sys.version_info[:2])"],
                                capture_output=True, text=True, timeout=20, check=True)
        major, minor = result.stdout.split()
        return int(major), int(minor)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def posix_command(python: str, hook: str, flag: str, display: str | None = None,
                  agent: str | None = None) -> str:
    """A /bin/sh command line: no PowerShell, safe for paths with spaces."""
    prefix = f"HEADROOM_AGENT={agent} " if agent else ""
    prefix += f"HEADROOM_DISPLAY={display} " if display else ""
    return f"{prefix}{shlex.quote(python)} {shlex.quote(hook)} {flag}"


def windows_command(python: str, hook: str, flag: str) -> str:
    """The same PowerShell form install_windows.ps1 writes."""
    return f'& "{python}" "{hook}" {flag}'.replace("\\", "/")


def plain_command(python: str, hook: str, flag: str) -> str:
    """A quoted program plus arguments, for a Windows agent without a shell flag.

    Both cmd.exe and a POSIX sh run this, and neither has a portable way to set
    an environment variable in front of it. The hook still identifies the agent
    from the payload's ``transcript_path``, which every agent sends.
    """
    return f'"{python}" "{hook}" {flag}'


def build_hooks(root: Path, python: str, display: str | None = None,
                windows: bool | None = None, agent: str = "codex") -> dict:
    """Return one agent's ``hooks`` mapping.

    Codex's mapping mirrors hooks.json.template byte for byte, including the
    Windows pair install_windows.ps1 writes. The other agents reuse the same two
    events with their own field set.
    """
    spec = AGENTS.get(agent)
    if spec is None:
        raise ValueError(f"unsupported agent: {agent}")
    windows = sys.platform == "win32" if windows is None else windows
    hook = str(root / "hooks" / HOOK_SCRIPT)
    if windows:
        hook = hook.replace("\\", "/")
    hooks = {}
    for event in spec.events:
        if spec.windows and windows:  # Byte-for-byte what install_windows.ps1 writes.
            entry = {"type": "command", "command": f'python3 "{hook}" {event.flag}',
                     "commandWindows": windows_command(python, hook, event.flag)}
        elif windows:
            entry = {"type": "command", "command": plain_command(python, hook, event.flag)}
        else:
            # Codex's payload carries turn_id, which the hook already maps to
            # Codex; every other agent needs the variable to be identified
            # unambiguously. Only SessionStart reads HEADROOM_DISPLAY.
            entry = {"type": "command", "command": posix_command(
                python, hook, event.flag, display if event.display else None,
                None if spec.agent == "codex" else spec.agent)}
        entry.update({"timeout": event.timeout})
        if event.asynchronous:
            entry["async"] = True
        if event.status:
            entry["statusMessage"] = event.status
        if event.named:
            entry["name"] = "headroom"
        block = {"matcher": event.matcher} if event.matcher else {}
        block["hooks"] = [entry]
        hooks[event.name] = [block]
    return hooks


def is_headroom_hook(hook: object, event: str) -> bool:
    """Recognize installed commands without matching incidental mentions.

    A command counts only when the event is one headroom installs on, the
    argument is that event's flag, the script ends in ``hooks/headroom_hook.py``,
    and either the program looks like a python or the statusMessage is ours.
    That keeps ``echo /other/hooks/headroom_hook.py --user-prompt`` and
    ``python3 /other/hooks/headroom_hook.py.bak --user-prompt`` untouched.
    """
    flags = HOOK_FLAGS.get(event)
    if not flags or not isinstance(hook, dict) or hook.get("type") != "command":
        return False
    for key in ("command", "commandWindows", "command_windows"):
        command = hook.get(key)
        if not isinstance(command, str):
            continue
        try:
            parts = shlex.split(command)
        except ValueError:
            continue
        # Strip PowerShell's call operator and every leading env assignment
        # (HEADROOM_AGENT=..., HEADROOM_DISPLAY=...), in any order. Without this
        # an installed entry would not be recognized on a re-run and would be
        # appended a second time.
        while parts and (parts[0] == "&" or ENV_ASSIGNMENT.match(parts[0])):
            parts = parts[1:]
        if len(parts) != 3:
            continue
        python, script, argument = parts
        script = script.replace("\\", "/")
        python_name = python.replace("\\", "/").rsplit("/", 1)[-1]
        if (argument in flags and script.endswith("/hooks/" + HOOK_SCRIPT)
                and (PYTHON_NAME.fullmatch(python_name)
                     or hook.get("statusMessage") in HOOK_STATUSES)):
            return True
    return False


def load_config(target: Path) -> dict:
    if not target.exists():
        return {}
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError(f"{target} must contain a JSON object with a 'hooks' object")
    return data


def without_headroom(data: dict) -> tuple[dict, int]:
    """Drop only headroom's own commands, keeping each block's other entries."""
    result = {key: value for key, value in data.items() if key != "hooks"}
    hooks, removed = {}, 0
    for event, blocks in data.get("hooks", {}).items():
        if not isinstance(blocks, list):
            hooks[event] = blocks
            continue
        kept = []
        for block in blocks:
            if not isinstance(block, dict) or not isinstance(block.get("hooks"), list):
                kept.append(block)
                continue
            commands = [hook for hook in block["hooks"] if not is_headroom_hook(hook, event)]
            removed_here = len(block["hooks"]) - len(commands)
            removed += removed_here
            if not removed_here:
                kept.append(block)
            elif commands:
                kept.append({**block, "hooks": commands})
        if kept:
            hooks[event] = kept
    result["hooks"] = hooks
    return result, removed


def merged(data: dict, headroom_hooks: dict, description: str | None = None) -> dict:
    result, _removed = without_headroom(data)
    if not data and description:  # A new file mirrors hooks.json.template; never relabel a user's file.
        result = {"description": description, **result}
    for event, blocks in headroom_hooks.items():
        result["hooks"].setdefault(event, []).extend(blocks)
    return result


def backup(target: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = target.with_name(f"{target.name}.bak-{stamp}")
    counter = 1
    while path.exists():
        path = target.with_name(f"{target.name}.bak-{stamp}-{counter}")
        counter += 1
    path.write_bytes(target.read_bytes())
    return path


def write_json(target: Path, data: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".hooks-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def skill_link_path() -> Path:
    # Codex discovers user skills in ~/.agents/skills and follows symlinks.
    return Path.home() / ".agents" / "skills" / "headroom"


def link_skill(root: Path, dry_run: bool) -> str:
    link = skill_link_path()
    if link.is_symlink() and link.resolve() == root.resolve():
        return f"Skill link already present: {link}"
    if link.exists() or link.is_symlink():
        return f"Skipped skill link: {link} already exists and is not a link to {root}"
    if not dry_run:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(root, target_is_directory=True)
    return f"{'Would link' if dry_run else 'Linked'} skill: {link} -> {root}"


def unlink_skill(root: Path, dry_run: bool) -> str | None:
    link = skill_link_path()
    if link.is_symlink() and link.resolve() == root.resolve():
        if not dry_run:
            link.unlink()
        return f"{'Would remove' if dry_run else 'Removed'} skill link: {link}"
    return None


def selected_agents(only: str) -> list[Agent]:
    """Resolve ``--agents``.

    ``auto`` wires up Codex (headroom's original target, always present) plus
    every other agent that already has a home directory here. It never creates
    ``~/.claude`` or ``~/.gemini`` for someone who does not use them.
    """
    if only == "all":
        return list(AGENTS.values())
    if only not in ("", "auto"):
        chosen = []
        for key in (item.strip() for item in only.split(",")):
            if not key:
                continue
            if key not in AGENTS:
                raise ValueError(f"unknown agent {key!r}; choose from "
                                 f"{', '.join(AGENTS)}, all, or auto")
            chosen.append(AGENTS[key])
        return chosen
    return [spec for spec in AGENTS.values()
            if spec.key == "codex" or default_home(spec).is_dir()]


def target_path(spec: Agent, args) -> Path:
    home = args.codex_home if spec.key == "codex" else default_home(spec)
    return home / spec.config


def note(spec: Agent) -> str:
    """Say when an agent's id differs from the config file's owner."""
    return f" (recorded as agent {spec.agent!r})" if spec.agent != spec.key else ""


def only_headroom(updated: dict, spec: Agent) -> bool:
    """True when nothing but headroom's own entries would be left behind."""
    if updated.get("hooks"):
        return False
    keys = set(updated) - {"hooks"}
    if not keys:
        return True
    return spec.description and keys == {"description"} \
        and updated.get("description") == DESCRIPTION


def install(args) -> int:
    root = skill_root()
    if not (root / "hooks" / HOOK_SCRIPT).is_file():
        print(f"error: {root / 'hooks' / HOOK_SCRIPT} not found", file=sys.stderr)
        return 1
    version = python_version(args.python)
    if version is None or version < MIN_PYTHON:
        found = "not runnable" if version is None else "Python %d.%d" % version
        print(f"error: hooks need Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+, but {args.python} is "
              f"{found}. Install a newer Python (python.org or Homebrew) and re-run with "
              "--python /path/to/python3.", file=sys.stderr)
        return 1
    try:
        specs = selected_agents(args.agents)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # Read every config before writing any of them, so an unparseable file in
    # one agent cannot leave another agent half-installed.
    plans = []
    for spec in specs:
        target = target_path(spec, args)
        current = load_config(target)
        updated = merged(current, build_hooks(root, args.python, args.display, agent=spec.key),
                         DESCRIPTION if spec.description else None)
        plans.append((spec, target, current, updated))
    messages, changed_any = [], False
    for spec, target, current, updated in plans:
        changed = updated != current
        changed_any = changed_any or changed
        if args.dry_run:
            print(f"# {target}")
            print(json.dumps(updated, indent=2, ensure_ascii=False))
            messages.append(f"[dry run] Would {'update' if changed else 'leave unchanged'} {target}")
        elif changed:
            if target.exists():
                messages.append(f"Backed up {target} to {backup(target)}")
            write_json(target, updated)
            messages.append(f"Installed headroom hooks in {target}{note(spec)}")
        else:
            messages.append(f"headroom hooks already up to date in {target}")
    data_dir = args.codex_home / "headroom"
    if not args.dry_run:
        data_dir.mkdir(parents=True, exist_ok=True)
    messages.append(f"Data directory: {data_dir}")
    if args.link_skill:
        messages.append(link_skill(root, args.dry_run))
    print("\n".join(messages))
    if changed_any and not args.dry_run:
        for spec in specs:
            print(f"Next: {spec.review}, review and trust headroom's SessionStart and "
                  f"{spec.events[-1].name} hooks, then start a new session.")
    return 0


def uninstall(args) -> int:
    try:
        specs = selected_agents(args.agents)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    messages = []
    for spec in specs:
        target = target_path(spec, args)
        current = load_config(target)
        updated, removed = without_headroom(current)
        if not removed:
            messages.append(f"No headroom hooks found in {target}")
            continue
        if args.dry_run:
            messages.append(f"[dry run] Would remove {removed} headroom hook(s) from {target}")
            continue
        messages.append(f"Backed up {target} to {backup(target)}")
        if only_headroom(updated, spec):
            # Safe to drop the file only when headroom's entries were all it held.
            target.unlink()
            messages.append(f"Removed {target} (it only contained headroom hooks)")
        else:
            write_json(target, updated)
            messages.append(f"Removed {removed} headroom hook(s) from {target}")
    unlinked = unlink_skill(skill_root(), args.dry_run)
    if unlinked:
        messages.append(unlinked)
    messages.append(f"Kept your data in {args.codex_home / 'headroom'}; delete it manually if desired.")
    print("\n".join(messages))
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--codex-home", type=Path, default=default_codex_home(),
                        help="Codex home (default: $CODEX_HOME or ~/.codex)")
    parser.add_argument("--python", default=default_python(),
                        help="interpreter the hooks run with (default: this Python, "
                             "so pip-installed desktop extras are found)")
    parser.add_argument("--agents", default="auto", metavar="LIST",
                        help="which agents to wire up: auto (default: Codex plus every "
                             "other agent already installed here), all, or a comma-"
                             f"separated list from {', '.join(AGENTS)}")
    parser.add_argument("--display", choices=DISPLAYS,
                        help="what SessionStart opens on macOS/Linux; default: the web dashboard "
                             "(desktop = the tray or menu bar card, and falls back to the web "
                             "dashboard where that is unavailable)")
    parser.add_argument("--link-skill", action="store_true",
                        help="also symlink the skill into ~/.agents/skills/headroom")
    parser.add_argument("--uninstall", action="store_true", help="remove headroom's hooks")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing")
    args = parser.parse_args(argv)
    if args.display and sys.platform == "win32":
        parser.error("--display applies to macOS/Linux; on Windows set HEADROOM_DISPLAY instead")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        return uninstall(args) if args.uninstall else install(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
