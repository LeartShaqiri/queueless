import json
import math
import secrets
import sqlite3
import statistics
import time
from datetime import datetime
from pathlib import Path

import forms

DB_PATH = Path(__file__).parent / "queueless.db"
NO_SHOW_SECONDS = 60
PRIORITY_HEAD_START = 10 * 60  # priority tickets jump 10 min ahead, so nobody waits forever
MAX_RECALLS = 1  # one missed call -> back of the line, second miss -> no-show

SERVICES = [
    ("F", "Food pickup", "Collect an order you've already placed", 2.5),
    ("S", "Services", "Support, repairs, returns and contracts", 8.0),
    ("M", "Shopping", "Pay for purchases from Royal, Albi or Prishtina Mall", 5.0),
    ("P", "Payments", "Bills, utilities and municipal fees", 4.0),
]
COUNTERS = ["Counter 1", "Counter 2", "Counter 3"]

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


class QueueError(Exception):
    pass


def init_db():
    if q1("SELECT 1 FROM sqlite_master WHERE name='services'"):
        codes = {r["code"] for r in q("SELECT code FROM services")}
        cols = {r["name"] for r in q("PRAGMA table_info(tickets)")}
        if codes != {s[0] for s in SERVICES} or "details" not in cols:
            conn.executescript("DROP TABLE IF EXISTS tickets; DROP TABLE IF EXISTS services;")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, description TEXT, default_minutes REAL);
        CREATE TABLE IF NOT EXISTS counters(
            id INTEGER PRIMARY KEY, name TEXT, is_open INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY, token TEXT UNIQUE, number TEXT, service_id INTEGER,
            name TEXT, priority INTEGER DEFAULT 0, status TEXT,
            created_at REAL, sort_at REAL, called_at REAL, ack_at REAL,
            started_at REAL, finished_at REAL, counter_id INTEGER,
            recalls INTEGER DEFAULT 0, est_wait_at_issue REAL, simulated INTEGER DEFAULT 0,
            details TEXT, last_recall_at REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value REAL);
        CREATE INDEX IF NOT EXISTS ix_t_status ON tickets(status);
        CREATE INDEX IF NOT EXISTS ix_t_created ON tickets(created_at);
        """
    )
    if "last_recall_at" not in {r["name"] for r in q("PRAGMA table_info(tickets)")}:
        conn.execute("ALTER TABLE tickets ADD COLUMN last_recall_at REAL")
    if not conn.execute("SELECT 1 FROM services").fetchone():
        conn.executemany("INSERT INTO services(code, name, description, default_minutes) VALUES (?,?,?,?)", SERVICES)
    if not conn.execute("SELECT 1 FROM counters").fetchone():
        conn.executemany("INSERT INTO counters(name) VALUES (?)", [(c,) for c in COUNTERS])
    conn.commit()
    _apply_settings()


def q(sql, args=()):
    return conn.execute(sql, args).fetchall()


def q1(sql, args=()):
    return conn.execute(sql, args).fetchone()


def day_start(ts):
    return datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def services():
    return [dict(r) for r in q("SELECT * FROM services ORDER BY code")]


def counters():
    return [dict(r) for r in q("SELECT * FROM counters ORDER BY id")]


TICKET_SQL = """
SELECT t.*, s.code, s.name AS service, c.name AS counter_name
FROM tickets t JOIN services s ON s.id = t.service_id
LEFT JOIN counters c ON c.id = t.counter_id
"""


def _hydrate(r):
    t = dict(r)
    details = json.loads(t.pop("details") or "{}")
    t["details_rows"] = forms.display_rows(t["code"], details)
    return t


def _ticket(where, args=()):
    r = q1(f"{TICKET_SQL} WHERE {where}", args)
    return _hydrate(r) if r else None


def current(counter_id):
    return _ticket("t.counter_id=? AND t.status IN ('called','serving')", (counter_id,))


def waiting_queue():
    return [
        _hydrate(r)
        for r in q(
            f"{TICKET_SQL} WHERE t.status='waiting' "
            f"ORDER BY t.sort_at - t.priority * {PRIORITY_HEAD_START}, t.id"
        )
    ]


def strip(t, details=True):
    if t is None:
        return None
    return {k: v for k, v in t.items() if k != "token" and (details or k != "details_rows")}


# ---------- learning wait-time model ----------

def _ewma(xs, alpha=0.3):
    m = xs[0]
    for x in xs[1:]:
        m = alpha * x + (1 - alpha) * m
    return m


def service_models(now=None):
    """Per-service duration model: recent live data > same-hour history > default."""
    now = now or time.time()
    hour = datetime.fromtimestamp(now).hour
    models = {}
    for s in services():
        recent = [
            r["d"]
            for r in q(
                "SELECT finished_at - started_at AS d FROM tickets WHERE service_id=? "
                "AND status='done' AND started_at IS NOT NULL AND finished_at BETWEEN ? AND ? "
                "ORDER BY finished_at",
                (s["id"], now - 3 * 3600, now),
            )
        ]
        if len(recent) >= 3:
            mean, sd, source = _ewma(recent), statistics.pstdev(recent), "live"
            conf = "high" if len(recent) >= 8 else "medium"
            n = len(recent)
        else:
            hist = [
                r["d"]
                for r in q(
                    "SELECT finished_at - started_at AS d FROM tickets WHERE service_id=? "
                    "AND status='done' AND started_at IS NOT NULL AND finished_at BETWEEN ? AND ? "
                    "AND CAST(strftime('%H', started_at, 'unixepoch', 'localtime') AS INTEGER) BETWEEN ? AND ?",
                    (s["id"], now - 28 * 86400, day_start(now), hour - 1, hour + 1),
                )
            ]
            n = len(hist)
            if n >= 5:
                mean, sd, source, conf = statistics.fmean(hist), statistics.pstdev(hist), "history", "medium"
            else:
                mean = s["default_minutes"] * 60
                sd, source, conf = mean * 0.5, "default", "low"
        models[s["id"]] = {
            "code": s["code"], "name": s["name"], "mean": mean,
            "sd": sd or mean * 0.3, "n": n, "source": source, "confidence": conf,
        }
    return models


def estimate_all(now=None):
    """Simulate the expected path of the queue across open counters.

    Each open counter becomes free after its current ticket's remaining time; every
    waiting ticket goes to whichever counter frees first. Variance accumulates per
    counter, giving an honest low/high range instead of one fake-precise number.
    """
    now = now or time.time()
    models = service_models(now)
    queue = waiting_queue()
    open_ids = [c["id"] for c in counters() if c["is_open"]]
    if not open_ids:
        for i, t in enumerate(queue):
            t.update(position=i + 1, wait_s=None, low_s=None, high_s=None, confidence="low")
        return queue, None, models

    free, var = {}, {}
    for cid in open_ids:
        cur = current(cid)
        rem = v = 0.0
        if cur:
            m = models[cur["service_id"]]
            if cur["status"] == "serving":
                rem = max(m["mean"] * 0.1, m["mean"] - (now - cur["started_at"]))
            else:
                rem = m["mean"] + 20
            v = m["sd"] ** 2
        free[cid], var[cid] = rem, v

    for i, t in enumerate(queue):
        cid = min(free, key=free.get)
        m = models[t["service_id"]]
        sd = math.sqrt(var[cid])
        t.update(
            position=i + 1, wait_s=free[cid], low_s=max(0.0, free[cid] - sd),
            high_s=free[cid] + sd, confidence=m["confidence"],
        )
        free[cid] += m["mean"]
        var[cid] += m["sd"] ** 2

    cid = min(free, key=free.get)
    sd = math.sqrt(var[cid])
    next_wait = {"wait_s": free[cid], "low_s": max(0.0, free[cid] - sd), "high_s": free[cid] + sd}
    return queue, next_wait, models


# ---------- ticket lifecycle ----------

def next_number(service, ts):
    start = day_start(ts)
    n = q1(
        "SELECT COUNT(*) AS c FROM tickets WHERE service_id=? AND created_at>=? AND created_at<?",
        (service["id"], start, start + 86400),
    )["c"] + 1
    return f"{service['code']}-{n:03d}"


def create_ticket(service_id, data=None, priority=False, now=None, trusted=None):
    """`trusted` = (details, name) skips validation; only the simulator uses it."""
    now = now or time.time()
    s = q1("SELECT * FROM services WHERE id=?", (service_id,))
    if not s:
        raise QueueError("Unknown service")
    details, name = trusted or forms.validate(s["code"], data)
    cur = conn.execute(
        "INSERT INTO tickets(token, number, service_id, name, priority, status, created_at, sort_at, details) "
        "VALUES (?,?,?,?,?,'waiting',?,?,?)",
        (secrets.token_urlsafe(9), next_number(s, now), service_id, name, int(bool(priority)), now, now,
         json.dumps(details)),
    )
    tid = cur.lastrowid
    queue, _, _ = estimate_all(now)
    me = next((x for x in queue if x["id"] == tid), None)
    if me and me["wait_s"] is not None:
        conn.execute("UPDATE tickets SET est_wait_at_issue=? WHERE id=?", (me["wait_s"], tid))
    conn.commit()
    return _ticket("t.id=?", (tid,))


def ticket_view(token):
    t = _ticket("t.token=?", (token,))
    if not t:
        return None
    queue, _, _ = estimate_all()
    if t["status"] == "waiting":
        me = next((x for x in queue if x["id"] == t["id"]), None)
        if me:
            t.update({k: me[k] for k in ("position", "wait_s", "low_s", "high_s", "confidence")})
            t["ahead"] = me["position"] - 1
    if t["status"] == "called":
        t["deadline"] = max(t["called_at"], t["last_recall_at"] or 0) + NO_SHOW_SECONDS * (3 if t["ack_at"] else 1)
    t["waiting_total"] = len(queue)
    t["now_serving"] = [
        {"counter": c["name"], "number": cur["number"]}
        for c in counters()
        if (cur := current(c["id"]))
    ]
    t["server_now"] = time.time()
    return t


def call_next(counter_id):
    c = q1("SELECT * FROM counters WHERE id=?", (counter_id,))
    if not c:
        raise QueueError("Unknown counter")
    if not c["is_open"]:
        raise QueueError("Counter is closed - open it first")
    now = time.time()
    cur = current(counter_id)
    if cur:
        if cur["status"] == "serving":
            conn.execute("UPDATE tickets SET status='done', finished_at=? WHERE id=?", (now, cur["id"]))
        else:
            raise QueueError(f"{cur['number']} was called but hasn't arrived - start or mark no-show first")
    queue = waiting_queue()
    if not queue:
        conn.commit()
        return None
    t = queue[0]
    conn.execute(
        "UPDATE tickets SET status='called', called_at=?, counter_id=? WHERE id=?",
        (now, counter_id, t["id"]),
    )
    conn.commit()
    return _ticket("t.id=?", (t["id"],))


def start(counter_id):
    cur = current(counter_id)
    if not cur or cur["status"] != "called":
        raise QueueError("No called ticket to start")
    now = time.time()
    conn.execute(
        "UPDATE tickets SET status='serving', started_at=?, ack_at=COALESCE(ack_at, ?) WHERE id=?",
        (now, now, cur["id"]),
    )
    conn.commit()
    return _ticket("t.id=?", (cur["id"],))


def complete(counter_id):
    cur = current(counter_id)
    if not cur or cur["status"] != "serving":
        raise QueueError("Nobody is being served at this counter")
    conn.execute("UPDATE tickets SET status='done', finished_at=? WHERE id=?", (time.time(), cur["id"]))
    conn.commit()
    return _ticket("t.id=?", (cur["id"],))


def _no_show(t, now):
    if t["recalls"] >= MAX_RECALLS:
        conn.execute("UPDATE tickets SET status='no_show', finished_at=? WHERE id=?", (now, t["id"]))
        outcome = "no_show"
    else:
        conn.execute(
            "UPDATE tickets SET status='waiting', sort_at=?, recalls=recalls+1, counter_id=NULL, "
            "called_at=NULL, ack_at=NULL, last_recall_at=NULL WHERE id=?",
            (now, t["id"]),
        )
        outcome = "requeued"
    return outcome


def recall(counter_id):
    """Re-announce the called customer and give them a fresh hold window."""
    cur = current(counter_id)
    if not cur or cur["status"] != "called":
        raise QueueError("Nothing to recall")
    conn.execute("UPDATE tickets SET last_recall_at=? WHERE id=?", (time.time(), cur["id"]))
    conn.commit()
    return _ticket("t.id=?", (cur["id"],))


def no_show(counter_id):
    cur = current(counter_id)
    if not cur or cur["status"] != "called":
        raise QueueError("No called ticket to mark as no-show")
    outcome = _no_show(cur, time.time())
    conn.commit()
    return cur, outcome


def sweep_no_shows(now=None):
    now = now or time.time()
    rows = q(
        "SELECT * FROM tickets WHERE status='called' AND "
        "((ack_at IS NULL AND MAX(called_at, COALESCE(last_recall_at, 0)) < ?) OR "
        "(ack_at IS NOT NULL AND MAX(called_at, COALESCE(last_recall_at, 0)) < ?))",
        (now - NO_SHOW_SECONDS, now - 3 * NO_SHOW_SECONDS),
    )
    for r in rows:
        _no_show(dict(r), now)
    conn.commit()
    return len(rows)


def ack(token):
    t = _ticket("t.token=?", (token,))
    if not t or t["status"] != "called":
        raise QueueError("Ticket is not being called")
    conn.execute("UPDATE tickets SET ack_at=? WHERE id=?", (time.time(), t["id"]))
    conn.commit()


def cancel(token):
    t = _ticket("t.token=?", (token,))
    if not t or t["status"] != "waiting":
        raise QueueError("Ticket is not waiting")
    conn.execute("UPDATE tickets SET status='cancelled', finished_at=? WHERE id=?", (time.time(), t["id"]))
    conn.commit()


def toggle_counter(counter_id):
    conn.execute("UPDATE counters SET is_open = 1 - is_open WHERE id=?", (counter_id,))
    conn.commit()


def reset():
    conn.execute("DELETE FROM tickets")
    conn.execute("UPDATE counters SET is_open=1")
    conn.commit()


# ---------- admin ----------

SETTING_LIMITS = {
    "no_show_seconds": (15, 600),
    "priority_head_start": (0, 3600),
    "max_recalls": (0, 5),
}


def get_settings():
    return {"no_show_seconds": NO_SHOW_SECONDS, "priority_head_start": PRIORITY_HEAD_START, "max_recalls": MAX_RECALLS}


def _apply_settings():
    global NO_SHOW_SECONDS, PRIORITY_HEAD_START, MAX_RECALLS
    stored = {r["key"]: r["value"] for r in q("SELECT key, value FROM settings")}
    NO_SHOW_SECONDS = int(stored.get("no_show_seconds", NO_SHOW_SECONDS))
    PRIORITY_HEAD_START = int(stored.get("priority_head_start", PRIORITY_HEAD_START))
    MAX_RECALLS = int(stored.get("max_recalls", MAX_RECALLS))


def update_settings(values: dict):
    for key, v in values.items():
        if key not in SETTING_LIMITS:
            raise QueueError(f"Unknown setting {key}")
        lo, hi = SETTING_LIMITS[key]
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise QueueError(f"{key} must be a whole number")
        if not lo <= v <= hi:
            raise QueueError(f"{key} must be between {lo} and {hi}")
        conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, v))
    conn.commit()
    _apply_settings()
    return get_settings()


def update_service(service_id, name=None, description=None, default_minutes=None):
    s = q1("SELECT * FROM services WHERE id=?", (service_id,))
    if not s:
        raise QueueError("Unknown service")
    name = (name if name is not None else s["name"]).strip()[:40]
    description = (description if description is not None else s["description"] or "").strip()[:120]
    try:
        minutes = float(default_minutes if default_minutes is not None else s["default_minutes"])
    except (TypeError, ValueError):
        raise QueueError("Minutes must be a number")
    if not name or not 0.5 <= minutes <= 120:
        raise QueueError("Name is required and minutes must be between 0.5 and 120")
    conn.execute("UPDATE services SET name=?, description=?, default_minutes=? WHERE id=?", (name, description, minutes, service_id))
    conn.commit()


def add_counter(name):
    name = (name or "").strip()[:30]
    if not name:
        raise QueueError("Give the counter a name")
    conn.execute("INSERT INTO counters(name) VALUES (?)", (name,))
    conn.commit()


def rename_counter(counter_id, name):
    name = (name or "").strip()[:30]
    if not name:
        raise QueueError("Give the counter a name")
    conn.execute("UPDATE counters SET name=? WHERE id=?", (name, counter_id))
    conn.commit()


def delete_counter(counter_id):
    if current(counter_id):
        raise QueueError("Finish or requeue the customer at this counter first")
    if len(counters()) <= 1:
        raise QueueError("Keep at least one counter")
    conn.execute("DELETE FROM counters WHERE id=?", (counter_id,))
    conn.commit()


def admin_tickets(status=None, code=None, search=None, scope="today", limit=300):
    where, args = ["1=1"], []
    if scope == "today":
        where.append("t.created_at >= ?"); args.append(day_start(time.time()))
    elif scope == "active":
        where.append("t.status IN ('waiting','called','serving')")
    if status:
        where.append("t.status = ?"); args.append(status)
    if code:
        where.append("s.code = ?"); args.append(code)
    if search:
        where.append("(t.number LIKE ? OR t.name LIKE ? OR t.details LIKE ?)")
        args += [f"%{search}%"] * 3
    rows = q(f"{TICKET_SQL} WHERE {' AND '.join(where)} ORDER BY t.created_at DESC LIMIT ?", (*args, int(limit)))
    return [_hydrate(r) for r in rows]


def admin_ticket_action(ticket_id, action, counter_id=None):
    t = _ticket("t.id=?", (ticket_id,))
    if not t:
        raise QueueError("Ticket not found")
    now, st = time.time(), t["status"]
    if action == "call":
        if st != "waiting":
            raise QueueError("Only waiting tickets can be called")
        c = q1("SELECT * FROM counters WHERE id=?", (counter_id,))
        if not c or not c["is_open"]:
            raise QueueError("Choose an open counter")
        if current(counter_id):
            raise QueueError(f"{c['name']} is busy")
        conn.execute("UPDATE tickets SET status='called', called_at=?, counter_id=? WHERE id=?", (now, counter_id, ticket_id))
    elif action == "complete":
        if st not in ("called", "serving"):
            raise QueueError("Only called or serving tickets can be completed")
        conn.execute("UPDATE tickets SET status='done', started_at=COALESCE(started_at, ?), finished_at=? WHERE id=?", (now, now, ticket_id))
    elif action == "cancel":
        if st not in ("waiting", "called", "serving"):
            raise QueueError("Ticket is already closed")
        conn.execute("UPDATE tickets SET status='cancelled', finished_at=? WHERE id=?", (now, ticket_id))
    elif action == "requeue":
        if st == "waiting":
            raise QueueError("Ticket is already waiting")
        conn.execute(
            "UPDATE tickets SET status='waiting', sort_at=?, counter_id=NULL, called_at=NULL, ack_at=NULL, "
            "started_at=NULL, finished_at=NULL, last_recall_at=NULL WHERE id=?", (now, ticket_id))
    elif action == "front":
        if st != "waiting":
            raise QueueError("Only waiting tickets can be moved")
        first = q1(f"SELECT MIN(sort_at - priority * {PRIORITY_HEAD_START}) AS m FROM tickets WHERE status='waiting'")["m"]
        conn.execute("UPDATE tickets SET sort_at=? WHERE id=?", (first - 1 + t["priority"] * PRIORITY_HEAD_START, ticket_id))
    elif action == "priority":
        conn.execute("UPDATE tickets SET priority = 1 - priority WHERE id=?", (ticket_id,))
    elif action == "delete":
        conn.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))
    else:
        raise QueueError("Unknown action")
    conn.commit()
    return t


def admin_overview():
    now = time.time()
    today = day_start(now)
    rows = q(
        "SELECT t.status, t.details, s.code, s.name AS service FROM tickets t "
        "JOIN services s ON s.id=t.service_id WHERE t.created_at >= ?", (today,))
    by_status, by_service, money = {}, {}, {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        svc = by_service.setdefault(r["code"], {"name": r["service"], "tickets": 0, "waiting": 0})
        svc["tickets"] += 1
        svc["waiting"] += r["status"] == "waiting"
        if r["status"] in ("cancelled",):
            continue
        d = json.loads(r["details"] or "{}")
        amount = d.get("total") or d.get("amount")
        if amount:
            money[r["service"]] = round(money.get(r["service"], 0) + float(amount), 2)
    return {
        "by_status": by_status, "by_service": by_service, "money": money,
        "total_today": len(rows), "settings": get_settings(),
    }


def snapshot():
    now = time.time()
    queue, next_wait, models = estimate_all(now)
    return {
        "now": now,
        "services": services(),
        "counters": [{**c, "current": strip(current(c["id"]))} for c in counters()],
        "waiting": [strip(t, details=False) for t in queue],
        "next_wait": next_wait,
        "models": list(models.values()),
        "no_show_seconds": NO_SHOW_SECONDS,
    }
