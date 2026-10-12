# 本地任务选择与语音绑定

## 当前验证：加宽卡片与列表拖动

用户实测仍在手指放上时立即进入对话。进一步确认采样层问题：touchPoll在tpWasDown期间无新IRQ也getPoint；CST92xx驱动读取后ACK消费数据，无新报告返回0，被误当release。改为只在fresh IRQ读驱动，空闲轮询维持按住和上次已转换坐标，同时继续长按计时和拖动处理；IRQ锁存/清除用短临界区。TouchReportState回归覆盖100次无事件仍保持held、真实fresh release才清除。触摸诊断新增held_ms及reports，实际采样行为仍需新版用户手指测试。

卡片加宽为416×52，x32、y128/188/248/308，圆角12。标题及状态基线分别+25/+47；命中同步尺寸，行间隙和横向留白不选中任务。

旧列表滑动沿用face旋转delta，quarter-turn时y方向与dashboardXY相反；并要求60px且仅松手滚动。新DashboardGesture统一点击与拖动坐标，24px开始拖动、后续每40px逐行滚动；移动超过12px或正文长按600ms消费点击，避免松手误进对话。拖动时仍冻结后台列表替换。底部按钮不走正文长按逻辑。

纯C++测试firmware/test/test_dashboard_gesture.cpp通过，覆盖上下、反向、短移、横向以及四个旋转方向；Host标准378项通过。仍需实机截图、上下滑动、长按和底部按钮验收。

设备任务页统一显示进行中、原生未读、近期已读；进行中蓝色、未读橙色、已读灰色。进行中且未读保留未读标记。已读按 SQLite updated_at 降序，初始 5 个，更多每次增加 5 个。上下滑动列表，返回在左、刷新在右。Claude 没有原生未读来源，近期会话明确显示“阅读状态未知”。远程和云端仍未采集。

选择任务后显示标题，可上下滑动查看长标题。单条协议上限 4000 字节，极长标题裁剪并显示完整内容请在 Mac 查看。选中目标由随机 token 绑定账号与完整对话 ID；原生标记已读或列表重排不会改变目标。账号变化、来源过期、任务移除、设备重新连接时撤销目标。

右键按住录入，松开后在对话页点击发送。所选任务的语音与发送绕过旧的全局当前应用目标，失败时禁止退回应用级发送。Claude 使用已有精确终端定位，禁用应用回退。Codex 使用本地原生 deep link，并要求前台应用与焦点多行输入框的祖先 URL 暴露同一个对话路径；不使用侧栏链接作为证明。不暴露该路径的桌面版本会提示“无法确认目标，请在Mac查看”，禁止发送。麦克风准备后再次验证焦点与 token，发送为一次性操作。

## 验证边界

- 固件 amoled216 构建成功；Mac 使用 /usr/bin/python3，该版记录曾把 426 项测试写为通过，复查发现一个 PyObjC mock teardown 错误；已在后续修正版修复并重新跑完整套件。包含账号切换、身份在最后聚焦时变化、麦克风准备后焦点变化、目标删除、重复发送、JSON 转义长度，以及既有 Claude 允许/拒绝操作的回归。
- 本轮通过 USB 更新 app0，保留 NVS、SD 与另一个分区。Mac 服务同步更新。
- 实机截图确认蓝色进行中和灰色已读、更多、返回/刷新布局。更多实机从 7 条（2 条进行中加 5 条已读）增加到 10 条，read_limit 从 5 增加至 10；滑动 top 从 0 增至 3。约 29 秒麦克风流与 USB 截图并行测试收到 721 帧、gaps/dropped/stale/txerr 均为 0，坏行计数为 0，停止后 live=false。当前原生未读为零，橙色真实未读样例没有实机覆盖。
- Codex 窗口精确定位与语音实际进入目标输入框仍待人工验证。本轮 Computer Use 工具不允许操作 Codex 应用，没有改用其他工具绕过限制；全部 focus/Enter 回归测试使用 mock。
- 当前配置 voice_source=board；Mac 缺少 BlackHole 2ch，设备 PCM 流接收成功不代表可进行语音识别。已准备 BlackHole 0.7.1 安装包，校验 Homebrew SHA256、开发者签名和 Apple 公证。安装需要本机管理员密码，安装后需要重启 Mac；未自动提权或重启。

产物与安装包：/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/task-voice/。原版完整 Flash 与上一版固件仍保留在同级备份目录。

## 后续修正（2026-10-10）

