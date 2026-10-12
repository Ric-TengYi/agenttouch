# 右上角常驻电量

用户要求页面实时显示当前电量，固定右上角。原固件仅低电量图标和设置卡可查看，dashboard独立局部刷新没有常驻电量。新增共用battery badge：电池图标及百分比，未知显示--，低电量颜色提示，充电绿色；使用默认ASCII字体，不依赖SD字体。

沿用AXP2101现有2秒电源采样，将有效0..100缓存；无电池/无PMU/无效数值为未知。替代渲染循环内逐帧I2C读取；安全关机规则保留。主页面、任务列表、对话/语音预览、额度、方向页均绘制；dashboard将百分比/充电状态纳入渲染key，变化时使用现有局部帧差分，不触碰TCP/BLE编码或音频链路。

徽标矩形x320..395、y69..87，位于R232内；标题末尾y67、正文首行起点y88，避免相互覆盖。独立复审发现播放页长标题会相撞，已将该标题块起点限制在y88或以下，最长94px仍在slider y196上方。复审确认无剩余阻塞问题。

验证：纯C++电量范围/圆屏边界测试通过，Host379通过 /tmp/agenttouch-battery-host.log；amoled216构建通过 /tmp/agenttouch-battery-build.log，diff检查通过。固件2119680字节，SHA256 eb12d3255151b9f482e0ed7434e30b3596b971ce9a053279cf4c9df39b20cfd1；旧固件备份 ~/Documents/AgentTouch-backups/2026-10-12/battery-status/fw.bin。无线OTA进行中，结果保存 /tmp/agenttouch-battery-ota.json。

待验证：实际电量截图、列表/详情页可见、电量与充电状态随硬件变化。active工作树的构建产物留供实机跟进，不执行清理。

无线OTA成功：app1、Oct 12 2026 09:38:29，total182168ms，结果 /tmp/agenttouch-battery-ota.json。重连BLE=true、boards=1。主页面截图 /Users/tengyi/.agentpet/shots/20261012-094425.png 已目视确认，右上角96%与充电绿色可读、不裁切、不覆盖任务数量。列表截图 /Users/tengyi/.agentpet/shots/20261012-094517.png 已目视检查，电量徽标保留，标题与任务卡片未碰撞；列表8行、full_frames1/partial_frames7，仍使用局部刷新。板端诊断仅打开列表后返回主页，未选择/打开任何Codex对话或发消息。

仍待实测：充放电过程数值和颜色变化、详情页及旋转页面的物理观察。代码已覆盖这些路径，不能将源码覆盖等同物理验收。

## 电量贴近右上边缘

用户反馈仍不在角落。移除原R232内缩位置，将徽标向右12px至x332..407，保持y69..87；百分比文字右对齐增加4px，实际字形最右端x407，位于物理R240内。图标坐标改为相对徽标位置，避免数字与图标不同步。边界/无效读数测试、Host379、固件构建和diff检查通过；不改变采样频率、手势及消息区域。

候选固件2119680字节，SHA256 e7c2cafde8f3a10d45c74019492e62b89233f30669c9412fae88db20e2aa2d8e。初次OTA未开始推送，原因no TCP board，仅蓝牙可用；WiFi扫描找到已知网络但未建立Mac TCP。用户随后告知已连接有线，确认USB为Espressif VID303a/PID1001、/dev/cu.usbmodem1401。PIO有线刷写成功，hash验证通过，日志 /tmp/agenttouch-battery-edge-usb.log；重启为app0、Oct12 2026 10:34:33，BLE及TCP恢复。

USB截图 /Users/tengyi/.agentpet/shots/20261012-104538.png 已目视检查：设备侧放时钟页，电量98%位于相应阅读方向的右上圆屏边缘，图标和百分比完整，无裁切。实际截图为旋转后的native framebuffer，不误认其角落方向。是否足够贴边的主观位置待用户确认。
