# Agent Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AgentTouch 上显示 Codex / Claude 七日剩余额度，并显示包含本机、远程和云端的 Codex 运行数及原生未读数。

**Architecture:** Mac host 使用独立适配器采集，聚合模块建立账号隔离的快照，设备通过现有 JSON 行链路显示摘要及分页列表。先验证独立 host 接入 Codex 桌面真实跨主机状态的可行性；接入验证失败时停止依赖它的开发，提交实测证据与替代接入方案。

**Tech Stack:** Python 3.9 兼容代码与标准库 unittest；现有 macOS host / Claude statusline；Arduino C++、ArduinoJson、PlatformIO `amoled216`。复用已有依赖，不新增在线第三方统计服务。

**Spec:** `docs/superpowers/specs/2026-10-10-agent-dashboard-design.md`

## Global Constraints

- Codex 待阅读严格跟随桌面应用原生未读状态。
- Codex 统计当前登录账号在侧栏中的本机、远程、云端主会话；排除归档、删除记录和子代理。
- 按账号、执行主机、会话 ID 去重；未读与运行状态是两个独立维度。
- Claude Code 提供七日额度和运行中的主会话数量；本次不实现 Claude 待阅读，显示 `--`。
- 额度每 5 分钟查询；缺少任务通知时每 5 秒只读刷新。
- 任务快照超过 30 秒、额度超过 15 分钟未成功刷新标为过期。
- 每页最多 4 行；协议版本 1；未知计数用 null，确认为零才用 0。
- 不修改 Codex 应用包、不写回 Codex 状态、不在日志复制凭据；不启动或恢复任务来采集状态。
- 六套皮肤覆盖；现有批准、听写、认领、多会话条及横放页面保留。
- 本计划批准后在独立 worktree 开发；先检查已有附件，合适则复用。上线前保留现有 host、配置及固件回退产物。

## Review Focus

- 切账号时旧请求晚到：旧账号响应必须丢弃，旧句柄失效（Task 3）。
- 原生文件在读取时截断或换版本：不把读取失败转为未读零（Task 2）。
- 远程断开但有旧状态：只能显示下界或过期，不能冒充全量实时值（Task 3）。
- BLE 上长中文标题与分页响应乱序：字节上限内 UTF-8 完整，generation / request_id 不匹配时丢弃（Task 4）。
- 用户已有复杂 statusLine 命令：重复安装保持输出、stdin 和退出语义；不能解析时保留配置并报告不可用（Task 5）。

## 文件与接口约定

创建 `host/codex_dashboard.py`（Codex 接入）、`host/claude_dashboard.py`（额度与 session 规范化）、`host/dashboard.py`（聚合）、`host/dashboard_protocol.py`（编码和分页）；对应测试为 `host/test_dashboard_adapters.py`、`host/test_dashboard.py`、`host/test_dashboard_protocol.py`。

创建 `host/claude_statusline.py` 与 `host/test_claude_statusline.py`；修改 `host/setup.sh` 部署和链接现有配置，修改 `host/agentpet_host.py` 的调度、board 消息处理、hello 重发和设置页诊断。

创建 `firmware/src/dashboard.h` / `dashboard.cpp`，承担设备快照、任务页状态及绘制；修改 `main.cpp` 消息和触摸路由、`face.h` / `face.cpp` 顶部摘要覆盖。不重构其他页面。

host 各模块使用标准库 dataclass 和 dict，接口类型在 `dashboard.py` 定义：

- `TaskRecord(identity_key, host_key, thread_id, title, host_label, state, unread, archived, is_subagent, observed_at)`；state 为 running / waiting / idle / unknown，unread 为 bool 或 None。
- `SourceSnapshot(identity_key, tasks, hosts_total, hosts_available, catalog_complete, statuses_complete, unread_complete, observed_at, error_code)`；只有当前账号的 TaskRecord 可以进入该快照。
- `QuotaRecord(remaining_pct, reset_at, observed_at, quality)`；quality 为 ok / partial / stale / unavailable，remaining_pct 为 float 或 None。
- `DashboardSnapshot(agent, identity_key, generation, observed_at, quota, running, unread, waiting, coverage, tasks)`；计数为 `dict(value, quality)`，coverage 为 `dict(total, available, quality)`。
- `CodexDashboardSource.read_snapshot(now: float) -> SourceSnapshot`、`.read_quota(now: float) -> QuotaRecord`；网络失败有截止时间，不阻塞 host 主锁。
- `normalize_claude_sessions(sessions: dict, now: float) -> SourceSnapshot`、`parse_claude_quota(payload: dict, now: float) -> QuotaRecord`。
- `DashboardStore.update(agent: str, source: SourceSnapshot, quota: QuotaRecord, now: float) -> DashboardSnapshot`、`.get(agent: str, now: float) -> DashboardSnapshot`、`.clear(agent: str) -> None`。
- `encode_dashboard(snapshot: DashboardSnapshot) -> bytes`、`encode_task_page(snapshot: DashboardSnapshot, filter_name: str, cursor: Optional[str], request_id: str) -> bytes`、`encode_task_detail(snapshot: DashboardSnapshot, handle: str, request_id: str) -> List[bytes]`；typing 类型使用标准库以兼容 3.9。

