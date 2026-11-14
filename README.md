# 汽水音乐「领时长」Skill

连上安卓手机，**像素快路径 + 无障碍树（AX）文字定位 + 轻量 OCR 兜底**，
识别到关键词/特征就直接点，无人值守完成「领时长 → 看激励视频 → 领取奖励 → 下一轮」循环。
Agent 不参与逐帧决策，只负责启动、等结束、如实回报。

> **2026-11-14 更新**：默认引擎改为**无障碍树优先**，OCR 降级为兜底。
> 思路来自 [vercel-labs/agent-desktop](https://github.com/vercel-labs/agent-desktop)，
> 但它不支持 Android，因此是把方法论移植到 adb 侧，详见「定位引擎」。

## 一句话安装

```
从这个 GitHub 仓库安装 WorkBuddy Skill：https://github.com/yangxivi/qishui-ad-automation —— 请 clone 到 ~/.workbuddy/skills/qishui-ad-automation/（Windows 为 C:/Users/<用户名>/.workbuddy/skills/qishui-ad-automation/），运行 scripts/setup_ocr.py，然后按 SKILL.md 执行。
```

手动：

```bash
git clone https://github.com/yangxivi/qishui-ad-automation.git ~/.workbuddy/skills/qishui-ad-automation/
python ~/.workbuddy/skills/qishui-ad-automation/scripts/setup_ocr.py
python ~/.workbuddy/skills/qishui-ad-automation/scripts/setup_ocr.py --check
python ~/.workbuddy/skills/qishui-ad-automation/scripts/selftest_ax.py   # 离线自测，不需要手机
```

`setup_ocr.py` 只为 OCR 兜底准备；用 `--engine ax` 时完全不需要 OCR。

## 定位引擎（2026-11-14 新增）

[vercel-labs/agent-desktop](https://github.com/vercel-labs/agent-desktop) 的做法是：
读 OS 无障碍树 → 每个元素带 ref → 按 ref 点击 → 再读一次树验证（observe / act / verify），
不靠截图与像素匹配。

**但它不能直接用于本 Skill**：该 CLI 只支持 macOS（AX API）/ Windows（UI Automation）/
Linux（AT-SPI）的**桌面应用**，README 明写 "without screenshots or pixel matching"，
仓库 `skills/` 下也只有 desktop / macos / windows / linux / ffi，**没有 Android 或 adb 支持**。
汽水音乐跑在手机上，够不着。

因此 `scripts/ax_engine.py` 把同一套机制落到安卓侧 ——
`adb shell uiautomator dump` 就是安卓的无障碍树快照：

- `AXSnapshot.capture()` → observe，snapshot_id 为 XML 内容哈希，UI 变化即变化
- 每个节点生成 `@ax<snapshot_id>:eN` 的 ref，含 text / content-desc / resource-id / bounds
- `snap.items()` 转成 `decide()` 同构数据，**直接复用原关键词决策表与黑名单**：
  倒计时优先、广告主 CTA 永不点击等规则完全不变
- `snap.click_ref()` 按 ref 点 bounds 中心；旧 ref 抛 `StaleRef`（对应 `STALE_REF`）
- `snap.verify()` 重新 observe，比较 snapshot_id 判断动作是否生效

主程序用统一观察入口 `probe_items()` 选择引擎：

| `--engine` | 观察方式 | 是否启动 OCR |
|---|---|---|
| `ax` | 仅 `uiautomator` 树 | **否** |
| `auto`（默认） | 树优先，读不到再 OCR | 仅兜底时 |
| `ocr` | 逐帧 OCR | 是 |

像素快路径（绿色按钮质心）仍作为主路径保留，它本来就不依赖 OCR。

**已知限制**：激励视频广告页若由 WebView / 自绘控件渲染，无障碍树里可能没有可点文字节点。
此时 `auto` 自动回退 OCR，`ax` 不猜测、不盲点，靠 `--max-seconds` / `--max-ads` 硬上限停机。
首次上真机建议先 `--engine auto --debug` 观察一轮再决定是否切 `ax`。

若确实要在 PC 上用 agent-desktop 操作桌面应用，另行安装
`npm i -g agent-desktop` 并运行 `agent-desktop skills get desktop`；与本 Skill 的安卓链路无关。

## 轻量 OCR 引擎（仅兜底）

安装脚本按「最轻优先」自动选型，不改系统、不需管理员权限：

- **Windows（默认）**：系统内置 `Windows.Media.Ocr` + `zh-Hans-CN` 中文模型，
  **零下载、零安装、离线、0 MB 额外体积**。
- **非 Windows / `--force-rapidocr`**：`rapidocr-onnxruntime`（PP-OCR ONNX，
  纯 CPU、约 15 MB 模型），模型复制到 `scripts/models/`，Skill 自包含。
- **都不可用**：自动回退像素状态机，功能不残缺。

不用 PaddleOCR / EasyOCR——需拉 PyTorch（1–2 GB）并联网下模型，不叫轻量。

## 前置条件

1. 手机 USB 连电脑，开启「USB 调试」并授权（`adb devices` 状态为 `device`）
2. 已安装并登录汽水音乐（`com.luna.music`）
3. 手机保持亮屏，建议临时关闭自动锁屏
4. Python 3.9+ 与 **Pillow**（主程序顶层就 import，务必先装：`python -m pip install Pillow`）；
   adb 缺失时把官方 platform-tools 解压到 `~/.workbuddy/binaries/platform-tools/`
5. **小米 / Redmi（MIUI / HyperOS）额外必开「USB 调试（安全设置）」**：仅开普通 USB 调试不够，
   `adb shell input tap` 注入点击需要 `INJECT_EVENTS` 权限，而这一项藏在开发者选项里、与「USB 调试」
   是两项独立开关。不开它，`input tap` 会直接抛 `SecurityException: INJECT_EVENTS permission`。
   该开关若为灰色需先登录小米账号 + 插 SIM 卡 + 联网；打开后**拔掉 USB 线重插一次**才生效。
   验证：`adb shell input tap 100 100` 不再报错即通。

## 功能特性

- 自动点击「领时长 / 继续领」入口按钮，打开视频或直播广告
- 视频广告：等待倒计时结束 → 自动关闭 → 点击「领取奖励」→ 自动进入下一广告
- 直播广告：5 秒倒计时内自动点击「取消」，避免误入直播间
- 直播间容错：万一进入直播间，自动定位右上角 X 退出，并处理「退出不看了」推荐弹窗
- 自动处理「坚持退出」免费解锁弹窗（点击「继续观看 / 领取奖励」继续）
- 额外容错：「当前无新视频」遮罩、开屏广告「跳过」、MIUI「启动应用」确认（点拒绝）、
  桌面/未知界面自动拉回 App
- **无障碍树文字定位**：按 text / content-desc / bounds 定位并点击，不再依赖 OCR 读图
- **直播间容错分级**：点右上角 X → 识别并点掉「退出不看了」弹窗 → 返回键 → 拉回福利页断链；
  只认退出类文字，绝不误点「继续观看」
- **防死循环护栏**：领奖准入校验（排除非奖励页 + 12s 内重复绿块）、
  连点「领时长」无响应自动停机、独立直播间连续计数
- 广告主 CTA 全部进黑名单，永不误点
- 可设置广告数量上限与时长上限，到达后自动停止
- 内置 GUI 控制面板（本地网页版，零第三方依赖、无需 tkinter）：可视化配置所有参数 + 实时日志 + 统计
- 调试模式：保存带文字标注和点击位置的截图，便于排查
- `scripts/selftest_ax.py`：9 项离线回归自测，换机器/改代码后无需手机即可验证

## 运行

```bash
# 主程序（默认 --engine auto：无障碍树优先、OCR 兜底）
python scripts/automate_fast.py --max-ads 120 --max-seconds 3600 --target-day 31

# 纯无障碍树，零 OCR
python scripts/automate_fast.py --engine ax --max-ads 120 --max-seconds 3600

# 回到旧版逐帧 OCR
python scripts/automate_fast.py --engine ocr --max-ads 5

python scripts/automate_fast.py --max-ads 5 --debug                               # 调试标注截图
python scripts/gui.py                                                             # 本地网页面板，自动开浏览器 127.0.0.1:8765
python scripts/selftest_ax.py                                                     # 离线回归自测，不需要手机
python scripts/automate_ocr.py --max-ads 5 --dry-run                              # 只打印决策不点屏幕
python scripts/automate_fixed.py --max-ads 5 --max-seconds 480                    # 纯像素状态机（对照/回退）
```

日志 `scripts/automate_fast.log`，统计 `scripts/stats.json`，调试截图 `scripts/debug/`。
**务必带 `--max-ads` / `--max-seconds`**，别用无限挂机。

## 判定表（确定性查表，零逐步推理）

| 识别到 | 动作 |
|---|---|
| `知道了` / `未检测到音乐音量变化` | **最高优先级**：点「知道了」关遮罩，不点「去设置」 |
| `N秒后可领取奖励 ×` | 等待，倒计时中不点 X |
| `取消` | 点，避开直播间 |
| `继续观看` / `退出不看了` | 点，处理退出类弹窗 |
| `领取奖励` | 点它，计入一轮 |
| `领取成功 ×` | 点右上胶囊，揭开弹窗 |
| `领时长` / `继续领` | 点它，起一条广告 |
| `当前无新视频` | 关提示层后重试 |
| `×` / `关闭`（弹窗上下文） | 点关闭；右上角广告 X 除外 |
| 无命中 | 回退像素状态机 |

文字来源由 `--engine` 决定（无障碍树 / OCR），决策表与黑名单两者共用，规则一致。
倒计时是 App 强制的（18~39 秒），跳过就没有奖励，无法压缩；
优化掉的是逐帧 OCR 进程、二次截图与冗余等待（轮询 2s → 0.35s）。

## 实测记录

### 2026-11-12（Redmi K70E / 1220×2712）

- Windows 内置 OCR 在真实画面上稳定识别 `领时长`、`领取成功×`、`领取奖励`、
  `39秒后可领取奖励×`、`坚持退出`、`前往微保`，坐标误差 ≤ 5 px。
- OCR 决策表离线验证 10 类关键词全部映射到正确动作，广告主 CTA 被正确忽略。
- 极速 v2 实机连续领取，自动处理了「直播间误入」「当前无新视频」「MIUI 跳转确认」等异常，
  无误点、无死循环。
- 福利中心「免费听长」由 4 天逐档提升到 16 天（截图核对），每多一天需再看 2–4 个视频。
- **长跑踩坑**：OCR 临时帧最初每帧 `os.remove`，累计删除触发宿主环境的批量删除保护
  （一轮 50 次即强制中断进程，已领 27 轮后被杀）。现改为固定路径覆盖写入、不再删除，
  文件由 `.gitignore` 忽略。
- **遮罩弹窗要优先处理**：小米会在福利页弹「未检测到音乐音量变化」提示，盖住「领时长」按钮。
  已加入 OCR 最高优先级规则点「知道了」（绝不误点「去设置」）；同时修正主页分支顺序，
  OCR 兜底必须先于「福利 tab」文字定位——否则 tab 一命中就 continue，遮罩永远轮不到处理。
- **广告池会耗尽**：连续约 28 轮后广告 SDK 返回「当前无新视频」并反复把用户导流进直播间，
  此时无法继续领取。已加入自动停机：连续无视频 / 累计 12 次直播间且 2 分钟无新奖励即停止，
  不再无效空转。当晚实测从 8 天领到 **16 天**（截图核对），未达 31 天，
  非脚本故障；广告池通常隔一段时间或次日恢复。

### 2026-11-14（同机型，无障碍树引擎）

- 新增 `ax_engine.py` 与 `--engine`，OCR 由默认路径降为兜底；SKILL.md / README 同步。
- 离线自测 9 项全通过：福利页 → `领时长`、倒计时 → 等待、奖励弹窗 → 领取、
  纯广告主 CTA → 不误点、陈旧 ref 拒绝、`ax` 零 OCR、`auto` 回退、`ocr` 不读树。
- 真机 `--engine auto` 长跑：连续领取 30+ 轮无故障，每 10 轮抽查稳定返回 3 个文字节点，
  自动处理「当前无新视频」提示层与直播间跳转；主流程全程命中像素快路径。
- 另修复环境坑：WorkBuddy 自带 Python 3.13 若未装 Pillow，主程序会直接崩，
  现已确认两个解释器均可用并写入前置条件。
- **实机长跑 21 分钟后修掉两个死循环**（截图核对福利中心「免费听长 17 天」）：
  1. 「领奖 → 进直播间 → 点 X → 又领奖」：`rew_n > 900` 只看中央绿块，把残留弹窗 /
     直播间绿按钮误判为「领取奖励」，5~6s 虚假计一轮并刷新 `last_gain_t`、清零
     `live_total`，所有「2 分钟无新奖励」停机条件永不成立；且直播间兜底依赖的
     `other_cnt` 每回主流程都被重置为 0，「退出不看了」弹窗一直没被处理。
     修复：领奖准入 `reward_allowed()`、独立 `live_streak` 分级容错、
     直播间专用 `live_exit_pos()`（只认退出类文字，`decide()` 会优先点「继续观看」）。
  2. 福利页无限点「领时长」：每次点击都把 `no_progress` 清零，连点保护不触发。
     当天广告池耗尽后按钮仍是绿色、点击只弹瞬时 toast，脚本连点了 60+ 次。
     修复：`ling_tap_action()` 三次点击 → 文字兜底 → 明确停机并写入 `stats.json`。
- 12 项离线回归自测覆盖以上两个场景（`python scripts/selftest_ax.py`）。

## 如实说明

- 「领时长」是**阶梯解锁**：每多一天需要再看 2–4 个视频，没有「当天领完」的硬终点，
  请用 `--max-ads` / `--max-seconds` 设停止点。
- 广告池有真实上限，耗尽后应隔一段时间或次日再跑，不要为凑天数无限重试，那只会触发风控。
- `--engine ax` 在广告页无文字节点时不会盲点，可能领不到轮数；默认 `auto` 会自动回退 OCR。
- 自动看激励广告可能违反汽水音乐使用条款，存在账号限制风险；仅建议用于本人账号。

## 文件

`SKILL.md` · `scripts/ax_engine.py`（无障碍树后端）· `scripts/selftest_ax.py`（离线自测）·
`scripts/setup_ocr.py` · `scripts/ocr_engine.py` · `scripts/win_ocr.ps1` ·
`scripts/automate_fast.py`（主程序）· `scripts/automate_ocr.py`（关键词决策表）·
`scripts/automate_fixed.py`（像素工具/回退）· `scripts/gui.py`（本地网页面板）·
`scripts/models/`（可选 ONNX 模型）· `scripts/stats.json` · `scripts/debug/`