- 标题优先读取 `local_thread_catalog.display_title`，兼容旧库没有该列时回退原标题。当前本机 10 条归属账号的任务与原生重命名标题一致；包含专门回归测试。
- 用户实机点击左下返回的诊断：`shownRot=1, native=(415,354)`，旧映射到 `(354,415)` 命中刷新。任务页独立采用 canvas 坐标转换，修正为 `(125,415)`；保留其他原有页面坐标映射。修正版已 USB 刷入；用户随后确认物理返回正常、标题与 Codex 重命名标题一致。
- Codex 使用 MemoryRouter，AX 窗口 URL 无法证明当前对话。用户批准改为独立 Mac 预览窗口（Cocoa NSTextView）录入、编辑，设备点击发送后按所选完整对话 ID 投递。选择任务仍由用户的设备点击触发 deep link 导航，录音不再读取或操作 Codex 编辑框，也不向 Codex 发送全局 Enter。
- 新预览流程在麦克风就绪及最终编辑框读取之后再次校验账号/token；最终校验到 Fn down、最终校验到 socket sendall 分别通过控制锁保护。IPC 的发现/等待位于锁外，取消可及时撤销。空预览允许修改再发；任何已经尝试投递的失败均不自动重试。取消、返回、设备 hello 释放麦克风并关闭预览。
- 按现有 desktop IPC 协议发现 owner 并读取 model settings，再调用 `thread-follower-start-turn` v2（idle、继承线程设置）或 `thread-follower-steer-turn` v1（running）。等待批准、未知状态、非本地目标拒绝下发；状态变化导致原生拒绝时不退回键盘或切换投递方式。私有接口的版本变化可能需要后续适配。
- 使用原生 SDK 代码核对协议；只读实测已确认 owner discovery 和 model-settings 返回。没有自动发送测试消息。独立 reviewer 复审通过，13 项预览与投递专项测试通过；完整 Host 套件 **440 项通过**，固件构建通过，USB 写入 app0 哈希校验通过。
- Mac 预览窗口真实显示、异步激活后 `active=true` 已验证；BlackHole 2ch 已安装、sink=true。它仅承担音频路由，识别仍由 Mac 当前语音输入完成；用户已确认物理返回正常；预览实际识别文字、按 ID 真实下发仍未通过验收。当前使用既有 hold-Fn 语音快捷键，若当前输入法不响应，可进一步调整语音快捷键。
- 新产物位于 `/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/task-corrections/final/`。正在等待实机语音与触摸复验，保留约 1.1 GiB `.pio` 构建目录，以便快速修正；未清理共享 checkout 或运行中服务。

- 修正版传输回归：第一次并行 USB 截图缺少末尾 5 个块，坏行仍为 0。停止麦克风后单独截图通过；再次运行完整 10 秒并行检查，截图成功、收到 260 帧，gaps/dropped/stale/txerr/tcp_dropped 均为 0、坏行前后为 0、停止后 live=false。已经查看截图；此检查仅证明音频传输和图像读取，不证明语音识别或真实消息投递。


## Codex 原生全局听写接入（Control+M）

用户确认 Codex 全局听写快捷键为 Control+M（按住录音），麦克风已明确选择 BlackHole 2ch。用户要求无线、设备选任务、设备录音、预览后由设备发送。没有刷入 USB 验证固件。

Host 的 Codex 任务语音分支改为按住 Control+M：无线音频沿用 Wi-Fi/BLE → Host 解码 → BlackHole；Codex 自身负责识别并将文字填入 AgentTouch 自有预览。此分支不触发 Fn，不开启系统听写，也不更改系统默认输入。Claude 保留既有分支。

NativeHold 防止重复按下，异常时尝试释放 M 与 Control；取消先 Escape 再释放按键。PreviewVoice 独立保存 pending 原生听写状态，任务失效后仍可取消等待中的转写；停止失败关闭音频路由并禁止发送。取消失败保留预览目标和 pending 状态，避免主动关闭文字目的地；发送要求预览仍在前台，并先结束原生待处理会话，再按已有绑定 task/account 与 ID 投递。没有自动发送。

- 全量 Host 单元测试 457 项通过（/tmp/agenttouch-native-tests-final.log），包括快捷键异常释放、无系统输入切换、任务失效后的 pending 取消、失败清理及发送前取消。
- 独立 reviewer 首轮指出 3 个清理问题，修复后 27 项专项 mock 测试通过，无剩余重要发现。复审与测试均未触发真实键盘或操作 Codex UI。
- 运行模块 agentpet_host.py、preview_control.py、native_dictation.py 已安装至 ~/.agentpet，并重启 com.agentpet.host。重启健康检查 live=false、source=board、sink_device=BlackHole 2ch、gate=false。
- 回退备份：/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/native-codex-hold-ctrl-m/，包括原模块与部署模块哈希清单。
- 待用户实机验证：设备键是否触发 Codex 原生录音、预览是否出字、取消与完整按 ID 发送。未发送测试消息。当前模块已部署但还不能称为端到端通过。

