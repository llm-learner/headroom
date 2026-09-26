# 常见问题与排障

[English](faq.md) · **简体中文** · [返回 README](../README.zh-CN.md)

## 百分比不动

1. 确认显示正在运行，尝试刷新。默认每十秒刷新一次。
2. 如需评分扣点，检查 Codex `/hooks` 中两条 headroom 钩子是否启用并受信任。首次安装后新建一次会话即可，后续消息不需要反复新建。
3. 使用 Laya 时检查另行部署的服务；设置 `backend: laya` 不会启动它。
4. 查看账本旁的 `last-hook.json`，其中只记录最近结果，不含提示词正文。

`HEADROOM_SPENT_SOURCE=ledger` 时，没有评分就显示 100%。默认 `auto` 对评分合计未大于零的工具按消息条数估算。显示有消耗不代表钩子已成功评分。

## 为什么会按固定两点计算？

这是今日条数的估算，不是模型分数。`auto` 按工具使用大于零的评分合计，否则使用消息数 × 2；`counts` 始终估算，`ledger` 不估算。[计算说明](reference.zh-CN.md#额度与用量)

实际评分替换更大的估算值时，百分比可能回升；UTC+8 日期切换时，滚动额度也可能变化。它不是固定的一百点账户。

## 每个工具都会自动评分吗？

随附安装器只配置 Codex。其他支持的工具默认提供历史条数估算，除非另行配置评分钩子。自动任务排除尽力而为，默认接受缺少来源信息的载荷；严格模式也可能漏掉普通对话。

## 为什么查询余额也扣点？

打开界面、刷新、切语言或执行 `status` CLI 都不评分。但在聊天里问余额仍是用户消息，钩子可能正常扣点。不要手动对钩子已处理的消息执行 `turn`，不同事件 ID 可能造成重复扣点。

## 找不到托盘或卡片

- 在 Windows 隐藏图标箭头里找 H。
- 先退出已有显示，再加 `--show` 启动，直接展开卡片。
- 用 `python` 替换 `pythonw` 查看报错，检查 Tk 和 `requirements-desktop.txt` 依赖。
- 没有 Edge WebView2 时试 `--renderer tk`。macOS 缺 Tk / 托盘包时回退网页。
- 同一账本的重复显示可能被单实例锁阻止。

## 钩子文件解析或安装失败

确认 `hooks.json` 是有效 JSON，保存为无 BOM 的 UTF-8。Windows 安装器不会合并已有文件，请保留其他钩子并按[合并说明](guide.zh-CN.md#windows-钩子)操作，不要强制覆盖。

PowerShell 中被引号包围的 Python 可执行文件需要 `&`。保持源目录和 Python 路径有效，修改命令后重新信任。钩子支持 UTF-8 中文和 emoji，也兼容 GBK Windows 系统。

## 怎么停止或卸载？

退出托盘只关闭显示。要停止自动评分，在 Codex 禁用 / 移除 headroom 钩子。macOS / Linux 可用 `sh skills/headroom/hooks/install.sh --uninstall`，仅移除 headroom 钩子并保留数据。

Windows 只删除 headroom 的命令项，即便同一个钩子组里有其他命令也要保留。除非明确想重置历史，否则不要删除账本。

## 报告问题

提供系统 / Python 版本、显示模式、后端、预期和实际行为，以及脱敏后的诊断结果。不要附历史数据库、真实提示词、凭据或账本。详见 [CONTRIBUTING.md](../CONTRIBUTING.md#参与贡献)。
