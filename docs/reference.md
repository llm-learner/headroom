# Configuration and internals

**English** · [简体中文](reference.zh-CN.md) · [Back to README](../README.md)

## Budget and spend

All dates use **Asia/Shanghai (UTC+8)**, regardless of the machine's timezone. The cap uses the previous seven complete days, excluding today. For each day, sum messages across readable adapters; the largest sum × 2 is the daily cap. An empty window starts with a two-point floor.

Today's usage is separate from that window. The display calculates `max(0, (cap - spent) / cap × 100)`, shows percent left and used/cap points, and never blocks conversation at zero.

`HEADROOM_SPENT_SOURCE` controls usage:

| Value | Behavior |
| --- | --- |
| `auto` (default) | Per tool: use scored debits when today's total is positive; otherwise today's message count × 2 |
| `ledger` | Scored debits only; no debits means 100% left |
| `counts` | Today's messages × 2, ignoring scored debits |

In `auto`, estimates and scored points are alternatives for the **same tool**, not additive. Different tools can use different sources. The first scored debit can replace that tool's earlier count estimate, so the percentage can rise. A day as busy as the historical peak reaches zero in `counts`, but not necessarily with variable 0–10 scores.

The current implementation treats a scored total of zero as a count-fallback case in `auto`. Use `ledger` if only actual scores should count.

Cap counting follows each adapter's filters. Codex's recorded user-message items can include automated turns; debit eligibility is a separate check, not a universal filter on the cap.

## Configuration options

Set environment variables in the process that launches headroom. Hook and display processes may have different environments; changing a variable in a terminal does not update an already-running Codex or display.

