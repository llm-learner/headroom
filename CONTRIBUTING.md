# Contributing to headroom

**English** · [简体中文](#参与贡献)

Thanks for helping keep everyone's brain budget honest (and fun). Bug reports, fixes, translations, and ideas are all welcome.

## Set up

- **Python 3.10+** with Tk (`tkinter`). The python.org installers for Windows and macOS include Tk; on Linux distribution Pythons you may need a package such as `python3-tk`.
- **Node.js** (current LTS) for the dashboard JavaScript test.
- Scoring, the hook, and the web dashboard use only the Python standard library.
- Optional desktop displays: `python -m pip install -r skills/headroom/requirements-desktop.txt`. The animated Windows card also needs Microsoft Edge WebView2 Runtime; macOS uses the static Tk card. These extras are not required for the core tests.

```text
git clone https://github.com/<your-name>/headroom.git
cd headroom
git remote add upstream https://github.com/llm-learner/headroom.git
```

## Run the tests

Run from the repository root with `HEADROOM_DISABLE_DASHBOARD=1`, so lifecycle tests never start a real dashboard or display against a temporary ledger.

PowerShell:

```powershell
$env:HEADROOM_DISABLE_DASHBOARD = "1"
python -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
node skills/headroom/tests/test_dashboard_mood.js
```

macOS / Linux:

```bash
export HEADROOM_DISABLE_DASHBOARD=1
python3 -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
HEADROOM_TEST_PYTHON=python3 node skills/headroom/tests/test_dashboard_mood.js
```

- The Node test starts Python to render the dashboard; `HEADROOM_TEST_PYTHON` selects the executable (default: `python` on Windows, `python3` elsewhere).
- Tests that need Windows, the optional tray packages, or a real tray/WebView window skip automatically. The native smoke tests are opt-in (`HEADROOM_TEST_NATIVE_TRAY=1`, `HEADROOM_TEST_WEBVIEW=1`, Windows only).
- Tests must use temporary histories and ledgers only, never your real `~/.codex` data, and ephemeral loopback ports, never the live dashboard port 8766.

GitHub Actions runs on pushes, pull requests, and manual dispatch. Its matrix covers Linux, Windows, and macOS with Python 3.10–3.13 and Node.js 22. Windows also installs optional desktop dependencies and reruns the suite on Python 3.13; native tray/WebView smoke tests remain opt-in.

## Code style

- **Standard library only** for scoring, the hook, and the dashboard. New third-party packages are acceptable only for optional features (like the tray card), must be listed in `requirements-desktop.txt`, and must fail gracefully when missing.
- **Keep Windows and PowerShell working.** Most users run Codex on Windows: keep `install_windows.ps1` and `hooks.json.template` in sync with the hook, handle paths with spaces, and read/write text as UTF-8 (GBK systems included).
- **Privacy first.** Never store prompt text or raw session/turn IDs, never add network calls beyond loopback, and never add telemetry.
- Viewing, refreshing, or playing clips must never charge points.
- Match the surrounding style, keep changes focused, and add or update tests for behavior changes.

## Branches and pull requests

1. Fork the repository and create a branch from the latest `upstream/main` (for example `fix/tray-tooltip` or `docs/readme-typo`).
2. Keep each pull request focused on one change; small commits with clear messages are easiest to review.
3. Run both test commands before pushing.
4. Open a pull request against `main` and describe what changed, why, and how you tested it (including your OS and Python version).

## Keep both READMEs in sync

`README.md` (English) and `README.zh-CN.md` (简体中文) should describe the same features, commands, and sections. Keep the paired guides, reference, and FAQ under `docs/` in sync too. Keep implementation detail out of the READMEs. When you change one language, update the other in the same pull request; if you cannot write it, say so so a maintainer can help.

Please do not commit runtime state, diagnostics (`last-hook.json`), ledgers, Codex history, or credentials.

---

# 参与贡献

[English](#contributing-to-headroom) · **简体中文**

感谢你帮忙让大家的「脑力额度」更靠谱（也更好玩）。欢迎提交 bug、修复、翻译和想法。

## 环境准备

- **Python 3.10+**，并带有 Tk（`tkinter`）。Windows 和 macOS 的 python.org 安装包自带 Tk；Linux 发行版自带的 Python 可能需要安装 `python3-tk` 之类的包。
- **Node.js**（当前 LTS），用于面板 JavaScript 测试。
- 评分、钩子和网页面板只使用 Python 标准库。
- 可选桌面显示：`python -m pip install -r skills/headroom/requirements-desktop.txt`。Windows 动态卡片还需 Microsoft Edge WebView2 Runtime；macOS 使用静态 Tk 卡片。核心测试不依赖这些扩展。

```text
git clone https://github.com/<你的用户名>/headroom.git
cd headroom
git remote add upstream https://github.com/llm-learner/headroom.git
```

## 运行测试

在仓库根目录运行，并设置 `HEADROOM_DISABLE_DASHBOARD=1`，避免生命周期测试针对临时账本启动真实的面板或桌面显示。

PowerShell：

```powershell
$env:HEADROOM_DISABLE_DASHBOARD = "1"
python -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
node skills/headroom/tests/test_dashboard_mood.js
```

macOS / Linux：

```bash
export HEADROOM_DISABLE_DASHBOARD=1
python3 -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
HEADROOM_TEST_PYTHON=python3 node skills/headroom/tests/test_dashboard_mood.js
```

- Node 测试会调用 Python 渲染面板，可用 `HEADROOM_TEST_PYTHON` 指定（Windows 默认 `python`，其他平台默认 `python3`）。
- 需要 Windows、可选托盘依赖或真实托盘 / WebView 窗口的测试会自动跳过。原生冒烟测试需要手动开启（`HEADROOM_TEST_NATIVE_TRAY=1`、`HEADROOM_TEST_WEBVIEW=1`，仅 Windows）。
- 测试只能使用临时历史和账本，不要读写真实的 `~/.codex` 数据；只使用临时回环端口，不占用实际面板端口 8766。

GitHub Actions 在推送、PR 和手动触发时运行，矩阵覆盖 Linux、Windows、macOS 的 Python 3.10–3.13 和 Node.js 22。Windows 还在 Python 3.13 安装桌面依赖并重跑测试；原生托盘 / WebView 冒烟测试仍需手动开启。

## 代码风格

- 评分、钩子和面板**只用标准库**。第三方包只用于可选功能（例如托盘卡片），需要写进 `requirements-desktop.txt`，缺失时要能优雅降级。
- **保持 Windows 和 PowerShell 可用。** 大多数用户在 Windows 上使用 Codex：修改钩子时同步更新 `install_windows.ps1` 和 `hooks.json.template`，注意带空格的路径，文本读写统一用 UTF-8（包括 GBK 系统）。
- **隐私优先。** 不保存提示词正文或原始 session/turn ID，不添加回环地址以外的网络请求，不添加遥测。
- 查看、刷新或播放片段都不能扣点。
- 跟随周边代码风格，保持改动聚焦；行为变化需要新增或更新测试。

## 分支与 Pull Request

1. Fork 本仓库，从最新的 `upstream/main` 创建分支（例如 `fix/tray-tooltip`、`docs/readme-typo`）。
2. 每个 PR 只做一件事；小而清晰的提交更容易审查。
3. 推送前运行上面两条测试命令。
4. 向 `main` 发起 PR，说明改了什么、为什么改、如何测试（包括操作系统和 Python 版本）。

## 保持两份 README 同步

`README.md`（英文）和 `README.zh-CN.md`（简体中文）应描述相同的功能、命令和章节，`docs/` 中成对的指南、配置与排障也要同步。实现细节不要放回首页。修改一种语言时，在同一个 PR 中更新另一种；不熟悉该语言时请在 PR 中说明，维护者会协助。

请不要提交运行时状态、诊断文件（`last-hook.json`）、账本、Codex 历史或凭据。
