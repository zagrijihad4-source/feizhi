# -*- coding: utf-8 -*-
r"""本地网页模拟器：扮演陌生人跟绯栀聊天，看她现在什么反应。

只走「生成」这一段真实链路，**不碰微信、不写记忆、不发任何消息**：
  · relation 档位可切（stranger / friend / intimate），默认 stranger
  · memory_ctx 为空 —— 陌生人本来就没有关于她的记忆，这是真实状态
  · life_ctx 用她自己的真实日子（海报、糊糊、此刻心情）

用法：
    python _sim_web.py [--port 8799]
然后浏览器打开 http://127.0.0.1:8799
"""
import argparse
import json
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from autoreply import FeizhiReplyGenerator     # noqa: E402
import outguard                                # noqa: E402
from llm import LLMClient                      # noqa: E402
from peer_state import self_life               # noqa: E402

_LOCK = threading.Lock()
_SESSIONS: dict[str, "SimSession"] = {}


class SimSession:
    """一次模拟对话。别人看不到，也不影响线上任何状态。"""

    def __init__(self, relation: str = "stranger", name: str = "陌生人"):
        self.relation = relation
        self.name = name
        self.history: list[tuple[str, str]] = []
        self.gen = FeizhiReplyGenerator(llm=LLMClient(), timeout=60, attempts=2)
        self.turns = 0

    def ask(self, text: str) -> dict:
        self._refresh_ctx()
        t0 = time.time()
        plan = self.gen.generate_plan(text, list(self.history))
        elapsed = time.time() - t0
        raw = [str(getattr(m, "text", "") or "") for m in (plan.messages or [])]
        # ★ 必须过 outguard：实测模型在没有历史时会直接把 system prompt 的标题
        #   吐出来（「【你的来处 · 这不是设定，是你的记忆】 我叫绯栀……」）。
        #   线上是 _send_plan 里拦的，这里单独跑生成链路，得自己拦一遍。
        msgs = []
        for t in raw:
            if not t.strip():
                continue
            clean, gstate = outguard.guard(t, regenerate=None,
                                           log=lambda m: print("  outguard:", m))
            if not clean:
                print("  outguard 丢弃一条（%s）：%r" % (gstate, t[:50]))
                continue
            if gstate != "pass":
                print("  outguard 处置=%s -> %r" % (gstate, clean[:50]))
            msgs.append(clean)
        # ★ 历史必须**按条**记：线上 store.history 返回的就是一条消息一条记录，
        #   合并成一条会让她以为自己上次只发了一句，多轮的连贯性就对不上。
        if msgs:
            self.history.append(("user", text))
            for t in msgs:
                self.history.append(("assistant", t))
            self.turns += 1
        return {
            "messages": msgs,
            "elapsed": round(elapsed, 2),
            "relation": self.relation,
            "life": self._life_brief(),
            "turns": self.turns,
        }

    def _refresh_ctx(self):
        """每轮重新读她的日子 —— 别拿几小时前的快照聊天。"""
        g = self.gen
        g.relation = self.relation
        g.peer_name = self.name
        g.memory_ctx = ""          # 陌生人：没有任何关于他的记忆
        g.context_text = ""
        g.search_ctx = ""
        try:
            life = self_life()
            life.reload_shared()
            g.life_ctx = life.render(include_loops=False)
        except Exception as exc:   # noqa: BLE001
            print("life 渲染失败：%r" % (exc,))
            g.life_ctx = ""

    def _life_brief(self) -> str:
        try:
            life = self_life()
            life.reload_shared()
            proj = [p.get("title", "") for p in life.ongoing()]
            mood = (life.data.get("mood") or {}).get("state", "")
            return " | ".join(x for x in ("、".join(proj), mood) if x)
        except Exception:  # noqa: BLE001
            return ""


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>陌生人测试 · 绯栀</title>
<style>
:root{
  --bg:#111315; --panel:#181b1d; --line:#25292d; --ink:#e8e6e3;
  --dim:#8b9199; --green:#3fb950; --me:#2b6cb0; --tag:#20262c;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:radial-gradient(1200px 600px at 20% -10%,#1b2226 0%,var(--bg) 55%);
  color:var(--ink);height:100vh;display:flex;flex-direction:column;
  font:15px/1.7 "PingFang SC","Microsoft YaHei","Source Han Sans SC",sans-serif;
}
header{
  display:flex;align-items:center;gap:14px;padding:14px 20px;
  border-bottom:1px solid var(--line);background:rgba(24,27,29,.85);
  backdrop-filter:blur(8px);flex-wrap:wrap;
}
h1{font-size:15px;font-weight:600;letter-spacing:.5px}
h1 small{color:var(--dim);font-weight:400;margin-left:8px;font-size:12px}
.seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{
  background:transparent;border:0;color:var(--dim);padding:6px 14px;
  font:inherit;font-size:13px;cursor:pointer;transition:.16s;
}
.seg button:hover{color:var(--ink);background:#1e2327}
.seg button.on{background:var(--green);color:#0b0d0e;font-weight:600}
.meta{margin-left:auto;color:var(--dim);font-size:12px;display:flex;gap:16px}
main{flex:1;overflow-y:auto;padding:24px 20px;display:flex;flex-direction:column;gap:14px}
.row{display:flex;gap:10px;max-width:820px}
.row.me{align-self:flex-end;flex-direction:row-reverse}
.who{
  width:34px;height:34px;border-radius:9px;flex:none;display:grid;
  place-items:center;font-size:13px;font-weight:600;
}
.me .who{background:var(--me);color:#fff}
.her .who{background:linear-gradient(145deg,#3a4a3f,#26302a);color:var(--green)}
.bubbles{display:flex;flex-direction:column;gap:8px}
.bubble{
  background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:9px 14px;white-space:pre-wrap;word-break:break-word;
}
.me .bubble{background:#1d2b3a;border-color:#27405a}
.tag{
  display:inline-block;background:var(--tag);border:1px dashed #3a4249;
  border-radius:7px;padding:2px 9px;margin:2px 0;font-size:13px;color:#9fb3c8;
}
.tag.sing{color:#e2c07a;border-color:#5c4a24}
.tag.voice{color:#7fc4e8;border-color:#24485c}
.tag.img{color:#c9a0e0;border-color:#432f52}
.tag.draw{color:#e0a0a0;border-color:#5c2f2f}
.raw{margin-top:6px;color:#5c646c;font-size:11.5px;font-family:Consolas,monospace}
footer{padding:14px 20px;border-top:1px solid var(--line);background:var(--panel)}
form{display:flex;gap:10px;max-width:900px;margin:0 auto}
input[type=text]{
  flex:1;background:#0e1113;border:1px solid var(--line);border-radius:10px;
  padding:12px 15px;color:var(--ink);font:inherit;outline:none;transition:.16s;
}
input[type=text]:focus{border-color:#3a5a43;box-shadow:0 0 0 3px rgba(63,185,80,.09)}
button.send{
  background:var(--green);color:#0b0d0e;border:0;border-radius:10px;
  padding:0 24px;font:inherit;font-weight:600;cursor:pointer;transition:.16s;
}
button.send:disabled{opacity:.4;cursor:default}
.hint{max-width:900px;margin:8px auto 0;color:#5c646c;font-size:12px}
.spin{color:var(--dim);font-size:13px;padding-left:44px}
</style></head><body>
<header>
  <h1>陌生人测试<small>只走生成链路，不碰微信</small></h1>
  <div class="seg" id="seg">
    <button data-r="stranger" class="on">陌生</button>
    <button data-r="friend">熟人</button>
    <button data-r="intimate">恋人</button>
  </div>
  <button class="seg" id="reset" style="background:transparent;border:1px solid var(--line);color:var(--dim);padding:6px 14px;border-radius:8px;cursor:pointer;font:inherit;font-size:13px">重开</button>
  <div class="meta"><span id="life">—</span><span id="turn"></span></div>
</header>
<main id="chat"></main>
<footer>
  <form id="f">
    <input id="q" type="text" autocomplete="off" placeholder="你以陌生人身份说点什么…（试试「你是谁」「唱个歌我听听」「你头像很丑」）">
    <button class="send" id="go">发送</button>
  </form>
  <div class="hint">记忆为空（陌生人本就没有），日子和心情用她真实的。括号里是模型实际吐出的标记。</div>
</footer>
<script>
let relation='stranger', busy=false;
const chat=document.getElementById('chat'), q=document.getElementById('q'),
      go=document.getElementById('go'), lifeEl=document.getElementById('life'),
      turnEl=document.getElementById('turn');

function tagify(t){
  let h=t.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  h=h.replace(/\[sing:([^\]]+)\]/g,'<span class="tag sing">♪ 唱《$1》</span>');
  h=h.replace(/\[voice:([^:\]]+):([^\]]+)\]/g,'<span class="tag voice">▮ 语音·$1「$2」</span>');
  h=h.replace(/\[voice:([^\]]+)\]/g,'<span class="tag voice">▮ 语音「$1」</span>');
  h=h.replace(/\[img:([^\]]+)\]/g,'<span class="tag img">◧ 表情「$1」</span>');
  h=h.replace(/\[draw:([^\]]+)\]/g,'<span class="tag draw">✎ 现画：$1</span>');
  return h;
}
function add(who, texts, raw){
  const row=document.createElement('div'); row.className='row '+who;
  const av=document.createElement('div'); av.className='who';
  av.textContent = who==='me'?'我':'她';
  const box=document.createElement('div'); box.className='bubbles';
  (Array.isArray(texts)?texts:[texts]).forEach(t=>{
    const b=document.createElement('div'); b.className='bubble';
    b.innerHTML=tagify(t); box.appendChild(b);
    if(raw){const r=document.createElement('div');r.className='raw';r.textContent=t;box.appendChild(r);}
  });
  row.append(av,box); chat.appendChild(row);
  chat.scrollTop=chat.scrollHeight;
}
function setRel(r){
  relation=r;
  document.querySelectorAll('#seg button').forEach(b=>b.classList.toggle('on',b.dataset.r===r));
  newSession();
}
async function newSession(){
  chat.innerHTML=''; turnEl.textContent='';
  await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({relation})});
}
document.getElementById('seg').onclick=e=>{ if(e.target.dataset.r) setRel(e.target.dataset.r); };
document.getElementById('reset').onclick=()=>newSession();

document.getElementById('f').onsubmit=async e=>{
  e.preventDefault();
  const text=q.value.trim(); if(!text||busy) return;
  busy=true; go.disabled=true; q.value='';
  add('me', text, false);
  const spin=document.createElement('div'); spin.className='spin';
  spin.textContent='她在打字…'; chat.appendChild(spin); chat.scrollTop=chat.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({relation, text})});
    const d=await r.json();
    spin.remove();
    if(d.error){ add('her','[出错] '+d.error,false); }
    else{
      add('her', d.messages.length?d.messages:['（这一轮她没有要说的）'], true);
      lifeEl.textContent=d.life||'—';
      turnEl.textContent='第 '+d.turns+' 轮 · '+d.elapsed+'s';
    }
  }catch(err){
    spin.remove(); add('her','[请求失败] '+err,false);
  }
  busy=false; go.disabled=false; q.focus();
};
q.focus();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):      # 静音默认访问日志
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
        if self.path == "/api/reset":
            rel = str(data.get("relation") or "stranger")
            with _LOCK:
                _SESSIONS.clear()
                _SESSIONS["web"] = SimSession(rel)
            body = json.dumps({"ok": True, "relation": rel}, ensure_ascii=False)
            self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")
            return
        if self.path == "/api/chat":
            text = str(data.get("text") or "").strip()
            rel = str(data.get("relation") or "stranger")
            if not text:
                self._send(200, json.dumps({"error": "空消息"}, ensure_ascii=False)
                           .encode("utf-8"), "application/json; charset=utf-8")
                return
            with _LOCK:
                sess = _SESSIONS.get("web")
                if sess is None or sess.relation != rel:
                    sess = SimSession(rel)
                    _SESSIONS["web"] = sess
            try:
                out = sess.ask(text)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                out = {"error": "%s: %s" % (type(exc).__name__, exc)}
            self._send(200, json.dumps(out, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    args = ap.parse_args()

    with _LOCK:
        _SESSIONS["web"] = SimSession("stranger")
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("=" * 60)
    print("绯栀 · 陌生人模拟器")
    print("  http://127.0.0.1:%d" % args.port)
    print("  只走生成链路；不写记忆、不发微信")
    print("=" * 60, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n停止")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
