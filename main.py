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

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import analytics
import auth
import core
import forms
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
    task = asyncio.create_task(no_show_watcher())
    yield
    task.cancel()


app = FastAPI(title="QueueLess", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP connect sends nothing; just picks the LAN interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def join_url():
    base = os.environ.get("PUBLIC_URL") or f"http://{lan_ip()}:{PORT}"
    return base.rstrip("/") + "/join"


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
    img = qrcode.make(join_url(), image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml")


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
