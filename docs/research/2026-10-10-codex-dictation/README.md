# Codex 原生听写与设备麦克风可行性核查

核查日期：2026-10-10。已安装桌面版本 26.1007.21159 / build 20052；内置 CLI 0.162.0-alpha.17.2。

## 结论

已确认 Codex 桌面自身有录音上传转写和 PCM 流式听写实现。设备音频可在 Host 解码后直接交给识别服务，从架构上不需要 BlackHole、Fn 按键或 macOS 系统听写。但当前外部 Host 的两个直连探针均返回 403，尚未取得任何识别文本，不能称为可用方案。

## 本机代码证据

只读检查 /Applications/ChatGPT.app/Contents/Resources/app.asar，未修改应用。

- app-initial-c468e3fd7f91.js：录音以 multipart file 和 language 字段 POST 到 /transcribe；返回结果包含 text。流式启动指定 pcm16、单声道、采样率，使用 session.start / audio.append / session.close，接收 transcript 系列事件。
- main-39FdJ_vp.js：原生 dictationStreaming 服务使用 /dictation/stream WebSocket，管理应用认证和网络路由。它属于桌面内部服务；此次未找到供第三方 Host 调用的独立听写 Unix IPC 方法。
- Host agentpet_host.py：IMA_RATE=16000，设备音频解码为 16 kHz 单声道 PCM16，可直接组装 WAV 或流式音频。当前失败点不是必须使用虚拟声卡才能取得设备音频。

提取文件 SHA-256：

- main-39FdJ_vp.js：78ffc19681d7605d0b48c8cbfdc185211a58d218c4512647de567519dd5ca3bc
- app-initial-c468e3fd7f91.js：efd785d44bc6f07771f3d5a21cf255112d0f17969b398889e6a8a4868338152f

## 直连实验

仅生成一句中文合成测试语音，WAV 为 16 kHz / 单声道 / PCM16，约 4.55 秒。没有上传用户历史录音，没有向任何对话发送指令。

1. https://chatgpt.com/backend-api/transcribe：使用现有 ChatGPT 登录认证，POST 合成 WAV，返回 HTTP 403、HTML，未返回 JSON 文本。见 probe-result.json。
2. wss://chatgpt.com/backend-api/dictation/stream?dictation_surface=composer：握手返回 HTTP 403，cf-mitigated 标头为 challenge；未建立连接，未发送音频。见 stream-result.json。

流式错误明确属于网络验证；批量接口只能确认 403，不能据此断言同一原因，也不能据此断言账号没有听写权限。没有伪装桌面身份、提取浏览器 cookie 或绕过网络验证。没有操作 Codex 界面或启用系统听写。

## 对外协议与边界

对已安装 CLI 执行只读 app-server generate-json-schema --experimental。ClientRequest 的相关方法仅有 thread/realtime/start、appendAudio、appendText、appendSpeech、stop、listVoices，未发现独立 dictation/transcribe 方法。

官方源码：https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/realtime.rs

thread/realtime 是实验性的对话语音会话，绑定 threadId，并具有 Codex 响应/委派语义；不能直接当成只转写、不执行的预览接口。本次没有对用户对话启动 realtime 会话。

## 建议的接入结构

设备麦克风 → TCP/BLE → Host 解码 PCM16 → 听写服务 → Mac 可编辑预览 → 用户点击发送 → 按所选对话 ID 下发。

如能获得允许外部调用的 Codex 听写入口，这条链可以移除 BlackHole 与系统听写。需要保留账号/对话绑定、取消、录音时长限制、失败明确提示，以及发送前确认；听写结果不得自动下发。当前剩余阻塞是可用、获支持的认证/网络入口，设备真实语音识别与端到端发送尚未验证。

## 当前运行状态

研究没有部署新 Host 或固件。此前返回按钮、重命名标题已获用户实机确认；预览无文字仍未解决。此前完整 Host 套件 440 项通过，后续未部署的语音快捷键兼容改动测试为 443 项通过，这些测试不能证明原生听写可用。


## 第二轮核查：原生成功、外部请求被拦截

用户亲自验证：Codex 自己的输入框听写可以正常显示文字（未要求发送）。这证明本机原生听写可用，但不能证明 AgentTouch 的外部请求拥有相同网络上下文。

再次使用合成 WAV 进行同一录音上传探针，未伪装原生客户端身份：HTTP 403，`cf-mitigated: challenge`，服务响应为 Cloudflare HTML；现有 token 的 exp 未过期。见 probe-result-followup.json。这补足了第一轮批量接口缺少错误类型的证据。两个外部路径均遇到网络验证；没有证据支持通过修改录音编码、重新启用系统听写或更换 BlackHole 就能消除 403。

本机检查：HTTP/HTTPS/SOCKS/自动代理配置均未启用；进程没有相应代理环境变量；Codex 配置未发现 chatgpt_base_url/base_url 等覆盖项。这不排除其他网络扩展、VPN 或桌面应用内部网络策略差异。最近 8 个桌面日志没有相关转写失败记录，不能从日志定位原生成功请求的实际路径。

### CLI 是否有替代路径

官方合并 PR #3381 的 voice.rs 实现：ChatGPT 登录时调用同一 /transcribe；API key 模式调用 https://api.openai.com/v1/audio/transcriptions。它是 TUI 内部转写函数，不是现有 app-server 可直接请求的独立方法；封装同一 ChatGPT 请求没有消除网络验证的保证。此证据来自历史合并源码，不用于声称当前 CLI 仍完整保留该模块。

来源：https://github.com/openai/codex/pull/3381