## Task 1: 独立 host 跨主机接入验证

**Files:** Create `host/probe_codex_dashboard.py`、`docs/superpowers/evidence/2026-10-10-codex-dashboard-source.md`。

**Interfaces:** Produces 支持版本、身份选择、完整目录分页、真实运行状态、额度请求和通知的已验证入口；该结果决定 Task 2 的传输实现，不预设私有 IPC 地址。

- [x] Step 1：执行时创建/复用独立 worktree，读取 spec 和适用 AGENTS.md；记录基线 commit、桌面版本和来源覆盖，不打印认证数据。
- [x] Step 2：检查本机安装代码、可用 app-server schema 与桌面只读连接入口，区分新进程状态和已有桌面状态，记录支持的查询及认证方式。
- [x] Step 3：写只读 probe，设置单次请求 5 秒截止时间；输出版本、目录数量、状态计数、来源覆盖和能力错误码，不输出对话正文或凭据。
- [ ] Step 4：通过后台可持续调用的入口取得全部分页目录与运行状态；与桌面快照逐项核对本机、远程、云端，至少覆盖一次运行→等待/完成转换，记录实测或缺少样本。
- [ ] Step 5：验证原生未读的当前身份和执行主机映射，以及七日窗口读取。确认 probe 不更改任务、原生文件和应用包。
- [x] Step 6：形成 pass / blocked 证据。无法取得跨主机真实状态时停止 Task 2–7，报告替代桥接方案；缺少云端/远程样本时不得把该来源标为验收通过。
- [ ] Step 7：通过后提交 probe 与去敏证据：`git commit -m "docs: verify Codex dashboard data sources"`。

## Task 2: 可测试的数据适配器

**Files:** Create `host/dashboard.py` 类型定义、`host/codex_dashboard.py`、`host/claude_dashboard.py`、`host/test_dashboard_adapters.py`。

**Interfaces:** Consumes Task 1 实测入口；Produces 文件与接口约定中的类型、CodexDashboardSource、normalize_claude_sessions、parse_claude_quota。

- [ ] Step 1：写失败测试：`test_native_unread_identity_and_catalog_intersection` 断言旧账号/已删除/归档/子代理不进入未读；`test_full_catalog_pagination` 断言第 51 个及后续页记录被纳入；`test_duplicate_cloud_projection` 断言同一执行会话只出现一次。
- [ ] Step 2：写失败测试：`test_unread_truncated_or_unknown_version` 断言失败为 unread_complete=False 而非空集成功；`test_status_not_loaded_is_unknown` 断言未加载不当 idle；`test_quota_window_duration` 断言任一槽位的 10080 分钟窗口被选中，66% 已用得到 34%，缺失为 None，越界夹到 0–100。
- [ ] Step 3：运行 ` /usr/bin/python3 -m unittest discover -s host -p test_dashboard_adapters.py -v`，确认失败来自缺失实现；实现类型与依赖注入适配器，只读文件异常最多重试两次，解析失败保留错误质量。
- [ ] Step 4：实现 Claude session 规范化与官方 seven_day 解析；测试五小时字段不替代七日额度、未读始终未知、子 session 不重复计数。
- [ ] Step 5：重跑相同命令通过，再提交：`git commit -m "feat: add dashboard source adapters"`。

## Task 3: 聚合、完整性与时效

**Files:** Modify `host/dashboard.py`；Create `host/test_dashboard.py`。

**Interfaces:** Consumes Task 2 SourceSnapshot / QuotaRecord；Produces DashboardStore.update / get / clear 和 generation 递增快照。

