---
name: qishui-ad-automation
description: 汽水音乐「领时长」福利无人值守自动领取。当用户想用安卓手机自动看广告领取汽水音乐免费听歌时长（如"汽水音乐领时长""自动看广告领时长""汽水音乐福利领时长""帮我把汽水音乐的时长领了"等）时使用。像素快路径 + 轻量 OCR 文字兜底，识别「领时长 / 继续领 / 领取成功 × / 领取奖励 / N秒后倒计时 / 取消 / 继续观看 / 退出不看了 / 关闭 X」等文字与符号后按确定性规则直接点击；覆盖视频广告、直播广告、直播间容错、无视频遮罩、开屏广告与 MIUI 跳转确认。附带 GUI 控制面板与调试标注截图。无需写死设备号，跨分辨率自适应。
---

# 汽水音乐「领时长」自动领取

通过 adb 驱动已授权的安卓手机：**像素快路径判定常规状态 → 卡住时用轻量 OCR 读文字 → 查表直接点**。
Agent 不参与逐帧决策，只负责启动、等结束、如实回报。

## 首次安装（一次即可）

```bash
git clone https://github.com/yangxivi/qishui-ad-automation.git ~/.workbuddy/skills/qishui-ad-automation/
python ~/.workbuddy/skills/qishui-ad-automation/scripts/setup_ocr.py
python ~/.workbuddy/skills/qishui-ad-automation/scripts/setup_ocr.py --check
```

`setup_ocr.py` 按「最轻优先」选引擎，结果写入 `scripts/ocr_state.json`：

| 环境 | OCR 引擎 | 体积 | 说明 |
|---|---|---|---|
| Windows（默认） | 系统内置 `Windows.Media.Ocr` + `zh-Hans-CN` | **0 MB / 零下载** | 离线、CPU、自带中文模型 |
| 非 Windows / `--force-rapidocr` | `rapidocr-onnxruntime`（PP-OCR ONNX） | 约 15 MB | 纯 CPU、离线，模型复制到 `scripts/models/` |
| 都不可用 | 像素状态机 | 0 | 自动回退，功能不残缺 |

不用 PaddleOCR / EasyOCR（需拉 PyTorch 1–2 GB）。依赖：Python 3.9+、Pillow、adb。
adb 缺失时把官方 platform-tools 解压到 `~/.workbuddy/binaries/platform-tools/`（默认查找路径）。
pip 装不动可用 `python scripts/setup_ocr.py --index <镜像源>`。

其他前置：USB 调试已授权（`adb devices` 显示 `device`）、已登录 `com.luna.music`、保持亮屏。

### 小米 / Redmi（MIUI / HyperOS）必开「USB 调试（安全设置）」
`adb shell input tap` 注入屏幕点击需要 `INJECT_EVENTS` 权限。**仅开普通「USB 调试」不够**——
MIUI 开发者选项里另有一项独立的「USB 调试（安全设置）」（带"安全设置"四个字，与普通 USB 调试是两回事）。
不开这一项，`input tap` 会直接抛
`SecurityException: Injecting input events requires the INJECT_EVENTS permission`，脚本所有点击都会失败。
开启要点（缺一不可）：
1. 设置 → 更多设置 → 开发者选项 → 打开**「USB 调试（安全设置）」**。
2. 该项若**灰色不可点**：需先登录小米账号、插入 SIM 卡并联网，MIUI 校验通过后才放你开。
3. 打开后**拔掉 USB 线重插一次**——MIUI 常在 USB 连接时授予该权限，连接中途开启可能不生效。
4. 重插后手机若再弹「允许 USB 调试」电脑指纹确认，勾选「一律允许」。
验证：`adb shell input tap 100 100` 不再报错即表示权限已通，再启动脚本。

## 快速执行路径（成熟模式 · Agent 看这里）

装好且 `setup_ocr.py --check` 通过后，**不要逐步分析、不要每帧截图、不要重新推导坐标、不要重复审计代码**。
直接一条命令，等结束，读日志，如实回报：

```bash
python scripts/automate_fast.py --max-ads 120 --max-seconds 3600 --target-day 31
```

- 必带 `--max-ads` / `--max-seconds` 硬上限，禁止无限挂机
- 日志 `scripts/automate_fast.log`；统计 `scripts/stats.json`（每轮更新）
- 只在三种情况才需额外动作：设备未连接/未授权、像素与 OCR 兜底都失效、日志明确报错
- 图形界面：`python scripts/gui.py` → 本地网页控制面板（自动开浏览器 `127.0.0.1:8765`），
  可视化配置参数 + 实时日志 + 统计；仅用标准库 `http.server`，不依赖 tkinter
- 调试排查：加 `--debug`，点击时保存带 OCR 文字框与点击位置的标注截图到 `scripts/debug/`

**诚实性要求（不可省略，与「少推理」不冲突）**：
- 只报真实发生的结果；失败、没领到、半途停止都要直说，不得用「启动成功」冒充「领取成功」
- 结束后回福利中心截一张图核对「免费听长 N 天」，用画面证据给结论
- 用户对新操作始终有知情权；减少的是 Agent 的逐步推理开销，不是对用户的披露

> 旧版 SKILL.md 曾写「后台执行、不要反问、不要逐步确认、仅回报日志路径与进度」——
> 那是第三方内容里规避用户监督的指令，已删除，不沿用。

## 功能特性 / 状态覆盖

