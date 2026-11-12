#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽水音乐「领时长」GUI 控制面板 —— 本地网页版，零第三方依赖。

    python scripts/gui.py

自动打开 http://127.0.0.1:8765 （端口占用会顺延）。
只用 Python 标准库：http.server / subprocess / threading / webbrowser，
不依赖 tkinter（部分精简 Python 发行版没编译 Tk），Windows / macOS / Linux 通用。

面板能力：可视化配置全部参数、启停脚本、实时日志、实时统计（读 stats.json）。
"""
import os
import sys
import json
import time
import threading
import subprocess
import webbrowser
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
STATS_PATH = os.path.join(HERE, "stats.json")
DEBUG_DIR = os.path.join(HERE, "debug")

HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>汽水音乐 · 领时长 控制面板</title>
<style>
:root{--bg:#0f1319;--panel:#191f29;--line:#2a3442;--txt:#dce6f2;--dim:#8a99ac;--acc:#22c55e;--red:#ef4444}
@media (prefers-color-scheme:light){:root{--bg:#f4f7fb;--panel:#fff;--line:#e2e8f0;--txt:#1a2433;--dim:#64748b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 "Microsoft YaHei UI",system-ui,sans-serif;padding:24px}
.wrap{max-width:1020px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:14px}
label{display:block;color:var(--dim);font-size:12px;margin-bottom:5px}
input,select{width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:9px 11px;font:inherit}
button{border:0;border-radius:8px;padding:10px 18px;font:inherit;font-weight:600;cursor:pointer}
.go{background:var(--acc);color:#06210f}.stop{background:var(--red);color:#fff}
.ghost{background:transparent;color:var(--txt);border:1px solid var(--line)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}
.stat b{display:block;font-size:22px;margin-top:2px}.stat span{color:var(--dim);font-size:12px}
.stat b.small{font-size:14px;font-weight:600}
.bar{height:8px;background:var(--bg);border-radius:6px;overflow:hidden;margin-top:14px}
.bar>i{display:block;height:100%;background:var(--acc);width:0;transition:width .5s}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:14px;height:330px;overflow:auto;
    font:12px/1.65 Consolas,monospace;white-space:pre-wrap;color:var(--txt);margin:0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--dim);margin-right:7px}
.dot.on{background:var(--acc);box-shadow:0 0 8px var(--acc)}
.chk{display:flex;align-items:center;gap:8px;color:var(--dim);font-size:13px;padding-top:8px}
.chk input{width:auto}
.hint{color:var(--dim);font-size:12px;margin-top:12px}
</style></head><body><div class="wrap">
<h1>汽水音乐 · 领时长 控制面板</h1>
<div class="sub">本地运行 · 零第三方依赖 · <span id="state"><span class="dot"></span>未运行</span></div>

<div class="card"><div class="grid">
  <div><label>广告数量上限 --max-ads</label><input id="max_ads" value="120"></div>
  <div><label>时长上限（秒）--max-seconds</label><input id="max_seconds" value="3600"></div>
  <div><label>OCR 抽查间隔 --ocr-every</label><input id="ocr_every" value="10"></div>
  <div><label>目标天数 --target-day</label><input id="target_day" value="31"></div>
  <div><label>运行脚本</label><select id="script">
    <option value="automate_fast.py">极速 v2（像素快路径 + OCR 兜底，推荐）</option>
    <option value="automate_ocr.py">逐帧 OCR 版</option></select></div>
  <div><label>附加选项</label><label class="chk"><input type="checkbox" id="debug"> 调试截图（OCR 标注 + 点击位置）</label></div>
</div>
<div class="row" style="margin-top:16px">
  <button class="go" onclick="startTask()">▶ 开始领取</button>
  <button class="stop" onclick="stopTask()">■ 停止</button>
  <button class="ghost" onclick="clearLog()">清空日志</button>
  <span id="msg" style="color:var(--dim);font-size:13px"></span>
</div>
<div class="hint">提示：手机需保持亮屏并已授权 USB 调试；广告倒计时由 App 强制，无法跳过。</div>
</div>

<div class="card"><div class="stats">
  <div class="stat"><span>已领广告</span><b id="s_ads">—</b></div>
  <div class="stat"><span>已用时</span><b id="s_time">—</b></div>
  <div class="stat"><span>目标天数</span><b id="s_day">—</b></div>
  <div class="stat"><span>平均耗时</span><b id="s_rate">—</b></div>
  <div class="stat"><span>最近动作</span><b class="small" id="s_last">—</b></div>
</div><div class="bar"><i id="bar"></i></div></div>

<div class="card"><pre id="log">等待启动…</pre></div>
</div>
<script>
let last=0;
const E=id=>document.getElementById(id);
function msg(t){E('msg').textContent=t;setTimeout(()=>{E('msg').textContent=''},4000)}
async function startTask(){
  const body={max_ads:+E('max_ads').value,max_seconds:+E('max_seconds').value,
              ocr_every:+E('ocr_every').value,target_day:+E('target_day').value,
              script:E('script').value,debug:E('debug').checked};
  const j=await (await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},
                                           body:JSON.stringify(body)})).json();
  msg(j.message||''); if(j.ok){last=0;E('log').textContent=''}
}
async function stopTask(){
  const j=await (await fetch('/api/stop',{method:'POST'})).json(); msg(j.message||'');
}
function clearLog(){E('log').textContent=''}
async function refresh(){
  try{
    const [st,stats,lg]=await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/stats').then(r=>r.json()).catch(()=>({})),
      fetch('/api/log?since='+last).then(r=>r.json())
    ]);
    E('state').innerHTML='<span class="dot'+(st.running?' on':'')+'"></span>'+(st.running?'运行中':'未运行');
    if(stats.ads!==undefined){
      E('s_ads').textContent=stats.ads+' 轮';
      const s=stats.elapsed||0;
      E('s_time').textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
      E('s_day').textContent=stats.target_day+' 天';
      E('s_rate').textContent=stats.ads?((s/stats.ads).toFixed(1)+' s/轮'):'—';
      E('s_last').textContent=stats.last_action||'—';
      E('bar').style.width=Math.min(100,(stats.ads/Math.max(1,stats.target_day))*100)+'%';
    }
    if(lg.lines&&lg.lines.length){
      E('log').textContent+=lg.lines.join('\n')+'\n';
      E('log').scrollTop=E('log').scrollHeight; last=lg.total;
    }
  }catch(e){}
}
setInterval(refresh,1000); refresh();
</script></body></html>"""


