# 安装与使用

[English](guide.md) · **简体中文** · [返回 README](../README.zh-CN.md)

以下命令均在仓库根目录执行。需要 Python 3.10+；桌面显示需要 Tk。macOS 自带的 `/usr/bin/python3` 可能过旧，请从 python.org 或 Homebrew 安装支持的版本。

## Windows 钩子

Windows 安装器使用 PATH 中的 `python.exe`，将 `SessionStart` 和 `UserPromptSubmit` 写入 `$CODEX_HOME/hooks.json`（默认 `~/.codex/hooks.json`）。审查脚本后运行：

```powershell
powershell -ExecutionPolicy Bypass -File skills/headroom/hooks/install_windows.ps1
```

**已有 `hooks.json` 时，安装器拒绝覆盖。** 请保留其他钩子，合并 `skills/headroom/hooks/hooks.json.template` 中的两条定义。将 `__PLUGIN_ROOT__` 替换为 `skills/headroom` 的绝对路径，`__PYTHON__` 替换为 Python 可执行文件。PowerShell 调用被引号包围的可执行文件需要 `&`。保存为无 BOM 的 UTF-8，并确认 JSON 有效。不要用 `-Force` 代替合并，它会替换整个文件。

在 Codex 打开 `/hooks`，审查并信任两条定义，再新建一次会话。之后同一会话的消息能正常扣点；修改钩子命令后，需要重新审查该定义。

请保留源目录，钩子使用绝对路径。安装插件或把 `skills/headroom` 复制进用户 skills 目录可以提供 `$headroom`，但不会启用或信任钩子。

`SessionStart` 打开显示；`UserPromptSubmit` 在提交消息后异步评分，不等助手回复结束。评分完成后，显示在下一次刷新更新。

## macOS 与 Linux 钩子

```sh
sh skills/headroom/hooks/install.sh --dry-run
sh skills/headroom/hooks/install.sh --link-skill
```

安装器只合并 headroom 的命令，保留其他钩子，变更前备份，可重复运行。`--link-skill` 在 `~/.agents/skills/headroom` 创建链接，不替换已有的无关目录。

包装脚本寻找 Python 3.10+，并在钩子中固定它。如需使用已安装桌面依赖的环境：

```sh
PYTHON=/path/to/python3 sh skills/headroom/hooks/install.sh --link-skill
```

在 `/hooks` 中信任两条定义，再新建一次会话。`SessionStart` 默认启动网页面板。用 `sh skills/headroom/hooks/install.sh --uninstall` 卸载钩子，不删除账本。

随附安装器**只配置 Codex**。其他工具无需钩子也能按历史估算用量，但评分钩子需要另行配置。[适配器说明](reference.zh-CN.md#agent-适配器)

## Windows 托盘卡片

```powershell
python -m pip install -r skills/headroom/requirements-desktop.txt
pythonw skills/headroom/scripts/headroom_desktop.py --lang zh --show
```

动态卡片需要 Tk、pystray、Pillow、pywebview 和 Edge WebView2 Runtime。用 `python` 替换 `pythonw` 可查看报错。省略 `--show` 时保持收起；修改启动参数前先退出已有显示。

- 点击 H 展开 / 收起，`−` 和 Escape 也能收起；悬停显示剩余百分比。
- Windows 可能把 H 放在**隐藏图标**箭头里，可拖到任务栏外面常驻。
- **EN / ZH** 切换语言，小喇叭按钮切换静音。
- 右键 → **退出 headroom**只关闭显示，不关闭评分，之后的 Codex 会话可以重新打开。

同一账本、同一 Windows 登录会话只运行一个显示，每十秒刷新。卡片使用随机端口上的只读回环服务，不依赖 8766 面板。账本旁的 `desktop.json` 保存位置 / 语言 / 静音。它随可信任的 Codex 会话启动，**不是 Windows 登录自启**。

没有 WebView2 时使用 `--renderer tk` 启动静态卡片。`--mode orb` 切换旧版可拖动悬浮球，不需要 pystray；默认是 `--mode tray`。切换前退出当前显示。

## macOS 菜单栏

使用带 Tk 的 Python；Homebrew Python 可能需要配套的 `python-tk` 包：

```sh
python3 -m pip install -r skills/headroom/requirements-desktop.txt
python3 skills/headroom/scripts/headroom_desktop.py --lang zh
```

点击菜单栏 H → **展开用量**查看静态卡片。`--mode orb` 切换悬浮球。缺少 Tk / 托盘依赖时回退到网页面板。如需随会话启动，使用同一 Python 环境，给钩子安装器加 `--display desktop`。动态卡片仅支持 Windows，macOS 在网页面板播放片段。不会添加登录启动项。

## 网页面板与语言

```sh
python3 skills/headroom/scripts/headroom_dashboard.py --lang zh
```

打开 `http://127.0.0.1:8766/?lang=zh` 或 `?lang=en`。已有服务时直接打开网址，不要重复启动。Windows 如无 `python3` 命令则改用 `python`。

| 显示入口 | 语言优先级 |
| --- | --- |
| 托盘 / 悬浮球 | `--lang` → `HEADROOM_LANG` → 保存的偏好 → 中文 |
| 网页 | 网址 `?lang=` → `--lang` → `HEADROOM_LANG` → 中文 |

语言只改变显示。启动参数在重启后生效，网址参数可立即切换运行中的网页。

## 梗片段

在 Windows 动态卡片或网页面板点击表情，播放自带的有声片段。小喇叭按钮静音；打开界面不会自动播放。

第一次播放「诶大狗」。点击间隔小于 3.5 秒时，从其他八段中选择，不立即重复；更长的间隔回到「诶大狗」。「大狗叫叫叫哒哒哒」和「INDUSTRY BABY」只播放音频，图片随音频律动。系统减少动态效果设置会关闭动画。

再次点击切换，Escape 停止。刷新不打断播放，收起卡片或切换其语言会停止。静音不停止音频律动。这些操作不扣点。

## 本地 Laya 评分

默认使用 Mock，不打包模型权重或服务。自行在 `http://127.0.0.1:8765/predict` 部署兼容服务，再创建 / 更新 `$CODEX_HOME/headroom/config.json`（默认 `~/.codex/headroom/config.json`）：

```json
{"backend": "laya"}
```

钩子每轮重读，已有会话也生效。改成 `mock` 切回，`HEADROOM_BACKEND` 优先于文件。配置不会下载 / 启动模型。配置错误或 Laya 不可用时跳过**评分扣点**，不回退到 Mock；显示层仍可能按条数估算。[计算与接口说明](reference.zh-CN.md)

Jev API 尚未接入，`jev-mock-local` 只是 Mock 的 provider 名，不是真实 Jev 调用。

## 更新

先退出显示，更新仓库且不覆盖本地改动，再重新启动。保留配置和账本。移动仓库 / 改变 Python 后，要更新并重新信任钩子命令。

本地安装的 Codex 插件需从已配置的市场重装，并新建会话加载新版 Skill。钩子评分和独立显示不依赖这次 Skill 重载。

启动失败或百分比异常请查阅[常见问题](faq.zh-CN.md)。