- [ ] Step 1：写失败测试 `test_running_waiting_unread_are_independent`：两个 running、一个 waiting、三个 unread 得到 2/1/3；未读可与 running 重叠。
- [ ] Step 2：写失败测试 `test_partial_hosts_lower_bound`：2/3 主机可用的已知运行数 2，quality=partial；全部不可用值=None；目录和原生集合完整时 unread 仍可为 ok。
- [ ] Step 3：写失败测试 `test_age_thresholds`：任务 30 秒与额度 900 秒内有效，超过阈值 stale；`test_account_switch_rejects_late_response` 断言账号切换后晚到旧结果不会替换新账号；`test_complete_zero_only` 断言完整空目录才得到 ok 的零。
- [ ] Step 4：运行 `/usr/bin/python3 -m unittest discover -s host -p test_dashboard.py -v` 确认失败；实现 Store、身份 epoch、单调 generation、只读质量计算，保留最后成功时间。
- [ ] Step 5：相同命令通过，提交：`git commit -m "feat: aggregate dashboard counts and freshness"`。

## Task 4: 摘要与分页协议

**Files:** Create `host/dashboard_protocol.py`、`host/test_dashboard_protocol.py`；Modify `doc/05-architecture.md`、`doc/05-architecture.zh-CN.md`。

**Interfaces:** Consumes DashboardSnapshot；Produces encode_dashboard / encode_task_page / encode_task_detail，以及 `tasks_open` 句柄验证，协议 schema 由这两份文档固定。

- [ ] Step 1：写失败测试 `test_summary_schema_v1_and_unknowns`，断言 t=dashboard、v=1、null 与零区分、generation 及各指标 quality；身份哈希及凭据不进入板端消息。
- [ ] Step 2：写失败测试 `test_page_utf8_byte_limit`，长中文标题下每行含换行不超过 4000 字节（现有 BLE/TCP/USB 上限均为 4096），每页最多 4 行；截断后仍可 UTF-8 解码，next_cursor 能遍历全部记录。
- [ ] Step 3：写失败测试 `test_cursor_generation_filter_binding` 和 `test_handle_invalid_after_account_switch`，断言旧页/错筛选 cursor/旧账号句柄被拒绝，列表请求不会写原生已读。
- [ ] Step 4：运行 `/usr/bin/python3 -m unittest discover -s host -p test_dashboard_protocol.py -v` 确认失败；实现长度预算、分页 cursor、request_id 和只映射当前快照的短句柄。`task_detail` 请求的响应包含 handle、generation、request_id、part、parts、title_chunk；每个 UTF-8 分段在 4000 字节行预算内，完整标题逐段浏览，不在板端拼接无界字符串；仅桌面打开事件导航会话。
- [ ] Step 5：相同命令通过；在架构文档写双向 JSON 示例与版本、未知、分页语义；提交：`git commit -m "feat: add dashboard summary and task paging protocol"`。

## Task 5: host 调度与兼容安装

**Files:** Modify `host/agentpet_host.py:2968`（board 消息）、`:4173` 附近（独立推送）、主循环及设置页；Modify `host/setup.sh:122`；Create `host/claude_statusline.py`、`host/test_claude_statusline.py`；Extend `host/test_dashboard.py` 集成测试。

**Interfaces:** Consumes Tasks 2–4；Produces `/dashboard` 本机诊断、board dashboard / tasks / tasks_open 路由及 quota statusline 输入。tasks_open 使用 Task 1 已验证桌面导航方式。

- [ ] Step 1：写失败测试 `test_scheduler_intervals_and_no_global_lock_io`：额度 300 秒、无通知状态 5 秒刷新，5 秒查询超时独立失败，期间 key/voice 路由能继续处理；`test_reconnect_full_snapshot` 断言 hello 后重新发摘要且不复用旧页。
- [ ] Step 2：写失败测试 `test_statusline_chaining_and_repeat_install`：相同 JSON stdin 交给原命令，stdout/stderr/退出码保留；重复安装不套娃；无 statusLine 可创建包装器，不支持的配置保持原样并诊断不可用。所有安装测试在临时 HOME / fixture 中运行。
- [ ] Step 3：运行 ` /usr/bin/python3 -m unittest discover -s host -p 'test_dashboard*.py' -v` 与 `/usr/bin/python3 -m unittest discover -s host -p test_claude_statusline.py -v` 确认失败；实现独立调度、快照锁、白名单导航和已有 push_raw 发送路径。HTTP 接口只绑定现有 localhost 服务，statusline 采集失败不影响原输出。
- [ ] Step 4：安装复制名单加入新增模块及包装器；备份原 statusLine，拒绝覆盖无法安全串接的格式，设置页报告原因；保留既有 hooks / notify 链。运行 `bash -n host/setup.sh` 通过。
- [ ] Step 5：重跑新增测试及 `/usr/bin/python3 host/test_host.py -v` 全部通过，提交：`git commit -m "feat: integrate dashboard host and quota collection"`。

## Task 6: 固件看板与任务页

