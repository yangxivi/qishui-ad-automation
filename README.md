# 汽水音乐「领时长」Skill

连上安卓手机，**像素快路径 + 轻量 OCR 文字兜底**，识别到关键词/特征就直接点，
无人值守完成「领时长 → 看激励视频 → 领取奖励 → 下一轮」循环。
Agent 不参与逐帧决策，只负责启动、等结束、如实回报。

## 一句话安装

```
从这个 GitHub 仓库安装 WorkBuddy Skill：https://github.com/yangxivi/qishui-ad-automation —— 请 clone 到 ~/.workbuddy/skills/qishui-ad-automation/（Windows 为 C:/Users/<用户名>/.workbuddy/skills/qishui-ad-automation/），运行 scripts/setup_ocr.py，然后按 SKILL.md 执行。
```

手动：

```bash
git clone https://github.com/yangxivi/qishui-ad-automation.git ~/.workbuddy/skills/qishui-ad-automation/
python ~/.workbuddy/skills/qishui-ad-automation/scripts/setup_ocr.py
python ~/.workbuddy/skills/qishui-ad-automation/scripts/setup_ocr.py --check
```

## 轻量 OCR 引擎

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
4. Python 3.9+ 与 Pillow；adb 缺失时把官方 platform-tools 解压到
   `~/.workbuddy/binaries/platform-tools/`

## 功能特性

- 自动点击「领时长 / 继续领」入口按钮，打开视频或直播广告
- 视频广告：等待倒计时结束 → 自动关闭 → 点击「领取奖励」→ 自动进入下一广告
- 直播广告：5 秒倒计时内自动点击「取消」，避免误入直播间
- 直播间容错：万一进入直播间，自动定位右上角 X 退出，并处理「退出不看了」推荐弹窗
- 自动处理「坚持退出」免费解锁弹窗（点击「继续观看 / 领取奖励」继续）
- 额外容错：「当前无新视频」遮罩、开屏广告「跳过」、MIUI「启动应用」确认（点拒绝）、
  桌面/未知界面自动拉回 App
- 广告主 CTA 全部进黑名单，永不误点
- 可设置广告数量上限与时长上限，到达后自动停止
- 内置 GUI 控制面板（本地网页版，零第三方依赖、无需 tkinter）：可视化配置所有参数 + 实时日志 + 统计
- 调试模式：保存带 OCR 标注和点击位置的截图，便于排查

## 运行

```bash
python scripts/automate_fast.py --max-ads 120 --max-seconds 3600 --target-day 31  # 主程序（推荐）
python scripts/automate_fast.py --max-ads 5 --debug                               # 调试标注截图
python scripts/gui.py                                                             # 本地网页控制面板，自动开浏览器 127.0.0.1:8765
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

倒计时是 App 强制的（18~39 秒），跳过就没有奖励，无法压缩；
优化掉的是逐帧 OCR 进程、二次截图与冗余等待（轮询 2s → 0.35s）。

## 实测记录（2026-11-12，Redmi K70E / 1220×2712）

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
  不再无效空转。2026-11-12 晚实测从 8 天领到 **16 天**（截图核对），当晚未能到 31 天，
  非脚本故障；广告池通常隔一段时间或次日恢复。

## 两点如实说明

- 「领时长」是**阶梯解锁**：每多一天需要再看 2–4 个视频，没有「当天领完」的硬终点，
  请用 `--max-ads` / `--max-seconds` 设停止点。
- 自动看激励广告可能违反汽水音乐使用条款，存在账号限制风险；仅建议用于本人账号。

## 文件

`SKILL.md` · `scripts/setup_ocr.py` · `scripts/ocr_engine.py` · `scripts/win_ocr.ps1` ·
`scripts/automate_fast.py`（主程序）· `scripts/automate_ocr.py`（OCR 决策表）·
`scripts/automate_fixed.py`（像素工具/回退）· `scripts/gui.py`（本地网页面板）·
`scripts/models/`（可选 ONNX 模型）· `scripts/stats.json` · `scripts/debug/`