原生服务进一步确认：dictationStreaming.connect 接收 composer/global 场景与 RPC 回调，并由桌面应用自己的 backend auth 和网络层管理。服务通过 WindowContext 暴露给桌面视图。当前已检查的 thread-follower IPC 方法和 app-server schema 没有独立转写接口；不能把内部视图服务地址当成外部 HTTP API。没有尝试注入视图、修改应用、通过被禁止的 UI 通道调用内部服务。

官方仓库近期存在内置 VS Code 听写也收到相同 challenge 的用户报告，它说明此错误并非 AgentTouch 独有，不是 OpenAI 已确认的根因或修复：
https://github.com/openai/codex/issues/52706

### USB 原生麦克风替代路径

板卡 USB-C 确实连接 ESP32-S3 原生 USB GPIO19/20；ES7210 通过 I2S 提供音频。Espressif 官方 USB Device UAC 组件支持 ESP32-S3 和可配置麦克风采样率/声道，macOS 需要相应兼容配置。因此把板卡固件改造成真实 USB Audio Class 麦克风，在硬件架构上可行，有机会让 Codex 原生听写直接采集设备麦克风，不需要 BlackHole。

这仍是未经实机验证的方案。当前固件 ARDUINO_USB_MODE=1 使用 Serial/JTAG；需要改用 USB-OTG/TinyUSB，实现 UAC，评估 CDC 复合设备、刷机/恢复路径、I2S 采集并发。当前 Arduino USB 库没有现成 USB Audio 包装类，不能只改一行宏就交付。

USB UAC 只解决音频输入。原生 Codex 输入框可承担预览并由用户在 Mac 点击发送；若必须继续使用 AgentTouch 独立预览与设备发送按钮，仍缺少合法的原生转写文本返回接口。此次没有实现 USB UAC，也没有更改系统默认输入或重新刷机。

来源：
- https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.16
- https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_device/usb_device_uac.html
- https://github.com/espressif/esp-iot-solution/blob/master/components/usb/usb_device_uac/README.md

### 保留完整交互的可支持路径

官方文件转写 API 接收录音、返回文本，能接入现有设备 PCM → Mac 预览 → 设备发送 → 对话 ID 下发流程，不需要虚拟声卡或系统听写。它需要 API 凭证，与 ChatGPT 订阅分开计费，不能直接视为使用现有 Codex 7 日额度。本次没有寻找或使用其他 API 密钥，也没有发起收费 API 调用。

- https://developers.openai.com/api/docs/guides/speech-to-text
- https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform

最终状态：定位了外部 403 的类型，未解决原生外部入口。USB 原生输入有硬件与官方驱动证据，但不自动解决独立预览/按 ID 发送。完整交互若继续使用原生订阅听写，需要官方可调用入口；若采用官方转写 API，则可直接复用当前预览与投递模块。


## 无线要求与新发现：Codex 全局听写

用户进一步明确：必须无线；在设备上选择任务、触发录音，使用 Codex 原生语音转写，预览后由设备发送，使所选任务继续。撤销有线 USB 麦克风验证方向。

USB throwaway probe 已使用原有 Arduino 平台编译通过（63.48 秒），但未刷入；设备继续运行既有固件。可回退 app0 备份保存于 /Users/tengyi/Documents/AgentTouch-backups/2026-10-10/usb-mic-spike/restore-firmware.bin。USB 枚举和录音均未测试，不能称为 USB 功能可用。

旧语音路径：板卡 I2S → Wi-Fi/BLE ADPCM → Host PCM16 → BlackHole → Fn 触发输入法/系统听写。后续独立预览替换了投递方式，没有替换识别引擎；收到音频不代表已启动识别。

新的只读源码证据：
- voice-settings-a41de9d463e2.js 存在麦克风选择设置 microphoneInputDeviceId，以及全局听写 hold/toggle 快捷键设置。
- app-initial-c468e3fd7f91.js 使用所选 deviceId 构造 getUserMedia 的精确设备约束。未选择设备时可能优先内置麦克风，所以仅修改系统默认输入未必能让 Codex 采用 BlackHole。
- main-39FdJ_vp.js 的全局听写控制器接收完成文本，调用 handleTranscript，记录听写历史，再通过原生文本填入功能返回前台应用。快捷键入口受功能开关和注册状态控制，源码存在不等于用户账号已开放。
- global-dictation-page-c72a21049682.js 有原生全局录音、流式识别、转写失败与文本返回流程。

可验证的设计：所选任务与账号先绑定 → 激活 AgentTouch 自有预览输入框 → 设备物理语音键触发 Codex 用户配置的全局听写快捷键，同时传送无线音频到 BlackHole → 松开结束 → Codex 原生转写填入自有预览 → 设备发送时读取自有编辑框并按已绑定任务 ID 下发。无需系统听写、无需 Host 直连 /transcribe，也无需在 Codex 输入框模拟回车。禁止转写结果自动下发；取消或焦点/账号/任务变化必须撤销发送。

尚未验证：用户账号是否开放全局听写设置、快捷键是否接受设备 Host 的事件、原生文本返回是否可稳定落到预览框、真实识别与按 ID 发送。已请用户查看 Codex 语音设置，确认麦克风选择与全局快捷键。

无线情况下，当前可行候选仍需虚拟输入层。ESP32-S3 支持 BLE，不能直接当作经典蓝牙 HFP 耳麦；自研 CoreAudio 虚拟输入驱动仍是另一种音频桥接，不能因为换了名称就称为消除依赖。此候选复用已安装 BlackHole，仅作路由，识别由 Codex 完成。

参考：
- https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
- https://developer.apple.com/documentation/coreaudio/creating-an-audio-server-driver-plug-in