## 实机音频确认及 Codex 主页面快捷键修复

用户实机反馈：手动点击 Codex 话筒，同时按住设备 IO18，能得到文字。该结果确认设备无线音频经 BlackHole 进入 Codex 原生转写可用，尚不能证明设备能自动启动听写。Host 日志显示这些无 target 的 voice 请求进入旧 Fn 分支；任务详情的有 target 分支已使用 Control+M。

修复无 target 的 Codex 主页面录音：按下使用 Control+M，松开仅结束听写，不发 Enter；Claude 与 front 光标录入保留原路线。按下时锁存快捷键及板端音频路由，worker 内顺序设置、清除会话，避免快速松键在 focus 等待时提前关闭音频 gate。sink/focus/key 异常关闭音频，不回退至错误麦克风。

- 全量 Host 测试 463 项通过：`/tmp/agenttouch-native-face-tests-final.log`。审查后新增延迟队列、focus 中松键、focus 异常覆盖，独立相关测试 33 项通过。旧 focus 测试 fixture 已隔离新的原生键盘边界。
- BlackHole 合成音回环独立通过，4 秒输入采样 63882 帧，peak=7982、rms=4466.1；没有调用 Codex 后端。
- 已部署 agentpet_host.py 并核对哈希，重启 com.agentpet.host；健康检查 live=false、gate=false、sink_device=BlackHole 2ch。
- 回退备份：`/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/native-codex-face/`。
- 未改固件或传输路径。待用户验证自动启动/结束 Codex 原生听写与预览文字；没有发送真实测试消息。

### Codex 主页面原生按键实测（14:35:57）

新版部署后用户返回了测试转写文字。日志显示 14:35:57 Control+M DOWN、14:36:01 Control+M UP；BLE 音频 75 帧，gaps/dropped/stale/txerr/tcp_dropped 均 0，结束后 live=false、gate=false。14:36:03 独立收到 board key enter，说明松键和设备点击发送为两次独立事件。该测试属于无 target 的 Codex 主页面，确认设备自动触发原生听写路线；不证明任务详情 AgentTouch 预览、取消或绑定 ID 投递。

### 任务详情全局听写入口（待实机）

用户反馈从任务列表选择任务后未正常启动。14:36:56–14:36:58 Host 确认调用 Control+M，非旧 Fn；详情流程先激活自有预览，所以走 Codex 全局入口而非窗口内入口。用户随后确认：预览前台时，手动按住 Control+M 可以出现 Codex 原生录音提示。这将差异缩小至模拟快捷键全局触发。

本机 Quartz 只创建、不发布的对象检查发现：左 Control down 默认是 flagsChanged，flags=0x20040001；原 emitter 覆盖为通用 Control mask 0x40000，丢失左 Control 设备位。SDK `IOKit.framework/Headers/hidsystem/IOLLEvent.h` 定义 NX_DEVICELCTLKEYMASK=0x1。修正 emitter 明确设置 Control|0x1，release 为 0；不继承其他物理修饰键，保持原先组合隔离。该差异是本次验证假设，不能仅凭对象 flags 认定全局入口已修好。

- 全量 465 项 Host 测试通过，日志 `/tmp/agenttouch-native-global-tests-final.log`；Quartz 边界测试全部 mock CGEventPost，不向应用发送键。
- 独立审查确认设备位及其他 modifier 组合隔离正确。
- 已更新 ~/.agentpet/agentpet_host.py 并重启服务；live=false、gate=false、BlackHole 2ch。备份在 `/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/native-codex-global-modifier/`。
- 待用户再次在任务详情按设备 IO18，确认原生提示与预览出字。无固件或传输变更，无真实消息投递。

## 改为 Codex 输入框预览、Mac 手动发送

用户最终更正：AgentTouch 预览没有文字，Codex 设置的语音记录能看到录入内容；并已选择改用所选任务的 Codex 输入框。原转写已完成但跨应用预览回填失败，此处不再使用外部预览回填。

新增 ComposerVoice：设备选择的本地 task/account 经身份复验，通过既有 codex://threads/<ID> 用户触发导航，给原生编辑器挂载 0.5 秒，再触发 Control+M。音频继续无线进入 BlackHole；Codex 的窗口内听写负责将文字写入自身 composer。没有读取 Codex UI、draft 或内部注入。stop 只释放快捷键和音频，后续发送由用户在 Mac 执行，设备不发 Enter/IPC。正常松键后不再记录永久 pending，避免下一次录入/换任务向已发送 turn 误发 Escape；仍按住时取消释放 native 键并清理音频。

