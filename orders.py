"""Scan-to-order: every business has its own QR sticker, menu and order screen.

Flow: sent -> accepted (with ETA) -> ready (customer's phone rings) -> collected.
Side exits: declined (by business), cancelled (by customer while still 'sent').
Payment: 'card' is paid when ordering; 'cash' is paid at pickup and marked when collected.
"""
import hashlib
import hmac
import json
import re
import secrets
import time
from decimal import Decimal

import catalog
import core
import forms

conn = core.conn
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ACTIVE = ("sent", "accepted", "ready")


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", "")).strip("-")


BUSINESSES = {}
for _name, _r in catalog.RESTAURANTS.items():
    BUSINESSES[_slug(_name)] = {"slug": _slug(_name), "name": _name, "logo": _r["logo"], "sub": _r["sub"],
                                "place": "", "kind": "food", "items": _r["menu"]}
for _mall, _stores in catalog.STORES.items():
    for _s in _stores:
        _sl = _slug(f"{_s['name']} {_mall}")
        BUSINESSES[_sl] = {"slug": _sl, "name": _s["name"], "logo": _s["logo"], "sub": _s["sub"],
                           "place": _mall, "kind": "shop", "items": _s["products"]}


def init():
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY, token TEXT UNIQUE, business TEXT, number TEXT, pickup_code TEXT,
            customer TEXT, items TEXT, total TEXT, payment TEXT, paid INTEGER DEFAULT 0, card TEXT,
            status TEXT, eta_minutes INTEGER, decline_reason TEXT,
            created_at REAL, accepted_at REAL, ready_at REAL, collected_at REAL, last_ring_at REAL);
        CREATE INDEX IF NOT EXISTS ix_o_biz ON orders(business, created_at);
        CREATE TABLE IF NOT EXISTS businesses(slug TEXT PRIMARY KEY, is_open INTEGER DEFAULT 1, pin TEXT);
        CREATE TABLE IF NOT EXISTS biz_counters(
            id INTEGER PRIMARY KEY, business TEXT, name TEXT, is_open INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS biz_qr(
            code TEXT PRIMARY KEY, business TEXT, created_at REAL, active INTEGER DEFAULT 1, scans INTEGER DEFAULT 0);
        """
    )
    if "counter_name" not in {r["name"] for r in core.q("PRAGMA table_info(orders)")}:
        conn.execute("ALTER TABLE orders ADD COLUMN counter_name TEXT")
    conn.executemany("INSERT OR IGNORE INTO businesses(slug) VALUES (?)", [(s,) for s in BUSINESSES])
    import auth
    if re.fullmatch(r"\d{4,8}", auth.DEMO_PIN or ""):
        for r in core.q("SELECT slug FROM businesses WHERE pin IS NULL OR pin = ''"):
            conn.execute("UPDATE businesses SET pin=? WHERE slug=?", (_hash_pin(auth.DEMO_PIN), r["slug"]))
    have = {r["business"] for r in core.q("SELECT DISTINCT business FROM biz_counters")}
    for slug, b in BUSINESSES.items():
        if slug not in have:
            conn.executemany("INSERT INTO biz_counters(business, name) VALUES (?, ?)", [(slug, n) for n in _default_counters(slug, b)])
    conn.commit()


DEFAULT_COUNTERS = {
    "hebs": ["Pickup 1", "Pickup 2"],
    "kfc": ["Pickup 1", "Pickup 2", "Pickup 3"],
    "pano-pizza": ["Counter"],
    "zara-albi-mall": ["Till 1", "Till 2"],
    "h-m-prishtina-mall": ["Till 1", "Till 2"],
    "neptun-royal-mall": ["Collection desk", "Till 1"],
}


def _default_counters(slug, b):
    return DEFAULT_COUNTERS.get(slug) or (["Counter"] if b["kind"] == "food" else ["Till 1"])


# ---------- per-business counters ----------

def counters(slug):
    return [dict(r) for r in core.q("SELECT * FROM biz_counters WHERE business=? ORDER BY id", (slug,))]


def _counter(slug, cid):
    r = core.q1("SELECT * FROM biz_counters WHERE id=? AND business=?", (cid, slug))
    if not r:
        raise core.QueueError("Counter not found")
    return r


def add_counter(slug, name):
    name = (name or "").strip()[:30]
    if not name:
        raise core.QueueError("Give the counter a name")
    if len(counters(slug)) >= 20:
        raise core.QueueError("That's a lot of counters — 20 is the limit")
    conn.execute("INSERT INTO biz_counters(business, name) VALUES (?, ?)", (slug, name))
    conn.commit()


def rename_counter(slug, cid, name):
    _counter(slug, cid)
    name = (name or "").strip()[:30]
    if not name:
        raise core.QueueError("Give the counter a name")
    conn.execute("UPDATE biz_counters SET name=? WHERE id=?", (name, cid))
    conn.commit()


def toggle_counter(slug, cid):
    _counter(slug, cid)
    conn.execute("UPDATE biz_counters SET is_open = 1 - is_open WHERE id=?", (cid,))
    conn.commit()


def delete_counter(slug, cid):
    _counter(slug, cid)
    if len(counters(slug)) <= 1:
        raise core.QueueError("Keep at least one counter")
    conn.execute("DELETE FROM biz_counters WHERE id=?", (cid,))
    conn.commit()


# ---------- generated QR codes ----------

def current_qr(slug):
    r = core.q1("SELECT * FROM biz_qr WHERE business=? AND active=1 ORDER BY created_at DESC LIMIT 1", (slug,))
    return dict(r) if r else None


def generate_qr(slug):
    """Create a fresh QR link for this business. Any previous sticker stops working."""
    if slug not in BUSINESSES:
        raise core.QueueError("Unknown business")
    conn.execute("UPDATE biz_qr SET active=0 WHERE business=?", (slug,))
    code = secrets.token_urlsafe(6)
    conn.execute("INSERT INTO biz_qr(code, business, created_at) VALUES (?, ?, ?)", (code, slug, time.time()))
    conn.commit()
    return current_qr(slug)


def resolve_qr(code):
    """Returns (slug, active) for a scanned code, counting the scan; (None, False) if unknown."""
    r = core.q1("SELECT * FROM biz_qr WHERE code=?", (code,))
    if not r:
        return None, False
    if r["active"]:
        conn.execute("UPDATE biz_qr SET scans = scans + 1 WHERE code=?", (code,))
        conn.commit()
    return r["business"], bool(r["active"])


def reset():
    conn.execute("DELETE FROM orders")
    conn.commit()


def public_business(slug):
    b = BUSINESSES.get(slug)
    if not b:
        return None
    row = core.q1("SELECT is_open FROM businesses WHERE slug=?", (slug,))
    return {**b, "is_open": bool(row["is_open"]) if row else True}


# ---------- PINs ----------

def _hash_pin(pin, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 120_000).hex()
    return f"{salt}${digest}"


def set_pin(slug, pin):
    if slug not in BUSINESSES:
        raise core.QueueError("Unknown business")
    pin = str(pin or "").strip()
    if not re.fullmatch(r"\d{4,8}", pin):
        raise core.QueueError("PIN must be 4 to 8 digits")
    conn.execute("UPDATE businesses SET pin=? WHERE slug=?", (_hash_pin(pin), slug))
    conn.commit()


def check_pin(slug, pin):
    row = core.q1("SELECT pin FROM businesses WHERE slug=?", (slug,))
    if not row or not row["pin"]:
        return False
    salt, _ = row["pin"].split("$", 1)
    return hmac.compare_digest(_hash_pin(str(pin), salt), row["pin"])


def toggle_open(slug):
    if slug not in BUSINESSES:
        raise core.QueueError("Unknown business")
    conn.execute("UPDATE businesses SET is_open = 1 - is_open WHERE slug=?", (slug,))
    conn.commit()


# ---------- ordering ----------

def _hydrate(r):
    o = dict(r)
    o["lines"] = json.loads(o.pop("items") or "[]")
    o["card"] = json.loads(o["card"]) if o.get("card") else None
    if o["status"] == "accepted" and o["accepted_at"] and o["eta_minutes"]:
        o["ready_by"] = o["accepted_at"] + o["eta_minutes"] * 60
    return o


def place_order(slug, data):
    b = public_business(slug)
    if not b:
        raise core.QueueError("Unknown business")
    if not b["is_open"]:
        raise core.QueueError(f"{b['name']} isn't taking orders right now")
    errors = {}
    name = str(data.get("name") or "").strip()
    if not name:
        errors["name"] = "Required"
    elif len(name) > 60:
        errors["name"] = "Too long"

    by_id = {i["id"]: i for i in b["items"]}
    raw = data.get("items") if isinstance(data.get("items"), dict) else {}
    lines, total = [], Decimal("0")
    for item_id, qty in raw.items():
        if item_id not in by_id or not isinstance(qty, int) or not 0 <= qty <= 20:
            errors["items"] = "Something in your order isn't available"
            break
        if qty:
            it = by_id[item_id]
            lines.append({"name": it["name"], "qty": qty, "price": it["price"]})
            total += Decimal(it["price"]) * qty
    if not lines and "items" not in errors:
        errors["items"] = "Add at least one item"

    payment = data.get("payment")
    card = None
    if payment not in ("card", "cash"):
        errors["payment"] = "Choose how you'll pay"
    elif payment == "card":
        card, card_errors = forms.check_card(data.get("card_number"), data.get("card_expiry"), data.get("card_cvv"))
        errors.update(card_errors)
    if errors:
        raise forms.FormError(errors)

    now = time.time()
    start = core.day_start(now)
    n = core.q1("SELECT COUNT(*) AS c FROM orders WHERE business=? AND created_at>=?", (slug, start))["c"] + 1
    token = secrets.token_urlsafe(9)
    conn.execute(
        "INSERT INTO orders(token, business, number, pickup_code, customer, items, total, payment, paid, card, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?, 'sent', ?)",
        (token, slug, f"#{n:03d}", "".join(secrets.choice(CODE_ALPHABET) for _ in range(4)), name,
         json.dumps(lines), f"{total:.2f}", payment, int(payment == "card"), json.dumps(card) if card else None, now),
    )
    conn.commit()
    return token


def order_view(token):
    r = core.q1("SELECT * FROM orders WHERE token=?", (token,))
    if not r:
        return None
    o = _hydrate(r)
    b = BUSINESSES.get(o["business"], {})
    o["business_info"] = {"slug": o["business"], "name": b.get("name"), "logo": b.get("logo"), "place": b.get("place"), "sub": b.get("sub")}
    if o["status"] in ("sent", "accepted"):
        o["ahead"] = core.q1(
            "SELECT COUNT(*) AS c FROM orders WHERE business=? AND status IN ('sent','accepted') AND created_at < ?",
            (o["business"], o["created_at"]))["c"]
    o["server_now"] = time.time()
    return o


def cancel(token):
    r = core.q1("SELECT * FROM orders WHERE token=?", (token,))
    if not r or r["status"] != "sent":
        raise core.QueueError("This order can no longer be cancelled — please speak to the counter")
    conn.execute("UPDATE orders SET status='cancelled', collected_at=? WHERE id=?", (time.time(), r["id"]))
    conn.commit()
    return r["business"]


# ---------- business side ----------

def biz_orders(slug):
    rows = core.q(
        "SELECT * FROM orders WHERE business=? AND (status IN ('sent','accepted','ready') OR created_at >= ?) "
        "ORDER BY created_at DESC LIMIT 200",
        (slug, core.day_start(time.time())))
    return [_hydrate(r) for r in rows]


def biz_action(slug, order_id, action, eta=None, reason=None, counter_id=None):
    r = core.q1("SELECT * FROM orders WHERE id=? AND business=?", (order_id, slug))
    if not r:
        raise core.QueueError("Order not found")
    now, st = time.time(), r["status"]
    if action == "accept":
        if st != "sent":
            raise core.QueueError("Only new orders can be accepted")
        try:
            eta = int(eta)
        except (TypeError, ValueError):
            raise core.QueueError("Choose a ready time")
        if not 1 <= eta <= 180:
            raise core.QueueError("Ready time must be 1–180 minutes")
        conn.execute("UPDATE orders SET status='accepted', eta_minutes=?, accepted_at=? WHERE id=?", (eta, now, order_id))
    elif action == "decline":
        if st not in ("sent", "accepted"):
            raise core.QueueError("This order can't be declined now")
        conn.execute("UPDATE orders SET status='declined', decline_reason=?, collected_at=? WHERE id=?",
                     ((reason or "").strip()[:120] or None, now, order_id))
    elif action == "ready":
        if st != "accepted":
            raise core.QueueError("Accept the order first")
        open_counters = [c for c in counters(slug) if c["is_open"]]
        if not open_counters:
            raise core.QueueError("Open a counter first, so the customer knows where to collect")
        c = next((c for c in open_counters if c["id"] == counter_id), None) if counter_id else open_counters[0]
        if not c:
            raise core.QueueError("Choose an open counter")
        conn.execute("UPDATE orders SET status='ready', ready_at=?, last_ring_at=?, counter_name=? WHERE id=?",
                     (now, now, c["name"], order_id))
    elif action == "ring":
        if st != "ready":
            raise core.QueueError("Only ready orders can be rung")
        conn.execute("UPDATE orders SET last_ring_at=? WHERE id=?", (now, order_id))
    elif action == "collect":
        if st != "ready":
            raise core.QueueError("Mark the order ready first")
        conn.execute("UPDATE orders SET status='collected', collected_at=?, paid=1 WHERE id=?", (now, order_id))
    else:
        raise core.QueueError("Unknown action")
    conn.commit()
    return dict(r)


def admin_businesses():
    today = core.day_start(time.time())
    stats = {r["business"]: dict(r) for r in core.q(
        "SELECT business, COUNT(*) AS orders, SUM(status IN ('sent','accepted','ready')) AS active, "
        "SUM(CASE WHEN status NOT IN ('declined','cancelled') THEN CAST(total AS REAL) ELSE 0 END) AS value, "
        "SUM(CASE WHEN status='collected' AND payment='cash' THEN CAST(total AS REAL) ELSE 0 END) AS cash "
        "FROM orders WHERE created_at >= ? GROUP BY business", (today,))}
    rows = {r["slug"]: r for r in core.q("SELECT * FROM businesses")}
    out = []
    for slug, b in BUSINESSES.items():
        s = stats.get(slug, {})
        out.append({
            "slug": slug, "name": b["name"], "logo": b["logo"], "place": b["place"], "sub": b["sub"], "kind": b["kind"],
            "is_open": bool(rows[slug]["is_open"]) if slug in rows else True,
            "has_pin": bool(rows.get(slug) and rows[slug]["pin"]),
            "counters": [c["name"] for c in counters(slug)],
            "qr": current_qr(slug),
            "orders_today": s.get("orders", 0) or 0, "active": s.get("active", 0) or 0,
            "value_today": round(s.get("value") or 0, 2), "cash_today": round(s.get("cash") or 0, 2),
        })
    return out
