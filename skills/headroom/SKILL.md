---
name: headroom
description: Track a playful daily headroom meter pooled across every local AI agent (Codex, Claude Code, opencode, Antigravity/Gemini, WorkBuddy). Reads each agent's own local history; the Codex hook charges turns automatically. Entertainment, not a cognitive measurement.
---

# headroom

> I need a reset.

This is an entertainment-only meter, not a measure of intelligence or health. The default scorer is a deterministic fake Jev API; `--backend laya` sends the prompt only to the user's loopback Laya service at `http://127.0.0.1:8765/predict`. No cloud Jev API is implemented.

## Which agents are supported

Each agent gets an adapter that reads its own local history and answers one question: how many direct human prompts did this agent record per day? Nothing about an agent leaks into the ledger, the scorer, or the display.

| Agent | History source | Hook |
| --- | --- | --- |
| `codex` | `$CODEX_HOME/thread_history_1.sqlite` → `thread_items` | yes |
| `claude` | `$CLAUDE_CONFIG_DIR/projects/*/*.jsonl` (falls back to `history.jsonl`) | — |
| `opencode` | `$XDG_DATA_HOME/opencode/opencode.db` → `message` | — |
| `antigravity` | `$GEMINI_DIR/antigravity/brain/*/.system_generated/logs/transcript_full.jsonl` | — |
| `workbuddy` | `$WORKBUDDY_HOME/projects/*/*.jsonl` | — |

`python scripts/headroom.py agents` lists every adapter, whether it is readable on this machine, and its recent per-day counts. Discovery is automatic: `--agents auto` (the default) reads every adapter that has local history.

A JSONL transcript is not a turn log. Claude Code replays tool results as user-role messages, so the Claude adapter requires a plain string body or a `text` block and drops `system`/`sdk` prompt sources and sidechain records. Codex and opencode are read straight from SQL. This is why the counts are not raw record counts.

## One shared ledger

The daily cap pools every readable agent: take the busiest of the previous seven complete Asia/Shanghai days, sum that day across all agents, and multiply by two. The balance resets by calendar day; zero never blocks conversation.

The ledger defaults to `~/.headroom/ledger.sqlite3`, or the pre-existing `$CODEX_HOME/headroom/ledger.sqlite3` when that already exists. `HEADROOM_STATE_PATH` overrides it. The `debits` table carries an `agent` column; opening a ledger written by headroom 0.x migrates it in place and attributes existing rows to `codex`. The ledger stores only opaque event IDs, local dates, scores, provider names, and agent names — never prompt bodies.

## What the number means

Two independent halves:

- **The cap (the scale)** comes from history: the busiest of the previous seven complete Asia/Shanghai days, summed across every readable agent, doubled. Today is excluded from the cap window.
- **The spend (the numerator)** is today only, and resets at local midnight.

`HEADROOM_SPENT_SOURCE` picks how the spend is derived:

| Value | Behaviour |
| --- | --- |
| `auto` (default) | **Per agent**: scored debits where a hook charged today, that agent's message count everywhere else |
| `ledger` | Scored debits only. Without hooks, spend stays 0 and the meter reads 100% |
| `counts` | Always `today_messages x 2`, ignoring the ledger |

`COUNT_POINTS` is 2, matching the cap's x2, so a day as busy as your busiest recorded day reads 0% left.

`auto` resolves **per agent, not per day**. A single switch for the whole day means one Codex charge erases every other agent's day — with a hook on only one agent, 84 counted messages would collapse to that agent's score. Per agent, counting and scoring never mix, which is what stops a turn being charged twice; `spent_origin` reports `counts`, `ledger`, or `mixed`, and `spent_scored_agents` / `spent_counted_agents` say which is which.

## Reading the balance

- `python scripts/headroom.py status` — read-only balance. Never charges.
- `python scripts/headroom.py agents` — discovery report with per-agent counts.
- `python scripts/headroom_dashboard.py` — browser dashboard at `http://127.0.0.1:8766/`. It refreshes every 10 seconds, shows a per-agent source breakdown, and its Refresh button and 10-second timer never charge.
- Windows desktop display: install `requirements-desktop.txt` into the hook's Python environment and run `pythonw scripts/headroom_desktop.py`. Default is a small ring gauge in the taskbar notification area. All displays read the same ledger.

Because the display re-reads local history on every refresh, **no hook is required to see the cap, the per-agent breakdown, or the spend**.

## Charging turns