设备详情文案改为 Codex 输入框录入，结束提示“请在Codex确认并发送”，不显示可点击的设备发送按钮。Claude 路径保持原操作。

- 全量 Host 472 tests PASS：`/tmp/agenttouch-composer-tests-final.log`；最后取消 finally 调整后的 7 项专项复跑 PASS，独立复审无部署阻塞。
- 固件 build PASS：`/tmp/agenttouch-composer-build.log`；USB upload PASS、flash data hash verified：`/tmp/agenttouch-composer-upload.log`。固件 SHA256 `a200acb6017e4f2ef8c8178d95ea475a349f494be5fd6b214df43432d3f3e71c`。
- agentpet_host.py、composer_control.py 已部署，重启 Host；设备 BLE=true、Wi-Fi boards=1，mic live=false、gate=false。main.cpp 未改、复用旧对象，因此 hello build 字符串仍为 Oct 10 2026 13:44:53；新固件以写入验证及二进制 SHA 为证据，不以该字符串为证据。
- 回退备份与 manifests：`/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/native-codex-composer/`。active worktree 构建依赖仍用于实机后续验证，未清理。
- 待用户实机验证：重新从列表选任务后，是否不再出现外部预览、是否出现 Codex 原生录音提示、是否在所选对话输入框出现文字。Mac Send 没有自动测试或代点。此阶段不能称为端到端接受。

## 恢复设备确认发送（Native composer）

用户实机确认任务详情的原生录入正常，要求设备提供确认发送，避免回 Mac 手动点发送。新增可选 native submit 回调，设备 stop 成功后 armed；必须同一 token、已松键、ready，才能触发一次发送。Send 前消耗 ready，即使无法确认结果也不自动重试；重新打开绑定 Codex URI 后，在 selection lock 内复验 task/account，提交回调再次检查账号和 Codex 前台应用，再由这次明确的设备 Send 发出原生 Enter。使用 Codex 当前草稿，保留 Mac 上对文本的修改，不读取 UI/draft、不从语音历史重放文本。

设备录音结束显示绿色“发送”，提示先确认文字。keyboard dispatch 回包 phase=send_requested，设备显示“已触发发送，请在Mac查看”，并不宣称 Codex accepted。URI 导航返回及 0.5 秒挂载等待、前台应用检查不能证明实际 composer first responder；真实正确对话提交仍需用户实机验证。

- 全量 Host 484 tests PASS：`/tmp/agenttouch-device-send-tests-final.log`，包括按住不可Send、错误token不可Send、重复点击单次、导航时目标变化阻断、submit异常不重试、错误前台应用阻断；19 项 composer 专项由独立审查复跑通过，无新实现阻塞。
- 固件 build PASS：`/tmp/agenttouch-device-send-build-final.log`。
- Host agentpet_host.py、composer_control.py 已部署核对 SHA。回退备份：`/Users/tengyi/Documents/AgentTouch-backups/2026-10-10/native-codex-device-send/`。
- USB upload 在打开串口阶段失败：/dev/cu.usbmodem1401 已不存在，未写入设备。设备 BLE/Wi-Fi 在线，已启动无线 SD OTA；结果待后续记录。

- 无线 OTA 实际完成：`/tmp/agenttouch-device-send-ota.json` ok=true、stage=done，2110112 B 经 SD size/CRC 检查及写入 app1，push 82573 ms、flash 8493 ms、reboot 6554 ms；设备重新 hello/app1，BLE/Wi-Fi 恢复。等待用户在愿意追加指令的任务中，录入后点击设备绿色发送验证；尚未代发测试消息。


## Device Codex draft preview before Send (2026-10-10)