| Variable | Purpose |
| --- | --- |
| `HEADROOM_SPENT_SOURCE` | `auto`, `ledger`, or `counts` |
| `HEADROOM_BACKEND` | `mock` or `laya`; overrides the hook's `config.json` |
| `HEADROOM_STATE_PATH` | Shared ledger path |
| `HEADROOM_AGENTS` | `auto` or comma-separated adapter names |
| `HEADROOM_AGENTS_CONFIG` | Custom adapters file; default `~/.headroom/agents.json` |
| `HEADROOM_AGENT` | Agent name supplied to scoring hooks |
| `HEADROOM_DISPLAY` | `desktop`, `web`, `both`, or `off`; display startup only |
| `HEADROOM_DESKTOP_MODE` | `tray` (default) or `orb` |
| `HEADROOM_LANG` | `en` or `zh`; [display-specific precedence](guide.md#web-dashboard-and-language) |
| `HEADROOM_HOOK_STRICT` | `1` rejects missing provenance, which can also exclude ordinary chat |
| `HEADROOM_DEBUG_PATH` | Diagnostic file path; empty string disables diagnostics |
| `HEADROOM_DISABLE_DASHBOARD` | `1` suppresses automatic display startup for tests |

The hook's backend file is `$CODEX_HOME/headroom/config.json` (default `~/.codex/headroom/config.json`). It is reread each turn. Manual CLI scoring uses its explicit `--backend` option instead.

The default ledger is `~/.headroom/ledger.sqlite3`. If that file does not exist but the legacy `$CODEX_HOME/headroom/ledger.sqlite3` does, headroom reuses the legacy ledger. `HEADROOM_STATE_PATH` overrides both. Opening an old ledger for writing migrates it in place and attributes older entries to `codex`.

## Agent adapters

Discovery checks local history availability. Run `python skills/headroom/scripts/headroom.py agents` to list adapters, availability, and recent counts. Histories are read-only; SQL adapters select counting metadata, while JSONL adapters parse records locally and may inspect content to distinguish user requests from tool results.

| Adapter | History source |
| --- | --- |
| `codex` | `$CODEX_HOME/thread_history_1.sqlite` → `thread_items` |
| `claude` | `$CLAUDE_CONFIG_DIR/projects/*/*.jsonl`, falling back to `history.jsonl` |
| `opencode` | `$XDG_DATA_HOME/opencode/opencode.db` → `message` |
| `antigravity` | `$GEMINI_DIR/antigravity/brain/*/.system_generated/logs/transcript_full.jsonl` |
| `workbuddy` | `$WORKBUDDY_HOME/projects/*/*.jsonl` |

Claude's filter accepts string/text user content and excludes `system`/`sdk` prompt sources and sidechains. Transcript record count is not necessarily human-turn count.

The bundled installers configure Codex only. For other tools, manually wire their prompt hooks to `headroom_hook.py --user-prompt`, provide the appropriate payload, and set `HEADROOM_AGENT`. The hook recognizes aliases including `prompt`/`user_prompt`, `session_id`/`sessionId`, `turn_id`/`promptId`, and `permission_mode`/`permissionMode`. Compatibility does not imply every tool's hook lifecycle is configured or tested automatically.

To declare another JSONL or SQLite adapter, add it to `$HEADROOM_AGENTS_CONFIG`:

```json
{"agents": [
  {"name": "aider", "label": "Aider", "kind": "jsonl", "root": "~/.aider",
   "glob": "**/*.history", "where": {"role": "user"},
   "day_field": "timestamp", "day_format": "ms"}
]}
```

This is a schema example, not a verified Aider integration. `day_format` accepts `ms`, `iso`, or `epoch`. A declaration replaces a built-in adapter of the same name. CLI options `--agents` and repeatable `--agent-home NAME=PATH` select tools/roots; `--codex-home` overrides the Codex root.

## Scoring and turn identity

Mock produces deterministic pretend scores from the current prompt, not a model inference. Laya scores the current request's estimated effort, not the assistant's entire response. Both are entertainment, not cognitive measurements.

Laya receives UTF-8 JSON via `POST http://127.0.0.1:8765/predict` with `state.body` and a `questions.brain_load` score question. The question includes instructions and eleven criteria for scores 0–10. Expected response shape:

```json
{"answers": {"brain_load": {"type": "score", "score": 4.2}}}
```

The score must be a finite number from 0 to 10, not a boolean. The client bypasses HTTP/system proxies and uses a 15-second timeout. Errors skip the debit; they never silently switch to Mock.

The hook rejects known non-interactive sources and plan-mode events. Manual scoring requires confirmed human origin and normal mode. Missing provenance is accepted by default for compatibility; strict mode may skip normal chat too. Goal/automation/subagent filtering is not audit-grade.

Explicit turn IDs allow duplicate-delivery deduplication. Without one, the ledger allocates a durable per-session sequence; this permits separate messages in the same session but cannot prove that two ID-less deliveries are the same turn. A present-but-blank turn ID is rejected. Do not manually score a hook-covered turn using another event ID.

## Data handling

| Data | Stored or processed by headroom |
| --- | --- |
| History | Read/parsed locally for counts; content can be inspected by JSONL filters, but is not uploaded or copied into the ledger |
| Current prompt | Passed in memory to Mock or the local Laya service |
| Ledger | Opaque event IDs, dates, scores, provider, agent names, and opaque session sequence bookkeeping; no prompt text |
| `last-hook.json` | Latest outcome/time, input presence/length, agent and scoring metadata; no prompt text or raw session/turn IDs |
| Desktop preferences | Position, language, and mute in `desktop.json` |
| UI | Bundled assets and loopback-only servers; no CDN, analytics, or cloud scoring |

Adapters skip sufficiently old files to reduce refresh work. UI/API output includes adapter names and source metadata; do not publish runtime state or diagnostics as documentation examples.

These guarantees apply to shipped headroom code, not AI tools or separately deployed model servers. Configure your model service's logs/network separately. Any future cloud Jev integration would require explicit opt-in and a new disclosure of what leaves the device.

For test setup and CI coverage, see [CONTRIBUTING.md](../CONTRIBUTING.md#run-the-tests).