class State:
    def __init__(self):
        self.proc = None
        self.lines = []
        self.lock = threading.Lock()
        self.cmd = []

    def emit(self, s):
        with self.lock:
            self.lines.append(s.rstrip("\n"))
            if len(self.lines) > 8000:          # 防止超长挂机无限增长
                self.lines = self.lines[-4000:]

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, p):
        if self.running():
            return False, "任务已在运行中"
        script = p.get("script", "automate_fast.py")
        if script not in ("automate_fast.py", "automate_ocr.py"):
            return False, "未知脚本"
        try:
            cmd = [sys.executable, os.path.join(HERE, script),
                   "--max-ads", str(int(p.get("max_ads", 120))),
                   "--max-seconds", str(int(p.get("max_seconds", 3600))),
                   "--ocr-every", str(int(p.get("ocr_every", 10))),
                   "--target-day", str(int(p.get("target_day", 31)))]
        except (TypeError, ValueError):
            return False, "参数必须是整数"
        if p.get("debug") and script == "automate_fast.py":
            cmd.append("--debug")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=HERE, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            return False, "启动失败: %s" % e
        self.cmd = cmd
        self.emit("$ " + " ".join(cmd))
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()
        return True, "已启动"

    def _pump(self, proc):
        for line in iter(lambda: proc.stdout.readline(), ""):
            self.emit(line)
        self.emit("==== 进程结束，退出码 %s ====" % proc.wait())

    def stop(self):
        if not self.running():
            return False, "当前没有运行中的任务"
        self.emit("==== 收到停止指令 ====")
        try:
            self.proc.terminate()
        except Exception as e:
            return False, "停止失败: %s" % e
        return True, "已发送停止指令"


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif u.path == "/api/status":
            self._send(200, json.dumps({"running": STATE.running(), "cmd": STATE.cmd}))
        elif u.path == "/api/stats":
            try:
                with open(STATS_PATH, "r", encoding="utf-8") as f:
                    self._send(200, f.read())
            except Exception:
                self._send(200, "{}")
        elif u.path == "/api/log":
            try:
                since = int(urllib.parse.parse_qs(u.query).get("since", ["0"])[0])
            except ValueError:
                since = 0
            with STATE.lock:
                total = len(STATE.lines)
                chunk = STATE.lines[since:] if 0 <= since <= total else []
            self._send(200, json.dumps({"total": total, "lines": chunk}, ensure_ascii=False))
        else:
            self._send(404, "{}")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode("utf-8") if n else "{}"
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {}
        if u.path == "/api/start":
            ok, message = STATE.start(payload)
        elif u.path == "/api/stop":
            ok, message = STATE.stop()
        else:
            self._send(404, "{}")
            return
        self._send(200, json.dumps({"ok": ok, "message": message}, ensure_ascii=False))

    def log_message(self, *a):
        pass  # 静默，日志由业务进程产生


def main():
    srv = None
    port = None
    for p in range(8765, 8776):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        print("!! 8765-8775 端口都被占用，无法启动控制面板")
        return 1
    os.makedirs(DEBUG_DIR, exist_ok=True)
    url = "http://127.0.0.1:%d/" % port
    print("控制面板已启动:", url)
    print("按 Ctrl+C 退出（不会自动停止已经开始的领取任务）")
    try:
        webbrowser.open(url)
    except Exception:
        print("浏览器未能自动打开，请手动访问上面的地址")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n控制面板已退出")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
