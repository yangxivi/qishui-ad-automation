#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽水音乐「领时长」极速稳态引擎 v2 —— 像素快路径 + OCR 文字兜底。

设计原则：识别到关键词/特征就直接点，Agent 不做逐步推理。
  - 常规状态：本地像素特征判定（~30ms/帧），不启动 OCR 进程
  - 卡住 / 新弹窗：Windows 内置 OCR 读文字 -> decide() 查表直接点
  - 广告倒计时是 App 强制的（18~39s），跳过就没有奖励，无法压缩

覆盖状态：
  福利页「领时长 / 继续领」   -> 起一条广告
  视频广告倒计时              -> 等待，绝不提前关
  「领取成功 ×」胶囊          -> 点开奖励弹窗
  「领取奖励」                -> 计入一轮并进入下一广告
  直播广告 5 秒「取消」       -> 点，避免误入直播间
  直播间 /「退出不看了」      -> 右上角 X / 确认退出
  「坚持退出」免费解锁弹窗    -> 点「继续观看」保住奖励
  「当前无新视频」遮罩        -> 点右上角 X 关掉继续
  开屏广告 / MIUI 跳转确认    -> 跳过 / 拒绝
  桌面 / 未知界面             -> 拉回 App

参数：--max-ads 广告数量上限 / --max-seconds 时长上限 / --ocr-every 抽查间隔
      --target-day 目标天数 / --debug 保存带 OCR 标注与点击位置的截图
