#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ax_engine.py — 安卓无障碍树后端（observe / act / verify），替代 OCR 图片识别。

思路来源：vercel-labs/agent-desktop
  桌面侧：读 OS 无障碍树 -> 给每个元素一个 ref -> 按 ref 点击 -> 再读一次树验证。
  该 CLI 只支持 macOS / Windows / Linux 的桌面应用（AX API / UI Automation / AT-SPI），
  不支持 Android / adb，所以无法直接调用。本模块把同一套机制落到安卓侧：
  `adb shell uiautomator dump` 就是安卓版的无障碍树快照。

对外接口：
    snap = AXSnapshot.parse(xml)          # 纯内存解析，可离线自测
    snap = AXSnapshot.capture()           # observe：从设备读一棵树
    snap.items()                          # -> decide() 兼容的 [((x,y), text, score), ...]
    snap.ref_at(pos) / click_ref(ref)     # act：按 ref 找到节点，点 bounds 中心
    snap.verify()                         # verify：重读树，比较 snapshot_id

约定与 agent-desktop 一致：
  - ref 形如 @ax1a2b3c:e7，只在所属快照内有效；UI 变化后旧 ref 视为 STALE_REF。
  - 每个元素带 text / content-desc / resource-id / bounds / clickable。
  - 不截图、不启动 OCR 进程、不依赖像素或分辨率。

关键词决策表直接复用 automate_ocr.decide（仅 import，不实例化 OCR 引擎），
避免两套逻辑分叉；黑名单、倒计时优先级、弹窗处理都保持原样。
"""
import os
import re
import sys
import hashlib
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from automate_ocr import decide, norm  # noqa: E402  复用关键词决策表，不跑 OCR

DUMP_PATH = "/sdcard/qs_ax_ui.xml"
_RE_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_RE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class StaleRef(Exception):
    """ref 不属于当前快照（对应 agent-desktop 的 STALE_REF）。"""


def _center(b):
    x0, y0, x1, y1 = b
    return ((x0 + x1) // 2, (y0 + y1) // 2)


class AXSnapshot:
    """一棵无障碍树快照；snapshot_id 由 XML 内容哈希得到，UI 变化即变化。"""

    def __init__(self, elements, sid, log=print):
        self.elements = elements
        self.sid = sid
        self.log = log
        self._by_ref = {e["ref"]: e for e in elements}

    @classmethod
    def parse(cls, xml, log=print):
        """解析 uiautomator dump 的 XML。无有效文字节点返回 None。"""
        if not xml or "<node" not in xml:
            return None
        xml = _RE_CTRL.sub("", xml)
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            log("[ax] XML 解析失败:", str(e)[:80])
            return None
        sid = hashlib.md5(xml.encode("utf-8", errors="replace")).hexdigest()[:8]
        els = []
        for node in root.iter("node"):
            text = norm(node.get("text", "") or "")
            desc = norm(node.get("content-desc", "") or "")
            label = text or desc
            if not label:
                continue
            m = _RE_BOUNDS.search(node.get("bounds", "") or "")
            if not m:
                continue
            x0, y0, x1, y1 = map(int, m.groups())
            if x1 <= x0 or y1 <= y0:
                continue
            idx = len(els)
            els.append({
                "ref": "@ax%s:e%d" % (sid, idx),
                "text": label,
                "desc": desc,
                "bounds": (x0, y0, x1, y1),
                "center": _center((x0, y0, x1, y1)),
                "clickable": (node.get("clickable", "") == "true"),
                "resource_id": node.get("resource-id", "") or "",
            })
        return cls(els, sid, log=log) if els else None

    @classmethod
    def capture(cls, timeout=12, log=print):
        """observe：从已授权设备拉一棵无障碍树。设备不可用/动画中返回 None。"""
        r = _rb(["shell", "uiautomator", "dump", DUMP_PATH], timeout=timeout)
        if b"dumped to" not in (r.stdout or b""):
            return None
        r2 = _rb(["exec-out", "cat", DUMP_PATH], timeout=timeout)
        xml = (r2.stdout or b"").decode("utf-8", errors="replace")
        return cls.parse(xml, log=log)

    def items(self):
        """喂给 automate_ocr.decide()：文字节点中心等价于 OCR 文本框中心。"""
        return [(e["center"], e["text"], 1.0) for e in self.elements]

    def ref_at(self, pos, tol=2):
        """把决策表给出的坐标反查回 ref；固定坐标兜底会返回 None。"""
        for e in self.elements:
            cx, cy = e["center"]
            if abs(cx - pos[0]) <= tol and abs(cy - pos[1]) <= tol:
                return e["ref"]
        return None

    def click_pos(self, pos, why="", dry_run=False, tap=None):
        """act：优先按 ref 对应的节点中心点击，坐标无对应节点时直接点坐标。"""
        ref = self.ref_at(pos)
        target = self._by_ref.get(ref) if ref else None
        if target is None:
            self.log("[ax] 固定坐标兜底 ->", pos)
            x, y = int(pos[0]), int(pos[1])
        else:
            x, y = target["center"]
            self.log("[ax] act %s %r -> (%d,%d) %s"
                     % (ref, target["text"][:20], x, y, why))
        if dry_run:
            return True
        if tap is None:
            _rb(["shell", "input", "tap", str(x), str(y)])
        else:
            tap(x, y, why=why)
        return True

    def click_ref(self, ref, why="", dry_run=False, tap=None):
        e = self._by_ref.get(ref)
        if not e:
            raise StaleRef("ref=%s 不属于快照 @ax%s" % (ref, self.sid))
        return self.click_pos(e["center"], why=why, dry_run=dry_run, tap=tap)

    def verify(self, timeout=12):
        """verify：重新 observe，树内容变化即认为动作生效。"""
        nxt = AXSnapshot.capture(timeout=timeout, log=self.log)
        if nxt is None:
            return False
        return nxt.sid != self.sid

    def find(self, keyword, tol_text=None):
        """按文字/描述找节点，返回元素 dict 或 None。"""
        k = norm(keyword)
        for e in self.elements:
            if k in e["text"] or (e["desc"] and k in e["desc"]):
                return e
        return None


def ax_decide(snap, W, H):
    """直接复用现有关键词决策表（含黑名单、倒计时优先级）。"""
    return decide(snap.items(), W, H)


def _rb(args, timeout=12):
    """延迟加载 adb 封装，便于在没有设备的环境里离线自测 parse()。"""
    from automate_fixed import rb
    return rb(args, timeout=timeout)


if __name__ == "__main__":
    # 离线自检：给一段 XML 路径或直接跑内置样例
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            s = AXSnapshot.parse(f.read())
    else:
        s = AXSnapshot.parse(
            '<hierarchy><node text="领取奖励" clickable="true" '
            'bounds="[400,1200][820,1360]"/><node text="了解更多" '
            'bounds="[100,2200][1100,2350]"/></hierarchy>')
    print("snapshot =", s.sid if s else None, "| nodes =", len(s.elements) if s else 0)
    if s:
        for e in s.elements:
            print(" ", e["ref"], repr(e["text"]), e["center"], "clickable=", e["clickable"])
        print("decide =", ax_decide(s, 1220, 2712))
