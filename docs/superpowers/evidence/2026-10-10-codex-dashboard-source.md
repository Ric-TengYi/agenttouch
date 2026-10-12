# Codex 看板接入验证记录

日期：2026-10-10。结论：Task 1 接入关卡未通过；不是完整功能验收。

## 环境和基线

- 仓库开发分支：`codex/agent-dashboard`，基线 `a81a1eb`。
- 桌面应用：26.1007.21159，build 20052。
- CLI：0.162.0-alpha.17.2；既有 daemon：0.162.1。
- 独立 worktree 建立后，现有 host 378 项测试通过。
- 未安装新依赖；未更新已安装 host、配置或板子固件；未发送任务消息或恢复任务。
- 用户明确允许自行打开已有远程和云端任务，已执行导航用于验证。导航由 Codex 决定阅读状态；probe 不写回未读文件。

## 已验证入口

### 七日额度与已有 daemon

既有 `~/.codex/app-server-control/app-server-control.sock` 接受 Unix socket 上的 WebSocket `/rpc` 握手。`codex app-server proxy` 转发原始字节，不是直接接受 JSON 行的 stdio RPC；直接发 JSON 行超时后已关闭该临时代理，没有启动或重启 daemon。

WebSocket initialize、`account/rateLimits/read`、`thread/loaded/list` 和分页 `thread/list` 成功。最新 probe 七日窗口 10080 分钟、剩余 33%；quota 返回的账号 ID 与本地缓存的账号一致，只记录比对布尔值。

daemon 已加载数为 0，完整分页返回 119 条非归档记录。同期桌面 IPC 能返回正在运行的本机会话；因此不能把 daemon 的“0”当成桌面运行总数。

### 原生未读

桌面代码使用 `electron-thread-read-state-v1`，按身份哈希和执行主机键隔离集合。环境缓存中的账号/用户组合哈希与保存的原生集合匹配，且已核对一条实际未读会话。

这证明保存格式可读，不等于已经实现可靠的当前登录身份变化监听或完整侧栏过滤。目录仍需排除旧主机、归档、删除和子代理；不能直接用集合长度显示精确总数。

### 桌面实际 IPC

`~/.codex/ipc/ipc.sock` 使用四字节 little-endian 长度前缀 JSON。只读观察通过 initialize 和 `thread-stream-following-changed`（版本 1，订阅）获得 `thread-stream-state-changed`（版本 11）快照。

单会话 probe 成功取得本机 `threadRuntimeStatus={type:active,activeFlags:[]}` 和原生 hasUnreadTurn；另一个本机运行会话也能取得该状态。订阅仅建立观察关系，断开关闭观察客户端，不发送 start/resume/approval/read-state 更改。

但该入口传输完整会话快照，包含无关正文。对缓存目录批量订阅时出现超过 16 MiB 的帧；随后观察窗口内超时。诊断程序改为每主机最多两条近期样本，并跳过过大帧，避免保留无界内容；后续 5 秒窗口仍未证明稳定取得远程或云端状态。

最新缓存有 248 条候选记录（过滤 missing_candidate、排除普通 ChatGPT 记录、加入两条 durable 云端引用）。这是缓存数量，不能证明实时完整目录；旧 sync complete 标记和本机 daemon 的分页都不能补足全部当前远程/云端覆盖。

## 关卡结论与后续选择

- 本机运行状态：一次性只读快照可获取，持续稳定性仍需实现验证。
- 七日额度：只读查询已验证。
- 原生未读：保存集合及账号映射可读，完整过滤及账号切换监听未完成。
- 远程/云端：打开已有任务后，当前环境未取得可用于完整统计的稳定快照。超时不能被解释为任务零，也不能据此断言这些来源永远不支持。
- 完整目录与任务转换：未通过全来源验收。

按已确认计划 Task 1 Step 6，Task 2–7 尚未执行。继续保持完整范围，需要优先建立或验证轻量、持续的桌面摘要入口（当前内部 IPC 不提供已验证的精确跨主机总数）。

可供用户选择的范围调整是先实现已验证来源，远程/云端未知部分明确显示“部分状态不可用”或 `--`；原生未读仍须完成账号及目录过滤，才允许显示精确值。此调整不能自行当成完整范围已完成。

## 可复现命令与软件检查

`/usr/bin/python3 host/probe_codex_dashboard.py` 输出去敏覆盖信息；这是诊断程序，不是已部署适配器。它不会因读取缓存成功把 gate 标成通过。

`/usr/bin/python3 -m unittest discover -s host -p 'test*.py'`：387 项通过（现有 378 + probe 9）。独立审阅提出的账号字段都缺失却判为匹配、必需 data 缺失却判为零，已各用失败测试复现并修正；完整 probe 输出去敏另有离线 fixture 测试。原有新测试已观察 RED→GREEN，包括未知来源不能算精确零、等待状态、七日窗口选择和大帧跳过后保持 framing。

审阅保留一项 Minor：诊断对任意非空 activeFlags 暂按等待处理；当前只有已验证等待 flag 的 fixture，生产适配器不得沿用这个宽泛判断，需确认完整状态 schema。它不影响本次“全来源未通过”的关卡结论。

Build: NOT RUN（未修改固件）
Host tests: PASS（387 项）
Device tests: NOT RUN（未部署变更）
Unverified: 完整远程/云端实时状态、账号切换、全目录过滤与事件转换、设备 UI 和传输验收。
