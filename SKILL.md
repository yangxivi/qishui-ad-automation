---
name: qishui-ad-automation
description: 汽水音乐「领时长」福利无人值守自动领取。当用户想用安卓手机自动看广告领取汽水音乐免费听歌时长（如"汽水音乐领时长""自动看广告领时长""汽水音乐福利领时长""帮我把汽水音乐的时长领了"等）时使用。自动连接已授权的安卓设备，点击领时长、观看激励视频广告、领取奖励并循环，直到领完；自动避开直播间跳转，无广告时退出重试并挂机等待后继续。无需写死设备号或坐标，跨设备/跨分辨率通用。
---

# 汽水音乐「领时长」自动领取

通过 adb 驱动已连接的安卓手机，无人值守地完成汽水音乐「领时长」福利循环：
福利页点「领时长」→ 看激励视频广告 → 领取奖励 → 循环，直到领完当天额度。

## 适用场景
- 用户要求自动领取汽水音乐「领时长」福利（看广告得免费听歌时长）
- 已连接安卓手机、已开启 USB 调试并授权、已安装并登录汽水音乐

## 前置条件（务必先确认）
1. 手机 USB 连接电脑，已开启「USB 调试」并在弹窗中**授权本机**（看到设备序列号且状态为 `device`）
2. 已安装并登录汽水音乐（包名 `com.luna.music`）
3. 手机**保持亮屏**（建议临时关闭自动锁屏/休眠，锁屏会使点击失效）
4. adb 可用：WorkBuddy 自带 `~/.workbuddy/binaries/platform-tools/adb`，或系统已装 Android 平台工具
   - 部分 Windows 环境 adb 默认后端无法枚举 USB，脚本会自动切 legacy 后端（`ADB_LIBUSB=0`），无需手动设置

## 执行约定（重要）
当用户表达"领时长 / 自动看广告 / 帮我把时长领了"等意图，且手机已连接时：
**直接运行脚本、后台执行、不要反问、不要逐步确认**。执行后仅回报日志路径与进度。
全程无人值守，用户不需要盯着屏幕。

## 安装（别的电脑 · 一句话即可）
仓库根目录本身就是 Skill 目录，把下面这句话连同链接发给支持 Skill 的 AI 即可自动装好：

> 从这个 GitHub 仓库安装 WorkBuddy Skill：https://github.com/yangxivi/qishui-ad-automation —— 请 clone 到 `~/.workbuddy/skills/qishui-ad-automation/`（Windows 为 `C:/Users/<用户名>/.workbuddy/skills/qishui-ad-automation/`），然后按 `SKILL.md` 执行。装好后连上手机，帮我把汽水音乐的时长领了。

等价的手动命令：
```bash
git clone https://github.com/yangxivi/qishui-ad-automation.git ~/.workbuddy/skills/qishui-ad-automation/
```
无需额外配置；首次运行脚本会自行安装 Pillow、自动定位 adb。

## 使用方式
直接运行脚本即可，adb / 设备 / 屏幕分辨率全部自动探测，关键按钮自动扫描定位：

```bash
# 默认：无限循环；无广告时挂机 5 分钟重试
python scripts/automate.py

# 限制挂机轮数（每轮 = idle-seconds），超过即停止，避免无限挂机
python scripts/automate.py --max-idle 6

# 自定义挂机时长（秒）
python scripts/automate.py --idle-seconds 600

# 无广告时直接退出，不挂机
python scripts/automate.py --no-idle
```

日志实时写入 `scripts/automate.log`，可随时查看进度。

## 运行机制
1. **直播间优先退出**：检测到 `LunaDefaultLivePlayerActivity` 立即点右上角 X 退出（含「退出不看了」面板兜底）
2. **绿按钮全屏扫描**：自动定位并点击绿色按钮（领时长 / 继续观看 / 领取奖励），看到就点
3. **广告结束态**：点「领取成功」胶囊揭开弹窗 → 点「领取奖励」继续下一轮
4. **无新视频**：点右上角白色 X 退出 → 回福利页重试
5. **福利页无入口**：挂机 5 分钟 → 重进汽水音乐重试（`--max-idle` 可限制总轮数）
6. 全程事件驱动，不依赖固定广告时长

## 自包含性
Skill 仅由 `SKILL.md` + `scripts/automate.py` 组成，无第三方服务、无密钥、
无写死设备号或坐标：
- 首次运行自动 `pip install Pillow`
- adb 自动从 WorkBuddy 自带目录或系统 PATH 定位（含 `ADB_LIBUSB=0` 回退）
- 设备、屏幕分辨率、绿色按钮与关闭按钮坐标全部运行时自适应
分发通道：GitHub 仓库 `yangxivi/qishui-ad-automation`（推荐，一句话 clone 即装）；
另有 `qishui-ad-automation.zip` 离线包，解压到 skills 目录即用。

## 注意事项
- 仅用于本人已登录账号的福利领取，请遵守 App 使用条款
- 手机需保持亮屏，锁屏会导致 `input tap` 失效
- 若当天广告已放完，脚本会按设定挂机等待，属正常行为；可用 `--max-idle 0`/小值避免长期占用
- 运行中按 `Ctrl+C` 可随时停止
