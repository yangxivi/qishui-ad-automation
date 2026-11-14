# -*- coding: utf-8 -*-
"""离线自测：无障碍树解析 / 决策表 / ref / 零 OCR 路径（不需要安卓设备）。"""
import os
import sys

SK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SK)
os.chdir(SK)

from ax_engine import AXSnapshot, ax_decide, StaleRef  # noqa: E402


def node(text, bounds, clickable="true"):
    return '<node text="%s" content-desc="" clickable="%s" bounds="%s"/>' % (
        text, clickable, bounds)


def xml(nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


welfare = xml([
    node("福利中心", "[0,100][1220,200]", "false"),
    node("领时长", "[900,920][1180,1100]"),
    node("去听歌", "[100,2200][500,2350]"),
    node("了解更多", "[600,2200][1100,2350]"),
])
countdown = xml([
    node("39秒后可领取奖励", "[700,100][1180,180]", "false"),
    node("领取奖励", "[400,1200][820,1360]"),
])
reward = xml([
    node("领取成功", "[700,100][1180,180]", "false"),
    node("领取奖励", "[400,1200][820,1360]"),
])
cta_only = xml([
    node("了解更多", "[100,2200][1100,2350]"),
    node("去提现", "[100,2400][1100,2550]"),
])

# 1) 解析 + ref
s = AXSnapshot.parse(welfare)
assert s is not None and len(s.elements) == 4, "解析失败"
assert all(e["ref"].startswith("@ax" + s.sid + ":e") for e in s.elements)
assert s.ref_at((1040, 1010)) is not None, "ref 反查失败"
print("[1] parse/ref OK  snapshot=%s nodes=%d" % (s.sid, len(s.elements)))

# 2) 决策表：福利页命中「领时长」，广告主 CTA 被黑名单挡住
a, pos, why = ax_decide(s, 1220, 2712)
assert a == "ling", (a, why)
assert s.ref_at(pos) == s.elements[1]["ref"], "应该定位到领时长节点"
print("[2] 福利页 -> %s / %s / ref=%s OK" % (a, why, s.ref_at(pos)))

# 3) 倒计时优先，绝不提前点领取奖励
a2, _, why2 = ax_decide(AXSnapshot.parse(countdown), 1220, 2712)
assert a2 == "wait", (a2, why2)
print("[3] 倒计时 -> wait OK")

# 4) 奖励弹窗
a3, pos3, why3 = ax_decide(AXSnapshot.parse(reward), 1220, 2712)
assert a3 == "reward", (a3, why3)
print("[4] 奖励弹窗 -> %s / %s OK" % (a3, why3))

# 5) 纯 CTA 页面不乱点
a4, _, why4 = ax_decide(AXSnapshot.parse(cta_only), 1220, 2712)
assert a4 == "none", (a4, why4)
print("[5] 广告主 CTA -> none（不误点）OK")

# 6) dry-run 点击 + 快照一致性 + STALE_REF
assert s.click_pos(pos, why="selftest", dry_run=True) is True
try:
    s.click_ref("@axdeadbeef:e0", dry_run=True)
    raise AssertionError("陈旧 ref 应该被拒绝")
except StaleRef:
    pass
assert AXSnapshot.parse(welfare).sid == s.sid
assert AXSnapshot.parse(reward).sid != s.sid
print("[6] click/STALE_REF/snapshot_id OK")

# 7) & 8) 引擎路由：ax 绝不触发 OCR、auto 回退 OCR、ocr 不读树
import ax_engine  # noqa: E402
import automate_fast as af  # noqa: E402

orig_capture = ax_engine.AXSnapshot.capture
orig_ocr = af.ocr_items
try:
    def boom_ocr(*a, **k):
        raise AssertionError("ax 模式下竟然调用了 OCR")

    af.CTX.update(W=1220, H=2712, engine="ax")
    af.ocr_items = boom_ocr
    ax_engine.AXSnapshot.capture = classmethod(lambda cls, **kw: s)
    got = af.probe_items(None)
    assert len(got) == 4, got
    print("[7] engine=ax：probe_items(None) 返回 %d 个文字节点，零 OCR OK" % len(got))

    af.CTX["engine"] = "auto"
    ax_engine.AXSnapshot.capture = classmethod(lambda cls, **kw: None)
    af.ocr_items = lambda im, width=960: [((10, 10), "领取奖励", 1.0)]
    assert len(af.probe_items(object())) == 1
    print("[8] engine=auto：树读不到时回退 OCR OK")

    af.CTX["engine"] = "ocr"
    ax_engine.AXSnapshot.capture = classmethod(
        lambda cls, **kw: (_ for _ in ()).throw(AssertionError("ocr 模式不该读树")))
    assert len(af.probe_items(object())) == 1
    print("[9] engine=ocr：完全不读树，保持旧行为 OK")
finally:
    ax_engine.AXSnapshot.capture = orig_capture
    af.ocr_items = orig_ocr

# 10) & 11) 实机死循环回归：领奖准入 + 直播间退出确认（2026-11-14）
from automate_fast import reward_allowed, live_exit_pos, MIN_REWARD_GAP  # noqa: E402

NOW = 1000.0
EXC = "com.ss.android.excitingvideo.ExcitingVideoActivity"
LIVE = "com.luna.biz.live.LunaDefaultLivePlayerActivity"
assert reward_allowed(EXC, NOW, NOW - 25)[0] is True
assert reward_allowed(EXC, NOW, NOW - 5)[0] is False, "5s 内的重复绿块必须拦下"
assert reward_allowed(LIVE, NOW, NOW - 25)[0] is False, "直播间不能计入奖励"
assert MIN_REWARD_GAP >= 10
print("[10] 领奖准入：真实间隔放行 / 5s 重复拦截 / 直播间拦截 OK")

live_items = [((100, 200), "继续观看", 1.0), ((600, 1800), "退出不看了", 1.0)]
pos_live, txt_live = live_exit_pos(live_items, 1220, 2712)
assert pos_live == (600, 1800) and "不看了" in txt_live, (pos_live, txt_live)
assert live_exit_pos([((100, 200), "继续观看", 1.0)], 1220, 2712)[0] is None
assert live_exit_pos([((5000, 100), "退出不看了", 1.0)], 1220, 2712)[0] is None
print("[11] 直播间容错：只点退出确认，不误点继续观看 / 越界坐标 OK")

# 12) 福利页连点「领时长」保护：广告池耗尽时必须停机（第二个实机死循环）
from automate_fast import ling_tap_action, LING_TAP_LIMIT  # noqa: E402
assert [ling_tap_action(i) for i in range(1, 7)] == [
    "tap", "tap", "tap", "recover", "stop", "stop"]
assert LING_TAP_LIMIT == 5
print("[12] 领时长连点：3 次点击 -> 文字兜底 -> 停机 OK")

print("ALL SELFTESTS PASSED")