**Files:** Create `firmware/src/dashboard.h` / `dashboard.cpp`；Modify `firmware/src/main.cpp:1563` 及帧构造/触摸、`face.h` / `face.cpp`；Extend `host/test_dashboard_protocol.py` 固件用协议 fixtures。

**Interfaces:** Consumes v1 协议；Produces `dashboardHandle(const JsonDocument&, uint32_t nowMs)`、`dashboardClear()`、`dashboardDrawSummary(Arduino_Canvas*, uint8_t agent, uint32_t nowMs)`、`dashboardDrawPage(Arduino_Canvas*, uint32_t nowMs)`、`dashboardTap(int x,int y)`（返回是否消费触摸），重用既有发送入口而非新建连接。

- [ ] Step 1：增加协议 fixture：新旧 host/firmware、未知版本、错 request_id、错 generation、未知值、部分覆盖、长标题、多页、离线重连；先记录当前固件不识别 dashboard 的预期失败。
- [ ] Step 2：实现受限快照与四行页缓存；请求匹配当前 agent、generation、request_id 后才更新页面；设备离线立即灰化，首次未收到摘要隐藏看板。
- [ ] Step 3：实现左上圆环与 7日/百分比，低于 20% 橙、低于 10% 红；右上运行/未读及 ≥ / --。点击额度显示重置/更新时间，点击数量进入对应筛选列表，行详情提供标题及 Codex 打开按钮。
- [ ] Step 4：优先路由批准/认领/麦克风等浮层；为 Claude 会话条预留不同区域，只有 Claude / Codex 脸页画看板；任务页有明确返回。新增模块绘制所有皮肤共用覆盖层。
- [ ] Step 5：在 worktree 的 firmware 目录运行 `/Users/tengyi/uniubi/work/IdeaProjects/agenttouch/.tools-venv/bin/pio run -e amoled216 -j2`，要求 SUCCESS；通过模拟推送与截图检验全部 fixture，修正协议/显示后重新构建必要部分。
- [ ] Step 6：提交：`git commit -m "feat: display quota and task dashboard on device"`。

## Task 7: 安装、真实设备验收与交付

**Files:** Modify `doc/03-usage.md`、`doc/03-usage.zh-CN.md`；Create `docs/superpowers/evidence/2026-10-10-agent-dashboard-acceptance.md`。

**Interfaces:** Consumes 通过测试的 host 与固件；Produces 带 hash 的构建/回退产物、逐来源验收结果和部署版本。

- [ ] Step 1：运行 Tasks 2–5 的测试及 host 现有套件一次，检查 `git diff --check`；确认 build SUCCESS，保存固件 hash 和日志至 worktree 外交付目录。
- [ ] Step 2：备份已安装 `~/.agentpet` 相关程序和 Claude statusLine 配置，保存当前可回退固件；确认 USB 是此前 ESP32-S3-Touch-AMOLED-2.16，再更新 host 和固件。刷写中止时保留产物并恢复可运行版本。
- [ ] Step 3：真实设备比对 Codex 七日额度、本机/远程/云端 running/waiting 和原生未读。需要用户提供的运行或未读样本通过简短提示协调；不擅自启动任务或改变原生已读状态制造样本。
- [ ] Step 4：验证用户原生阅读/标记未读后的数量变化，设备只开列表不标已读，打开按钮导航正确主机；按来源记录通过、失败或缺少样本，不以模拟测试替代真实覆盖。
- [ ] Step 5：验证远程断连、Mac 睡眠/恢复、设备重连、六皮肤、Claude 多会话、批准与听写和横放页面；截图覆盖正常、部分可用、未知及任务分页。
- [ ] Step 6：更新实际使用文档及验收证据；提交交付文档。停止开发/build 进程，确认专用 worktree 后先 dry-run `codex-task-cleanup <worktree>`，再执行 `codex-task-cleanup --execute <worktree>`；如果后续设备验证仍依赖构建环境则保留并报告大小。只有确实填充全局缓存或磁盘压力时考虑 --global-caches。

## 执行与审阅

推荐 Native：在本会话逐项实施，先完成 Task 1 关卡，再顺序推进；最后安排一次独立整分支审阅。这里的 Native 是计划的执行方式，代码执行本身仍使用 `superpowers:executing-plans`。也可选择 Subagent-driven，以每项实现和审阅分别交接；需要用户明确选择后才开始。

执行方式已选 Native。2026-10-10 已建立实施 worktree，Task 1 probe 已运行，接入关卡仍阻塞；证据见 `docs/superpowers/evidence/2026-10-10-codex-dashboard-source.md`。Task 2–7 未开始。阶段完成只更新对应 checkbox，跨主机入口阻塞时不把后续功能写成已完成。