- Local selected conversation only: read `~/.codex/.codex-global-state.json` / `electron-persisted-atom-state.composer-prompt-drafts-v2[local:<thread ID>]`. No Codex UI scraping, authentication extraction, or transcription replay. Native dictation history is only a completion marker (single composer recording within the key-held interval, completed audio plus nonempty transcript). Preview displays the selected persisted draft, including Mac edits.
- Hold/release does not arm Send. After completion and 750 ms of stable changed draft, send full preview with a random revision and voice round ID. Device scrolls the preview; Send is disabled during recording/transcription. Excessive escaped JSON (>3700 B) or unsupported rich nodes/attachments block confirmation and direct the user to Mac. No silently clipped submission.
- Each physical recording immediately clears preview and increments voice round ID. Firmware rejects stale rounds and backwards stage events. Selected voice does not arm the generic six-second send bubble.
- Explicit Send carries preview revision. Host revalidates selected account/thread, reopens that conversation, re-reads persisted draft fingerprint before native Enter. Changed draft blocks that click and refreshes the preview. Submission remains keyboard dispatch, not acceptance proof; persisted draft cannot prove the latest not-yet-flushed editor state or first responder.
- Focused tests cover early Send, delayed ASR, ambiguous/unsupported preview, draft revision edits, task/account loss, overlong text, temporary read recovery after 90 s, timeout, and duplicate confirmation. Full Host suite: 515 PASS; firmware amoled216 build PASS. All keyboard-boundary tests mock actual posting.
- Deployment: runtime Host copy and SD OTA staged; backup `~/Documents/AgentTouch-backups/2026-10-10/native-codex-device-preview/`. Physical preview/send acceptance and screenshot inspection pending. Build dependencies retained in active worktree (~1.1 GiB) for hardware verification.

- Wireless OTA completed: app1 → app0, 2,111,824 B, 89,563 ms total (75,938 ms push, 8,451 ms flash, 4,979 ms reboot), build `Oct 10 2026 15:10:22`, SHA256 `7b510b8ccdd0c847e934abca3fc2f019957d7603bc038a214ac5689b3ba2f834`. Host/board reconnect verified (BLE true, TCP boards 1). Two full screenshot requests returned no answer; no new preview layout screenshot obtained yet. User physical recording/preview comparison requested; no actual chat test message sent by tools.

- Transport smoke check: 10 s diagnostic mic stream, 26.3 FPS, native transcription gate remained closed, bad lines 0 → 0. 120×120 screenshot succeeded and was visually inspected (device home page); full screenshot timed out at current transfer rate. Preview page screenshot and physical transcription comparison remain pending user action. Plain text preview rejects rich text marks (e.g. hidden links); latest full Host suite still 515 PASS.


## Round-panel usable-area layout (2026-10-10)

- Scope: AgentTouch dashboard summary, quota, task catalogue, selected conversation/native draft preview. Body/task titles/buttons now use existing AF_BODY26; auxiliary status uses AF_TINY18. No new font dependency.
- Panel is 480×480, content bounds follow R232 (8 px inside the physical circle), including glyph height. Catalogue card widths 360 / 438 / 448 / 386 px instead of 332 px. Four cards at y94/164/234/304 with 64 px height; lower More region y370..389; footer tap cells y390..455.
- Preview 8 lines, baselines 114..338 at 32 px spacing. UTF-8 wrapping uses the corresponding row width; scroll uses whole groups of 8 so narrower edge rows always retain correct widths. Page hint baseline362, status386 max350px, footer labels424.
- Footer buttons inside safe circle: rectangles x118/202/286, y397, 76×39. Return/Send/Refresh hit partitions updated together. Existing explicit Send and preview revision validation retained.
- Quota detail now uses centered 180 px diameter arc and larger ASCII percentage. Face summary shifts quota ring left and enlarges counts when their measured width allows. Task card text anti-aliasing uses actual card background.
- Firmware amoled216 build PASS; required Host `test_host.py`: 378 PASS; static geometry checks confirmed card/footer corners inside safe circle. Independent code review found no important blocker; status safe width and preview line/hint spacing adjusted after review. OTA and physical screenshots pending. Active worktree .pio (~1.1GiB) retained for physical verification.

- Deployed via wireless OTA: app0 → app1, 2,112,544 B, 83,954 ms total, build `Oct 10 2026 15:19:43`, SHA256 `791f7d015b3b6da136c52e75f2444b7baba973bb9a362651e5cd03d4634b85f3`. Actual catalogue screenshot `~/.agentpet/shots/20261010-152416.png` and quota screenshot `20261010-152510.png` visually inspected at 240×240; title/card/footer regions fit the circle, larger body glyphs render. Screenshot framing bad lines remained 0. Device returned to catalogue without opening/submitting any Codex task. Native draft preview page still needs physical-user recording verification; this screenshot check does not claim preview content acceptance.

## 设备草稿回读失败的诊断（15:30 用户实测后）

用户确认松键后所选任务的 Codex 输入框已有文字，但设备显示“未读取到草稿，请在Mac查看”。Host 日志确认 15:30:28–15:30:35 原生 Control+M 按下/释放；本次 composer 听写记录 completed 且文字长度 23。当时全局缓存只有一个 local 草稿、正文长度 5，且其 ID 不在两份本地 state_5.sqlite 中，因此不能将该缓存或历史转写当作所选任务的实际草稿。源代码确认全局状态写入 debounce 为 500 ms，不能以等待不足解释。

