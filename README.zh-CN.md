<div align="center">

# headroom

**I need a reset.**

AI 有使用额度，你的大脑也该有。

[English](README.md) · **简体中文**

一个本地优先的**多 agent 插件 / Skill**，给大脑也配个日限额。<br>
发一句话，扣一点虚构的脑力 —— 在 Codex、Claude Code、opencode、Antigravity、WorkBuddy 里都算。

[支持的 agent](#支持的-agent) · [快速开始](#快速开始) · [任务栏托盘](#desktop-orb) · [界面语言](#界面语言) · [Jev 与 Laya](#scoring) · [隐私](#隐私)

</div>

| 剩余 100%–70% | 剩余低于 70% 至 30% | 剩余低于 30% |
| :---: | :---: | :---: |
| <img src="skills/headroom/assets/brain-full.png" width="110" alt="戴耳机的狗"> | <img src="skills/headroom/assets/brain-declining.webp" width="110" alt="流泪的猫"> | <img src="skills/headroom/assets/brain-low.png" width="110" alt="咆哮的狗"> |
| 再问最后一个问题。 | 这好像不是一个小问题。 | 这问题有问题啊！ |

**纯属娱乐，不是科学测量。** 这里的脑力负荷 / cognitive load 是好玩的估计，不代表智力、健康、疲劳程度或生产力。归零也不会阻止你聊天。

## 聊天时会发生什么？

- **按你的习惯给额度，跨 agent 合并计算。** 取之前七个完整自然日中用户消息最多的一天，把当天**所有** agent 的消息数相加，再乘以二。这个窗口没有历史消息时，暂用两点。**今天不在额度窗口内。**
- **分子只算今天。** 消耗在本地零点重置，来源由 `HEADROOM_SPENT_SOURCE` 决定：

  | 取值 | 行为 |
  | --- | --- |
  | `auto`（默认） | **按 agent 分别判断**：该 agent 今天有评分扣点就用扣点，否则用它的对话条数 |
  | `ledger` | 只认评分扣点。没装钩子时消耗恒为 0，表盘显示 100% |
  | `counts` | 始终按「今天条数 × 2」，不看账本 |

  这个 ×2 和额度基准的 ×2 对齐，所以「今天和你最忙的一天一样忙」就等于剩余 0%。

  `auto` 是**按 agent 分别判断，不是整天一刀切**。如果整天只切一次，那么 Codex 扣一次分就会把其他所有 agent 当天的对话全部抹掉 —— 只有一个 agent 装了钩子时，其他 agent 的对话会从那一刻起不再计入。按 agent 判断时，同一个 agent 内估算和评分**不会混算**，这是避免重复扣点的关键。
- **跨会话、跨工具共用一个余额。** 本地共享账本驱动百分比、进度条和表情。显示「已用 12.50 / 334 点」，并附各 agent 的来源明细，不额外显示剩余多少点。
- **刷新不扣点。** 面板每 10 秒自动刷新；刷新和切换界面语言都不扣点。不需要每发一句话就新建会话。
- **收进任务栏。** 一个小 H 托盘图标，点击才展开用量卡片。直接读取本地账本，不用浏览器标签页，也不占桌面位置。

自然日按 **Asia/Shanghai（UTC+8）** 划分。计算七天基准时会统计**所有**记录为 `userMessage` 的消息，包括自动任务；来源筛选只影响扣点，不影响额度基准。

## 支持的 agent

发现是自动的：headroom 逐个询问适配器本机是否存在它的历史，然后读取回答「有」的那些。agent 的任何细节都不会泄漏到账本、评分器或显示层。

| agent | 历史来源 | 钩子 |
| --- | --- | --- |
| `codex` | `$CODEX_HOME/thread_history_1.sqlite` → `thread_items` | ✅ |
| `claude` | `$CLAUDE_CONFIG_DIR/projects/*/*.jsonl`（回退到 `history.jsonl`） | ✅ |
| `opencode` | `$XDG_DATA_HOME/opencode/opencode.db` → `message` | — |
| `antigravity` | `$GEMINI_DIR/antigravity/brain/*/.system_generated/logs/transcript_full.jsonl` | ✅ |
| `workbuddy` | `$WORKBUDDY_HOME/projects/*/*.jsonl` | — |

`antigravity` 覆盖共用 `~/.gemini` 的两个 Google 工具，但只有 Gemini CLI 会装钩子：它有「提交提示词」这个事件，而 Antigravity 自己的钩子系统没有（它的 `PreInvocation` 在**每一次**模型调用前触发，一条提示词会被扣好几次）。

```text
python3 skills/headroom/scripts/headroom.py agents
```

列出每个适配器、本机是否可读、以及最近每天的计数。

**会话记录不等于轮次日志。** Claude Code 会把工具结果当作 user 角色消息回放，所以 Claude 适配器要求正文是纯字符串或含 `text` 块，并剔除 `system`/`sdk` 来源和 sidechain 记录。Codex 和 opencode 直接查 SQL。如果按原始记录条数统计，除了 Codex 之外每个 agent 的额度基准都会失去意义。

**不需要装钩子就能看到额度基准、各 agent 明细和消耗。** 显示层每次刷新都会重读本地历史，默认按今天的对话条数估算消耗。

### 不改代码新增 agent

在 `$HEADROOM_AGENTS_CONFIG`（默认 `~/.headroom/agents.json`）里声明：

```json
{"agents": [
  {"name": "aider", "label": "Aider", "kind": "jsonl", "root": "~/.aider",
   "glob": "**/*.history", "where": {"role": "user"},
   "day_field": "timestamp", "day_format": "ms"}
]}
```

`kind` 为 `jsonl` 或 `sqlite`；`day_format` 为 `ms`、`iso` 或 `epoch`。同名的声明式 agent 会覆盖内置适配器。

## 快速开始

网页面板中，点击表情图片会先向上跳动，再原地播放一段有声音的视频。第一次点击播放「诶大狗」。两次图片点击间隔小于 3.5 秒时，从其余八段（大狗叫 1–5、叫叫、大狗叫叫叫哒哒哒、INDUSTRY BABY）中随机播放一段，不连续重复当前片段；间隔达到 3.5 秒则从诶大狗重新开始。「大狗叫叫叫哒哒哒」和「INDUSTRY BABY」只播放音频，当前脑力状态图片随实时音频强弱和节拍峰值上跳、旋转、缩放，结束或切换时复原（系统开启减少动态效果时关闭律动），其余七段播放视频；播完恢复当前脑力状态图片，不自动连播。播放中再点会停止当前片段，按同样的点击间隔规则选取片段；图片按钮获得焦点时按 Esc 可停止。余额刷新不打断播放，播放视频不扣脑力值。卡片右下角的小喇叭图标可随时切换声音开 / 静音，不打断播放；浏览器记住设置，静音时图片律动继续。

当前自动安装流程面向 **Windows + PowerShell 上的 Codex**。需要 Python 3.10+，以及本机 Codex 历史索引 `thread_history_1.sqlite`。Mock 和网页面板只用 Python 标准库。

```powershell
git clone https://github.com/llm-learner/headroom.git
cd headroom
python skills/headroom/scripts/headroom.py status
python -m pip install -r skills/headroom/requirements-desktop.txt
pythonw skills/headroom/scripts/headroom_desktop.py --lang zh
```

任务栏右侧会出现小 H 托盘图标，可能在隐藏图标的箭头里。点击展开用量卡片，悬停查看剩余百分比。这一步只读，不会开启自动扣点。如果需要在终端看启动报错，用 `python` 替换 `pythonw`。

### 开启自动扣点

在仓库根目录先预览，再写入：

```bash
python3 skills/headroom/hooks/install_hooks.py --dry-run      # 打印每一处改动
python3 skills/headroom/hooks/install_hooks.py                # 合并进本机检测到的每个 agent
python3 skills/headroom/hooks/install_hooks.py --agents codex,claude
```

| Agent | 配置文件 | 事件 |
| --- | --- | --- |
| Codex | `$CODEX_HOME/hooks.json` | `SessionStart`、`UserPromptSubmit` |
| Claude Code | `$CLAUDE_CONFIG_DIR/settings.json` | `SessionStart`、`UserPromptSubmit` |
| Gemini CLI | `$GEMINI_DIR/settings.json` | `SessionStart`、`BeforeAgent` |

默认的 `--agents auto` 会装上 Codex，以及本机已存在主目录的其他 agent，因此不会为你没在用的工具凭空创建 `~/.claude` 或 `~/.gemini`。`--agents all` 装全部，逗号列表则只装指定的几个。每个文件写入前都会备份，无关的钩子条目会被保留，无法解析的配置不会被改写，重复运行是幂等的。

三个产品把同样两件事各自存在自己的 schema 里，安装器就按各自的 schema 写：Codex 和 Claude Code 的超时单位是秒，且 Claude Code 没有 `async` 字段；Gemini CLI 的超时单位是毫秒，并把提示词事件叫作 `BeforeAgent`。三者调用的是同一个 `headroom_hook.py`，所以无论你在哪个工具里打字，都由同一个本地评分器打分，每一笔扣点都进同一本共享账本。

在各自 agent 里审查并信任 headroom 的钩子（Codex `/hooks`、Claude Code `/hooks`、Gemini CLI `/hooks panel`）。首次安装钩子后，新开一个会话验证激活。之后在同一个会话继续发消息就能扣点，**不需要反复新建会话**。

`SessionStart` 在 Windows 和 macOS 上启动托盘显示（Linux 上启动网页面板）；`UserPromptSubmit`／`BeforeAgent` 在提交消息后评分，**不是等助手回复结束才评分**。Codex 是异步执行，Claude Code 和 Gemini CLI 是同步执行，所以请留出评分和界面刷新的时间。Windows 上仍可用 `powershell -ExecutionPolicy Bypass -File skills/headroom/hooks/install_windows.ps1` 单独安装 Codex 的钩子。

要把 `$headroom` 作为 Codex Skill 使用，可以通过本地插件市场安装这个仓库，或把 `skills/headroom` 复制到 Codex 的 skills 目录。仅安装插件 / Skill 不会自动启用或信任生命周期钩子。请保留钩子指向的源目录。

### macOS / Linux

需要 Python 3.10+（macOS 自带的 `/usr/bin/python3` 可能过旧，请从 python.org 安装或 `brew install python`）。余额查询和网页面板只用标准库：

```bash
python3 skills/headroom/scripts/headroom.py status
python3 skills/headroom/scripts/headroom_dashboard.py --lang zh
```

`headroom.py` 默认读取 `~/.codex` 中的 Codex 历史；如果设置了自定义的 `CODEX_HOME`，请同时传入 `--codex-home "$CODEX_HOME"`。

要开启自动扣点，请在仓库根目录审阅并运行安装器。它会把 headroom 的钩子合并进本机检测到的每个 agent 配置，不改动你的其他钩子；文件有变更时先备份，可重复运行。钩子使用运行安装器的那个 Python（可用 `PYTHON=/path/to/python3` 指定），不依赖 PowerShell：

```bash
sh skills/headroom/hooks/install.sh --dry-run   # 预览
sh skills/headroom/hooks/install.sh             # 加 --link-skill 可通过 ~/.agents/skills 提供 $headroom
```

然后像上面那样在各自 agent 中审查并信任这些定义。`SessionStart` 在 macOS 上启动菜单栏显示，在 Linux 上启动网页面板（打开[面板](http://127.0.0.1:8766/?lang=zh)）。`sh skills/headroom/hooks/install.sh --uninstall` 只移除 headroom 的钩子，保留账本。

**macOS 菜单栏（可选）。** 在同一个 Python 中安装 `requirements-desktop.txt`，然后运行 `python3 skills/headroom/scripts/headroom_desktop.py --lang zh`。菜单栏会出现 H 图标，点击后选择 **展开用量** 查看静态卡片；也可以用 `--mode orb` 显示悬浮球。动画 WebView2 卡片仅支持 Windows，片段请在网页面板中播放。Python 需要带 Tk（Homebrew：`brew install python-tk`）；缺少 Tk 或托盘依赖时会自动改用网页面板。想让 `SessionStart` 打开菜单栏显示，请用 `--display desktop` 重新运行安装器。不会添加登录启动项。

`opencode` 和 `WorkBuddy` 没有 JSON 钩子配置，因此它们保持只读：参与额度基准和各 agent 明细，但不扣点。`antigravity` 与 Gemini CLI 共用 `~/.gemini` 并在此计入，但 Antigravity 自己的钩子系统没有「提交提示词」事件（它的 `PreInvocation` 在每一次模型调用前触发），所以只有 Gemini CLI 会被装上钩子。其他工具可以手工添加钩子 —— 钩子会归一化各 agent 的载荷字段，并在设置了 `HEADROOM_AGENT` 时读取它，所以一条导出该变量的钩子定义就能直接工作。

<a id="desktop-orb"></a>

## 任务栏托盘（Windows）

- **单击**小 H 图标展开 / 收起；卡片右上角的 `−` 和 Escape 也可以收起。悬停图标显示剩余百分比。
- 启动时加 `--show` 可直接展开卡片（先退出已有显示）。
- 卡片出现在托盘附近，限制在显示器的可用工作区内。Windows 可能先把图标放进**隐藏图标**箭头里，可以手动拖到外面常驻。
- **右键 → 退出 headroom**只关闭显示，不关闭扣点。下一次 `SessionStart` 可以重新打开它。
- 卡片显示精确的**剩余百分比**、已用 / 日限额、当前表情和刷新按钮。
- **点击表情**就能播放与网页版相同的片段和随音乐律动的动画。小喇叭按钮会记住静音状态；收起卡片或切换语言会停止播放。展开时不会自动出声，播放也不扣点。
- 点击卡片的 **EN / ZH** 按钮即时切换语言。启动参数是 `--lang en` 或 `--lang zh`，优先级为：命令行 → `HEADROOM_LANG` → 记住的语言 → 中文。修改启动参数前先退出已经运行的显示。
- 同一账本、同一个 Windows 登录会话只显示一个入口，多个 Codex 会话不会重复生成。每十秒在后台读取一次用量，刷新不调用评分器。

动态托盘卡片需要带 **Tk** 的 Python、**pystray**、**Pillow**、**pywebview** 和 **Microsoft Edge WebView2 Runtime**（Python 依赖见 `requirements-desktop.txt`）。它是原生小窗口，不打开浏览器标签页，也不依赖 8766 网页面板。内部只读服务只监听 `127.0.0.1` 的随机空闲端口，用来读取打包素材和用量，退出显示时关闭。仅把位置 / 语言 / 静音偏好保存在账本旁的 `desktop.json`。它跟随可信任的 Codex `SessionStart` 启动，**没有添加 Windows 登录自启**。

如果没有 WebView2，退出显示后可用 `--renderer tk` 启动原来的静态托盘卡片，不带播放器，也不监听端口。

如果仍想用可拖动的悬浮球，退出托盘显示后加 `--mode orb` 启动。默认是 `--mode tray`；也可以用 `HEADROOM_DESKTOP_MODE=tray|orb` 指定启动模式。悬浮球模式不需要 pystray，Pillow 仍为可选，没有对应图片支持时用文字表情代替。

如需选择以后会话启动什么界面，可在钩子的环境里设置 `HEADROOM_DISPLAY`：`desktop`（Windows 默认）、`web`、`both` 或 `off`。只改变显示，不影响扣点。网页版仍可手动使用：

```text
python skills/headroom/scripts/headroom_dashboard.py --lang zh
```

打开[中文网页面板](http://127.0.0.1:8766/?lang=zh)。已有服务时直接打开网址，不要在同一端口重复启动。

## 界面语言

| 用法 | 英文 | 中文 |
| --- | --- | --- |
| 立即切换正在运行的面板 | [`?lang=en`](http://127.0.0.1:8766/?lang=en) | [`?lang=zh`](http://127.0.0.1:8766/?lang=zh) |
| 启动服务时指定默认语言 | `--lang en` | `--lang zh` |
| 通过服务进程的环境变量设置默认语言 | `HEADROOM_LANG=en` | `HEADROOM_LANG=zh` |

优先级：**网址参数 → 命令行参数 → 环境变量 → 默认中文**。不支持的网址语言值会回退到服务默认语言。英文模式覆盖标签、加载 / 错误提示、时间格式和图片说明。语言只影响显示，不影响评分、账本或 UTC+8 重置时间。已运行的面板用网址参数即可切换；启动参数在下次启动服务时生效。

<a id="scoring"></a>

## Jev、Laya 和 Mock 评分

| 后端 | 当前状态 | 提示词发送到哪里 |
| --- | --- | --- |
| **Mock**（`mock`） | 已包含；默认使用、确定性的虚构评分 | 本机进程内，不联网 |
| **Laya**（`laya`） | 已包含适配器，需自行部署本地 Laya 服务 | 固定回环地址：`http://127.0.0.1:8765/predict` |
| **Jev API** | **尚未实现**，是后续接入方向 | 当前版本没有 Jev / 云端请求 |

最初的原型设想使用 Jev 风格的评分 API，因此 Mock 的 provider 名叫 `jev-mock-local`。**它不是真实 Jev 调用**；headroom 也不是 Jev 或 Laya 的官方产品。

### 使用本地部署的 Laya

单独运行兼容的 Laya 服务，再把以下内容放到 `$CODEX_HOME/headroom/config.json`（默认 `~/.codex/headroom/config.json`）：

```json
{"backend": "laya"}
```

钩子**每轮都会重新读取**这个文件，已有会话也生效。改成 `mock` 即可切回演示评分。设置了 `HEADROOM_BACKEND` 时以环境变量为准。配置错误或 Laya 不可用时**跳过扣点**，不会偷偷降级成假分数。这个配置不会启动 / 下载模型，也不改变 CLI 显式传入的 `--backend`。

适配器发送的 JSON 中，`state.body` 是当前提示词，`questions.brain_load` 是评分问题。返回值要求 `answers.brain_load.type` 为 `"score"`，且 `answers.brain_load.score` 是 **0–10 的有限数值**。仓库**不打包模型权重或模型服务**。客户端对这条回环请求绕过系统 / HTTP 代理。

## 隐私

**本地评分，本地账本，不需要 headroom 云账号。** 当前自带的后端不添加云端评分请求或遥测。

| 数据 | headroom 如何处理 |
| --- | --- |
| 过去的对话 | 只查询消息类型 / 时间戳元数据来计数，不读取历史提示词正文。agent 数据库一律以只读方式打开 |
| 当前符合条件的提示词 | 在内存中传给 Mock 或配置的本地 Laya 服务 |
| 扣点账本 | 保存不透明事件 ID、本地日期、数值分数、provider 和 agent 名称，不保存提示词 |
| 钩子诊断 | 只保留最近一次结果、时间、输入是否存在 / 长度以及评分元数据，不保存提示词或原始 session/turn ID |
| 托盘 / 桌面显示 | 读取本地历史元数据和账本；动态卡片使用临时回环服务和打包素材，不调用云端评分；只保存位置 / 语言 / 静音偏好 |
| 面板 | 仅监听 `127.0.0.1`；图片随仓库附带，不加载 CDN 或统计脚本 |

默认共享账本是 `~/.headroom/ledger.sqlite3`；若已存在旧版的 `$CODEX_HOME/headroom/ledger.sqlite3`（未设置时为 `~/.codex/headroom/ledger.sqlite3`）则沿用旧路径，避免凭空从零开始。可用 `HEADROOM_STATE_PATH` 覆盖。打开由 headroom 0.x 写入的账本时会原地迁移，并把已有记录归属到 `codex`。不要公开运行时状态、诊断文件、agent 历史或凭据。

上述说明针对 **headroom**，不改变 Codex 自身的数据处理方式。单独部署的模型服务可能有自己的日志和联网行为，需要自行配置。未来若接云端 Jev，必须显式选择启用，并单独说明哪些数据会离开本机。

## 哪些对话会扣点？

目标是只计算人主动参与的对话，不计算无人值守的工作。钩子会拒绝已知非交互来源和 plan 模式；手动评分 CLI 也会拒绝非 normal 模式或未确认来源。

钩子会归一化各 agent 的载荷字段 —— `prompt`/`user_prompt`、`session_id`/`sessionId`、`turn_id`/`promptId`、`permission_mode`/`permissionMode` —— 并显式设置 `HEADROOM_AGENT`。Codex 提供 `turn_id`；Claude Code 和 Gemini 没有，因此 headroom 会从账本的 `hook_turns` 表分配一个持久的会话内序号。同一会话里两个不同的问题会扣两次；同一个轮次被重复投递只扣一次。`turn_id` 存在但为空视为载荷异常，直接跳过。

**自动识别来源是尽力而为，不是精确保证。** 当前钩子载荷不一定能可靠标识 Goal、自动任务或子代理。为兼容正常对话，缺少来源字段时默认接受；`HEADROOM_HOOK_STRICT=1` 会拒绝这类消息，但也可能漏掉普通聊天。不要把这个娱乐性筛选当成审计级规则。

<details>
<summary>排障与开发</summary>

- 不扣点？检查 `/hooks` 的信任状态、选择的后端和本地 Laya 是否可用。账本旁的 `last-hook.json` 记录最近结果。`HEADROOM_DEBUG_PATH` 可改路径，设为空字符串则关闭诊断。
- Windows PowerShell 钩子里，被引号包围的可执行文件路径需要 `&` 调用。钩子按 UTF-8 解码，支持 GBK 系统上的中文和 emoji。
- 修改钩子命令后，需要重新审查该定义。已被钩子覆盖的轮次不要再手动执行 `turn`，否则不同事件 ID 可能导致重复扣点。
- 切换语言、打开面板、点刷新都只读。但在聊天里发一句「查余额」仍是用户消息，可能被钩子正常计费。

使用临时历史和账本运行回归检查：

```text
python -m unittest discover -s skills/headroom/tests -p "test_*.py" -v
node skills/headroom/tests/test_dashboard_mood.js
```

JavaScript 测试需要 Node.js 和 Python，可用 `HEADROOM_TEST_PYTHON` 指定 Python 路径。使用临时账本的生命周期冒烟测试必须设置 `HEADROOM_DISABLE_DASHBOARD=1`。HTTP 测试使用临时回环端口，不占用实际面板端口。

GitHub Actions 会在每次推送和 PR 时运行这些检查，也支持手动触发。测试矩阵覆盖 Linux、Windows、macOS，使用 Python 3.10–3.13 和 Node.js 22。Windows 还会在 Python 3.13 上安装桌面依赖并重跑 Python 测试。原生托盘和 WebView2 冒烟测试仍需在本机显式启用。

</details>

## 贡献者

- [TOGET-H](https://github.com/TOGET-H)
- [cat0825](https://github.com/cat0825)
- [fuxiuht](https://github.com/fuxiuht)

欢迎参与贡献，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
