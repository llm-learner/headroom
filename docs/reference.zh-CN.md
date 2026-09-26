# 配置与实现

[English](reference.md) · **简体中文** · [返回 README](../README.zh-CN.md)

## 额度与用量

所有日期固定按 **Asia/Shanghai（UTC+8）** 划分，不跟随机器时区。额度基准取之前七个完整自然日，不含今天；逐天合计可读取适配器的消息数，最大值 × 2 为日限额。窗口为空时暂用两点。

今日用量与上述窗口分开。界面计算 `max(0, (额度 - 已用) / 额度 × 100)`，显示剩余百分比及已用 / 上限，归零不会阻止对话。

`HEADROOM_SPENT_SOURCE` 控制用量来源：

| 取值 | 行为 |
| --- | --- |
| `auto`（默认） | 按工具判断：今天评分扣点合计大于零时使用评分，否则按今日消息数 × 2 |
| `ledger` | 只使用评分扣点，没有扣点就显示 100% |
| `counts` | 始终使用今日消息数 × 2，忽略评分扣点 |

`auto` 中，同一工具的估算与评分互相替代，不叠加；不同工具可以使用不同来源。第一次评分可能替换此前的条数估算，所以百分比会回升。`counts` 下与历史峰值一样忙的一天会耗尽额度，但 0–10 的可变评分不一定如此。

当前实现把评分合计为零也当作 `auto` 的条数回退情况。如只想看真实评分，请用 `ledger`。

额度计数遵循各适配器的筛选规则。Codex 的用户消息记录可能包含自动任务；扣点资格是另一层检查，不会统一过滤所有额度基准。

## 配置选项

在启动 headroom 的进程里设置环境变量。钩子和显示可能有不同环境；在终端修改变量不会改变已运行的 Codex 或显示进程。