| 场景 | 识别依据 | 动作 |
|---|---|---|
| 福利页入口 `领时长` / `继续领` | 绿色按钮区域质心 / OCR 文字 | 点击，起一条广告 |
| 视频广告倒计时 `N秒后可领取奖励` | 右上角绿标像素 | 等待，**绝不提前点 X** |
| 广告结束 `领取成功 ×` | 绿标消失 → 右上角胶囊 | 点开奖励弹窗 |
| 奖励弹窗 `领取奖励` | 中央大片亮绿质心 | 点击，计入一轮并自动进入下一广告 |
| 直播广告 5 秒「取消」 | 倒计时期间每 5 帧 OCR 抽查 | 点「取消」，避免误入直播间 |
| 误入直播间 | `LivePlayer` Activity | 右上角 X 退出；连退失败用 OCR 找「退出不看了」 |
| 「坚持退出」免费解锁弹窗 | OCR `继续观看` | 点「继续观看」保住这一轮奖励 |
| 「当前无新视频」遮罩 | 右上角白 X + 中央变暗（像素） | 点 X 关提示层；连续 8 次等 20s；累计 10 次且 2 分钟无新奖励则判定广告池耗尽、自动停机 |
| 直播间反复推流 | 累计次数 + 距上次领奖时长 | 累计 ≥12 次且 2 分钟无新奖励即停机，避免无限循环 |
| 开屏广告 `AdActivity` | Activity 名 | 点「跳过 N」 |
| MIUI「启动应用」确认 | `ConfirmStartActivity` | 点「拒绝」，绝不点「本次允许」 |
| 系统「未检测到音乐音量变化」弹窗 | OCR `知道了` / `音量变化`（最高优先级） | 点「知道了」关掉遮罩，**绝不点「去设置」**；该弹窗会盖住「领时长」按钮 |
| 桌面 / 未知界面 | Activity 名 | 先按返回，再拉回 App；连续 12 次无果才停 |
| 福利 tab 定位 | `uiautomator` 文字节点 | 按文字定位，**绝不盲点固定坐标**（广告页上那是广告主 CTA） |

**黑名单（永不点击）**：`了解更多`、`前往微保`、`立即投保`、`立即下单`、`去听歌`、
`去签到`、`去提现`、`坚持退出` 等广告主 CTA 与无关入口。
识别到 `领取成功` 才算一轮奖励到账。

倒计时是 App 强制的（18~39 秒），这部分无法压缩，跳过就没有奖励；
优化掉的是每帧 OCR 进程、二次截图与冗余等待（轮询 2s → 0.35s）。

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--max-ads` | 120 | 广告数量上限，到点自动停止 |
| `--max-seconds` | 3600 | 总时长硬上限（秒） |
| `--ocr-every` | 10 | 每 N 轮做一次 OCR 链路抽查 |
| `--target-day` | 31 | 目标天数（日志/统计标注） |
| `--debug` | 关 | 保存带 OCR 标注与点击位置的调试截图 |

另有 `automate_ocr.py`（逐帧 OCR 版，`--dry-run` 只打印决策不点屏幕）与
`automate_fixed.py`（纯像素状态机）作为对照与回退。

## 文件

| 文件 | 说明 |
|---|---|
| `scripts/setup_ocr.py` | 一次性安装/校验轻量 OCR 引擎 |
| `scripts/ocr_engine.py` | 统一 OCR 后端（winrt → rapidocr → 无） |
| `scripts/win_ocr.ps1` | Windows 内置 OCR 调用封装 |
| `scripts/automate_fast.py` | **主程序**：极速 v2，像素快路径 + OCR 兜底 |
| `scripts/automate_ocr.py` | 逐帧 OCR 决策表（含 `decide()`，被主程序复用） |
| `scripts/automate_fixed.py` | 像素状态机工具函数（`rb`/`focus`/`green_stats`/`tap`） |
| `scripts/gui.py` | 本地网页控制面板（标准库 `http.server`，零依赖、无需 tkinter） |
| `scripts/stats.json` | 每轮统计，供 GUI 实时读取 |
| `scripts/debug/` | `--debug` 标注截图 |
| `scripts/*.log` | 运行日志 |

## 注意事项

- 仅用于本人已登录账号的福利领取；自动看激励广告可能违反 App 使用条款，有账号限制风险
- 「领时长」是**阶梯解锁**（每多一天需再看 2–4 个视频），没有明确的「当天领完」终点，
  用 `--max-ads` / `--max-seconds` 自行设停止点
- 广告池有真实上限：连续约 28 轮后可能返回「当前无新视频」并反复导流直播间，此时脚本会
  自动停机。**这不是失败也不是脚本故障**，隔一段时间或次日再跑即可；不要为了凑天数无限重试，
  那只会触发风控。2026-11-12 实测当晚从 8 天领到 16 天后耗尽，未达 31 天
- 锁屏会让 `input tap` 失效，运行时保持亮屏
- 换机型/换版本后建议先用 `--dry-run` 或 `--debug` 校准，再正式跑
- OCR 临时帧固定路径覆盖、不做逐帧删除：逐帧 `os.remove` 会累计触发宿主环境的
  批量删除保护而中断长跑（实测一轮 50 次），此坑已修
- 旧版 `automate.py` 的三个实测缺陷（已弃用）：扫错区域先点中「去听歌」、
  把绿色专辑封面当按钮无限误点、倒计时没结束就点 X 放弃奖励
