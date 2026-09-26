# Troubleshooting

**English** · [简体中文](faq.zh-CN.md) · [Back to README](../README.md)

## The percentage does not move

1. Check whether the display is running and refresh it. It normally refreshes every ten seconds.
2. For scored debits, confirm both headroom hooks are enabled/trusted in Codex `/hooks`. After initial setup, start one new session; subsequent messages do not require new sessions.
3. If using Laya, check the separately deployed service. Setting `backend: laya` does not start it.
4. Inspect `last-hook.json` beside the ledger for the latest outcome. It contains no prompt text.

If `HEADROOM_SPENT_SOURCE=ledger`, no scores means 100% left. In default `auto`, tools without positive scored totals use message-count estimates. The count shown by a display is not proof that its hook successfully scored a message.

## Why are there fixed two-point charges?

They are estimates from today's message count, not model scores. `auto` uses each tool's scored total if positive, otherwise its messages × 2. `counts` always estimates; `ledger` never does. [Calculation reference](reference.md#budget-and-spend)

The percentage can rise when actual scores replace a larger count estimate, or when the rolling cap changes at the UTC+8 day boundary. It is not a fixed 100-point account.

## Is scoring automatic for every tool?

The bundled installers configure Codex only. Other supported tools supply readable history for count estimates unless you separately configure their hooks. Automatic-task exclusion is best-effort; missing source metadata is accepted by default. Strict mode may exclude ordinary conversations too.

## Why does a balance query spend points?

Opening the UI, refreshing it, changing language, and running the `status` CLI do not score a turn. Sending a chat message asking for your balance is still a user prompt, so its hook can charge it. Avoid manual `turn` scoring for a hook-covered message: a different event ID can double-charge.

## The tray icon or card is missing

- Check Windows' hidden-icons arrow for H.
- Launch with `--show` to expand immediately, after exiting any existing display.
- Replace `pythonw` with `python` to see errors; verify Tk and `requirements-desktop.txt` dependencies.
- Without Edge WebView2, try `--renderer tk`. On macOS, missing Tk/tray packages fall back to the web dashboard.
- Two displays using the same ledger may be prevented by the single-instance lock.

## The hook file cannot be parsed or installed

Validate that `hooks.json` is JSON saved as UTF-8 without a BOM. The Windows installer refuses an existing file rather than merging it; preserve other hooks and follow the [merge instructions](guide.md#windows-hooks). Do not blindly force-overwrite.

A quoted Python executable in PowerShell requires `&`. Keep the source/Python paths valid and re-trust definitions after changing commands. Hook input supports UTF-8 Chinese and emoji, including GBK Windows systems.

## How do I stop or uninstall it?

Exiting the tray stops the display only. Disable/remove headroom's hooks in Codex to stop automatic scoring. On macOS/Linux, `sh skills/headroom/hooks/install.sh --uninstall` removes only headroom's hooks and keeps its data.

On Windows, remove only headroom's command entries, preserving other commands even when they share the same hook group. Keep the ledger unless you deliberately want to reset history.

## Reporting a bug

Include OS/Python version, display mode, backend, expected vs actual behavior, and a sanitized diagnostic outcome. Do not attach history databases, real prompts, credentials, or the ledger. See [CONTRIBUTING.md](../CONTRIBUTING.md).
