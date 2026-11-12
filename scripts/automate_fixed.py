#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽水音乐「领时长」修正版 —— 状态机驱动，替代 automate.py 的颜色盲扫。

原版 automate.py 的三个实测缺陷（2026-11-12 在 Redmi K70E / 1220x2712 上验证）：
  1) 福利页优先扫 GREEN_REGION(y 0.45-0.62)，先点中「去听歌」而不是「领时长」，
     直接跳到音乐播放页；
  2) 播放页的绿色专辑封面被判成绿色按钮，在同一坐标无限误点（实测 2 分钟点了 23 次）；
  3) 激励视频倒计时期间扫不到绿按钮，约 9 秒就点右上角 X 退出，放弃奖励。

本版按真实流程做状态判别：
  福利页「领时长」 -> 广告倒计时(pill 有绿色小图标) -> 「领取成功」(pill 无绿)
  -> 点右上胶囊揭弹窗 -> 「领取奖励」(中央大片亮绿) -> 下一轮

安全约束：只点「领时长 / 领取成功胶囊 / 领取奖励」三处，
绝不点底部广告主 CTA（了解更多 / 前往微保），不进直播间，全程有硬上限。
"""
import os
import sys
import time
import subprocess
import argparse
from datetime import datetime

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow：python -m pip install Pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "automate_fixed.log")
SHOT = os.path.join(HERE, "_fixed_shot.png")


def log(*a):
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), " ".join(str(x) for x in a))
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def find_adb():
    import shutil
    cands = [shutil.which("adb")]
    home = os.path.expanduser("~")
    for rel in [
        ".workbuddy/binaries/platform-tools/adb.exe",
        ".workbuddy/binaries/platform-tools/adb",
        "AppData/Local/Android/Sdk/platform-tools/adb.exe",
        "Android/Sdk/platform-tools/adb.exe",
    ]:
        cands.append(os.path.join(home, rel))
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


ADB = find_adb()
if not ADB:
    sys.exit("未找到 adb")


def rb(args, timeout=60):
    try:
        return subprocess.run([ADB] + args, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        class _R:
            returncode = 1
            stdout = b""
            stderr = b""
        return _R()


def focus():
    out = rb(["shell", "dumpsys", "window", "|", "grep", "mCurrentFocus"]).stdout.decode(errors="replace")
    s = out.strip()
    return s.split()[-1] if s else ""


def on_welfare_page():
    """用 UI 层级文字确认确实在「福利中心」，避免把播放页误判成福利页。"""
    r = rb(["shell", "uiautomator", "dump", "/sdcard/qs_fx_ui.xml"], timeout=40)
    if b"dumped to" not in r.stdout:
        return None  # 无法判定（动画中）
    xml = rb(["exec-out", "cat", "/sdcard/qs_fx_ui.xml"], timeout=40).stdout.decode(errors="replace")
    return ("福利中心" in xml) or ("赚时长" in xml)


def shot():
    rb(["shell", "screencap", "-p", "/sdcard/qs_fx.png"])
    data = rb(["exec-out", "cat", "/sdcard/qs_fx.png"], timeout=60).stdout
    if not data.startswith(b"\x89PNG"):
        return None
    with open(SHOT, "wb") as f:
        f.write(data)
    try:
        return Image.open(SHOT).convert("RGB")
    except Exception:
        return None


def is_green(p):
    r, g, b = p[:3]
    return g > 180 and g > r + 30 and g > b + 20


def green_stats(im, box, step=3):
    """返回 (亮绿像素数, 质心)。box 为 (x0,y0,x1,y1) 绝对像素。"""
    px = im.load()
    x0, y0, x1, y1 = box
    pts = []
    for y in range(y0, min(y1, im.height), step):
        for x in range(x0, min(x1, im.width), step):
            try:
                if is_green(px[x, y]):
                    pts.append((x, y))
            except Exception:
                pass
    if not pts:
        return 0, None
    return len(pts), (sum(p[0] for p in pts) // len(pts), sum(p[1] for p in pts) // len(pts))


def tap(x, y, why=""):
    rb(["shell", "input", "tap", str(int(x)), str(int(y))])
    log("[tap] %s (%d,%d)" % (why, x, y))
    time.sleep(0.6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ads", type=int, default=5, help="最多领取轮数，默认 5")
    ap.add_argument("--max-seconds", type=int, default=600, help="总运行硬上限（秒），默认 600")
    args = ap.parse_args()

    devs_out = rb(["devices"]).stdout.decode(errors="replace")
    ok_devs = []
    for line in devs_out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            ok_devs.append(parts[0])
    if not ok_devs:
        log("!! 没有已授权的安卓设备：", devs_out.strip().replace("\n", " | "))
        return 3
    log("设备 %s 已授权" % ok_devs[0])

    out = rb(["shell", "wm", "size"]).stdout.decode(errors="replace")
    W, H = 1220, 2712
    for line in out.splitlines():
        if "size" in line:
            try:
                w, h = line.split(":")[-1].strip().split("x")
                W, H = int(w), int(h)
            except Exception:
                pass
    log("==== 启动 %dx%d adb=%s 上限 %d 轮 / %ds ====" % (W, H, ADB, args.max_ads, args.max_seconds))

    R = lambda x0, y0, x1, y1: (int(W * x0), int(H * y0), int(W * x1), int(H * y1))
    LING_BOX = R(0.75, 0.34, 0.97, 0.42)    # 福利页「领时长」
    PILL_BOX = R(0.58, 0.04, 0.98, 0.085)   # 右上角倒计时胶囊（绿色小图标）
    REWARD_BOX = R(0.28, 0.47, 0.72, 0.60)  # 弹窗「领取奖励」
    WELFARE_TAB = (int(W * 0.70), int(H * 0.90))

    t0 = time.time()
    ads = 0
    last_state = ""
    idle_cycles = 0
    no_ad_taps = 0   # 连续点了「领时长」却没进广告页的次数（当天无广告了）
    other_cnt = 0    # 连续落在无关界面的次数

    while time.time() - t0 < args.max_seconds:
        if ads >= args.max_ads:
            log("==== 达到领取轮数上限 %d，停止 ====" % ads)
            break

        act = focus()

        # 1) 直播间：点右上角 X 退出；用返回键容易一路退回桌面/别的应用
        if "LivePlayer" in act:
            log("[live] 进入直播间，点右上角 X 退出")
            tap(int(W * 0.945), int(H * 0.072), why="直播间 X")
            time.sleep(1.2)
            if "LivePlayer" in focus():
                log("[live] X 未生效，补一次返回键")
                rb(["shell", "input", "keyevent", "4"])
                time.sleep(1.2)
            continue

        # 2) 广告页
        if "ExcitingVideo" in act:
            no_ad_taps = 0
            other_cnt = 0
            im = shot()
            if im is None:
                time.sleep(2)
                continue
            pill_n, _ = green_stats(im, PILL_BOX, 2)
            reward_n, reward_c = green_stats(im, REWARD_BOX, 3)

            if reward_n > 2000 and reward_c:
                # 「领取奖励」弹窗 -> 领取，进入下一轮
                tap(*reward_c, why="领取奖励")
                ads += 1
                log("==== 第 %d 轮奖励已领取 ====" % ads)
                last_state = "reward"
                idle_cycles = 0
                time.sleep(2)
                continue

            if pill_n > 25:
                # 倒计时中（右上角绿色小图标仍在），耐心等，绝不点 X
                if last_state != "countdown":
                    log("[ad] 倒计时中，等待结束 …")
                last_state = "countdown"
                idle_cycles = 0
                time.sleep(2)
                continue

            # 右上角无绿标 = 「领取成功」态 -> 点胶囊揭开弹窗
            if last_state != "capsule":
                log("[ad] 检测到「领取成功」，点右上角胶囊")
            tap(int(W * 0.85), int(H * 0.063), why="领取成功胶囊")
            last_state = "capsule"
            idle_cycles += 1
            if idle_cycles > 20:
                log("!! 胶囊点击无响应，停止以免误点")
                break
            time.sleep(1.5)
            continue

        # 3) App 主页：必须确认在福利中心
        if "MainActivity" in act:
            welfare = on_welfare_page()
            if welfare is None:
                time.sleep(1.5)
                continue
            if welfare is False:
                log("[nav] 不在福利中心，点底部「福利」返回")
                tap(*WELFARE_TAB, why="福利 tab")
                time.sleep(2)
                continue

            im = shot()
            if im is None:
                time.sleep(2)
                continue
            ling_n, ling_c = green_stats(im, LING_BOX, 2)
            if ling_n > 1500 and ling_c:
                no_ad_taps += 1
                if no_ad_taps > 3:
                    log("==== 连续点了 3 次「领时长」都没进广告页，判定当天暂无广告，停止 ====")
                    break
                tap(*ling_c, why="领时长")
                last_state = "ling"
                idle_cycles = 0
                time.sleep(2)
                continue

            idle_cycles += 1
            if idle_cycles >= 3:
                log("==== 福利页已无「领时长」入口，额度已领完，停止 ====")
                break
            time.sleep(2)
            continue

        # 4) 其他界面 -> 回 App；连续多次仍回不来就停，避免空转
        other_cnt += 1
        if other_cnt > 6:
            log("==== 连续 %d 次落在无关界面，停止 ====" % other_cnt)
            break
        log("[other] %s -> 回汽水音乐" % act[:60])
        rb(["shell", "am", "start", "-n", "com.luna.music/com.luna.biz.main.main.MainActivity"])
        time.sleep(3)

    log("==== 结束：共领取 %d 轮，用时 %ds ====" % (ads, int(time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