The installed `UserPromptSubmit` hook owns automatic charging. It normalizes each agent's payload — `prompt`/`user_prompt`, `session_id`/`sessionId`, `turn_id`/`promptId`, `permission_mode`/`permissionMode` — and sets `HEADROOM_AGENT` explicitly so the ledger attributes the debit correctly. Codex supplies a `turn_id`; Claude Code and Gemini do not, so headroom allocates a durable per-session sequence from the ledger's `hook_turns` table. Two different prompts in one session charge twice; a redelivered hook for the same turn charges once. A `turn_id` that is present but blank is treated as malformed and skipped.

`HEADROOM_BACKEND` overrides `$CODEX_HOME/headroom/config.json`, which the hook rereads on every turn; `{"backend":"laya"}` selects the separately running loopback Laya service. **Do not also run `turn` for a hook-covered turn**, or it may get a second event ID and debit twice. Without an active hook, use `python scripts/headroom.py turn --event-id <opaque-turn-id> --origin manual-user --mode normal --backend mock` from this skill directory, piping the UTF-8 user message on stdin. Never derive the event ID from message content.

Only direct human turns in normal interactive mode should charge. Skip plan mode, Goal/automation mode, scheduled work, subagents, continuations, unknown provenance, and scorer errors. The hook rejects known non-interactive sources, but current payloads do not independently certify human origin — this is best-effort amusement, not an audit-grade exclusion.

## Adding an agent without touching code

Declare it in `$HEADROOM_AGENTS_CONFIG` (default `~/.headroom/agents.json`):

```json
{"agents": [
  {"name": "aider", "label": "Aider", "kind": "jsonl", "root": "~/.aider",
   "glob": "**/*.history", "where": {"role": "user"},
   "day_field": "timestamp", "day_format": "ms"}
]}
```

`kind` is `jsonl` or `sqlite`; `day_format` is `ms`, `iso`, or `epoch`. A declared agent overrides a built-in of the same name.

## Overriding a root

`--agent-home NAME=PATH` (repeatable) overrides one adapter's root. `--codex-home PATH` is kept for compatibility and is equivalent to `--agent-home codex=PATH`. `--agents name,name` restricts the selection; naming an unreadable agent reports it instead of silently dropping it.

## Privacy

Local scoring, local ledger, no headroom cloud account. History queries select only item type and timestamp metadata — never prompt bodies. Adapters open agent databases read-only. The tray/desktop display reads local metadata and the ledger; the dashboard binds to `127.0.0.1`. A file untouched since before the seven-day window is skipped without being read, which is what keeps a 159 MB history directory from being rescanned on every refresh.

Run the regression tests:

```text
python -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
node skills/headroom/tests/test_dashboard_mood.js
```

## Installing the hooks

On Windows, install the user hook with `powershell -ExecutionPolicy Bypass -File hooks/install_windows.ps1` from this skill directory. Existing `hooks.json` is never overwritten without `-Force`; merge manually if it already exists.

On macOS or Linux, run `sh hooks/install.sh` from this skill directory. It merges headroom's entries into `hooks.json` and backs up the file; `--uninstall` removes only those entries. macOS can show a menu bar icon with the static Tk card, or use `--mode orb`. If Tk or tray packages are unavailable, the desktop display falls back to the web dashboard.

The installer wires up **Codex** only. The other agents are read-only: they contribute to the cap and the per-agent breakdown, but their turns are not charged. Their hooks can be added by hand — the hook normalizes each agent's payload and reads `HEADROOM_AGENT` when it is set, so a hook definition that exports that variable works without further changes.

Review and trust the two definitions in Codex `/hooks`, then start a new session. Plugin installation or implicit skill selection alone does not activate lifecycle hooks. `SessionStart` defaults to the tray display on Windows, and the loopback dashboard elsewhere. The tray and menu bar use `assets/menubar-icon.png`, or `assets/menubar-icon-dark.png` on a dark macOS menu bar; `HEADROOM_ICON` or `~/.headroom/icon.png` overrides both, and without a custom file headroom draws its own ring. `HEADROOM_DISPLAY=web|desktop|both|off` selects the display; `off` does not disable charging. Quitting the display leaves charging enabled; it can be manually started or reopened by the next session. No Windows-login startup is installed. `UserPromptSubmit` scores asynchronously and never blocks a response. Use temporary ledgers for tests and set `HEADROOM_DISABLE_DASHBOARD=1` to suppress all lifecycle displays.