统计：每轮写 scripts/stats.json，供 GUI 控制面板实时读取。
"""
import os
import sys
import io
import re
import json
import time
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from automate_fixed import ADB, rb, focus, green_stats, tap as do_tap  # noqa: E402

LOG_PATH = os.path.join(HERE, "automate_fast.log")
STATS_PATH = os.path.join(HERE, "stats.json")
DEBUG_DIR = os.path.join(HERE, "debug")

CTX = {}          # main() 里填充分辨率、各锚点、debug 开关
_SEQ = [0]        # 点击序号，用于调试截图命名
_ENGINE = [None]  # OCR 引擎单例（懒加载）


def log(*a):
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), " ".join(str(x) for x in a))
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def write_stats(ads=0, running=True, last=""):
    try:
        data = {
            "ads": ads,
            "elapsed": int(time.time() - CTX.get("t0", time.time())),
            "started": CTX.get("started", ""),
            "target_day": CTX.get("target_day", 31),
            "max_ads": CTX.get("max_ads", 0),
            "running": running,
            "last_action": last,
            "updated": datetime.now().strftime("%H:%M:%S"),
        }
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------- 基础工具
def shot_fast():
    """一次 adb 调用直接拿 PNG 字节流；失败回退两步法。"""
    try:
        d = rb(["exec-out", "screencap", "-p"], timeout=30).stdout
        if d.startswith(b"\x89PNG\r\n\x1a\n"):
            return Image.open(io.BytesIO(d)).convert("RGB")
    except Exception:
        pass
    try:
        rb(["shell", "screencap", "-p", "/sdcard/qs_fast.png"], timeout=30)
        d = rb(["exec-out", "cat", "/sdcard/qs_fast.png"], timeout=30).stdout
        if d.startswith(b"\x89PNG"):
            return Image.open(io.BytesIO(d)).convert("RGB")
    except Exception:
        pass
    return None


def ui_dump():
    """导出 UI 层级文本；动画中失败返回 None。"""
    r = rb(["shell", "uiautomator", "dump", "/sdcard/qs_fast_ui.xml"], timeout=40)
    if b"dumped to" not in r.stdout:
        return None
    return rb(["exec-out", "cat", "/sdcard/qs_fast_ui.xml"], timeout=40).stdout.decode(errors="replace")


def text_pos(xml, target):
    """按文字定位控件中心。找不到返回 None —— 不误触广告 CTA 的关键。"""
    if not xml:
        return None
    for tag in re.findall(r"<node[^>]*>", xml):
        m = re.search(r'text="([^"]*)"', tag)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', tag)
        if m and b and target in m.group(1):
            x0, y0, x1, y1 = map(int, b.groups())
            return ((x0 + x1) // 2, (y0 + y1) // 2)
    return None


def overlay_stats(im):
    """「当前无新视频」遮罩特征：右上角白色 X + 中央区域整体变暗。

    实测 1220x2712：遮罩 174 / 33；正常广告页 66~80 / 123~206；奖励弹窗 0 / 195。
    """
    px = im.load()
    W, H = im.size
    x0, y0, x1, y1 = int(W * .88), int(H * .015), int(W * .98), int(H * .06)
    white = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if r > 195 and g > 195 and b > 195:
                white += 1
    tot = cnt = 0
    for y in range(int(H * .42), int(H * .58), 6):
        for x in range(int(W * .25), int(W * .75), 6):
            r, g, b = px[x, y][:3]
            tot += (r + g + b) // 3
            cnt += 1
    return white, tot // max(cnt, 1)


def ocr_items(im, width=960):
    """懒加载 OCR，返回 [((cx,cy), text, score), ...]。"""
    try:
        if _ENGINE[0] is None:
            from ocr_engine import OCREngine
            _ENGINE[0] = OCREngine(width=width, log=lambda *a: None)
        return _ENGINE[0].read(im, width)
    except Exception as e:
        log("[ocr] 不可用:", str(e)[:100])
        return []


def probe_items(im, width=960):
    """统一观察入口：按 --engine 返回 [((x,y), text, score), ...]。

    ax / auto -> 先读安卓无障碍树（不截图、不启动 OCR 进程）；
    auto      -> 树读不到时回退 OCR；
    ax        -> 绝不启动 OCR（纯无障碍树 / 零截图模式）；
    ocr       -> 保持原来的逐帧 OCR 行为。

    这里移植的是 vercel-labs/agent-desktop 的 observe 思路（读 OS 无障碍树、
    每个元素带 ref），只是把桌面 AX/UIAutomation/AT-SPI 换成安卓的
    uiautomator dump —— 该 CLI 本身不支持 Android，无法直接调用。
    """
    engine = CTX.get("engine", "auto")
    if engine in ("ax", "auto"):
        try:
            from ax_engine import AXSnapshot
            snap = AXSnapshot.capture(log=lambda *a: None)
            if snap is not None:
                CTX["ax_nodes"] = len(snap.elements)
                return snap.items()
        except Exception as e:
            log("[ax] 不可用:", str(e)[:100])
    if engine == "ax":
        return []
    if im is None:
        return []
    return ocr_items(im, width)


def hit(im, pos, why):
    """统一点击入口：执行点击 + 可选调试标注。"""
    _SEQ[0] += 1
    do_tap(int(pos[0]), int(pos[1]), why=why)
    if CTX.get("debug"):
        debug_save(im, pos, why, _SEQ[0])


def _font():
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
              "C:/Windows/Fonts/msyhbd.ttc"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, 26)
            except Exception:
                pass
    return ImageFont.load_default()


def debug_save(im, pos, why, seq):
    """调试模式：保存带 OCR 文字框与点击位置的标注截图。"""
    if im is None:
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        canvas = im.copy()
        d = ImageDraw.Draw(canvas)
        font = _font()
        for (x, y), txt, score in ocr_items(canvas):
            d.rectangle([x - 100, y - 24, x + 100, y + 24], outline=(0, 210, 255), width=2)
            d.text((x - 96, y - 22), txt[:14], fill=(0, 235, 255), font=font)
        if pos:
            x, y = int(pos[0]), int(pos[1])
            d.ellipse([x - 26, y - 26, x + 26, y + 26], outline=(255, 40, 40), width=5)
            d.line([x - 38, y, x + 38, y], fill=(255, 40, 40), width=3)
            d.line([x, y - 38, x, y + 38], fill=(255, 40, 40), width=3)
            d.text((x + 32, y - 46), why, fill=(255, 70, 70), font=font)
        canvas.thumbnail((610, 1356))
        safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", why)[:18]
        name = "%04d_%s_%s.png" % (seq, datetime.now().strftime("%H%M%S"), safe)
        canvas.save(os.path.join(DEBUG_DIR, name))
    except Exception as e:
        log("[debug] 保存失败:", str(e)[:100])


def urgent_recover(im):
    """倒计时期间的低频抽查：直播广告「取消」这类有时限的文字。

    不走 decide() 的优先级，因为倒计时文案「39秒后可领取奖励」会先命中 wait，
    把「取消」挡掉；这里只找有时限的关键词，命中立刻点。
    """
    for pos, txt, score in probe_items(im):
        if any(b in txt for b in ("了解更多", "立即投保", "前往微保", "向上滑动")):
            continue
        if ("取消" in txt) or ("继续观看" in txt) or ("不看了" in txt):
            log("[ad] 时限文字命中 -> %s" % txt[:20])
            hit(im, pos, "时限:" + txt[:12])
            return True
    return False


def smart_recover(im, tag):
    """像素状态机卡住时：无障碍树(优先)/OCR 读文字 -> decide() 查表直接点。"""
    items = probe_items(im)
    if not items:
        return False
    try:
        from automate_ocr import decide
    except Exception as e:
        log("[fix] 决策表不可用:", str(e)[:100])
        return False
    action, pos, why = decide(items, CTX["W"], CTX["H"])
    log("[fix] %s -> %s / %s (%d 个文字节点)" % (tag, action, why, len(items)))
    if action in ("wait", "none"):
        return False
    if action == "novideo":
        hit(im, CTX["NO_VIDEO_X"], "关闭无视频提示")
        return True
    if not pos:
        return False
    x, y = pos
    if not (0 <= x <= CTX["W"] and 0 <= y <= CTX["H"]):
        return False
    hit(im, (x, y), "OCR:" + why)
    return True


# ---------------------------------------------------------------- 启动引导
def ensure_welfare(LING_BOX, max_tries=14):
    """冷启动引导：确认真的站在福利中心且「领时长」可见。"""
    MAIN = CTX["MAIN"]
    for i in range(max_tries):
        act = focus()
        if "AdActivity" in act:
            log("[boot] 开屏广告 -> 跳过")
            hit(None, CTX["SKIP_SPLASH"], "开屏跳过")
            time.sleep(1.0)
            continue
        if "ExcitingVideo" in act:
            log("[boot] 上次残留的广告页，交给主循环处理")
            return True
        if "ConfirmStartActivity" in act or "securitycenter" in act:
            log("[boot] MIUI 跳转确认 -> 拒绝")
            hit(None, CTX["DENY_BTN"], "拒绝跳转")
            time.sleep(0.6)
            continue
        if "com.luna.music" not in act:
            log("[boot] 当前 %s -> 拉起汽水音乐" % (act[:55] or "(无焦点)"))
            rb(["shell", "am", "start", "-n", MAIN])
            time.sleep(2.0)
            continue
        im = shot_fast()
        if im is not None:
            n, _ = green_stats(im, LING_BOX, 3)
            if n > 600:
                log("[boot] 已在福利中心，领时长可见")
                return True
        # 只按 UI 文字定位「福利」tab；固定坐标在广告页是广告主 CTA，绝不能盲点
        xml = ui_dump()
        tab = text_pos(xml, "福利")
        if xml and ("福利中心" in xml or "赚时长" in xml):
            log("[boot] 福利页加载中 (%d/%d)" % (i + 1, max_tries))
        elif tab:
            hit(im, tab, "福利 tab(文字定位)")
        else:
            log("[boot] 等待页面加载 (%d/%d)" % (i + 1, max_tries))
        time.sleep(1.2)
    log("!! 启动引导失败：没能进入福利中心")
    return False


# ---------------------------------------------------------------- 主循环
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ads", type=int, default=120, help="广告数量上限，到点自动停止")
    ap.add_argument("--max-seconds", type=int, default=3600, help="总运行时长上限（秒）")
    ap.add_argument("--ocr-every", type=int, default=10, help="每 N 轮 OCR 抽查一次")
    ap.add_argument("--target-day", type=int, default=31, help="目标天数（日志/统计标注）")
    ap.add_argument("--debug", action="store_true", help="保存带文字标注与点击位置的截图")
    ap.add_argument("--engine", choices=["ax", "ocr", "auto"], default="auto",
                    help="定位引擎：ax=纯无障碍树(零OCR) / ocr=原OCR / "
                         "auto=无障碍树优先、OCR兜底（默认）")
    args = ap.parse_args()

    devs = rb(["devices"]).stdout.decode(errors="replace")
    ok = [l.split()[0] for l in devs.splitlines()
          if len(l.split()) >= 2 and l.split()[1] == "device"]
    if not ok:
        log("!! 没有已授权的安卓设备")
        return 3

    out = rb(["shell", "wm", "size"]).stdout.decode(errors="replace")
    W, H = 1220, 2712
    for line in out.splitlines():
        if "size" in line:
            try:
                w, h = line.split(":")[-1].strip().split("x")
                W, H = int(w), int(h)
            except Exception:
                pass

    R = lambda x0, y0, x1, y1: (int(W * x0), int(H * y0), int(W * x1), int(H * y1))
    PILL_BOX = R(0.58, 0.04, 0.98, 0.085)
    REWARD_BOX = R(0.28, 0.47, 0.72, 0.60)
    LING_BOX = R(0.75, 0.34, 0.97, 0.42)

    CTX.update(
        W=W, H=H, debug=args.debug, engine=args.engine,
        target_day=args.target_day, max_ads=args.max_ads,
        started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), t0=time.time(),
        MAIN="com.luna.music/com.luna.biz.main.main.MainActivity",
        LIVE_X=(int(W * 0.945), int(H * 0.072)),
        CAPSULE=(int(W * 0.85), int(H * 0.063)),
        SKIP_SPLASH=(int(W * 0.862), int(H * 0.083)),
        DENY_BTN=(int(W * 0.50), int(H * 0.88)),
        NO_VIDEO_X=(int(W * 0.92), int(H * 0.034)),
    )

    log("==== 极速 v2 启动 %dx%d | engine=%s | 上限 %d 轮 / %ds | 抽查每 %d 轮 | 目标 %d 天 | debug=%s ===="
        % (W, H, args.engine, args.max_ads, args.max_seconds,
           args.ocr_every, args.target_day, args.debug))
    write_stats(0, True, "启动")

    if not ensure_welfare(LING_BOX):
        write_stats(0, False, "启动引导失败")
        return 4

    t0 = time.time()
    ads = 0
    capsule_streak = 0
    no_progress = 0
    other_cnt = 0
    novideo_cnt = 0
    wait_frames = 0
    last_log_t = t0
    last_gain_t = t0        # 上次真正领到奖励的时刻
    live_total = 0          # 累计直播间次数（成功领取时清零）
    novideo_total = 0       # 累计「无新视频」次数（成功领取时清零）

    while time.time() - t0 < args.max_seconds:
        if ads >= args.max_ads:
            log("==== 达到广告数量上限 %d，自动停止 ====" % ads)
            break

        act = focus()

        # --- 直播间：右上角 X 退出；连续退不掉就交给 OCR 找「退出不看了」
        if "LivePlayer" in act:
            live_total += 1
            log("[live] 直播间 -> X (累计 %d)" % live_total)
            im_live = shot_fast()
            if other_cnt >= 2 and smart_recover(im_live, "直播间兜底"):
                pass
            else:
                hit(im_live, CTX["LIVE_X"], "直播间 X")
            other_cnt += 1
            # 广告池空时 SDK 会反复把用户导流进直播间，逐次点 X 只会无限循环；
            # 累计多次且长时间没有新奖励，判定广告池耗尽，主动停机。
            if other_cnt > 10 or (live_total >= 12 and time.time() - last_gain_t > 120):
                log("==== 广告池疑似耗尽（反复进直播间、%ds 无新奖励），停止 ===="
                    % int(time.time() - last_gain_t))
                break
            time.sleep(0.5)
            continue

        if "AdActivity" in act:
            log("[splash] 开屏广告 -> 跳过")
            hit(shot_fast(), CTX["SKIP_SPLASH"], "开屏跳过")
            other_cnt = 0
            time.sleep(0.8)
            continue

        # MIUI「启动应用」确认：广告主 CTA 想拉起京东/淘宝等，必须拒绝
        if "ConfirmStartActivity" in act or "securitycenter" in act:
            log("[miui] 应用跳转确认 -> 拒绝")
            hit(shot_fast(), CTX["DENY_BTN"], "拒绝跳转")
            other_cnt = 0
            time.sleep(0.5)
            continue

        if act and not any(k in act for k in ("ExcitingVideo", "MainActivity", "LivePlayer", "AdActivity")):
            other_cnt += 1
            if other_cnt > 12:
                log("==== 连续落在无关界面 %s，停止 ====" % act[:60])
                break
            if other_cnt <= 3:
                rb(["shell", "input", "keyevent", "4"])
                time.sleep(0.8)
            else:
                log("[other] %s -> 拉起 App" % act[:60])
                rb(["shell", "am", "start", "-n", CTX["MAIN"]])
                time.sleep(1.2)
            continue
        other_cnt = 0

        im = shot_fast()
        if im is None:
            time.sleep(0.5)
            continue

        rew_n, rew_c = green_stats(im, REWARD_BOX, 4)
        pill_n, _ = green_stats(im, PILL_BOX, 3)
        ling_n, ling_c = green_stats(im, LING_BOX, 3)

        # 1) 奖励弹窗「领取奖励」-> 点质心，计入一轮，自动进入下一广告
        if rew_n > 900 and rew_c:
            hit(im, rew_c, "领取奖励")
            ads += 1
            capsule_streak = 0
            no_progress = 0
            novideo_cnt = 0
            wait_frames = 0
            last_gain_t = time.time()
            live_total = 0
            novideo_total = 0
            log("==== 第 %d 轮已领取 (%ds) ====" % (ads, int(time.time() - t0)))
            write_stats(ads, True, "第%d轮已领取" % ads)
            if args.ocr_every and ads % args.ocr_every == 0:
                its = probe_items(im)
                log("[check] 第%d轮抽查完成，%d 个文字节点" % (ads, len(its)))
            time.sleep(0.45)
            last_log_t = time.time()
            continue

        # 2) 广告页
        if "ExcitingVideo" in act:
            # 「当前无新视频」遮罩：关掉提示层后广告会重新拉取
            ov_white, ov_bright = overlay_stats(im)
            if ov_white > 130 and ov_bright < 90:
                novideo_cnt += 1
                novideo_total += 1
                log("[ad] 「当前无新视频」提示层 -> 关闭 (%d)" % novideo_cnt)
                hit(im, CTX["NO_VIDEO_X"], "关闭无视频提示")
                capsule_streak = 0
                no_progress = 0
                # 连续无视频且 2 分钟没有任何新奖励 -> 广告池耗尽，停止空转
                if novideo_total >= 10 and time.time() - last_gain_t > 120:
                    log("==== 广告池耗尽（连续无视频、%ds 无新奖励），停止 ===="
                        % int(time.time() - last_gain_t))
                    break
                time.sleep(0.6 if novideo_cnt < 8 else 20.0)
                if novideo_cnt >= 8:
                    novideo_cnt = 0
                    log("[ad] 广告池暂空，等待 20s 后重试")
                continue

            if pill_n > 20:
                capsule_streak = 0
                wait_frames += 1
                # 倒计时是 App 端固定走的，这里跑 OCR 不增加墙钟时间；
                # 每 5 帧（~2s）扫一次「取消」，覆盖直播广告 5 秒窗口。
                if wait_frames <= 40 and wait_frames % 5 == 1 and urgent_recover(im):
                    wait_frames = 0
                    continue
                if time.time() - last_log_t > 20:
                    log("[wait] 倒计时中 … 已领 %d 轮" % ads)
                    last_log_t = time.time()
                time.sleep(0.35)
                continue

            # 倒计时结束 -> 点「领取成功 ×」胶囊揭弹窗
            capsule_streak += 1
            if capsule_streak > 3:
                # 连点无响应：多半是「取消 / 继续观看 / 退出不看了」等文字弹窗
                if smart_recover(im, "广告页兜底"):
                    capsule_streak = 0
                    no_progress = 0
                    time.sleep(0.5)
                    continue
            if capsule_streak > 12:
                log("!! 胶囊连点无响应，做一次文字诊断")
                its = probe_items(im)
                log("[diag] 可见文字: %s" % [t for _, t, _ in its][:12])
                capsule_streak = 0
                no_progress += 1
                if no_progress > 3:
                    log("==== 多次诊断无进展，停止 ====")
                    break
            hit(im, CTX["CAPSULE"], "领取成功胶囊")
            time.sleep(0.45)
            continue

        # 3) App 主页：福利页「领时长 / 继续领」
        if "MainActivity" in act:
            if ling_n > 600 and ling_c:
                no_progress = 0
                hit(im, ling_c, "领时长")
                time.sleep(0.5)
                continue
            if "MainActivity" not in focus():
                time.sleep(0.4)
                continue
            no_progress += 1
            # 兜底必须先于 tab：否则 UI 层级里只要读得到「福利」就一直点 tab，
            # 遮罩弹窗（如音量提示）永远轮不到 OCR 处理。
            if no_progress >= 3:
                if smart_recover(im, "主页兜底"):
                    no_progress = 0
                    time.sleep(0.5)
                    continue
            xml = ui_dump()
            tab = text_pos(xml, "福利")
            if tab:
                hit(im, tab, "福利 tab(文字定位)")
                time.sleep(0.8)
                continue
            if no_progress >= 10:
                log("==== 判定当天已无广告或页面异常，停止 ====")
                break
            time.sleep(0.8)
            continue

        time.sleep(0.5)

    log("==== 结束：共领取 %d 轮，用时 %ds ====" % (ads, int(time.time() - t0)))
    write_stats(ads, False, "结束：共%d轮" % ads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
