#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一 OCR 后端，按「最轻优先」自动选型：

  1) winrt    Windows 内置 Windows.Media.Ocr（zh-Hans-CN 中文模型）
              —— 零下载、零安装、离线，0 MB 额外体积，最轻量
  2) rapidocr scripts/models/*.onnx（setup_ocr.py 安装）
              —— 跨平台、纯 CPU、约 15 MB 模型，非 Windows 或需要可移植时用
  3) None     都不可用 -> 调用方自动回退到像素状态机，功能不残缺

对外只暴露 OCREngine.read(im) -> [(center_xy, text, score), ...]
"""
import os
import re
import json
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
WIN_PS = os.path.join(HERE, "win_ocr.ps1")
MODELS_DIR = os.path.join(HERE, "models")


def norm(s):
    s = re.sub(r"\s+", "", str(s).strip())
    return s.replace("Ｘ", "X").replace("ｘ", "x").replace("✓", "").replace("✔", "")


def ps_exe():
    for p in ("powershell.exe", "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"):
        if os.path.exists(p) or p == "powershell.exe":
            return p
    return "powershell.exe"


def winrt_available():
    """探测 Windows 内置 OCR 是否有中文识别器。"""
    if os.name != "nt" or not os.path.exists(WIN_PS):
        return False
    cmd = [ps_exe(), "-NoProfile", "-Command",
           "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null; "
           "([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }) -join ','"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=25, text=True)
        return r.returncode == 0 and "zh" in (r.stdout or "")
    except Exception:
        return False


class OCREngine:
    def __init__(self, prefer="auto", width=960, log=print):
        self.width = width
        self.log = log
        self.backend = None
        self._rapid = None

        if prefer in ("auto", "winrt") and winrt_available():
            self.backend = "winrt"
        elif prefer in ("auto", "rapidocr"):
            self._init_rapid()

        if self.backend:
            self.log("[ocr] 后端 = %s" % self.backend)
        else:
            self.log("[ocr] 无可用 OCR 后端，将使用像素状态机回退")

    def _init_rapid(self):
        try:
            from setup_ocr import make_engine, ocr_items
            self._rapid = (make_engine(), ocr_items)
            self.backend = "rapidocr"
        except Exception as e:
            self.log("[ocr] RapidOCR 不可用：%s" % str(e)[:100])

    def _read_winrt(self, png):
        out = png + ".ocr.json"
        cmd = [ps_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", WIN_PS, "-Path", png, "-Out", out]
        try:
            subprocess.run(cmd, capture_output=True, timeout=40)
            if not os.path.exists(out):
                raise RuntimeError("WinRT OCR 无输出")
            with open(out, "r", encoding="utf-8") as f:
                d = json.load(f)
            # 不删除：out 是固定路径，PowerShell 每次覆盖写入。
            # 逐帧删除会累计触发宿主环境的批量删除保护（一轮 50 次即中断进程）。
        except Exception as e:
            raise RuntimeError("WinRT OCR 失败: %s" % e)

        items = []
        for ln in d.get("lines", []) or []:
            items.append((ln["x"] + ln["w"] // 2, ln["y"] + ln["h"] // 2, ln["text"], 1.0))
        for w in d.get("words", []) or []:
            items.append((w["x"] + w["w"] // 2, w["y"] + w["h"] // 2, w["text"], 0.9))
        return items

    def _read_rapid(self, png):
        ocr, ocr_items = self._rapid
        return [(cx, cy, txt, score) for (cx, cy), txt, score in ocr_items(ocr(png))]

    def read(self, im, width=None):
        """缩小图 -> OCR -> 坐标还原。返回 [((x,y), 归一化文本, score), ...]"""
        if self.backend is None:
            return []
        from PIL import Image
        W, H = im.size
        scale = min(1.0, (width or self.width) / float(W))
        small = im if scale == 1.0 else im.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
        # 固定路径覆盖写入，绝不删除。
        # 实测：逐帧 os.remove 会让长跑累计大量删除操作，触发宿主环境的
        # 批量删除保护（一轮 50 次即强制中断进程，已领 27 轮后被杀）。
        # 该文件很小、每次覆盖、且已被 .gitignore 忽略。
        tmp = os.path.join(HERE, "_ocr_frame.png")
        try:
            small.save(tmp)
            raw = self._read_winrt(tmp) if self.backend == "winrt" else self._read_rapid(tmp)
            out = []
            for x, y, txt, score in raw:
                if score < 0.45:
                    continue
                t = norm(txt)
                if t:
                    out.append(((int(x / scale), int(y / scale)), t, score))
            return out
        except Exception as e:
            self.log("[ocr] 本帧失败: %s" % str(e)[:110])
            return []


if __name__ == "__main__":
    import sys
    eng = OCREngine()
    print("backend =", eng.backend)
    for p in sys.argv[1:]:
        from PIL import Image
        im = Image.open(p).convert("RGB")
        items = eng.read(im)
        print(os.path.basename(p), "->", [t for _, t, _ in items])