读取器另有独立缺陷：原生 composer 会添加 usedDictation 布尔标记，旧的额外字段检查会误拒绝。现仅放行严格布尔值；附件、检查等额外内容仍拒绝。新增 /test/composer，由串行 worker 返回阶段、草稿字符数量、是否变化、听写是否完成及选择是否有效，不返回正文、线程 ID 或 token，不操作应用。新增回归测试；全量 518 项通过，日志 /tmp/agenttouch-preview-diagnostics-tests.log。

本次修改尚不能证明所选任务缓存可读取，仍需新的用户录音与诊断关联；不以 23 字历史转写回放代替实际输入框预览，不进行真实测试投递。固件无需再次更新。

诊断版 Host 已部署并重启，源文件与 runtime SHA 核对一致；/test/composer 空闲读正常。备份 ~/Documents/AgentTouch-backups/2026-10-10/draft-read-diagnostics。独立复审发现 wrapped draft 外层附件可被忽略，已改为解包前拒绝非空外层字段并补回归测试，复审通过。仍待用户实际录音核对。

## 全局听写完成标记（15:47 用户实测）

/test/composer 显示 waiting_for_transcript 后超时。与 Host start=1791618471.8624241 / stop=1791618478.407635 对照，本次唯一听写记录 createdAtMs=1791618472168、status=completed、surface=global、正文长度19，落在完整时间范围内。根因之一是完成标记仅接受composer，忽略global。现同时接受composer/global，未知surface仍拒绝；时间区间、唯一性、completed、非空转写条件均保留。只将历史作为完成标记，预览正文仍读取 exact-bound 草稿。新增 global/unknown 测试；全量518项通过 /tmp/agenttouch-global-completion-tests.log。Host已部署此单模块修改并重启；备份 ~/Documents/AgentTouch-backups/2026-10-10/global-completion。无固件修改或真实消息发送。缓存仍只含不属于本地SQLite任务的草稿，设备预览尚未验收；等待用户手动切换对话验证保存时机。

## 发送返回详情与任务列表局部刷新

成功 send_requested/sent 清除 previewText/revision，重新 wrap 话题标题，保留当前话题 token，可继续语音录入；错误仍保留对应处理。所有任务卡片固定360×64、70px行距。后台代际更新保留旧列表，incoming 收齐分页后在触摸采样之后、手指未按住时原子替换；加载期间允许选择可见任务。

catalog新增stable_handle（agent/account identity/host/thread ID哈希），在当前账号的新快照中解析，旧generation:index handle保持兼容；避免后台更新期间旧卡片因generation变化无法选择。跨账号或已移除任务拒绝；增加回归测试。

Dashboard 独立绘制，跳过下层动画 face；可见内容不变时不重新绘制/传屏，变化后比较native framebuffer逐行，仅传输变化的连续像素行。手动刷新 forcefull；离开face进入钟/日历使缓存失效，返回必须full，旋转通过native framebuffer比较。PSRAM增加460800字节frame cache，分配失败回退full。独立复审修复触摸提交时序及跨页面缓存失效两个问题。

Build PASS /tmp/agenttouch-partial-list-build.log；Host test_host 378项通过，完整519项通过 /tmp/agenttouch-partial-list-all-tests.log。Host模块已部署，固件无线更新中；备份 ~/Documents/AgentTouch-backups/2026-10-10/partial-task-list。尚待截图、物理刷新计数及用户发送返回/点击验收。

无线OTA完成：2115584 bytes，SHA256 d284c6ce37abe8a4a36dca84a988886a2dd9dd31299cfcd74e2ce1f2fea5f3f3，app0，hello build Oct 10 2026 16:00:11。/tmp/agenttouch-partial-list-ota.json 返回ok true，total141312ms。实机列表7行加载完成，full_frames=1/partial_frames=5，说明进入一次full后执行局部传输。full截图s1服务返回no answer in30s；随后10s板端音频诊断（不触发Codex快捷键、gate=false）259frames/25.5fps，gaps,dropped,stale,txerr,tcp_dropped全0；bad_lines前后均0。局部渲染额外帧缓存保留于运行固件，工作树.pio约1.1GiB继续留作实机复验，不清理active/uncommitted目录。

240×240截图 /Users/tengyi/.agentpet/shots/20261010-160651.png 已目视检查：四个等宽任务卡片、标题及状态可读、返回/刷新边界未裁切。拍摄前列表7行、full_frames=2/partial_frames=14（第二次full为音频诊断关闭列表后重新进入），连续后台更新未增加full计数。第一次小图抓到切换前主页；稳定加载后重新截图。睡眠黑屏也需invalidate缓存，已补充：唤醒后必须full，避免partial缓存以为黑屏仍是旧任务页。

