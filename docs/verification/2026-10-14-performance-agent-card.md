# Mac 性能移入 Agent 切换序列

用户要求 Mac 性能成为 Agent 左右切换中的独立一项；时钟页恢复播客、时钟、当前播放，并刷入设备。

采用本地虚拟卡片，位于 Agent 序列末尾。沿用真实 Agent 的 selected 索引，使用独立布尔值保存性能卡选择，不扩大 AGENTS 或修改 Host 按索引下发的协议。离线 Agent 按现有配置跳过，性能卡始终可达；只有切回真实 Agent 时发送 select，不为性能卡打开 Mac 应用。

性能卡只处理左右滑动，阻止误触任务、宠物设置及语音键；保留电量与差分刷新。性能卡选中期间，进入时钟朝向仍显示原时钟序列；返回 Agent 朝向恢复性能项。调试 perf 视图改为 Agent 页；Host 设置提示同步调整。

验证：Agent/时钟导航原生 C++ 测试通过，覆盖双向循环、离线跳过、单个 Agent 在线及全部离线场景。最新 Host 534 项通过（/tmp/agenttouch-perf-agent-tests.log）。固件构建及实机结果待补充。

复审发现并修正同一 Agent 的 Host select 和新 needs_you 请求无法从性能卡返回的问题。复核通过；保留已有待确认请求不重复抢回的规则。最终 amoled216 构建通过（/tmp/agenttouch-perf-agent-build-final.log），固件保存于 ~/Documents/AgentTouch-backups/2026-10-14/performance-agent/firmware.bin。Host 设置提示已同步部署并重启。

设备暂未刷写：仅蓝牙可用，TCP boards=0，Mac 未发现 USB 串口。已请求用户连接 USB；待刷写、实机截图及 Agent/时钟左右滑动验收。工作树仍活跃，保留构建依赖供后续刷机。

随后 Host 重启恢复 TCP boards=1，转为无线更新；无需 USB。最终固件 SHA256：0f4a540725b7e7189e63b3966f06d0ad80b906c2bbc5904530c821581516148e，OTA 结果保存 /tmp/agenttouch-perf-agent-ota.json。

OTA 成功：2126624 字节，104276 ms，app1，Oct 14 2026 15:28:25，设备重连。无线截图 s=1 与 s=2 均 no answer in 30 s，未取得可供目视验收的新截图，不能称布局已实机验证。10 秒板端音频回归 269 帧、gaps=0、dropped=0、txerr=0，bad_lines 前后均 0；gate=false，未调用 Codex 听写/发送。停止后 live=false。测试视图已解除，并请求用户验证两组导航。
