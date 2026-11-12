# 汽水音乐「领时长」自动领取

**WorkBuddy Skill · 开箱即用**

连上手机，说一句「领时长」，剩下的全自动 —— 看广告、领奖励、循环到领完。

无需写死设备号、坐标或 adb 路径，跨设备、跨分辨率通用；自动避开直播间跳转，没广告时退出重试并挂机等待后继续。

公开仓库：**https://github.com/yangxivi/qishui-ad-automation**

---

## ⭐ 最省事：一句话发给 AI 自动装

把下面这句话连同 GitHub 链接发给支持 Skill 的 AI，它会自动 clone 装好，**不用解压、不用配置**：

```
从这个 GitHub 仓库安装 WorkBuddy Skill：https://github.com/yangxivi/qishui-ad-automation
请 clone 到 ~/.workbuddy/skills/qishui-ad-automation/（Windows 为 C:/Users/<用户名>/.workbuddy/skills/qishui-ad-automation/），然后按 SKILL.md 执行。装好后连上手机，帮我把汽水音乐的时长领了。
```

> 仓库根目录本身就是 Skill 目录（`SKILL.md` + `README.md` + `scripts/automate.py`），clone 完即被 WorkBuddy 自动识别加载。

---

## 下载 Skill 安装包

`qishui-ad-automation.zip` · 约 9 KB · 含 `SKILL.md` + `README.md` + 自动化脚本。

- 在线下载页（点「下载安装包」）：https://qishui-duration-skill.app.workbuddy.host/?sharecode=DPDU6UMDWK
- 或直接取仓库压缩包：https://github.com/yangxivi/qishui-ad-automation/archive/refs/heads/main.zip （解压后把 `qishui-ad-automation-main/` 改名为 `qishui-ad-automation/`）

---

## 三步装好

1. **解压**下载得到的 zip，得到 `qishui-ad-automation/` 文件夹
   —— 里面是 `SKILL.md` 和 `scripts/automate.py`，无需安装任何依赖。
2. **放到 skills 目录**
   - Windows：`C:/Users/你的用户名/.workbuddy/skills/`
   - macOS / Linux：`~/.workbuddy/skills/`

   WorkBuddy 会自动识别并加载这个 Skill。
3. **手机连上电脑，打开汽水音乐**，然后直接说「帮我把汽水音乐的时长领了」
   —— Skill 会自动接管，全程不用盯着屏幕。

### 等价的手动 clone 命令

```bash
git clone https://github.com/yangxivi/qishui-ad-automation.git ~/.workbuddy/skills/qishui-ad-automation/
```

Windows：

```bat
git clone https://github.com/yangxivi/qishui-ad-automation.git "%USERPROFILE%\.workbuddy\skills\qishui-ad-automation"
```

---

## 也可以直接跑脚本

不想等 AI 调用？进入 `scripts/` 目录直接运行：

```bash
# 默认：无限循环，没广告时挂机 5 分钟后重试
python automate.py

# 最多挂机 6 轮后自动停止
python automate.py --max-idle 6

# 自定义挂机时长（秒）
python automate.py --idle-seconds 600

# 没广告就直接退出，不挂机
python automate.py --no-idle
```

从仓库根目录运行则写成 `python scripts/automate.py`（参数相同）。

进度实时写入 `scripts/automate.log`；按 **Ctrl+C** 随时停止。首次运行会自动 `pip install Pillow`、自动定位 adb。

---

## 内置能力

| | 能力 | 说明 |
| --- | --- | --- |
| ✓ | **换电脑直接用** | 不写死设备号、坐标、adb 路径；分辨率与按钮位置自动探测 |
| ✓ | **看到按钮就点** | 自动扫描并点击绿色按钮：领时长 / 继续观看 / 领取奖励 |
| ✓ | **自动避开直播间** | 一旦跳转直播间，第一时间点右上角 X 退出，不耽误领时长 |
| ✓ | **没广告会等待** | 「当前无新视频」时退出重试；仍没有就挂机 5 分钟后再试 |
| ✓ | **时长不固定也不怕** | 纯事件驱动，不依赖固定广告秒数，长短视频都能跑 |
| ✓ | **领完自动停** | 福利页再无可领入口时判定完成，不会无限空转 |

### 运行机制

1. **直播间优先退出**：检测到 `LunaDefaultLivePlayerActivity` 立即点右上角 X 退出（含「退出不看了」面板兜底）
2. **绿按钮全屏扫描**：自动定位并点击绿色按钮（领时长 / 继续观看 / 领取奖励），看到就点
3. **广告结束态**：点「领取成功 ✕」胶囊揭开弹窗 → 点「领取奖励」继续下一轮
4. **无新视频**：点右上角白色 X 退出 → 回福利页重试
5. **福利页无入口**：挂机 5 分钟 → 重进汽水音乐重试（`--max-idle` 可限制总轮数）
6. 全程事件驱动，不依赖固定广告时长

---

## 使用前请确认

- 手机已用**数据线**连接电脑（不是只充电的线），并在弹窗中点了「允许 USB 调试」
- 已安装并登录汽水音乐（包名 `com.luna.music`）
- 手机保持**亮屏**，建议临时关闭自动锁屏 —— 锁屏会让模拟点击失效
- 电脑上有 adb：WorkBuddy 自带，或系统已装 Android 平台工具（脚本会自动找）

> ⚠️ 部分 Windows 环境 adb 默认后端无法枚举 USB，脚本会自动切 legacy 后端（`ADB_LIBUSB=0`），无需手动设置。

> 仅供本人账号的福利领取使用，请遵守汽水音乐的用户条款。若当天广告已放完，脚本按设定挂机等待属正常行为（可用 `--max-idle` 设小值避免长期占用）。

---

## 文件

| 文件 | 说明 |
| --- | --- |
| `SKILL.md` | Skill 描述与执行约定（WorkBuddy 读取） |
| `README.md` | 本说明（安装、运行、能力、注意事项） |
| `scripts/automate.py` | 自动化主程序，自包含，无第三方服务与密钥 |

---

**曦微 · WorkBuddy Skill　|　连上手机，全程自动领取，不用管**
