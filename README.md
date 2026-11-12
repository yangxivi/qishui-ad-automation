# 汽水音乐「领时长」Skill

连上安卓手机，全自动看广告领汽水音乐免费听歌时长，直到领完为止。无需写死设备号或坐标，跨设备、跨分辨率通用。

## 一句话安装（复制发给你的 AI）

> 从这个 GitHub 仓库安装 WorkBuddy Skill：https://github.com/yangxivi/qishui-ad-automation —— 请 clone 到 `~/.workbuddy/skills/qishui-ad-automation/`（Windows 为 `C:/Users/<用户名>/.workbuddy/skills/qishui-ad-automation/`），然后按 `SKILL.md` 执行。装好后连上手机，帮我把汽水音乐的时长领了。

仓库根目录本身就是 Skill 目录（`SKILL.md` + `scripts/automate.py`），clone 完即被自动识别，不需要解压或改配置。

## 手动安装

```bash
git clone https://github.com/yangxivi/qishui-ad-automation.git ~/.workbuddy/skills/qishui-ad-automation/
```

Windows：

```bat
git clone https://github.com/yangxivi/qishui-ad-automation.git "%USERPROFILE%\.workbuddy\skills\qishui-ad-automation"
```

## 前置条件

1. 手机 USB 连电脑，开启「USB 调试」并授权本机
2. 已安装并登录汽水音乐（包名 `com.luna.music`）
3. 手机保持亮屏，建议临时关闭自动锁屏
4. 电脑有 adb（WorkBuddy 自带或系统 PATH 中）；Windows 上 adb 无法枚举 USB 时脚本会自动切 `ADB_LIBUSB=0`

## 运行

```bash
python scripts/automate.py            # 无限循环；无广告时挂机 5 分钟再试
python scripts/automate.py --max-idle 6   # 最多挂机 6 轮
python scripts/automate.py --no-idle      # 无广告直接退出
```

日志：`scripts/automate.log`。首次运行会自动安装 Pillow。

## 行为

- 看到绿色按钮就点（领时长 / 继续观看 / 领取奖励），事件驱动，不依赖固定广告时长
- 广告结束点右上角「领取成功 ✕」揭开弹窗，再点「领取奖励」继续下一轮
- 一旦跳转直播间，第一时间点右上角 X 退出
- 当前无新视频：点右上角白色 X 返回福利页重试；仍没有则挂机 5 分钟后再试

## 文件

| 文件 | 说明 |
| --- | --- |
| `SKILL.md` | Skill 描述与执行约定（WorkBuddy 读取） |
| `scripts/automate.py` | 自动化主程序 |

仅用于本人已登录账号的福利领取，请遵守 App 使用条款。
