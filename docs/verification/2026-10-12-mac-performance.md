# 时钟页 Mac 性能卡片

用户确认监控设备当前连接的 Mac，通过时钟页左右滑动切换独立卡片。顺序：播客、时钟、Mac 性能、当前播放。已有卡片协议编号保留，监控页不会触发播放或音量控制。

Host 使用 psutil 7.2.2 读取 CPU、内存、数据卷剩余容量、物理 en* 网卡收发速率和磁盘读写速率。采样与发送分为两个线程，约每 2 秒采样；发送阻塞时仅保留最新样本。首次差分采样、计数重置、接口切换、长时间休眠和不可用指标显示未知，不伪装成零。设备收到数据后超过 10 秒未更新显示过期。

监控页使用帧差分更新变化区域，保留边缘电量。设置页的 Host 分区增加只读监控摘要。setup.sh 纳入新模块部署及依赖检测。无需额外服务器或远程采集配置。

## 验证记录

- 最新 Host 全套 534 项通过：/tmp/agenttouch-mac-perf-tests-final.log；标准 Host 379 项此前通过。新增采集测试覆盖首样本、有效差分及无效/重置情况。原生 C++ 卡片切换顺序测试通过。
- amoled216 构建通过：/tmp/agenttouch-mac-perf-build.log。USB 刷写及 hash 校验通过：/tmp/agenttouch-mac-perf-upload.log。
- 固件 SHA256：a89227f82962deda204b69f89dc7047a4dc90c72e905bec267f3f21177a7e840。归档于 ~/Documents/AgentTouch-backups/2026-10-12/mac-performance/firmware.bin。
- 服务已部署并重启；运行模块 SHA256 与源码一致：05d6ea2becd2c3100f00782869e30c825b23d85eb077dc2a05239bc7a788e199。
- /host/performance 连续 5 个样本 seq 9..13，间隔 2.072、2.033、2.074、2.063 秒，status=ok、stale=false。这是短时实测，不代表长期稳定性验收。
- 480×480 USB 截图 /tmp/agenttouch-mac-performance.png 已目视检查：所有指标、更新提示、滑动提示及电量显示完整。初次截图发生在页面切换到达前，显示时钟；随后重新捕获确认监控页。
- 监控开启期间板端音频测试 10 秒：257 帧、gaps=0、dropped=0、txerr=0；bad_lines 前后均为 0。mic gate=false，未调用 Codex 听写或发送消息。停止后 live=false。
- git diff --check 通过。构建目录约 1.1 GiB；工作树仍活跃且有未提交变更，留供实机验证，不执行清理。
- 独立复审无阻断问题：模拟阻塞首次发送约 4 秒，采样仍推进到第三个样本；解除阻塞后直接发送第三个样本，跳过积压样本。未修改实现。

待用户实测左右滑动及持续刷新；暂未做长时间休眠/重连的物理验收。设备测试视图锁已解除。

用户确认持续更新、左右切换正常；反馈 CPU 和内存进度条没有对齐。定位为 CPU x76/宽328、内存 x54/宽372。统一两条进度条为 x76/宽328，标签 x76、数值 x320，保留各自纵向位置。此修改仅涉及监控页布局，无 Host 或协议变更。

对齐版构建、USB 刷写及 hash 校验通过（/tmp/agenttouch-mac-perf-align.log）。480×480 实机截图 /tmp/agenttouch-mac-performance-align.png 已目视确认两条进度条左右端点、标签和百分比起点一致。布局微调未重复 Host 测试，沿用此前 534 项通过记录。测试视图已解除。
