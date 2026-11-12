#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽水音乐「领时长」无人值守自动领取  —— 通用版（跨设备 / 跨分辨率）
================================================================
核心能力：
  * 自动定位 adb（WorkBuddy 自带或系统 PATH / Android SDK）
  * 自动选择已授权的安卓设备（无需写死设备号）
  * 自动探测屏幕分辨率，所有关键坐标用「相对比例」计算
  * 绿色按钮（领时长 / 继续观看 / 领取奖励）全屏扫描自动定位，不依赖固定坐标
  * 直播间（LunaDefaultLivePlayerActivity）第一时间点 X 退出
  * 无广告视频时：点右上角 X 返回 -> 重试；连续没有则挂机 5 分钟后再试
  * 福利页无领时长入口时：挂机 5 分钟重进重试（直到领完 / 当天无广告）

用法：
  python automate.py                # 默认：无限循环挂机重试
  python automate.py --max-idle 6   # 最多挂机 6 轮（每轮 5 分钟）后停止
  python automate.py --idle-seconds 600  # 挂机时长改为 10 分钟
  python automate.py --no-idle      # 无广告时直接退出，不挂机

前置：
  * 手机 USB 调试已开启并授权本机
  * 已安装并登录汽水音乐（com.luna.music）
  * 手机保持亮屏、不要锁屏