最终睡眠重绘补丁OTA完成：2115600 bytes，SHA256 6fbab81b9f5ac059cdfaff2c0d5602909567d57c5aa8c8255909af4a47adcecb，app1、Oct 10 2026 16:07:22；total90011ms，/tmp/agenttouch-partial-list-final-ota.json ok true。Host dashboard.py/task_control.py 与工作树SHA一致。布局截图对应同一布局，最终修改仅睡眠缓存失效分支。尚待用户实测发送后回详情、自动刷新期间点击、手动刷新、睡眠唤醒。

Wide/drag OTA: {"ok": true, "stage": "done", "push_ms": 62963, "push_kbps": 32.8, "flash_ms": 8467, "bytes": 2116160, "slot": "app0", "old": {"build": "Oct 10 2026 16:07:22", "part": "app1"}, "new": {"build": "Oct 10 2026 16:32:03", "part": "app0"}, "reboot_ms": 8282, "total_ms": 80066}
Firmware SHA256: 42e23aac510a8fcf651a71b9ab342b2e6fd0d5debeff02cae837cdc661e75623. Build PASS; 378 Host tests PASS; native gesture tests PASS. Actual user gesture acceptance pending.

Device wide-layout screenshot visually inspected: /Users/tengyi/.agentpet/shots/20261010-163447.png (240x240), equal-width cards closer to edges; title/status/footer legible without clipping. Board scroll diagnostic changed top 0 -> 1; full_frames remained 1 and partial_frames 5 -> 6. This verifies list scroll/render state, not physical finger input. User real up/down/hold-drag test requested. No Codex UI actions or real sends used.

## 触摸 IRQ 状态保持修正部署

用户实测上一版无法滚动，触碰即进入对话，因此上一版物理手势验收失败。修正无新 IRQ 时保持触摸状态，避免重复读取已消费报告导致假松手；仍处理长按计时和拖动。新增 release held_ms/reports 诊断。原生 C++ 状态及手势测试通过；固件构建通过 /tmp/agenttouch-touch-irq-build.log；Host 378 项通过 /tmp/agenttouch-touch-irq-host.log。

无线 OTA 成功：2116608 bytes，SHA256 6fbe86de9593788ca10760e8bedea2afecc0c79bf35f9a6038e5061796d4351b，app1，build Oct 10 2026 16:39:06，total122005ms。/tmp/agenttouch-touch-irq-ota.json 保存结果；重启后 BLE=true、boards=1。布局沿用已目视检查的416px卡片，尚待用户再次长按/拖动实测；fresh IRQ 的无效报告与释放仍由现有驱动统一返回0，此边界未声称已解决。

用户实机验收：触摸 IRQ 状态保持修正版刷入后，任务列表可上下滚动，且长按/拖动松手不会误进对话。用户回复“可滚动，且不误进对话”。该反馈确认本次物理手势修复；不扩大为其他语音、远程或云端功能验收。

## 主对话状态与最近消息详情

用户反馈子任务完成导致对话数量不一致，且详情中部空白；补充要求标题固定一行，超长省略。源日志只统计字段及数量，确认子轮次带 parent_turn_id，turn_id 不同于 root_turn_id；旧 rollout_status 未校验归属。现跳过子轮次生命周期，主轮次完成须匹配 active_turn；notify 对 session_meta.source.subagent 也拒绝，原生未读来源保持不变。

详情由所选 token、账号及本地 rollout_path 读取最近一组 user/assistant 文本。Codex 按消息元数据 turn_id 排除交错子任务，Claude 排除 isSidechain 和工具块。读取预算8MiB，不记录正文；每3秒检查变化，静态详情每6秒重发以恢复首次选择确认与详情的顺序竞争。单条 wire 小于4000字节，长文本裁剪并提示Mac查看；历史消息只显示，绝不用于草稿或发送。固件标题一行省略，宽220px；中间显示你问/助手，支持现有上下滑动，语音草稿优先。

构建 PASS /tmp/agenttouch-details-build.log；标准Host379通过，全量526通过 /tmp/agenttouch-details-all.log；独立复审确认交错子消息过滤及首次详情重发恢复，无剩余重要问题。Host模块备份并部署；固件2118848字节，SHA256 3b5c9c16d92d683cc79cc785156ece6765b134d357ef3a04f3d23a281bebb32f；无线OTA进行中。仍需截图、传输回归、用户主对话计数及最近消息实测。