| 变量 | 作用 |
| --- | --- |
| `HEADROOM_SPENT_SOURCE` | `auto`、`ledger` 或 `counts` |
| `HEADROOM_BACKEND` | `mock` 或 `laya`，覆盖钩子的 `config.json` |
| `HEADROOM_STATE_PATH` | 共享账本路径 |
| `HEADROOM_AGENTS` | `auto` 或逗号分隔的适配器名 |
| `HEADROOM_AGENTS_CONFIG` | 自定义适配器文件，默认 `~/.headroom/agents.json` |
| `HEADROOM_AGENT` | 传给评分钩子的 agent 名称 |
| `HEADROOM_DISPLAY` | `desktop`、`web`、`both` 或 `off`，只影响显示启动 |
| `HEADROOM_DESKTOP_MODE` | `tray`（默认）或 `orb` |
| `HEADROOM_LANG` | `en` 或 `zh`，[各显示入口优先级](guide.zh-CN.md#网页面板与语言) |
| `HEADROOM_HOOK_STRICT` | `1` 拒绝缺少来源信息的消息，也可能漏掉普通聊天 |
| `HEADROOM_DEBUG_PATH` | 诊断路径，空字符串关闭诊断 |
| `HEADROOM_DISABLE_DASHBOARD` | `1` 在测试时阻止自动启动显示 |

钩子的后端文件是 `$CODEX_HOME/headroom/config.json`（默认 `~/.codex/headroom/config.json`），每轮重读。手动 CLI 评分使用显式 `--backend` 参数。

默认账本为 `~/.headroom/ledger.sqlite3`。如果该文件不存在而旧版 `$CODEX_HOME/headroom/ledger.sqlite3` 存在，则沿用旧账本。`HEADROOM_STATE_PATH` 覆盖两者。以写入方式打开旧账本时会原地迁移，将旧记录归到 `codex`。

## Agent 适配器

自动发现会检查本机历史是否存在。运行 `python skills/headroom/scripts/headroom.py agents` 查看适配器、可用性和近期计数。历史只读；SQL 适配器查询计数元数据，JSONL 适配器在本机解析记录，可能检查内容以区分用户请求与工具结果。

| 适配器 | 历史来源 |
| --- | --- |
| `codex` | `$CODEX_HOME/thread_history_1.sqlite` → `thread_items` |
| `claude` | `$CLAUDE_CONFIG_DIR/projects/*/*.jsonl`，回退到 `history.jsonl` |
| `opencode` | `$XDG_DATA_HOME/opencode/opencode.db` → `message` |
| `antigravity` | `$GEMINI_DIR/antigravity/brain/*/.system_generated/logs/transcript_full.jsonl` |
| `workbuddy` | `$WORKBUDDY_HOME/projects/*/*.jsonl` |

Claude 筛选接受字符串 / text 类型的用户内容，排除 `system` / `sdk` 来源及 sidechain。记录条数不一定等于人类对话轮数。

随附安装器只配置 Codex。其他工具需手工把其提示词钩子接到 `headroom_hook.py --user-prompt`，提供对应载荷并设置 `HEADROOM_AGENT`。钩子支持 `prompt` / `user_prompt`、`session_id` / `sessionId`、`turn_id` / `promptId`、`permission_mode` / `permissionMode` 等别名。载荷兼容不代表每个工具的钩子生命周期都已自动配置或验证。

在 `$HEADROOM_AGENTS_CONFIG` 中声明额外 JSONL 或 SQLite 适配器：

```json
{"agents": [
  {"name": "aider", "label": "Aider", "kind": "jsonl", "root": "~/.aider",
   "glob": "**/*.history", "where": {"role": "user"},
   "day_field": "timestamp", "day_format": "ms"}
]}
```

这是配置格式示例，不是已验证的 Aider 集成。`day_format` 支持 `ms`、`iso` 和 `epoch`；同名声明会替换内置适配器。CLI 的 `--agents` 和可重复 `--agent-home NAME=PATH` 选择工具 / 路径，`--codex-home` 覆盖 Codex 根目录。

## 评分与轮次标识

Mock 根据当前提示词生成确定性假分数，不做模型推理。Laya 估算当前请求需要的思考，不会给助手整段回复评分。两者都只是娱乐，不是认知测量。

Laya 接收发往 `POST http://127.0.0.1:8765/predict` 的 UTF-8 JSON，其中 `state.body` 是请求正文，`questions.brain_load` 是评分问题，含说明及对应 0–10 的十一档标准。返回格式：

```json
{"answers": {"brain_load": {"type": "score", "score": 4.2}}}
```

分数必须是 0–10 的有限数值，不能是布尔值。客户端绕过 HTTP / 系统代理，超时为十五秒；失败跳过扣点，不会偷偷切回 Mock。

钩子拒绝已知非交互来源及 plan 模式事件。手动评分要求确认人类来源和 normal 模式。为兼容正常聊天，默认接受缺少来源信息的载荷；严格模式也可能漏掉正常消息。Goal / 自动任务 / 子代理筛选不是审计级保证。

显式轮次 ID 可以对重复投递去重。没有轮次 ID 时，账本分配持久的会话内序号，支持同会话的不同消息，但不能证明两次无 ID 的投递属于同一轮。存在但为空的轮次 ID 会被拒绝。不要换一个事件 ID 手动给已由钩子处理的消息评分。

## 数据处理

| 数据 | headroom 的存储或处理方式 |
| --- | --- |
| 历史 | 在本机读取 / 解析用于计数；JSONL 筛选可能检查内容，不上传、不复制进账本 |
| 当前提示词 | 在内存中交给 Mock 或本地 Laya 服务 |
| 账本 | 不透明事件 ID、日期、分数、provider、agent 名及不透明会话序号记录，不含提示词正文 |
| `last-hook.json` | 最近结果 / 时间、输入存在性 / 长度、agent 和评分元数据，不含提示词或原始 session / turn ID |
| 桌面偏好 | `desktop.json` 中的位置、语言和静音 |
| 界面 | 本地打包素材及仅回环监听的服务，没有 CDN、统计脚本或云端评分 |

适配器跳过足够旧的文件以减少刷新开销。界面 / API 输出包含适配器名及来源元数据，不要把运行状态或诊断文件当成文档示例公开。

这些保证针对自带的 headroom 代码，不代表 AI 工具或另行部署的模型服务；请另行配置服务的日志和网络。未来接云端 Jev 需要显式启用，并更新数据外发说明。

测试和 CI 覆盖详见 [CONTRIBUTING.md](../CONTRIBUTING.md#运行测试)。