"""
import os, sys, time, subprocess, argparse
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "automate.log")


def log(*a):
    s = " ".join(str(x) for x in a)
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), s)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------
# adb / 设备
# ----------------------------------------------------------------------
def find_adb():
    import shutil
    cands = []
    p = shutil.which("adb")
    if p:
        cands.append(p)
    home = os.path.expanduser("~")
    for rel in [
        ".workbuddy/binaries/platform-tools/adb",
        ".workbuddy/binaries/platform-tools/adb.exe",
        "Android/Sdk/platform-tools/adb",
        "Android/Sdk/platform-tools/adb.exe",
        "AppData/Local/Android/Sdk/platform-tools/adb.exe",
        "android-sdk/platform-tools/adb",
    ]:
        cands.append(os.path.join(home, rel))
    if os.name == "nt":
        # os.getlogin() 在无控制台登录会话的机器上会抛 OSError，必须兜底
        try:
            user = os.getlogin()
        except Exception:
            user = os.environ.get("USERNAME", "")
        if user:
            cands.append(r"C:/Users/%s/.workbuddy/binaries/platform-tools/adb.exe" % user)
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


ADB = find_adb()
if not ADB:
    log("!! 未找到 adb。请确认已安装 Android 平台工具，或 WorkBuddy 自带 adb 存在。")
    sys.exit(2)

DEVICE = None


class _EmptyResult:
    returncode = 1
    stdout = b""
    stderr = b""


def rb(args, timeout=60, tries=1):
    base = [ADB]
    if DEVICE:
        base += ["-s", DEVICE]
    else:
        base += ["-d"]
    last = _EmptyResult()
    for _ in range(tries):
        try:
            last = subprocess.run(base + args, capture_output=True, timeout=timeout)
            if last.returncode == 0:
                return last
        except (subprocess.TimeoutExpired, OSError):
            pass
        time.sleep(1)
    return last


def list_devices():
    out = subprocess.run([ADB, "devices", "-l"], capture_output=True, timeout=30).stdout.decode(errors="replace")
    devs = []
    for line in out.splitlines():
        if "offline" in line or "unauthorized" in line:
            continue
        if "device" in line:
            parts = line.split()
            if parts and parts[0] not in ("List",):
                devs.append(parts[0])
    return devs


def ensure_device():
    global DEVICE
    devs = list_devices()
    if devs:
        DEVICE = devs[0]
        return True
    # 部分 Windows 环境 adb 37 默认 libusb 后端无法枚举 USB，切 legacy 后端重试
    if os.environ.get("ADB_LIBUSB") != "0":
        os.environ["ADB_LIBUSB"] = "0"
        devs = list_devices()
        if devs:
            DEVICE = devs[0]
            return True
    return False


def diagnose_connection():
    out = subprocess.run([ADB, "devices", "-l"], capture_output=True, timeout=30).stdout.decode(errors="replace")
    if "unauthorized" in out:
        log("提示：检测到设备但未授权，请在手机上点击「允许 USB 调试」弹窗。")
    elif "offline" in out:
        log("提示：设备 offline，请重新插拔 USB 或重启手机 USB 调试。")
    else:
        log("提示：未检测到任何设备。请检查：① USB 数据线连接牢固；② 手机已开启「USB 调试」；③ 手机亮屏并在弹窗点「允许」。")


# ----------------------------------------------------------------------
# 屏幕
# ----------------------------------------------------------------------
W, H = 1220, 2712  # 运行时更新


def update_resolution():
    global W, H
    out = rb(["shell", "wm", "size"]).stdout.decode(errors="replace")
    for line in out.splitlines():
        if "size" in line:
            try:
                s = line.split(":")[-1].strip()
                w, h = s.split("x")
                W, H = int(w), int(h)
            except Exception:
                pass
    return W, H


def rx(f):
    return int(W * f)


def ry(f):
    return int(H * f)


def shot(name="auto_shot.png"):
    try:
        rb(["shell", "screencap", "-p", "/sdcard/qs_auto.png"])
        time.sleep(0.4)
        data = rb(["exec-out", "cat", "/sdcard/qs_auto.png"]).stdout
        with open(name, "wb") as f:
            f.write(data)
        return data
    except Exception as e:
        log("shot err", e)
        return b""


def tap(x, y):
    rb(["shell", "input", "tap", str(int(x)), str(int(y))])
    time.sleep(0.3)


def keyev(code):
    rb(["shell", "input", "keyevent", str(code)])


def fg_activity():
    try:
        out = rb(["shell", "dumpsys", "window", "|", "grep", "mCurrentFocus"]).stdout.decode(errors="replace")
        return out.strip().split()[-1]
    except Exception:
        return ""


# ----------------------------------------------------------------------
# 图像分析（绿按钮 / 白色X / 胶囊）
# ----------------------------------------------------------------------
def load_im(path):
    try:
        from PIL import Image
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def is_green(p):
    r, G, b = p
    return G > 200 and G > r + 35 and G > b + 25


def is_white(p):
    r, g, b = p
    return r > 210 and g > 210 and b > 210


def best_green_cluster(im, x0f, x1f, y0f, y1f, min_area=160):
    x0, x1 = int(W * x0f), int(W * x1f)
    y0, y1 = int(H * y0f), int(H * y1f)
    px = im.load()
    pts = []
    step = 3
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            try:
                if is_green(px[x, y]):
                    pts.append((x, y))
            except Exception:
                pass
    if len(pts) < min_area:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2, len(pts))


def white_x(im, x0f, x1f, y0f, y1f, min_area=40):
    x0, x1 = int(W * x0f), int(W * x1f)
    y0, y1 = int(H * y0f), int(H * y1f)
    px = im.load()
    pts = []
    step = 2
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            try:
                if is_white(px[x, y]):
                    pts.append((x, y))
            except Exception:
                pass
    if len(pts) < min_area:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2)


# 关键区域（比例，跨分辨率通用）
GREEN_REGION = (0.20, 0.85, 0.45, 0.62)   # 中下部：继续观看 / 领取奖励
LING_REGION = (0.55, 0.95, 0.33, 0.42)    # 中上部：福利页「领时长」
WHITEX_REGION = (0.85, 1.0, 0.0, 0.07)    # 右上角：广告/弹窗退出白X


# ----------------------------------------------------------------------
# 直播间退出
# ----------------------------------------------------------------------
def exit_live_room():
    log(">>> 检测到直播间，立即退出")
    for _ in range(8):
        if "LivePlayer" not in fg_activity():
            log("<<< 已退出直播间")
            return True
        tap(rx(0.945), ry(0.072))  # 直播间右上角 X
        time.sleep(1.5)
        if "LivePlayer" not in fg_activity():
            log("<<< X退出成功")
            return True
        tap(rx(0.20), ry(0.366))  # 「退出不看了」
        time.sleep(1.5)
        if "LivePlayer" not in fg_activity():
            log("<<< 退出不看了成功")
            return True
        keyev(4)  # 系统返回
        time.sleep(1.5)
    if "LivePlayer" in fg_activity():
        log("!!! 退出直播间失败，回桌面重进")
        keyev(3)
        time.sleep(2)
        rb(["shell", "am", "start", "-n", "com.luna.music/com.luna.biz.main.main.MainActivity"])
        time.sleep(4)
        return False
    return True


def relaunch():
    rb(["shell", "am", "start", "-n", "com.luna.music/com.luna.biz.main.main.MainActivity"])
    time.sleep(4)


# ----------------------------------------------------------------------
# 主循环
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-idle", type=int, default=999, help="无广告时最多挂机轮数（每轮=idle-seconds），默认几乎无限")
    ap.add_argument("--idle-seconds", type=int, default=300, help="挂机时长（秒），默认 300=5 分钟")
    ap.add_argument("--no-idle", action="store_true", help="无广告时直接退出，不挂机")
    args = ap.parse_args()

    if not ensure_device():
        log("!! 未检测到已授权的安卓设备。")
        diagnose_connection()
        sys.exit(3)
    log("==== 启动：设备 %s  adb=%s ====" % (DEVICE, ADB))
    update_resolution()
    log("分辨率 %dx%d" % (W, H))
    try:
        import PIL  # noqa
    except Exception:
        log("安装 Pillow ...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "Pillow"], timeout=240)

    cap_cnt = 0        # 广告页连续无绿钮计数（用于节流点胶囊）
    no_ad_cnt = 0      # 无新视频计数
    empty_cnt = 0      # 福利页空计数
    idle_rounds = 0    # 已挂机轮数

    try:
        for cycle in range(1, 20000):
            act = fg_activity()

            # 1) 直播间 —— 最高优先级，第一时间退出
            if "LivePlayer" in act:
                exit_live_room()
                cap_cnt = no_ad_cnt = empty_cnt = 0
                continue

            # 2) 广告流程 / 福利页
            if "ExcitingVideo" in act or "MainActivity" in act:
                data = shot("auto_shot.png")
                im = load_im("auto_shot.png") if data else None
                if im is None:
                    time.sleep(2)
                    continue

                # 绿按钮优先（领时长 / 继续观看 / 领取奖励）
                g_btn = best_green_cluster(im, *GREEN_REGION) or best_green_cluster(im, *LING_REGION)
                if g_btn:
                    tap(g_btn[0], g_btn[1])
                    log("[btn] 点绿按钮 (%d,%d) area=%d" % (g_btn[0], g_btn[1], g_btn[2]))
                    cap_cnt = no_ad_cnt = empty_cnt = 0
                    time.sleep(2)
                    continue

                # 福利页无绿钮 -> 当天可能已领完 / 无任务
                if "MainActivity" in act:
                    empty_cnt += 1
                    if args.no_idle:
                        log("==== 福利页无任务 (--no-idle)，退出 ====")
                        break
                    if empty_cnt >= 3:
                        idle_rounds += 1
                        if idle_rounds > args.max_idle:
                            log("==== 已挂机 %d 轮仍无广告，停止 ====" % idle_rounds)
                            break
                        log("==== 福利页无任务，挂机 %ds (第%d轮) ====" % (args.idle_seconds, idle_rounds))
                        time.sleep(args.idle_seconds)
                        relaunch()
                        cap_cnt = no_ad_cnt = empty_cnt = 0
                    else:
                        time.sleep(3)
                    continue

                # 广告页：无绿钮 -> 节流点胶囊 / 退无新视频
                cap_cnt += 1
                no_ad_cnt += 1
                if no_ad_cnt >= 3:
                    # 持续无绿钮：判定「当前无新视频」，点右上角白X退出 -> 回福利页重试
                    wx = white_x(im, *WHITEX_REGION)
                    if wx:
                        tap(wx[0], wx[1])
                        log("[x] 无新视频，点右上角白X (%d,%d) 退出" % (wx[0], wx[1]))
                    else:
                        keyev(4)
                        log("[x] 无新视频，系统返回")
                    no_ad_cnt = 0
                    cap_cnt = 0
                    time.sleep(2)
                    continue
                if cap_cnt % 3 == 0:
                    # 结束态：点「领取成功」胶囊揭弹窗
                    tap(rx(0.85), ry(0.063))
                    log("[cap] 点领取成功胶囊（揭弹窗）")
                    time.sleep(2)
                    continue
                log("[wait] 广告播放中/等待 cap=%d" % cap_cnt)
                time.sleep(2)
                continue

            # 3) 其他 Activity（微信/桌面/异常）-> 回汽水音乐
            log("[other] 意外界面 %s -> 回汽水音乐" % act[:50])
            relaunch()
            cap_cnt = no_ad_cnt = empty_cnt = 0
    except KeyboardInterrupt:
        log("==== 用户中断，停止 ====")
        sys.exit(0)

    log("==== 循环结束 ====")


if __name__ == "__main__":
    main()
