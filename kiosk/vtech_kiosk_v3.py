#!/usr/bin/env python3
"""Single-file LAN kiosk for the LF925 local monitor.

The kiosk proxies the typed local API and embeds go2rtc's stream page. It makes
no external network calls and uses only the Python standard library.

Environment:
  VTECH_KIOSK_BIND         default 0.0.0.0
  VTECH_KIOSK_PORT         default 8790
  VTECH_API_URL            default http://127.0.0.1:8787
  VTECH_API_TOKEN          optional bearer token forwarded to the API
  VTECH_CAM1_GO2RTC_PORT   default 1984
  VTECH_CAM2_GO2RTC_PORT   default 1985
  VTECH_CAM1_STREAM        default vtech_baby
  VTECH_CAM2_STREAM        default vtech_baby_2
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.getenv("VTECH_KIOSK_BIND", "0.0.0.0")
PORT = int(os.getenv("VTECH_KIOSK_PORT", "8790"))
API = os.getenv("VTECH_API_URL", "http://127.0.0.1:8787").rstrip("/")
API_TOKEN = os.getenv("VTECH_API_TOKEN", "")
CAM1_PORT = int(os.getenv("VTECH_CAM1_GO2RTC_PORT", "1984"))
CAM2_PORT = int(os.getenv("VTECH_CAM2_GO2RTC_PORT", "1985"))
CAM1_STREAM = os.getenv("VTECH_CAM1_STREAM", "vtech_baby")
CAM2_STREAM = os.getenv("VTECH_CAM2_STREAM", "vtech_baby_2")

CONFIG = {
    "cam1": {"port": CAM1_PORT, "stream": CAM1_STREAM, "label": "Camera 1"},
    "cam2": {"port": CAM2_PORT, "stream": CAM2_STREAM, "label": "Camera 2"},
}

HTML = r'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0d12"><title>LF925 Local Monitor</title>
<style>
:root{color-scheme:dark;--bg:#0b0d12;--panel:#151922;--line:#2a3140;--muted:#9ea8b7;--good:#54d38a;--bad:#ff727d;--accent:#99aaff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f5f7fb;font-family:system-ui,-apple-system,Segoe UI,sans-serif;padding-bottom:30px}
header{position:sticky;top:0;z-index:10;background:rgba(11,13,18,.94);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:12px}
.top{display:flex;justify-content:space-between;align-items:center;gap:10px}.title{font-weight:800}.status{font-size:12px;color:var(--muted)}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:10px}button{background:#1c2230;color:#fff;border:1px solid var(--line);border-radius:12px;padding:10px;cursor:pointer}button.active{background:var(--accent);color:#07101d;font-weight:800}
main{padding:12px;max-width:1200px;margin:auto}.banner{display:none;background:#311d21;border:1px solid var(--bad);color:#ffdadd;border-radius:12px;padding:10px;margin-bottom:10px}.banner.show{display:block}
.grid{display:grid;grid-template-columns:1fr;gap:12px}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden}.camhead{display:flex;justify-content:space-between;align-items:center;padding:10px 12px}.camhead small{color:var(--muted)}iframe{display:block;width:100%;aspect-ratio:16/9;border:0;background:#000}.metrics{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line)}.metric{text-align:center;padding:10px 5px}.metric b{display:block;font-size:18px}.metric span{font-size:10px;color:var(--muted)}
.controls{padding:12px;display:grid;gap:12px}.section{border-top:1px solid var(--line);padding-top:12px}.section:first-child{border-top:0;padding-top:0}.section h3{font-size:12px;margin:0 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.ptz{display:grid;grid-template-columns:repeat(3,54px);grid-template-rows:repeat(3,46px);justify-content:center;gap:5px}.ptz button{padding:0}.up{grid-column:2}.left{grid-row:2}.right{grid-column:3;grid-row:2}.down{grid-column:2;grid-row:3}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}select,input{background:#0e1219;color:#fff;border:1px solid var(--line);border-radius:10px;padding:9px}.events{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.event{background:#0f131b;border:1px solid var(--line);border-radius:10px;padding:9px;text-align:center}.event b{display:block;font-size:12px}.event span{font-size:10px;color:var(--muted)}
.night{position:fixed;inset:0;z-index:50;background:#030406;display:none;align-items:center;justify-content:center;font-size:18vw;color:#4b5361}.night.show{display:flex}.night small{position:absolute;bottom:8vh;font-size:12px;color:#5d6674}
@media(min-width:900px){.grid.two{grid-template-columns:1fr 1fr}.controlsGrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
</style></head><body>
<header><div class="top"><div class="title">LF925 Local Monitor</div><div><button id="nightBtn">Night</button> <span class="status" id="summary">Loading…</span></div></div>
<div class="tabs"><button data-view="cam1" class="active">CAM 1</button><button data-view="both">BOTH</button><button data-view="cam2">CAM 2</button></div></header>
<main><div id="banner" class="banner"></div><div id="cams" class="grid"></div>
<div class="card controls" style="margin-top:12px"><div class="controlsGrid">
<div><div class="section"><h3>PTZ</h3><div class="ptz"><button class="up" data-ptz="up">▲</button><button class="left" data-ptz="left">◀</button><button class="right" data-ptz="right">▶</button><button class="down" data-ptz="down">▼</button></div></div>
<div class="section"><h3>Night light</h3><div class="row"><select id="preset"><option value="blue">Blue</option><option value="white">White</option><option value="yellow">Yellow</option><option value="green">Green</option><option value="purple">Purple</option><option value="orange">Orange</option><option value="beige">Beige</option><option value="rainbow">Rainbow</option></select><select id="brightness"><option value="12">Low</option><option value="57">Medium</option><option value="98" selected>High</option></select><button id="lightOn">Apply</button><button id="lightOff">Off</button></div></div></div>
<div><div class="section"><h3>Lullaby</h3><div class="row"><select id="track"><option value="-1">Stop</option>__TRACKS__</select><button id="trackApply">Apply</button><select id="volume"><option value="1">Vol 1</option><option value="3" selected>Vol 3</option><option value="5">Vol 5</option></select><select id="ltimer"><option value="0">No timer</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option></select><button id="lullabyParams">Volume / timer</button></div></div>
<div class="section"><h3>Events</h3><div class="events"><div class="event"><b>Motion</b><span id="motion">—</span></div><div class="event"><b>Sound / baby</b><span id="sound">—</span></div><div class="event"><b>Temperature</b><span id="tempalert">—</span></div></div></div></div></div></div></main>
<div class="night" id="night"><div id="clock"></div><small>Tap anywhere to return</small></div>
<script>
const cfg=__CONFIG__; let view='cam1'; let states={};
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
function streamUrl(cam){const c=cfg[cam];const h=location.hostname;return `${location.protocol}//${h}:${c.port}/stream.html?src=${encodeURIComponent(c.stream)}&mode=webrtc`}
function age(ms){if(!ms)return '—';const s=Math.max(0,Math.round((Date.now()-ms)/1000));return s<60?`${s}s ago`:`${Math.floor(s/60)}m ago`}
function card(cam){const s=states[cam]||{};const temp=s.temperature_c==null?'—':`${s.temperature_c.toFixed(1)}°C`;const hum=s.humidity_percent==null?'—':`${s.humidity_percent}%`;const online=s.online&&s.runtime_alive;return `<section class="card" data-cam="${cam}"><div class="camhead"><b>${cfg[cam].label}</b><small>${online?'online':'offline'}</small></div><iframe allow="autoplay;fullscreen" src="${streamUrl(cam)}"></iframe><div class="metrics"><div class="metric"><b>${temp}</b><span>Temperature</span></div><div class="metric"><b>${hum}</b><span>Humidity</span></div><div class="metric"><b>${age(s.last_video_ms)}</b><span>Last video</span></div></div></section>`}
function render(){const cams=view==='both'?['cam1','cam2']:[view];$('#cams').className='grid'+(cams.length===2?' two':'');$('#cams').innerHTML=cams.map(card).join('');const s=states[view==='cam2'?'cam2':'cam1']||{};$('#motion').textContent=age(s.last_motion_ms);$('#sound').textContent=age(s.last_sound_ms);$('#tempalert').textContent=age(s.last_temperature_alert_ms);const stale=cams.filter(c=>{const x=states[c];return !x||!x.runtime_alive||!x.last_video_ms||Date.now()-x.last_video_ms>15000});$('#banner').classList.toggle('show',stale.length>0);$('#banner').textContent=stale.length?`Attention: ${stale.join(', ')} is offline or its video timestamp is stale.`:'';$('#summary').textContent=Object.values(states).filter(x=>x&&x.runtime_alive).length+' runtime(s) available';}
async function refresh(){try{const r=await fetch('/api/v1/cameras',{cache:'no-store'});const j=await r.json();states={};(j.cameras||[]).forEach(x=>states[x.camera_id]=x);render()}catch(e){$('#banner').classList.add('show');$('#banner').textContent='Local API unavailable';}}
function target(){return view==='cam2'?'cam2':'cam1'}
async function post(path,body){const r=await fetch(`/api/v1/cameras/${target()}/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){const j=await r.json().catch(()=>({}));alert(j.error||`HTTP ${r.status}`)}await refresh()}
$$('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;$$('[data-view]').forEach(x=>x.classList.toggle('active',x===b));render()});$$('[data-ptz]').forEach(b=>b.onclick=()=>post('ptz',{direction:b.dataset.ptz}));
$('#lightOn').onclick=()=>post('light',{enabled:true,preset:$('#preset').value,brightness:+$('#brightness').value});$('#lightOff').onclick=()=>post('light',{enabled:false,brightness:+$('#brightness').value});$('#trackApply').onclick=()=>post('lullaby',{track:+$('#track').value});$('#lullabyParams').onclick=()=>post('lullaby/params',{volume:+$('#volume').value,timer_seconds:+$('#ltimer').value});
const night=$('#night');$('#nightBtn').onclick=()=>night.classList.add('show');night.onclick=()=>night.classList.remove('show');setInterval(()=>{$('#clock').textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})},1000);refresh();setInterval(refresh,3000);
</script></body></html>'''
HTML = HTML.replace("__CONFIG__", json.dumps(CONFIG)).replace(
    "__TRACKS__", "".join(f'<option value="{i}">Track {i}</option>' for i in range(11))
)


def api_request(method: str, path: str, body: bytes | None = None) -> tuple[int, bytes, str]:
    url = API + path
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, res.read(), res.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
    except OSError as exc:
        payload = json.dumps({"ok": False, "error": f"local API unavailable: {exc}"}).encode()
        return HTTPStatus.BAD_GATEWAY, payload, "application/json"


class Handler(BaseHTTPRequestHandler):
    server_version = "LF925Kiosk/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[lf925-kiosk] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, status: int, data: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            self._send(HTTPStatus.OK, HTML.encode(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self._send(HTTPStatus.OK, b'{"ok":true}', "application/json")
            return
        if path == "/api/v1/cameras" or path.startswith("/api/v1/cameras/"):
            status, data, ctype = api_request("GET", path)
            self._send(status, data, ctype)
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if not path.startswith("/api/v1/cameras/"):
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 16 * 1024:
            self._send(HTTPStatus.BAD_REQUEST, b'{"ok":false,"error":"invalid body"}', "application/json")
            return
        body = self.rfile.read(length)
        status, data, ctype = api_request("POST", path, body)
        self._send(status, data, ctype)


def main() -> None:
    print(f"[lf925-kiosk] listening on http://{HOST}:{PORT} api={API}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