首次实机小图 /Users/tengyi/.agentpet/shots/20261010-165736.png 已目视检查，标题一行且未裁切，但正文停在正在读取。修正 main.cpp 的消息分派入口，加入 task_detail；这不是源读取失败。重新构建 PASS、Host379通过、native gesture测试通过、diff检查通过；复审确认完整wire流接通。最终固件仍为2118848字节，SHA256 5164281a76e9a993e0ef0f769d11e0c3d3a5f88707b23bc562b0e2e26ab4d036；OTA成功，app1、Oct 10 2026 16:58:14、total101974ms，结果 /tmp/agenttouch-details-final-ota.json。

传输回归：全尺寸shot请求超时，初次10秒mic检查0帧；连接重建后最终版10秒mic重测257帧、24.6fps、gaps=0、gate=false（不调用Codex听写或发送），bad_lines前后0；BLE=true、boards=1。全尺寸截图仍未通过，小图可用。已请求用户保持详情页面以核对实际最近消息；主对话子任务完成时计数及Claude真实消息仍需用户实测。工作树active/uncommitted，构建依赖保留供后续设备验证，不执行cleanup。

## 消息内部标记清理与右滑返回

用户实测确认标题一行、最近消息已经显示，但末尾出现 </oai-mem-citation>；因此最近消息读取与显示已获得该次物理验收，主任务计数不扩大验收。显示清理在长度裁剪之前移除完整/未闭合记忆引用区块及孤立结束标签，Codex和Claude共用，普通代码块保留；不修改原始对话或草稿。

新增松手触发的右滑返回：显示坐标向右至少80px且横向至少为纵向2倍，已进入竖向拖动则不返回；复用现有返回按钮路径（详情到列表，列表或额度到主页面），录音/审批/配对模态保护仍在。纯C++手势测试通过，Host全量527通过，构建通过；独立复审无阻塞问题。固件2119072字节，SHA256 0f254b972c4c7846d7f31433b2ae01b3a3bb04e64393a1b2d6d982594e666f5d。Host清理模块已备份部署，OTA进行中；待用户右滑和消息末尾复验。

OTA完成：app0、Oct 10 2026 17:06:38，total95547ms，/tmp/agenttouch-clean-back-ota.json ok=true。已请求用户实测标记清理、详情右滑返回列表、列表右滑返回主页面及竖向滚动。该版不修改传输编码或音频链路；不把上一版的257帧音频结果作为新版重测结果。

用户实机验收回复“三项都正常”：消息末尾内部引用标记已消失，详情右滑返回列表、列表右滑返回主页面正常，上下滑动仍正常。该次验收确认显示清理及返回手势；不扩大为主对话子任务完成计数、远程/云端覆盖或新版语音发送验收。

## 进行中计数与7日额度采集恢复

用户反馈两个任务运行时显示0，额度圆环没有数值。现场证据：约213MB的运行中rollout，本轮开始记录不在8MiB尾部预算内，旧解析返回unknown；仅凭文件30秒静默与尾部事件不足以判断主轮次完成。Codex原生 thread_history_1.sqlite 的 thread_turns 明确记录两个主轮次 inProgress。现优先读取各thread最新主轮次（turn_id=root_turn_id或兼容旧null），排除子轮次完成，inProgress保持running，已有pending等待判定保留；投影不可用才回退日志解析。账号/可见目录/子线程过滤保持。

额度旧 app-server-control.sock 已不存在，原生 usage limits 和已验证的 bundled Codex app-server stdio 均返回7日已用81、剩余19。Host改用仅允许 initialize/initialized/account/rateLimits/read 的有限时stdio进程，返回后核对账号身份，finally终止或kill并关闭管道；缺失额度15秒重试、成功缓存仍300秒刷新。安装脚本补充所依赖模块。没有改变模型任务或发送消息。

全量531项通过 /tmp/agenttouch-native-status-quota-tests.log，含大日志缺失start、子轮次不结束主轮次、额度身份、禁止写RPC及进程超时清理回归；独立复审无阻塞问题。本次仅Host，固件未重构建/刷写。部署 dashboard.py/dashboard_service.py/codex_stdio.py，源/runtime SHA一致，备份 ~/Documents/AgentTouch-backups/2026-10-10/native-state-quota。实际/dashboard显示running2、quota remaining_pct19、quality ok；BLE=true、boards=1。

实机小图 /Users/tengyi/.agentpet/shots/20261010-174652.png 目视确认额度圆环19；该帧任务文字未完整显示，后续截图请求超时，不将此帧作为任务数字验收。用户随后直接实机确认“进行中2，圆环19，正常”，确认本次两个报告问题已恢复。远程/云端覆盖和长期故障恢复仍未扩大验收。
