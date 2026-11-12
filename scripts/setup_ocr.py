#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性安装轻量 OCR 引擎（RapidOCR / ONNXRuntime，纯 CPU、离线、自带中英文模型）。

设计取舍：
  - 不用 PaddleOCR / EasyOCR（要拉 PyTorch，1~2 GB，还要联网下模型）
  - RapidOCR 把 PP-OCR 的检测+识别模型压成约 15 MB 的 ONNX，pip 装完即用，
    模型随包附带，运行时不联网。整包依赖约 100 MB，属于同类里最轻的一档。
  - 安装后把 .onnx 模型复制到 scripts/models/，Skill 自包含、可离线分发。

用法：
    python scripts/setup_ocr.py                # 安装 + 冒烟测试
    python scripts/setup_ocr.py --check        # 只检查是否已就绪
    python scripts/setup_ocr.py --index URL    # 指定 pip 镜像源

失败不会破坏原有能力：automate_ocr.py 检测不到 OCR 会自动回退到像素状态机。
"""
import os
import sys
import glob
import json
import shutil
import subprocess
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "models")
STATE_FILE = os.path.join(HERE, "ocr_state.json")
PKG = "rapidocr-onnxruntime"

MIRRORS = [
    None,  # 默认源
    "https://pypi.org/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
]


def say(*a):
    print(" ".join(str(x) for x in a), flush=True)


def pip_install(index, timeout=600):
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
           "--timeout", "30", "--retries", "2", PKG]
    if index:
        cmd += ["-i", index]
    say("[pip]", " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        out = (r.stdout + r.stderr).decode(errors="replace")
        if r.returncode == 0:
            return True, out
        return False, out[-1500:]
    except subprocess.TimeoutExpired:
        return False, "pip 超时"


def ensure_package(extra_index=None):
    try:
        import rapidocr_onnxruntime as r  # noqa
        return True, r.__file__
    except ImportError:
        pass

    indexes = ([extra_index] if extra_index else []) + [m for m in MIRRORS if m != extra_index]
    for idx in indexes:
        ok, info = pip_install(idx)
        if ok:
            try:
                import rapidocr_onnxruntime as r  # noqa
                return True, r.__file__
            except ImportError:
                return False, "安装成功但导入失败：" + info[-500:]
        say("[pip] 源不可用：", (idx or "default"), "->", info.strip().splitlines()[-1] if info.strip() else "")
    return False, "所有 pip 源均失败；可稍后重试，或手动 pip install " + PKG


def copy_models(pkg_file):
    """把随包附带的 ONNX 模型复制到 Skill 内部，保证离线自包含。"""
    base = os.path.dirname(pkg_file)
    found = glob.glob(os.path.join(base, "**", "*.onnx"), recursive=True)
    os.makedirs(MODELS_DIR, exist_ok=True)
    copied = []
    for f in found:
        dst = os.path.join(MODELS_DIR, os.path.basename(f))
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(f):
            shutil.copy2(f, dst)
        copied.append(os.path.basename(f))
    return copied


def make_engine():
    """版本 tolerant 地构造引擎，优先用 Skill 自带模型。"""
    from rapidocr_onnxruntime import RapidOCR
    if not os.path.isdir(MODELS_DIR):
        return RapidOCR()
    kw = {}
    for key, pat in [("det_model_path", "*det*.onnx"),
                     ("rec_model_path", "*rec*.onnx"),
                     ("cls_model_path", "*cls*.onnx")]:
        m = glob.glob(os.path.join(MODELS_DIR, pat))
        if m:
            kw[key] = m[0]
    if not kw:
        return RapidOCR()
    try:
        return RapidOCR(**kw)
    except TypeError:
        return RapidOCR()


def smoke_test_with_engine(eng):
    """用统一 OCR 后端跑中文冒烟测试。"""
    from PIL import Image, ImageDraw, ImageFont
    fonts = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
             "/System/Library/Fonts/PingFang.ttc",
             "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"]
    font = None
    for p in fonts:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, 48)
                break
            except Exception:
                pass
    img = Image.new("RGB", (640, 180), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 55), "领时长 领取奖励", fill="black", **({"font": font} if font else {}))
    tmp = os.path.join(HERE, "_ocr_smoke.png")
    img.save(tmp)
    try:
        items = eng.read(img)
        joined = " ".join(t for _, t, _ in items)
        say("[smoke] 识别结果:", repr(joined))
        return (("领" in joined) or ("奖励" in joined) or ("时长" in joined)), joined
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


def smoke_test():
    """用系统字体渲染中文，确认识别链路真的通（不是只 import 成功）。"""
    from PIL import Image, ImageDraw, ImageFont
    fonts = [
        "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    font = None
    for p in fonts:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, 48)
                break
            except Exception:
                pass
    img = Image.new("RGB", (640, 180), "white")
    d = ImageDraw.Draw(img)
    text = "领时长 领取奖励"
    if font:
        d.text((20, 55), text, fill="black", font=font)
    else:
        d.text((20, 55), text, fill="black")
    tmp = os.path.join(HERE, "_ocr_smoke.png")
    img.save(tmp)

    try:
        engine = make_engine()
        res = engine(tmp)
        items = ocr_items(res)
        joined = " ".join(t for _, t, _ in items)
        say("[smoke] 识别结果:", repr(joined))
        ok = ("领" in joined) or ("奖励" in joined) or ("时长" in joined)
        return ok, joined
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


def ocr_items(res):
    """兼容 RapidOCR 不同版本的返回结构 -> [(center_xy, text, score), ...]"""
    if res is None:
        return []
    raw = res[0] if isinstance(res, (tuple, list)) and len(res) == 2 and isinstance(res[0], (list, type(None))) else res
    if raw is None:
        return []
    out = []
    for it in raw:
        try:
            box, txt, score = it[0], it[1], it[2]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            cx, cy = int(sum(xs) / len(xs)), int(sum(ys) / len(ys))
            out.append(((cx, cy), str(txt), float(score)))
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查是否已就绪")
    ap.add_argument("--index", default=None, help="指定 pip 镜像源")
    ap.add_argument("--force-rapidocr", action="store_true",
                    help="即使在 Windows 上也强制安装/校验 RapidOCR 便携后端")
    args = ap.parse_args()

    # Windows 优先：系统自带 OCR（零下载、零安装、离线、含中文模型）
    winrt_ok = False
    if os.name == "nt" and not args.force_rapidocr:
        try:
            from ocr_engine import winrt_available, OCREngine
            winrt_ok = winrt_available()
        except Exception as e:
            say("[winrt] 探测失败:", e)

    if winrt_ok:
        from ocr_engine import OCREngine
        try:
            eng = OCREngine(log=lambda *a: say(*a))
            ok, joined = smoke_test_with_engine(eng)
        except Exception as e:
            ok, joined = False, "冒烟测试异常: %s" % e
        state = {"engine": "winrt", "models": ["Windows 内置 zh-Hans-CN"],
                 "models_dir": None, "smoke_ok": bool(ok), "smoke_text": joined,
                 "extra_download_mb": 0}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        say("[ok] 使用 Windows 内置 OCR，无需下载任何模型；状态写入", STATE_FILE)
        say("[smoke]", "通过" if ok else "未通过", repr(joined))
        return 0 if ok else 1

    if args.check:
        ok, joined = smoke_test()
        say("OCR 就绪:", ok, "| 模型:", sorted(os.listdir(MODELS_DIR)) if os.path.isdir(MODELS_DIR) else [])
        return 0 if ok else 1

    ok, pkg = ensure_package(args.index)
    if not ok:
        say("!! 安装失败:", pkg)
        say("   不影响使用：automate_ocr.py 会自动回退到像素状态机（automate_fixed.py 的逻辑）。")
        return 2

    say("[ok] 包路径:", pkg)
    models = copy_models(pkg)
    say("[ok] 模型已内置:", models)

    try:
        ok, joined = smoke_test()
        say("[smoke]", "通过" if ok else "未通过", repr(joined))
    except Exception as e:
        ok, joined = False, "冒烟测试异常: %s" % e
        say("[smoke] 异常:", e)

    state = {
        "engine": PKG,
        "models": models,
        "models_dir": MODELS_DIR,
        "smoke_ok": bool(ok),
        "smoke_text": joined,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    say("[ok] 状态写入:", STATE_FILE)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
