<div align="center">

# headroom

**I need a reset.**

Your AI has a usage limit. So do you.

**English** · [简体中文](README.zh-CN.md)

A local-first **multi-agent plugin and skill** that gives your brain a daily budget.<br>
Send a message. Spend a few imaginary brain points — in Codex, Claude Code, opencode, Antigravity, or WorkBuddy.

[Supported agents](#supported-agents) · [Quick start](#quick-start) · [Taskbar tray](#taskbar-tray-windows) · [English UI](#dashboard-language) · [Jev & Laya](#jev-laya-and-mock-scoring) · [Privacy](#privacy)

</div>

| 100%–70% left | Below 70%–30% left | Below 30% left |
| :---: | :---: | :---: |
| <img src="skills/headroom/assets/brain-full.png" width="110" alt="Dog wearing headphones"> | <img src="skills/headroom/assets/brain-declining.webp" width="110" alt="Crying cat"> | <img src="skills/headroom/assets/brain-low.png" width="110" alt="Barking dog"> |
| One more prompt. | That was not a quick question. | I need a reset. |

**For fun, not science.** This is a playful brain-load / cognitive-load estimate, not a measurement of intelligence, health, fatigue, or productivity. Zero percent never stops you from chatting.

## What happens when you chat?

- **A daily limit based on you, pooled across every agent.** Take the busiest day in the previous seven complete days, sum that day across every readable agent, and multiply by two. No history within that window? Start with two points. **Today is not part of the cap window.**
- **The numerator is today only.** The spend resets at local midnight, and `HEADROOM_SPENT_SOURCE` decides where it comes from:

  | Value | Behaviour |
  | --- | --- |
  | `auto` (default) | **Per agent**: scored debits where a hook charged today, that agent's message count everywhere else |
  | `ledger` | Scored debits only. Without hooks, spend stays 0 and the meter reads 100% |
  | `counts` | Always `today's messages × 2`, ignoring the ledger |

  The ×2 matches the cap's ×2, so a day as busy as your busiest recorded day reads 0% left.

  `auto` resolves **per agent, not per day**. A single switch for the whole day means one Codex charge erases every other agent's day, so with a hook on only one agent the other agents' conversations would stop counting the moment it fired.
- **One balance across sessions and across tools.** A shared local ledger powers the percentage-left meter, progress bar, and meme mood. It also shows `Used 12.50 / 334 points`, plus a per-agent source breakdown, without a separate remaining-points number.
- **Refresh without spending.** The dashboard refreshes every 10 seconds. Refreshing or switching its language never charges. A new chat is not required for each debit.
- **Keep it in your taskbar.** A small H tray icon opens a usage card on click. No browser tab or floating ball needed; it reads the local ledger directly.

The day boundary is **Asia/Shanghai (UTC+8)**. The seven-day cap counts **all** recorded user-message items, including automated ones; eligibility filtering applies to debits, not the cap.

## Supported agents

Discovery is automatic: headroom asks each adapter whether its local history exists and reads the ones that answer yes. Nothing about an agent leaks into the ledger, the scorer, or the display.

| Agent | History source | Hook |
| --- | --- | --- |
| `codex` | `$CODEX_HOME/thread_history_1.sqlite` → `thread_items` | ✅ |
| `claude` | `$CLAUDE_CONFIG_DIR/projects/*/*.jsonl` (falls back to `history.jsonl`) | ✅ |
| `opencode` | `$XDG_DATA_HOME/opencode/opencode.db` → `message` | — |
| `antigravity` | `$GEMINI_DIR/antigravity/brain/*/.system_generated/logs/transcript_full.jsonl` | ✅ |
| `workbuddy` | `$WORKBUDDY_HOME/projects/*/*.jsonl` | — |

`antigravity` covers both Google tools that share `~/.gemini`. Only Gemini CLI is wired up: it has a prompt event, and Antigravity's own hook system does not (its `PreInvocation` fires before *every* model call, which would charge one prompt several times).

```text
python3 skills/headroom/scripts/headroom.py agents
```

lists every adapter, whether it is readable here, and its recent per-day counts.

**A transcript is not a turn log.** Claude Code replays tool results back as user-role messages, so the Claude adapter requires a plain string body or a `text` block and drops `system`/`sdk` prompt sources and sidechain records. Codex and opencode are read straight from SQL. Counting raw records would make the cap meaningless on every agent except Codex.

**No hook is needed to see the cap, the per-agent breakdown, or the spend.** The display re-reads local history on every refresh and, by default, counts today's messages.

### Add an agent without touching code

Declare it in `$HEADROOM_AGENTS_CONFIG` (default `~/.headroom/agents.json`):

```json
{"agents": [
  {"name": "aider", "label": "Aider", "kind": "jsonl", "root": "~/.aider",
   "glob": "**/*.history", "where": {"role": "user"},
   "day_field": "timestamp", "day_format": "ms"}
]}
```

`kind` is `jsonl` or `sqlite`; `day_format` is `ms`, `iso`, or `epoch`. A declared agent overrides a built-in of the same name.

## Quick start

In the web dashboard, click the mood image to make it hop and play one local dog clip with sound. The first click plays Hey Dog. Consecutive image clicks less than 3.5 seconds apart randomly select one of the other eight clips (dog barks 1–5, Call, Dadada, or Industry Baby), without immediately repeating the current clip. A gap of 3.5 seconds or more restarts at Hey Dog. Dadada and Industry Baby play audio only while the current mood image bounces, rotates and scales to the live audio energy and beat peaks; reduced-motion settings disable these effects; the other seven clips show video. Playback ends on the current mood image without automatically starting another clip; clicking during playback stops it and applies the same click-interval rule. Press Esc while the image button is focused to stop. Refreshing the balance does not interrupt playback, and playing clips never spends points. Use the small speaker icon in the bottom-right corner of the card to change sound immediately without restarting playback. The browser remembers this setting; muting does not stop the audio-reactive animation.

The current automatic setup targets **Codex on Windows with PowerShell**. You need Python 3.10+ and a local Codex history index (`thread_history_1.sqlite`). Mock scoring and the dashboard use only Python's standard library.

```powershell
git clone https://github.com/llm-learner/headroom.git
cd headroom
python skills/headroom/scripts/headroom.py status
python -m pip install -r skills/headroom/requirements-desktop.txt
pythonw skills/headroom/scripts/headroom_desktop.py --lang en
```

A small H icon appears in the Windows taskbar notification area, possibly under the hidden-icons arrow. Click it to open the usage card, or hover for percent left. This first step is read-only; it does not enable automatic debits. Use `python` instead of `pythonw` if you need to see startup errors in a terminal.

### Enable automatic debits

From the repository root, preview the merge, then write it:

```bash
python3 skills/headroom/hooks/install_hooks.py --dry-run      # show every change
python3 skills/headroom/hooks/install_hooks.py                # merge into every detected agent
python3 skills/headroom/hooks/install_hooks.py --agents codex,claude
```

| Agent | Config file | Events |
| --- | --- | --- |
| Codex | `$CODEX_HOME/hooks.json` | `SessionStart`, `UserPromptSubmit` |
| Claude Code | `$CLAUDE_CONFIG_DIR/settings.json` | `SessionStart`, `UserPromptSubmit` |
| Gemini CLI | `$GEMINI_DIR/settings.json` | `SessionStart`, `BeforeAgent` |

The default `--agents auto` wires up Codex plus every other agent that already has a home directory here, so it never creates `~/.claude` or `~/.gemini` for a tool you do not use. `--agents all` takes every agent; a comma list takes exactly those. Every file is backed up before it is written, unrelated hook entries are preserved, an unparseable config is never rewritten, and re-running is idempotent.

Each product stores the same two ideas in its own schema, and the installer writes each one's: Codex and Claude Code time hooks in seconds and Claude Code has no `async` flag, while Gemini CLI counts milliseconds and calls the prompt event `BeforeAgent`. All three call the same `headroom_hook.py`, so a turn is scored by the same local scorer whichever tool you typed into, and every debit lands in one shared ledger.

Review and trust headroom's hooks in each agent (Codex `/hooks`, Claude Code `/hooks`, Gemini CLI `/hooks panel`). After the initial hook setup, start a new session to verify activation. Subsequent messages in that session can charge normally; you do **not** need to keep making new sessions.

`SessionStart` launches the tray display on Windows and macOS (the web dashboard on Linux). `UserPromptSubmit`/`BeforeAgent` scores after submission—not after the assistant finishes. Codex runs it asynchronously; Claude Code and Gemini CLI run hooks inline, so allow scoring to finish and the display to refresh. On Windows, `powershell -ExecutionPolicy Bypass -File skills/headroom/hooks/install_windows.ps1` remains available for Codex alone.

To expose `$headroom` as a Codex skill, install the repository through your local plugin marketplace, or copy `skills/headroom` into your Codex skills directory. Installing a skill/plugin alone does not activate or trust lifecycle hooks. Keep the hook's source directory in place.

### macOS / Linux

You need Python 3.10+ (macOS's built-in `/usr/bin/python3` may be older; use python.org or `brew install python`). Status and the web dashboard use only the standard library:

```bash
python3 skills/headroom/scripts/headroom.py status
python3 skills/headroom/scripts/headroom_dashboard.py --lang en
```

`headroom.py` reads the Codex history from `~/.codex` by default; if you use a custom `CODEX_HOME`, also pass `--codex-home "$CODEX_HOME"`.

To enable automatic debits, review and run the installer from the repository root. It merges headroom's hooks into every detected agent's config without touching your other hooks, backs up a changed file, and is safe to re-run. The hooks call the Python that ran the installer (choose one with `PYTHON=/path/to/python3`), with no PowerShell:

```bash
sh skills/headroom/hooks/install.sh --dry-run   # preview
sh skills/headroom/hooks/install.sh             # add --link-skill to expose $headroom via ~/.agents/skills
```

Then review and trust the definitions in each agent as above. `SessionStart` starts the tray display on macOS and the web dashboard on Linux (open [the dashboard](http://127.0.0.1:8766/?lang=en)). `sh skills/headroom/hooks/install.sh --uninstall` removes only headroom's hooks and keeps your ledger.

**macOS menu bar (optional).** Install `requirements-desktop.txt` into that Python, then run `python3 skills/headroom/scripts/headroom_desktop.py --lang en`. An H icon appears in the menu bar; click it and choose **Show usage** for the static card, or use `--mode orb` for the floating orb. The animated WebView2 card is Windows-only, so clips play in the web dashboard. Python must include Tk (Homebrew: `brew install python-tk`); if Tk or the tray packages are missing, headroom falls back to the web dashboard. To have `SessionStart` open the menu bar display, re-run the installer with `--display desktop`. Nothing is added to login items.

`opencode` and `WorkBuddy` have no JSON hook config, so they stay read-only: they contribute to the cap and the per-agent breakdown, but their turns are not charged. Antigravity shares `~/.gemini` with Gemini CLI and is counted there, but its own hook system has no prompt event (`PreInvocation` fires before every model call), so only Gemini CLI is wired up. A hook for any other tool can be added by hand — the hook normalizes each agent's payload (`prompt`/`user_prompt`, `session_id`/`sessionId`, `turn_id`/`promptId`) and reads `HEADROOM_AGENT` when it is set, so a hook definition that exports that variable works without further changes.

<a id="desktop-orb-windows"></a>

## Taskbar tray (Windows)

- **Click** the H tray icon to expand/collapse. The `−` button or Escape also collapses the card. Hover over the icon to see percent left.
- Add `--show` when launching to open the card immediately (exit any existing display first).
- The card opens near the tray, inside the monitor's work area. Windows may initially place the icon under **Show hidden icons**; drag it onto the visible tray if desired.
- **Right-click → Exit headroom** closes the display, not scoring. A later `SessionStart` can open it again.
- The card shows the exact **percent left**, spent/cap points, the current meme, and a Refresh button.
- **Click the meme** for the same clips and audio-reactive animation as the web dashboard. The small speaker button remembers mute; collapsing the card or switching languages stops playback. Nothing plays automatically when the card opens, and playing clips never spends points.
- Use the card's **EN / ZH** button to switch languages live. Launch options: `--lang en` or `--lang zh`. Priority: CLI → `HEADROOM_LANG` → saved language → Chinese. Exit the existing display before changing startup options.
- One display per shared ledger and Windows login session—even with multiple Codex sessions. Refresh runs every ten seconds, off the UI thread, and never calls a scorer.

The animated tray card needs Python with **Tk**, **pystray**, **Pillow**, **pywebview**, and the **Microsoft Edge WebView2 Runtime** (Python packages: `requirements-desktop.txt`). It runs in a native window, not a browser tab, and does not need the dashboard on port 8766. An internal read-only server binds only to `127.0.0.1` on a random free port for bundled media and balance data; it closes with the display. Only position, language, and mute preference are saved in `desktop.json` beside the ledger. It starts with a trusted Codex `SessionStart`, **not at Windows login**.

If WebView2 is unavailable, exit the display and use `--renderer tk` for the original static tray card without a media player or listening port.

Prefer the old draggable orb? Exit the tray display and launch with `--mode orb`. `--mode tray` is the default; `HEADROOM_DESKTOP_MODE=tray|orb` sets the startup default. Orb mode works without pystray; Pillow is optional there, with text faces for unsupported meme formats.

To choose what future sessions launch, set `HEADROOM_DISPLAY` in the hook's environment to `desktop` (Windows default), `web`, `both`, or `off`. This changes display startup only, not scoring. The browser UI remains available manually:

```text
python skills/headroom/scripts/headroom_dashboard.py --lang en
```

Open [the English web dashboard](http://127.0.0.1:8766/?lang=en). If it is already running, open the URL instead of starting another server on the same port.

## Dashboard language

| Option | English | Chinese |
| --- | --- | --- |
| Switch the running page immediately | [`?lang=en`](http://127.0.0.1:8766/?lang=en) | [`?lang=zh`](http://127.0.0.1:8766/?lang=zh) |
| Default when starting the server | `--lang en` | `--lang zh` |
| Default from the server environment | `HEADROOM_LANG=en` | `HEADROOM_LANG=zh` |

Priority: **URL parameter → CLI parameter → environment → Chinese**. Unknown URL values fall back to the server default. English covers labels, loading/error states, time formatting, and image descriptions. Language only affects presentation, not scoring, the ledger, or the UTC+8 reset time. To change an already-running dashboard, use the URL parameter; startup options take effect on the next server start.

## Jev, Laya, and mock scoring

| Backend | Status | Where the prompt goes |
| --- | --- | --- |
| **Mock** (`mock`) | Included; default, deterministic fake score | In-process on your machine; no network |
| **Laya** (`laya`) | Included adapter for a separately deployed local Laya service | Fixed loopback endpoint: `http://127.0.0.1:8765/predict` |
| **Jev API** | **Not implemented**; a future integration direction | No Jev/cloud request exists in this version |

The original prototype imagined a Jev-style scoring API, so the mock provider is named `jev-mock-local`. **It is not an actual Jev call**, and headroom is not an official Jev or Laya product.

### Use your local Laya deployment

Run a compatible Laya service separately, then put this in `$CODEX_HOME/headroom/config.json` (default: `~/.codex/headroom/config.json`):

```json
{"backend": "laya"}
```

The hook rereads this file on **every turn**, including existing sessions. Set `mock` to switch back. `HEADROOM_BACKEND` overrides this file when set. Invalid configuration or an unavailable Laya service **skips charging**, with no silent fallback to fake scores. This config does not launch/download a model or change the CLI's explicit `--backend` option.

The adapter posts JSON with the current prompt in `state.body` and a `questions.brain_load` scoring request. It expects a finite **0–10** number at `answers.brain_load.score`, with `type: "score"`. Model weights and the model server are **not bundled**. The client bypasses system/HTTP proxies for this loopback request.

## Privacy

**Local scoring. Local ledger. No headroom cloud account.** The shipped backends add no cloud scoring calls or telemetry.

| Data | What headroom does |
| --- | --- |
| Past conversations | Reads message-type/timestamp metadata to count turns, not historical prompt bodies. Agent databases are opened read-only |
| Current eligible prompt | Passes it in memory to mock scoring or the configured local Laya service |
| Debit ledger | Stores an opaque event ID, local date, numeric score, provider, and agent name—not prompt text |
| Hook diagnostics | Stores only the latest outcome, time, input-presence/length metadata, agent name, and scoring metadata—not prompt text or raw session/turn IDs |
| Tray / desktop display | Reads local history metadata and the ledger; the animated card uses an ephemeral loopback-only server and bundled media, with no cloud scoring; saves only position/language/mute |
| Dashboard | Binds to `127.0.0.1`; images are bundled locally, with no CDN or analytics |

The default shared ledger is `~/.headroom/ledger.sqlite3`, falling back to an existing `$CODEX_HOME/headroom/ledger.sqlite3` (otherwise `~/.codex/headroom/ledger.sqlite3`) so nobody silently starts at zero. `HEADROOM_STATE_PATH` can override it. Opening a ledger written by headroom 0.x migrates it in place and attributes existing rows to `codex`. Do not publish your runtime state, diagnostics, agent history, or credentials.

A file untouched since before the seven-day window is skipped without being read, which is what keeps a 159 MB history directory from being rescanned on every ten-second refresh.

These guarantees describe **headroom**, not Codex's own data processing. A separately deployed model server may have its own logs or network behavior; configure it accordingly. Any future cloud Jev integration would need explicit opt-in and a separate disclosure of what leaves the device.

## Which turns count?

The intent is to charge direct human conversation, not unattended work. Known non-interactive sources and plan-mode hooks are rejected. The manual scoring CLI also rejects non-normal modes and unconfirmed origins.

The hook normalizes each agent's payload — `prompt`/`user_prompt`, `session_id`/`sessionId`, `turn_id`/`promptId`, `permission_mode`/`permissionMode` — and sets `HEADROOM_AGENT` explicitly. Codex supplies a `turn_id`; Claude Code and Gemini do not, so headroom allocates a durable per-session sequence from the ledger's `hook_turns` table. Two different prompts in one session charge twice; a redelivered hook for the same turn charges once. A `turn_id` that is present but blank is treated as malformed and skipped.

**Automatic provenance filtering is best-effort.** Current hook payloads do not always identify Goal/automation/subagent provenance reliably. Missing source metadata is accepted for compatibility; `HEADROOM_HOOK_STRICT=1` rejects it, but may also skip ordinary conversation. Do not treat these exclusions as audit-grade guarantees.

<details>
<summary>Troubleshooting and development</summary>

- No debit? Check `/hooks` trust, the selected backend, and local Laya availability. `last-hook.json` beside the ledger records the latest outcome. Set `HEADROOM_DEBUG_PATH` to another path, or an empty string to disable it.
- On Windows, a quoted executable in a PowerShell hook needs `&`. Hook input is decoded as UTF-8, including Chinese and emoji on GBK systems.
- Changing the hook command requires a new review of that definition. Do not run manual `turn` scoring for a turn already covered by the hook—it can create a second event ID.
- Changing language, opening the dashboard, and its Refresh button are read-only. Sending a chat message asking for your balance is still a user prompt and may be charged by the hook.

Run the regression tests with temporary histories and ledgers:

```text
python -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
node skills/headroom/tests/test_dashboard_mood.js
```

The JavaScript test needs Node.js and Python (`HEADROOM_TEST_PYTHON` can select the Python executable). Lifecycle smoke tests must set `HEADROOM_DISABLE_DASHBOARD=1` when using a temporary ledger. HTTP tests use ephemeral loopback ports, never the live dashboard port.

GitHub Actions runs these checks on every push and pull request, and supports manual runs. The matrix covers Linux, Windows, and macOS with Python 3.10–3.13 and Node.js 22. Windows also reruns the Python suite with desktop dependencies on Python 3.13. Native tray and WebView2 smoke tests remain opt-in locally.

</details>

## Contributors

- [TOGET-H](https://github.com/TOGET-H)
- [cat0825](https://github.com/cat0825)
- [fuxiuht](https://github.com/fuxiuht)

Want to help? See [CONTRIBUTING.md](CONTRIBUTING.md).
