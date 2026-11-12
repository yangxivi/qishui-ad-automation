#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽水音乐「领时长」OCR 版 —— 识别到关键词就直接点，零逐步推理。

与旧版的区别
  automate.py        : 全屏扫绿色像素，误把专辑封面/「去听歌」当按钮，倒计时没完就点 X
  automate_fixed.py  : 像素状态机，能跑通，但靠颜色特征，换皮肤/换广告就脆弱
  automate_ocr.py    : OCR 直接读文字与符号，关键词 -> 动作的确定性映射表

判定表（按优先级，命中即执行，不做多余判断）：
  领取奖励        -> 点它，计入一轮
  领取成功 / ✕    -> 点右上胶囊，揭开奖励弹窗
  N秒后可领取奖励 -> 等待，绝不在倒计时里点 X
  领时长          -> 点它，起一条广告
  关闭 / X（弹窗）-> 仅当有弹窗上下文时才点，绝不误关广告
  以上都没命中     -> 回退到像素状态机（automate_fixed.py 的逻辑）

安全：广告主 CTA（了解更多 / 前往微保 / 立即下单 / 去听歌 …）一律进黑名单，永不点击。
硬上限：--max-ads / --max-seconds，到点即停。
"""
import os
import sys
import re
import time
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image  # noqa: E402
# 像素回退复用 fixed 版里已验证的工具函数
try:
    from automate_fixed import (ADB, rb, focus, shot as grab_shot, green_stats,  # noqa: E402
                                tap as do_tap, on_welfare_page, SHOT)
except Exception as _e:  # pragma: no cover
    sys.exit("无法加载 automate_fixed.py 的工具函数：%s" % _e)

LOG_PATH = os.path.join(HERE, "automate_ocr.log")

# ---------------------------------------------------------------- 关键词表
BLOCKLIST = (
    "了解更多", "前往微保", "立即下单", "立即下载", "立即投保", "立即咨询",
    "马上抢", "打开", "查看详情", "去看看", "去逛逛",
    "去听歌", "去签到", "去提现", "兑换", "开通", "坚持退出", "向上滑动",
    "反馈", "广告", "商城", "演出", "发现", "听抖音", "我的", "福利中心",
)
RE_COOLDOWN = re.compile(r"\d+\s*秒后")
RE_DAY = re.compile(r"第\s*\d+\s*[日天]")
CLOSE_WORDS = ("关闭", "×", "✕", "✖", "x", "X")


def log(*a):
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), " ".join(str(x) for x in a))
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def norm(s):
    """去空格、统一全半角与叉号写法，便于容错匹配。"""
    s = str(s).strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("Ｘ", "X").replace("ｘ", "x")
    s = s.replace("✓", "").replace("✔", "")
    return s


# ---------------------------------------------------------------- OCR
from ocr_engine import OCREngine  # noqa: E402

_ENGINE = None


def read_text(im, width=960):
    """OCR -> [((x,y), 归一化文本, score), ...]；无后端返回空列表走像素回退。"""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = OCREngine(width=width, log=log)
    return _ENGINE.read(im, width)


# ---------------------------------------------------------------- 决策表
def decide(items, W, H):
    """纯查表：返回 (action, (x,y), 说明)。没有任何推理链。"""
    usable = []
    for pos, txt, score in items:
        if any(b in txt for b in BLOCKLIST):
            continue
        usable.append((pos, txt, score))

    has_popup = any(("再看" in t) or ("提前" in t) or RE_DAY.search(t) for _, t, _ in usable)

    # 0) 系统「未检测到音乐音量变化」弹窗：点「知道了」，绝不点「去设置」
    #    该弹窗会遮住「领时长」按钮，必须最先处理，否则主页会被误判为无入口
    for pos, txt, _ in usable:
        if "知道了" in txt:
            return "dismiss", pos, "知道了(关音量提示)"
    for pos, txt, _ in usable:
        if "音量变化" in txt or "未检测到音乐" in txt or "音量单独调节" in txt:
            return "dismiss", (int(W * 0.57), int(H * 0.558)), "音量提示(固定坐标)"

    # 1) 倒计时必须先判：「39秒后可领取奖励×」里含有「领取奖励」，否则会误点
    for pos, txt, _ in usable:
        if RE_COOLDOWN.search(txt) or "后可领取" in txt:
            return "wait", None, "倒计时中"

    # 1) 直播广告 5 秒内的「取消」：不点就会被拉进直播间
    for pos, txt, _ in usable:
        if "取消" in txt:
            return "cancel", pos, "取消(避开直播间)"

    # 2) 「坚持退出」免费解锁弹窗 -> 点「继续观看」，保住这一轮奖励
    for pos, txt, _ in usable:
        if "继续观看" in txt:
            return "continue", pos, "继续观看"

    # 3) 直播间退出后的「退出不看了」推荐弹窗 -> 确认退出
    for pos, txt, _ in usable:
        if "退出不看了" in txt or "不看了" in txt:
            return "exit_confirm", pos, "退出不看了"

    # 4) 「当前无新视频」提示层 -> 交给像素层关掉遮罩
    for pos, txt, _ in usable:
        if "无新视频" in txt or "当前无" in txt:
            return "novideo", pos, "当前无新视频"

    for pos, txt, _ in usable:
        if "领取奖励" in txt:
            return "reward", pos, "领取奖励"

    for pos, txt, _ in usable:
        if "领取成功" in txt:
            return "capsule", pos, "领取成功"

    for pos, txt, _ in usable:
        if "领时长" in txt or "继续领" in txt:
            return "ling", pos, "领时长/继续领"

    # 关闭按钮：只在弹窗上下文里，且不碰右上角广告 X
    if has_popup:
        for pos, txt, _ in usable:
            if txt in CLOSE_WORDS or txt == "X":
                x, y = pos
                if y > 0.15 * H:
                    return "close", pos, "弹窗关闭 X"

    return "none", None, "无匹配关键词"


# ---------------------------------------------------------------- 主循环
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ads", type=int, default=5)
    ap.add_argument("--max-seconds", type=int, default=480)
    ap.add_argument("--ocr-width", type=int, default=960)
    ap.add_argument("--dry-run", action="store_true", help="只打印识别与决策，不点屏幕")
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
    WELFARE_TAB = (int(W * 0.70), int(H * 0.90))

    log("==== OCR 版启动 %dx%d | 上限 %d 轮 / %ds | dry-run=%s ===="
        % (W, H, args.max_ads, args.max_seconds, args.dry_run))

    t0 = time.time()
    ads = 0
    no_progress = 0
    other_cnt = 0

    while time.time() - t0 < args.max_seconds:
        if ads >= args.max_ads:
            log("==== 达到轮数上限，停止 ====")
            break
        act = focus()

        if "LivePlayer" in act:
            log("[live] 直播间 -> 点右上角 X")
            if not args.dry_run:
                do_tap(int(W * 0.945), int(H * 0.072), why="直播间 X")
            time.sleep(1.2)
            continue

        if act and not any(k in act for k in ("ExcitingVideo", "MainActivity", "LivePlayer")):
            other_cnt += 1
            if other_cnt > 6:
                log("==== 连续落在无关界面，停止 ====")
                break
            log("[other] %s -> 回 App" % act[:55])
            if not args.dry_run:
                rb(["shell", "am", "start", "-n", "com.luna.music/com.luna.biz.main.main.MainActivity"])
            time.sleep(2.5)
            continue
        other_cnt = 0

        im = grab_shot()
        if im is None:
            time.sleep(1.5)
            continue

        items = read_text(im, args.ocr_width)
        action, pos, why = decide(items, W, H)

        # OCR 没读到东西 -> 像素状态机兜底
        if action == "none" and not items:
            pill_n, _ = green_stats(im, PILL_BOX, 2)
            rew_n, rew_c = green_stats(im, REWARD_BOX, 3)
            ling_n, ling_c = green_stats(im, LING_BOX, 2)
            if rew_n > 2000 and rew_c:
                action, pos, why = "reward", rew_c, "像素回退:领取奖励"
            elif "ExcitingVideo" in act and pill_n > 25:
                action, pos, why = "wait", None, "像素回退:倒计时"
            elif "ExcitingVideo" in act and pill_n <= 25:
                action, pos, why = "capsule", (int(W * 0.85), int(H * 0.063)), "像素回退:领取成功"
            elif "MainActivity" in act and ling_n > 1500 and ling_c:
                action, pos, why = "ling", ling_c, "像素回退:领时长"

        if args.dry_run:
            log("[dry] act=%s | texts=%s | -> %s %s"
                % (act.split(".")[-1][:28], [t for _, t, _ in items][:12], action, why))
            time.sleep(2)
            continue

        if action == "reward":
            do_tap(*pos, why=why)
            ads += 1
            no_progress = 0
            log("==== 第 %d 轮奖励已领取 ====" % ads)
            time.sleep(1.5)
        elif action == "capsule":
            do_tap(*pos, why=why)
            time.sleep(1.2)
        elif action == "wait":
            log("[wait] 倒计时中，等待")
            time.sleep(2)
        elif action == "ling":
            if "MainActivity" in act:
                w = on_welfare_page()
                if w is False:
                    do_tap(*WELFARE_TAB, why="福利 tab")
                    time.sleep(1.5)
                    continue
            no_progress += 1
            if no_progress > 4:
                log("==== 连续 4 次点领时长未进广告，判定当天无广告，停止 ====")
                break
            do_tap(*pos, why=why)
            time.sleep(1.5)
        elif action == "close":
            do_tap(*pos, why=why)
            time.sleep(1.2)
        else:
            no_progress += 1
            if no_progress > 12:
                log("==== 长时间无任何可识别目标，停止 ====")
                break
            time.sleep(2)

    log("==== 结束：共领取 %d 轮，用时 %ds ====" % (ads, int(time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
