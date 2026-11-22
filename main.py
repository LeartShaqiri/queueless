import asyncio
import io
import os
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

import qrcode
import qrcode.image.svg
import csv
import html

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import re

import analytics
import auth
import catalog
import core
import forms
import orders
import simulate

STATIC = Path(__file__).parent / "static"
PORT = int(os.environ.get("PORT", 8000))


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, msg: dict):
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                self.clients.discard(ws)


hub = Hub()


async def changed(event: dict | None = None):
    if event:
        await hub.broadcast(event)
    await hub.broadcast({"type": "update"})


async def no_show_watcher():
    while True:
        await asyncio.sleep(3)
        try:
            if core.sweep_no_shows():
                await changed()
        except Exception as e:
            print("no-show watcher error:", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.init_db()
    orders.init()
    task =asyncio.create_task(no_show_watcher())
    yield
    task.cancel()


app = FastAPI(title="QueueLess", lifespan=lifespan)


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Make browsers re-check pages and assets every time, so updates show up immediately."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP connect sends nothing; just picks the LAN interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def base_url():
    return (os.environ.get("PUBLIC_URL") or f"http://{lan_ip()}:{PORT}").rstrip("/")


def join_url():
    return base_url() + "/join"


def qr_response(url):
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml")


# ---------- pages ----------

def _page(name):
    async def handler():
        return FileResponse(STATIC / name)
    return handler


for route, file in {"/": "index.html", "/join": "join.html", "/staff": "staff.html",
                    "/tv": "tv.html", "/dashboard": "dashboard.html", "/admin": "admin.html"}.items():
    app.add_api_route(route, _page(file), include_in_schema=False)


@app.get("/t/{token}", include_in_schema=False)
async def ticket_page(token: str):
    return FileResponse(STATIC / "ticket.html")


@app.get("/b/{slug}", include_in_schema=False)
async def business_page(slug: str):
    return FileResponse(STATIC / "order.html")


@app.get("/o/{token}", include_in_schema=False)
async def order_page(token: str):
    return FileResponse(STATIC / "myorder.html")


@app.get("/biz/{slug}", include_in_schema=False)
async def biz_page(slug: str):
    return FileResponse(STATIC / "biz.html")


@app.get("/admin/stickers", include_in_schema=False)
async def stickers_page():
    return FileResponse(STATIC / "stickers.html")


@app.get("/biz/{slug}/sticker", include_in_schema=False)
async def biz_sticker_page(slug: str):
    return FileResponse(STATIC / "stickers.html")


@app.get("/m/{slug}", include_in_schema=False)
async def mall_page(slug: str):
    return FileResponse(STATIC / "mall.html")


@app.get("/pay/{slug}", include_in_schema=False)
async def pay_page(slug: str):
    return FileResponse(STATIC / "quick.html")


@app.get("/service/{slug}", include_in_schema=False)
async def service_page(slug: str):
    return FileResponse(STATIC / "quick.html")


@app.get("/business", include_in_schema=False)
async def business_list_page():
    return FileResponse(STATIC / "business.html")


# ---------- directory (Take a number) ----------

MALL_SLUGS = {orders._slug(m): m for m in forms.MALLS}
BILLER_SLUGS = {orders._slug(b["value"]): b for b in catalog.BILLERS}
SERVICE_SLUGS = {orders._slug(s): s for s in forms.SERVICE_TYPES}
SERVICE_NOTES = {
    "Customer support": "Questions, complaints and general help",
    "Repairs & warranty": "Bring in a faulty product",
    "Returns & exchanges": "Return or swap something you bought",
    "Contracts & accounts": "Sign up, change or cancel a contract",
    "Other": "Anything else — staff will help",
}
LINK_RE = re.compile(r"^/(b|m|pay|service)/[a-z0-9-]{1,60}$")


def _biz_card(b):
    return {"slug": b["slug"], "name": b["name"], "logo": b["logo"], "sub": b["sub"], "path": f"/b/{b['slug']}"}


@app.get("/api/directory")
async def directory():
    snap = core.snapshot()
    return {
        "food": [_biz_card(b) for b in orders.BUSINESSES.values() if b["kind"] == "food"],
        "malls": [{"slug": s, "name": m, "logo": forms.MALL_LOGOS[m], "path": f"/m/{s}",
                   "sub": f"{len(catalog.STORES[m])} store{'s' if len(catalog.STORES[m]) != 1 else ''}"}
                  for s, m in MALL_SLUGS.items()],
        "payments": [{"slug": s, "name": b["value"], "logo": b["logo"], "bg": b.get("bg"), "sub": b["type"], "path": f"/pay/{s}"}
                     for s, b in BILLER_SLUGS.items()],
        "services": [{"slug": s, "name": n, "sub": SERVICE_NOTES.get(n, ""), "path": f"/service/{s}"} for s, n in SERVICE_SLUGS.items()],
        "queue": {"waiting": len(snap["waiting"]), "next_wait": snap["next_wait"]},
    }


@app.get("/api/malls/{slug}")
async def mall_info(slug: str):
    m = MALL_SLUGS.get(slug)
    if not m:
        raise HTTPException(404, "Mall not found")
    stores = [_biz_card(b) for b in orders.BUSINESSES.values() if b["place"] == m]
    return {"slug": slug, "name": m, "logo": forms.MALL_LOGOS[m], "stores": stores}


@app.get("/api/quick/{kind}/{slug}")
async def quick_info(kind: str, slug: str):
    svc = {s["code"]: s for s in core.services()}
    if kind == "pay" and slug in BILLER_SLUGS:
        b = BILLER_SLUGS[slug]
        return {"kind": "pay", "name": b["value"], "logo": b["logo"], "bg": b.get("bg"), "sub": f"{b['type']} bill",
                "service_id": svc["P"]["id"], "preset": {"biller": b["value"]}}
    if kind == "service" and slug in SERVICE_SLUGS:
        n = SERVICE_SLUGS[slug]
        return {"kind": "service", "name": n, "logo": None, "sub": SERVICE_NOTES.get(n, ""),
                "service_id": svc["S"]["id"], "preset": {"service": n}}
    raise HTTPException(404, "Not found")


@app.get("/api/link-qr.svg")
async def link_qr(to: str):
    if not LINK_RE.match(to):
        raise HTTPException(400, "Unsupported link")
    return qr_response(base_url() + to)


@app.get("/api/businesses")
async def business_directory():
    return [{**_biz_card(b), "place": b["place"]} for b in orders.BUSINESSES.values()]


@app.get("/s/{code}", include_in_schema=False)
async def scan(code: str):
    slug, active = orders.resolve_qr(code)
    if slug and active:
        return RedirectResponse(f"/b/{slug}", status_code=302)
    name = orders.BUSINESSES.get(slug, {}).get("name") if slug else None
    msg = (f"This {name} sticker has been replaced with a new one. Please scan the current sticker at the counter."
           if name else "This QR code isn't linked to any business.")
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
        <title>QR code not active</title><link rel="stylesheet" href="/static/style.css"></head>
        <body><div class="wrap narrow" style="padding-top:64px"><div class="eyebrow">QueueLess</div>
        <h1 class="display" style="font-size:44px;margin:10px 0 14px">QR code not active</h1><p class="muted">{html.escape(msg)}</p></div></body></html>""",
        status_code=410 if slug else 404)


# ---------- API ----------

class NewTicket(BaseModel):
    service_id: int
    details: dict[str, str] = Field(default_factory=dict)
    priority: bool = False


@app.get("/api/info")
async def info():
    return {"join_url": join_url()}


@app.get("/api/qr.svg")
async def qr_svg():
    return qr_response(join_url())


# ---------- scan-to-order ----------

async def orders_changed(slug):
    await hub.broadcast({"type": "orders", "business": slug})


@app.get("/api/b/{slug}")
async def get_business(slug: str):
    b = orders.public_business(slug)
    if not b:
        raise HTTPException(404, "Business not found")
    return b


@app.get("/api/b/{slug}/qr.svg")
async def business_qr(slug: str):
    if slug not in orders.BUSINESSES:
        raise HTTPException(404, "Business not found")
    return qr_response(f"{base_url()}/b/{slug}")


class NewOrder(BaseModel):
    name: str = Field(default="", max_length=60)
    items: dict[str, int] = Field(default_factory=dict)
    payment: str = ""
    card_number: str = Field(default="", max_length=30)
    card_expiry: str = Field(default="", max_length=7)
    card_cvv: str = Field(default="", max_length=4)


@app.post("/api/b/{slug}/orders")
async def new_order(slug: str, body: NewOrder):
    try:
        token = orders.place_order(slug, body.model_dump())
    except forms.FormError as e:
        raise HTTPException(422, {"message": str(e), "fields": e.errors})
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await orders_changed(slug)
    return {"token": token}


@app.get("/api/orders/{token}")
async def get_order(token: str):
    o = orders.order_view(token)
    if not o:
        raise HTTPException(404, "Order not found")
    return o


@app.post("/api/orders/{token}/cancel")
async def cancel_order(token: str):
    try:
        slug = orders.cancel(token)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await orders_changed(slug)
    return {"ok": True}


def biz_guard(request: Request, slug: str):
    if slug not in orders.BUSINESSES:
        raise HTTPException(404, "Business not found")
    if not auth.biz_allowed(request, slug):
        raise HTTPException(401, "Business sign-in required")


class PinBody(BaseModel):
    pin: str = Field(max_length=12)


@app.post("/api/biz/{slug}/login")
async def biz_login(slug: str, body: PinBody, request: Request):
    if slug not in orders.BUSINESSES:
        raise HTTPException(404, "Business not found")
    ok = orders.check_pin(slug, body.pin)
    auth.throttle(f"biz:{request.client.host if request.client else '?'}:{slug}", ok)
    if not ok:
        raise HTTPException(401, "Wrong PIN, or no PIN has been set for this business yet")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.BIZ_COOKIE, auth.make_biz_token(slug), max_age=auth.SESSION_SECONDS, httponly=True, samesite="strict")
    return resp


@app.post("/api/biz/{slug}/logout")
async def biz_logout(slug: str):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.BIZ_COOKIE)
    return resp


def qr_info(slug):
    qr = orders.current_qr(slug)
    return {**qr, "url": f"{base_url()}/s/{qr['code']}"} if qr else None


@app.get("/api/biz/{slug}/orders")
async def biz_list(slug: str, request: Request):
    biz_guard(request, slug)
    return {"business": orders.public_business(slug), "orders": orders.biz_orders(slug),
            "counters": orders.counters(slug), "qr": qr_info(slug), "server_now": time.time()}


@app.get("/api/biz/{slug}/qr")
async def biz_qr(slug: str, request: Request):
    biz_guard(request, slug)
    return {"business": orders.public_business(slug), "qr": qr_info(slug)}


@app.post("/api/biz/{slug}/qr")
async def biz_generate_qr(slug: str, request: Request):
    biz_guard(request, slug)
    orders.generate_qr(slug)
    await orders_changed(slug)
    return {"qr": qr_info(slug)}


@app.get("/api/qr/{code}.svg")
async def code_qr(code: str):
    if not core.q1("SELECT 1 FROM biz_qr WHERE code=?", (code,)):
        raise HTTPException(404, "QR code not found")
    return qr_response(f"{base_url()}/s/{code}")


class BizCounter(BaseModel):
    name: str = Field(default="", max_length=30)


async def _biz_counter_call(request, slug, fn, *args):
    biz_guard(request, slug)
    try:
        fn(slug, *args)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await orders_changed(slug)
    return {"counters": orders.counters(slug)}


@app.post("/api/biz/{slug}/counters")
async def biz_add_counter(slug: str, body: BizCounter, request: Request):
    return await _biz_counter_call(request, slug, orders.add_counter, body.name)


@app.put("/api/biz/{slug}/counters/{cid}")
async def biz_rename_counter(slug: str, cid: int, body: BizCounter, request: Request):
    return await _biz_counter_call(request, slug, orders.rename_counter, cid, body.name)


@app.post("/api/biz/{slug}/counters/{cid}/toggle")
async def biz_toggle_counter(slug: str, cid: int, request: Request):
    return await _biz_counter_call(request, slug, orders.toggle_counter, cid)


@app.delete("/api/biz/{slug}/counters/{cid}")
async def biz_delete_counter(slug: str, cid: int, request: Request):
    return await _biz_counter_call(request, slug, orders.delete_counter, cid)


class BizAction(BaseModel):
    action: str
    eta: int | None = None
    reason: str | None = Field(default=None, max_length=120)
    counter_id: int | None = None


@app.post("/api/biz/{slug}/orders/{oid}")
async def biz_order_action(slug: str, oid: int, body: BizAction, request: Request):
    biz_guard(request, slug)
    try:
        orders.biz_action(slug, oid, body.action, body.eta, body.reason, body.counter_id)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await orders_changed(slug)
    return {"ok": True}


@app.post("/api/biz/{slug}/toggle")
async def biz_toggle(slug: str, request: Request):
    biz_guard(request, slug)
    orders.toggle_open(slug)
    await orders_changed(slug)
    return {"ok": True}


@app.get("/api/forms")
async def get_forms():
    return forms.FORMS


@app.get("/api/queue")
async def queue():
    return core.snapshot()


@app.post("/api/tickets")
async def new_ticket(body: NewTicket):
    try:
        t = core.create_ticket(body.service_id, body.details, body.priority)
    except forms.FormError as e:
        raise HTTPException(422, {"message": str(e), "fields": e.errors})
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return {"token": t["token"], "number": t["number"]}


@app.get("/api/tickets/{token}")
async def get_ticket(token: str):
    t = core.ticket_view(token)
    if not t:
        raise HTTPException(404, "Ticket not found")
    return t


@app.post("/api/tickets/{token}/{action}")
async def ticket_action(token: str, action: str):
    try:
        if action == "ack":
            core.ack(token)
        elif action == "cancel":
            core.cancel(token)
        else:
            raise HTTPException(404, "Unknown action")
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return {"ok": True}


@app.post("/api/counters/{cid}/{action}")
async def counter_action(cid: int, action: str):
    event, result = None, {}
    try:
        if action == "call":
            t = core.call_next(cid)
            if t:
                event = {"type": "call", "number": t["number"], "counter": t["counter_name"]}
            result = {"ticket": core.strip(t), "message": None if t else "Queue is empty"}
        elif action == "recall":
            t = core.recall(cid)
            event = {"type": "call", "number": t["number"], "counter": t["counter_name"], "recall": True, "ticket_id": t["id"]}
        elif action == "start":
            core.start(cid)
        elif action == "complete":
            core.complete(cid)
        elif action == "noshow":
            t, outcome = core.no_show(cid)
            result = {"message": f"{t['number']} " + ("moved to the back of the line" if outcome == "requeued" else "marked as no-show")}
        elif action == "toggle":
            core.toggle_counter(cid)
        else:
            raise HTTPException(404, "Unknown action")
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed(event)
    return {"ok": True, **result}


@app.get("/api/dashboard")
async def dashboard():
    return analytics.dashboard()


@app.get("/api/best-times")
async def best_times():
    return analytics.best_times()


ADMIN = [Depends(auth.require_admin)]


@app.post("/api/simulate/history", dependencies=ADMIN)
async def sim_history(days: int = 14):
    n = simulate.simulate_history(max(1, min(days, 60)))
    await changed()
    return {"created": n}


@app.post("/api/simulate/rush", dependencies=ADMIN)
async def sim_rush(n: int = 10):
    simulate.simulate_rush(max(1, min(n, 50)))
    await changed()
    return {"created": n}


@app.post("/api/reset", dependencies=ADMIN)
async def reset():
    core.reset()
    orders.reset()
    await changed()
    return {"ok": True}


# ---------- admin ----------

class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@app.post("/api/admin/login")
async def admin_login(body: Login, request: Request):
    if not auth.check_login(request.client.host if request.client else "?", body.username, body.password):
        raise HTTPException(401, "Wrong username or password")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.SESSION_SECONDS, httponly=True, samesite="strict")
    return resp


@app.post("/api/admin/logout")
async def admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/api/admin/me", dependencies=ADMIN)
async def admin_me():
    return {"user": auth.ADMIN_USER}


@app.get("/api/admin/overview", dependencies=ADMIN)
async def admin_overview():
    return core.admin_overview()


@app.get("/api/admin/tickets", dependencies=ADMIN)
async def admin_tickets(status: str | None = None, code: str | None = None, q: str | None = None, scope: str = "today"):
    return core.admin_tickets(status or None, code or None, (q or "").strip()[:60] or None, scope)


class TicketAction(BaseModel):
    action: str
    counter_id: int | None = None


@app.post("/api/admin/tickets/{tid}", dependencies=ADMIN)
async def admin_ticket(tid: int, body: TicketAction):
    try:
        t = core.admin_ticket_action(tid, body.action, body.counter_id)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    event = None
    if body.action == "call":
        c = core.q1("SELECT name FROM counters WHERE id=?", (body.counter_id,))
        event = {"type": "call", "number": t["number"], "counter": c["name"]}
    await changed(event)
    return {"ok": True}


class CounterBody(BaseModel):
    name: str = Field(default="", max_length=30)


@app.post("/api/admin/counters", dependencies=ADMIN)
async def admin_add_counter(body: CounterBody):
    try:
        core.add_counter(body.name)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return {"ok": True}


@app.put("/api/admin/counters/{cid}", dependencies=ADMIN)
async def admin_rename_counter(cid: int, body: CounterBody):
    try:
        core.rename_counter(cid, body.name)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return {"ok": True}


@app.delete("/api/admin/counters/{cid}", dependencies=ADMIN)
async def admin_delete_counter(cid: int):
    try:
        core.delete_counter(cid)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return {"ok": True}


class ServiceBody(BaseModel):
    name: str = Field(max_length=40)
    description: str = Field(default="", max_length=120)
    default_minutes: float


@app.put("/api/admin/services/{sid}", dependencies=ADMIN)
async def admin_service(sid: int, body: ServiceBody):
    try:
        core.update_service(sid, body.name, body.description, body.default_minutes)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return {"ok": True}


@app.put("/api/admin/settings", dependencies=ADMIN)
async def admin_settings(body: dict[str, int]):
    try:
        s = core.update_settings(body)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await changed()
    return s


@app.get("/api/admin/businesses", dependencies=ADMIN)
async def admin_businesses():
    rows = orders.admin_businesses()
    for b in rows:
        if b["qr"]:
            b["qr"]["url"] = f"{base_url()}/s/{b['qr']['code']}"
    return {"businesses": rows, "base_url": base_url()}


@app.put("/api/admin/businesses/{slug}/pin", dependencies=ADMIN)
async def admin_business_pin(slug: str, body: PinBody):
    try:
        orders.set_pin(slug, body.pin)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/admin/businesses/{slug}/toggle", dependencies=ADMIN)
async def admin_business_toggle(slug: str):
    try:
        orders.toggle_open(slug)
    except core.QueueError as e:
        raise HTTPException(400, str(e))
    await orders_changed(slug)
    return {"ok": True}


@app.get("/api/admin/export.csv", dependencies=ADMIN)
async def admin_export(scope: str = "all"):
    rows = core.admin_tickets(scope=scope, limit=100000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["number", "category", "name", "status", "priority", "created", "called", "finished", "counter", "details"])
    fmt = lambda ts: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else ""
    for t in rows:
        w.writerow([t["number"], t["service"], t["name"] or "", t["status"], t["priority"], fmt(t["created_at"]),
                    fmt(t["called_at"]), fmt(t["finished_at"]), t["counter_name"] or "",
                    "; ".join(f"{r['label']}: {r['value']}".replace("\n", ", ") for r in t["details_rows"])])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=queueless-tickets.csv"})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)
