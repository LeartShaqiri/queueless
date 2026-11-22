"""Generates realistic traffic so the dashboard and estimator have data during a demo."""
import json
import math
import random
import secrets
import time
from datetime import datetime, timedelta

import catalog
import core
import forms

OPEN_H, CLOSE_H = 8, 18
HOURLY = {8: 0.6, 9: 1.1, 10: 1.0, 11: 1.2, 12: 1.9, 13: 1.6, 14: 0.9, 15: 0.8, 16: 1.3, 17: 1.0}
DOW = [1.3, 1.0, 0.9, 1.0, 1.4, 0.7, 0.5]  # Mon..Sun
BASE_PER_HOUR = 14
MIX = {"F": 0.35, "S": 0.20, "M": 0.30, "P": 0.15}
FIRST = ["Arben", "Blerta", "Driton", "Elira", "Faton", "Gentiana", "Ilir", "Jeta", "Kushtrim",
         "Liridona", "Mentor", "Nora", "Rinor", "Shqipe", "Valon", "Vjosa", "Ardit", "Era"]
LAST = ["Krasniqi", "Gashi", "Berisha", "Hoxha", "Morina", "Shala", "Bytyqi", "Kastrati", "Rexhepi", "Hajdari", "Ahmeti"]


def _fake_cart(catalog, rng, max_lines):
    picks = rng.sample(catalog, k=min(len(catalog), rng.randint(1, max_lines)))
    lines, total = [], 0.0
    for item in picks:
        qty = rng.choice([1, 1, 1, 2]) if max_lines > 2 else 1
        lines.append(f"{qty}× {item['name']}")
        total += float(item["price"]) * qty
    return {"items": "\n".join(lines), "total": f"{total:.2f}"}


def fake_details(code, rng=random):
    if code == "F":
        restaurant = rng.choice(list(catalog.RESTAURANTS))
        d = {"full_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "restaurant": restaurant,
             "order_code": "".join(rng.choices(forms.ORDER_ALPHABET, k=4)),
             **_fake_cart(catalog.RESTAURANTS[restaurant]["menu"], rng, 4)}
        return d, d["full_name"]
    d = {"first_name": rng.choice(FIRST), "last_name": rng.choice(LAST)}
    if code == "S":
        d["service"] = rng.choice(forms.SERVICE_TYPES)
    elif code == "M":
        mall = rng.choice(forms.MALLS)
        store = rng.choice(catalog.STORES[mall])
        d.update(
            mall=mall, store=store["name"], **_fake_cart(store["products"], rng, 2),
            card_brand=rng.choice(["Visa", "Mastercard"]), card_last4=f"{rng.randint(0, 9999):04d}",
            card_expiry=f"{rng.randint(1, 12):02d}/{rng.randint(27, 31)}",
        )
    elif code == "P":
        biller = rng.choice(catalog.BILLERS)
        d.update(biller=biller["value"], payment=biller["type"], reference=str(rng.randint(10**7, 10**8 - 1)),
                 amount=f"{rng.uniform(10, 180):.2f}")
    return d, f"{d['first_name']} {d['last_name']}"


def simulate_history(days=14, seed=None):
    rng = random.Random(seed)
    now = time.time()
    svcs = core.services()
    weights = [MIX.get(s["code"], 0.2) for s in svcs]
    counter_ids = [c["id"] for c in core.counters()]
    core.conn.execute("DELETE FROM tickets WHERE simulated=1")

    rows = []
    today0 = datetime.fromtimestamp(core.day_start(now))
    for d in range(days, -1, -1):
        day = today0 - timedelta(days=d)
        dow_factor = DOW[day.weekday()]
        if dow_factor == 0:
            continue
        arrivals = []
        for h in range(OPEN_H, CLOSE_H):
            lam = BASE_PER_HOUR * HOURLY[h] * dow_factor / 3600
            t = day.replace(hour=h).timestamp()
            end = t + 3600
            while (t := t + rng.expovariate(lam)) < end:
                arrivals.append(t)

        free = [day.replace(hour=OPEN_H).timestamp()] * len(counter_ids)
        numbers = {s["id"]: 0 for s in svcs}
        for a in arrivals:
            s = rng.choices(svcs, weights=weights)[0]
            numbers[s["id"]] += 1
            i = min(range(len(free)), key=free.__getitem__)
            called = max(a, free[i]) + rng.uniform(5, 20)
            if rng.random() < 0.05:
                status, started, finished = "no_show", None, called + core.NO_SHOW_SECONDS
            else:
                status = "done"
                started = called + rng.uniform(15, 45)
                finished = started + rng.lognormvariate(math.log(s["default_minutes"] * 60), 0.35)
            free[i] = finished
            if finished > now:
                continue
            wait = called - a
            est = max(0.0, wait * rng.gauss(1, 0.15) + rng.gauss(0, 30))
            details, name = fake_details(s["code"], rng)
            rows.append((
                secrets.token_urlsafe(9), f"{s['code']}-{numbers[s['id']]:03d}", s["id"],
                name, int(rng.random() < 0.06), status, a, a, called,
                started, started, finished, counter_ids[i], est, json.dumps(details),
            ))

    core.conn.executemany(
        "INSERT INTO tickets(token, number, service_id, name, priority, status, created_at, sort_at, "
        "called_at, ack_at, started_at, finished_at, counter_id, est_wait_at_issue, details, simulated) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        rows,
    )
    core.conn.commit()
    return len(rows)


def simulate_rush(n=10):
    svcs = core.services()
    weights = [MIX.get(s["code"], 0.2) for s in svcs]
    for _ in range(n):
        s = random.choices(svcs, weights=weights)[0]
        core.create_ticket(s["id"], priority=random.random() < 0.1, trusted=fake_details(s["code"]))
    return n
