"""
Owner dashboard — a lightweight HTTP server the shop owner opens on their
phone or tablet to see live sales, stock and alerts without installing anything.

Usage
-----
    import web_dashboard
    port = web_dashboard.start()          # starts once; safe to call again
    ip   = web_dashboard.get_local_ip()
    # owner visits  http://<ip>:<port>  on their phone
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import database as db
import db_connection

PORT = 8765
_server: "HTTPServer | None" = None
_thread: "threading.Thread | None" = None

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _summary() -> dict:
    from datetime import date, timedelta

    today_str = date.today().isoformat()
    all_inv   = [dict(r) for r in db.get_all_invoices()]
    products  = [dict(p) for p in db.get_all_products()]

    # Today's paid bills
    today_inv = [i for i in all_inv
                 if (i.get("invoice_date") or "")[:10] == today_str
                 and i.get("status") == "Paid"]
    today_rev = round(sum(float(i.get("grand_total") or 0) for i in today_inv), 2)

    # Last 7 days revenue
    week = []
    for d in range(6, -1, -1):
        ds  = (date.today() - timedelta(days=d)).isoformat()
        rev = round(sum(float(i.get("grand_total") or 0)
                        for i in all_inv
                        if (i.get("invoice_date") or "")[:10] == ds
                        and i.get("status") == "Paid"), 2)
        week.append({"date": ds, "revenue": rev})

    # This month
    month_prefix = today_str[:7]
    month_inv = [i for i in all_inv
                 if (i.get("invoice_date") or "").startswith(month_prefix)
                 and i.get("status") == "Paid"]
    month_rev = round(sum(float(i.get("grand_total") or 0) for i in month_inv), 2)

    # Low stock
    low_stock = []
    for p in products:
        qty       = float(p.get("stock_quantity") or 0)
        threshold = float(p.get("low_stock_threshold") or 0)
        if threshold > 0 and qty <= threshold:
            low_stock.append({
                "name":      p["name"],
                "stock":     qty,
                "threshold": threshold,
                "unit":      p.get("unit", "pcs"),
            })
    low_stock.sort(key=lambda x: x["stock"] / max(x["threshold"], 1))

    # Recent 10 paid bills
    paid = sorted(
        [i for i in all_inv if i.get("status") == "Paid"],
        key=lambda x: str(x.get("created_at") or x.get("invoice_date") or ""),
        reverse=True,
    )[:10]
    recent = [{
        "invoice_number": i["invoice_number"],
        "grand_total":    round(float(i.get("grand_total") or 0), 2),
        "invoice_date":   (i.get("invoice_date") or "")[:10],
    } for i in paid]

    # Offline queue
    queue_count = db.get_offline_queue_count()

    return {
        "today":        {"revenue": today_rev, "bills": len(today_inv), "date": today_str},
        "month":        {"revenue": month_rev, "bills": len(month_inv)},
        "week":         week,
        "low_stock":    low_stock,
        "recent_bills": recent,
        "cloud":        db_connection.is_cloud(),
        "queue_count":  queue_count,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Owner Dashboard</title>
<style>
:root{
  --bg:#0a0f1e;--card:#0d1424;--border:#1e2a3a;
  --accent:#2dd4bf;--green:#2ecc71;--red:#e74c3c;--yellow:#f59e0b;
  --text:#ecf0f1;--muted:#94a3b8;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;font-size:14px}
header{
  background:var(--card);border-bottom:1px solid var(--border);
  padding:14px 18px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:10;
}
header h1{font-size:1rem;color:var(--accent);font-weight:700}
#dot{font-size:0.8rem}
main{padding:14px;max-width:540px;margin:0 auto}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px}
.lbl{font-size:0.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}
.val{font-size:1.5rem;font-weight:700}
.sub{font-size:0.72rem;color:var(--muted);margin-top:3px}
.sec{font-size:0.75rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:18px 0 8px}
.bars{display:flex;align-items:flex-end;gap:5px;height:56px;margin-bottom:4px}
.bw{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;height:100%;justify-content:flex-end}
.b{background:var(--accent);border-radius:3px 3px 0 0;width:100%;min-height:2px;opacity:.8}
.b.today{background:var(--green);opacity:1}
.blbls{display:flex;gap:5px}
.blbl{flex:1;text-align:center;font-size:0.6rem;color:var(--muted)}
.row{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border)}
.row:last-child{border-bottom:none}
.rn{font-size:.85rem}
.rs{font-size:.7rem;color:var(--muted);margin-top:2px}
.badge{font-size:.7rem;padding:2px 8px;border-radius:999px;font-weight:600;white-space:nowrap}
.red{background:rgba(231,76,60,.15);color:var(--red)}
.ylw{background:rgba(245,158,11,.15);color:var(--yellow)}
.grn{color:var(--green);font-weight:600}
.empty{color:var(--muted);font-size:.82rem;text-align:center;padding:14px 0}
#ts{font-size:.68rem;color:var(--muted);text-align:center;margin-top:18px;padding-bottom:28px}
</style>
</head>
<body>
<header>
  <h1>🏪 Owner Dashboard</h1>
  <span id="dot">…</span>
</header>
<main>
  <div class="grid2">
    <div class="card">
      <div class="lbl">Today's Revenue</div>
      <div class="val" id="rev">—</div>
      <div class="sub" id="rev-sub"></div>
    </div>
    <div class="card">
      <div class="lbl">Bills Today</div>
      <div class="val" id="bills">—</div>
      <div class="sub">paid invoices</div>
    </div>
  </div>
  <div class="grid2">
    <div class="card">
      <div class="lbl">This Month</div>
      <div class="val" id="mrev">—</div>
      <div class="sub" id="mrev-sub"></div>
    </div>
    <div class="card">
      <div class="lbl">Low Stock Items</div>
      <div class="val" id="lscount">—</div>
      <div class="sub">need attention</div>
    </div>
  </div>

  <div class="sec">7-Day Revenue</div>
  <div class="card" style="padding:14px 10px 8px">
    <div class="bars" id="bars"></div>
    <div class="blbls" id="blbls"></div>
  </div>

  <div class="sec">⚠ Low Stock</div>
  <div class="card" id="ls-card"></div>

  <div class="sec">Recent Bills</div>
  <div class="card" id="rb-card"></div>

  <div id="ts"></div>
</main>
<script>
const D=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const fmt=n=>'₹'+Number(n).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});

async function load(){
  try{
    const r=await fetch('/api/summary');
    if(!r.ok)throw new Error(r.status);
    const d=await r.json();

    // header
    const online=d.cloud;
    const q=d.queue_count||0;
    document.getElementById('dot').innerHTML=online
      ?'<span style="color:#2ecc71">● Online</span>'+(q?` <span style="color:#f59e0b;font-size:.7rem">${q} queued</span>`:'')
      :'<span style="color:#e74c3c">● Offline</span>'+(q?` <span style="color:#f59e0b;font-size:.7rem">${q} queued</span>`:'');

    // KPIs
    document.getElementById('rev').textContent=fmt(d.today.revenue);
    document.getElementById('rev-sub').textContent=d.today.date;
    document.getElementById('bills').textContent=d.today.bills;
    document.getElementById('mrev').textContent=fmt(d.month.revenue);
    document.getElementById('mrev-sub').textContent=d.month.bills+' bills';
    document.getElementById('lscount').textContent=d.low_stock.length;

    // bars
    const mx=Math.max(...d.week.map(w=>w.revenue),1);
    const bEl=document.getElementById('bars');
    const lEl=document.getElementById('blbls');
    bEl.innerHTML=lEl.innerHTML='';
    d.week.forEach((w,i)=>{
      const pct=Math.max(4,Math.round(w.revenue/mx*100));
      const isToday=i===6;
      const bw=document.createElement('div');bw.className='bw';
      bw.innerHTML=`<div class="b${isToday?' today':''}" style="height:${pct}%" title="${fmt(w.revenue)}"></div>`;
      bEl.appendChild(bw);
      const ll=document.createElement('div');ll.className='blbl';
      ll.textContent=D[new Date(w.date+'T00:00:00').getDay()];
      lEl.appendChild(ll);
    });

    // low stock
    const lsEl=document.getElementById('ls-card');
    if(!d.low_stock.length){lsEl.innerHTML='<div class="empty">All stock levels OK 🎉</div>';}
    else{lsEl.innerHTML=d.low_stock.map(p=>{
      const pct=p.threshold>0?p.stock/p.threshold:0;
      const cls=pct===0?'red':'ylw';
      const lbl=pct===0?'Out of stock':`${p.stock} / ${p.threshold} ${p.unit}`;
      return`<div class="row"><div><div class="rn">${p.name}</div></div><span class="badge ${cls}">${lbl}</span></div>`;
    }).join('');}

    // recent bills
    const rbEl=document.getElementById('rb-card');
    if(!d.recent_bills.length){rbEl.innerHTML='<div class="empty">No paid bills yet.</div>';}
    else{rbEl.innerHTML=d.recent_bills.map(b=>
      `<div class="row">
        <div><div class="rn">${b.invoice_number}</div><div class="rs">${b.invoice_date}</div></div>
        <span class="grn">${fmt(b.grand_total)}</span>
      </div>`
    ).join('');}

    document.getElementById('ts').textContent='Updated '+new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('dot').innerHTML='<span style="color:#e74c3c">● Error</span>';
  }
}
load();
setInterval(load,30000);
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = _HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/summary":
            try:
                data = _summary()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                err = json.dumps({"error": str(exc)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):  # silence access log
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Best-guess LAN IP address (not 127.0.0.1)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def start(port: int = PORT) -> int:
    """Start the dashboard server (idempotent). Returns the port in use."""
    global _server, _thread
    if _thread and _thread.is_alive():
        return port
    _server = HTTPServer(("0.0.0.0", port), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True, name="dashboard-http")
    _thread.start()
    return port


def stop() -> None:
    global _server
    if _server:
        _server.shutdown()
        _server = None
