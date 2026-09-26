# Setup and use

**English** · [简体中文](guide.zh-CN.md) · [Back to README](../README.md)

Commands run from the repository root. Use Python 3.10+; desktop displays require Tk. macOS's `/usr/bin/python3` may be older: use a supported Python from python.org or Homebrew.

## Windows hooks

The Windows installer uses `python.exe` on PATH and writes `SessionStart` and `UserPromptSubmit` definitions to `$CODEX_HOME/hooks.json` (default `~/.codex/hooks.json`). Review the script before running it:

```powershell
powershell -ExecutionPolicy Bypass -File skills/headroom/hooks/install_windows.ps1
```

**If `hooks.json` exists, the installer refuses to overwrite it.** Preserve other hooks and merge the two definitions from `skills/headroom/hooks/hooks.json.template`. Replace `__PLUGIN_ROOT__` with the absolute path to `skills/headroom` and `__PYTHON__` with your Python executable. A quoted executable in PowerShell needs the `&` call operator. Save valid JSON as UTF-8 without a BOM. Do not use `-Force` as a shortcut: it replaces the entire file.

Open `/hooks` in Codex, review and trust both definitions, then start one new session. Later messages in that session can charge normally. Changing a hook command requires reviewing that definition again.

Keep the source directory in place: hooks use absolute paths. Installing a plugin or copying `skills/headroom` into your user skills directory exposes `$headroom`, but does not activate or trust hooks.

`SessionStart` opens the display. `UserPromptSubmit` scores asynchronously after submission, not after the assistant finishes. The display updates after scoring and its next refresh.

## macOS and Linux hooks

```sh
sh skills/headroom/hooks/install.sh --dry-run
sh skills/headroom/hooks/install.sh --link-skill
```

The installer merges only headroom's commands, preserves other hooks, backs up a changed file, and is safe to rerun. `--link-skill` links `~/.agents/skills/headroom`; it does not replace an unrelated entry.

The wrapper finds Python 3.10+ and pins it in hook commands. Choose the environment containing your optional desktop packages with:

```sh
PYTHON=/path/to/python3 sh skills/headroom/hooks/install.sh --link-skill
```

Review and trust both hooks in `/hooks`, then start one new session. `SessionStart` defaults to the web dashboard. Uninstall hooks without deleting the ledger with `sh skills/headroom/hooks/install.sh --uninstall`.

Bundled installers configure **Codex only**. Other tools' histories contribute without hooks; their scoring hooks need separate configuration. [Adapter reference](reference.md#agent-adapters)

## Windows tray card

```powershell
python -m pip install -r skills/headroom/requirements-desktop.txt
pythonw skills/headroom/scripts/headroom_desktop.py --lang en --show
```

The animated card needs Tk, pystray, Pillow, pywebview, and Edge WebView2 Runtime. Use `python` instead of `pythonw` to see errors. Omit `--show` to start collapsed; exit an existing display before changing launch options.

- Click H to open/collapse; `−` and Escape also collapse. Hover for percent left.
- Windows may put H under **Show hidden icons**; drag it to the visible tray if desired.
- **EN / ZH** switches language; the speaker button changes mute.
- Right-click → **Exit headroom** closes the display, not scoring. A later Codex session can reopen it.

One display runs per ledger and Windows login session, refreshing every ten seconds. The card uses a read-only loopback server on a random port, not dashboard port 8766. `desktop.json` beside the ledger stores position/language/mute. It starts with a trusted Codex session, **not at Windows login**.

Without WebView2, use `--renderer tk` for the static card. `--mode orb` selects the older draggable orb and does not require pystray; `--mode tray` is the default. Exit the display before switching.

## macOS menu bar

Use a Python environment with Tk; Homebrew Python may need the matching `python-tk` package:

```sh
python3 -m pip install -r skills/headroom/requirements-desktop.txt
python3 skills/headroom/scripts/headroom_desktop.py --lang en
```

Click H in the menu bar → **Show usage** for the static card. `--mode orb` selects the floating orb. Missing Tk/tray dependencies fall back to the web dashboard. For session-start launch, rerun the hook installer with `--display desktop` using the same Python environment. The animated card is Windows-only; use the web dashboard for clips on macOS. No login item is added.

## Web dashboard and language

```sh
python3 skills/headroom/scripts/headroom_dashboard.py --lang en
```

Open `http://127.0.0.1:8766/?lang=en` or `?lang=zh`. If it is running, open the URL rather than starting another server. Use `python` on Windows when appropriate.

| Display | Language priority |
| --- | --- |
| Tray / orb | `--lang` → `HEADROOM_LANG` → saved preference → Chinese |
| Web | URL `?lang=` → `--lang` → `HEADROOM_LANG` → Chinese |

Language affects presentation only. Startup options take effect on restart; URL parameters change the running web page immediately.

## Meme clips

Click the mood image on the animated Windows card or web dashboard to play a bundled clip with sound. The speaker button mutes; nothing plays automatically on opening.

The first click plays Hey Dog. Clicks less than 3.5 seconds apart choose one of the other eight clips without immediately repeating; a longer gap restarts at Hey Dog. Dadada and Industry Baby animate the image to audio instead of showing video. Reduced-motion settings disable animation.

Click again to switch; Escape stops. Refresh does not interrupt playback, but collapsing the card or changing its language stops it. Mute does not stop audio-reactive animation. These actions never charge points.

## Local Laya scoring

Mock is the default. Model weights and a server are not bundled. Deploy a compatible service at `http://127.0.0.1:8765/predict`, then create/update `$CODEX_HOME/headroom/config.json` (default `~/.codex/headroom/config.json`):

```json
{"backend": "laya"}
```

The hook rereads this file every turn, including existing sessions. Set `mock` to switch back; `HEADROOM_BACKEND` overrides the file. Config does not download/start a model. Invalid config or unavailable Laya skips **scored debits**, without falling back to Mock; count-based usage can still appear on the meter. [Calculation and API details](reference.md)

Jev API is not implemented. `jev-mock-local` is only the Mock provider's name, not a Jev call.

## Updating

Exit the display, update the repository without overwriting local work, then relaunch. Preserve config and the ledger. Moving the repository/changing Python requires updating and re-trusting hook commands.

For a locally installed Codex plugin, reinstall from its configured marketplace and start a new chat to load updated skills. Hook scoring and the independent display do not depend on that skill reload.

See the [FAQ](faq.md) for failures or unexpected percentages.
