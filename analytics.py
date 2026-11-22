import math
import time
from datetime import datetime

import pandas as pd

import core

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _num(x, nd=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def load(days=28):
    now = time.time()
    df = pd.read_sql_query(
        "SELECT t.id, t.status, t.priority, t.created_at, t.called_at, t.started_at, t.finished_at, "
        "t.est_wait_at_issue, s.code, s.name AS service FROM tickets t "
        "JOIN services s ON s.id = t.service_id WHERE t.created_at >= ?",
        core.conn,
        params=(now - days * 86400,),
    )
    if df.empty:
        return df
    df["created"] = pd.to_datetime(df["created_at"].map(datetime.fromtimestamp))
    df["wait_min"] = (df["called_at"] - df["created_at"]) / 60
    df["svc_min"] = (df["finished_at"] - df["started_at"]) / 60
    df["date"] = df["created"].dt.date
    df["hour"] = df["created"].dt.hour
    df["dow"] = df["created"].dt.dayofweek
    return df


def arrivals_heatmap(df):
    """Average arrivals per (weekday, hour), normalised by how many of that weekday we've seen."""
    counts = df.groupby(["dow", "hour"]).size()
    days_seen = df.groupby("dow")["date"].nunique()
    avg = counts.div(days_seen, level="dow").unstack(fill_value=0)
    hours = list(range(int(df["hour"].min()), int(df["hour"].max()) + 1))
    return avg.reindex(index=range(7), columns=hours, fill_value=0)


def dashboard():
    now = time.time()
    df = load()
    if df.empty:
        return {"empty": True}

    today = df[df["created_at"] >= core.day_start(now)]
    served = today[today["status"] == "done"]
    closed = today[today["status"].isin(["done", "no_show"])]
    pred = df.dropna(subset=["est_wait_at_issue", "called_at"])
    mae = ((pred["est_wait_at_issue"] / 60) - pred["wait_min"]).abs().mean() if len(pred) else None

    kpis = {
        "served_today": int(len(served)),
        "waiting_now": int((df["status"] == "waiting").sum()),
        "avg_wait_today": _num(today["wait_min"].mean()),
        "avg_service_today": _num(served["svc_min"].mean()),
        "no_show_rate": _num((closed["status"] == "no_show").mean() * 100) if len(closed) else None,
        "prediction_mae": _num(mae),
        "total_tickets": int(len(df)),
    }

    heat = arrivals_heatmap(df)
    flat = heat.stack()
    flat = flat[flat > 0]
    fmt = lambda idx: f"{DAYS[idx[0]]} {idx[1]:02d}:00"
    busiest = [{"slot": fmt(i), "avg": _num(v)} for i, v in flat.nlargest(3).items()]
    quietest = [{"slot": fmt(i), "avg": _num(v)} for i, v in flat.nsmallest(3).items()]

    by_hour = df.groupby("hour")["wait_min"].mean()
    daily = (
        df.groupby("date")
        .agg(served=("status", lambda s: int((s == "done").sum())), avg_wait=("wait_min", "mean"))
        .tail(14)
    )
    mix = df.groupby("service").size().sort_values(ascending=False)

    return {
        "empty": False,
        "kpis": kpis,
        "heatmap": {
            "days": DAYS,
            "hours": [f"{h:02d}:00" for h in heat.columns],
            "z": [[_num(v) for v in row] for row in heat.values.tolist()],
        },
        "busiest": busiest,
        "quietest": quietest,
        "wait_by_hour": {"hours": [f"{h:02d}:00" for h in by_hour.index], "wait": [_num(v) for v in by_hour.values]},
        "daily": {
            "dates": [d.strftime("%a %d %b") for d in daily.index],
            "served": daily["served"].tolist(),
            "avg_wait": [_num(v) for v in daily["avg_wait"].values],
        },
        "mix": {"labels": mix.index.tolist(), "values": [int(v) for v in mix.values]},
    }


def best_times():
    """Quietest upcoming hours today - shown to customers on the join page."""
    df = load()
    if df.empty:
        return []
    now = datetime.now()
    heat = arrivals_heatmap(df)
    row = heat.loc[now.weekday()]
    row = row[(row.index > now.hour) & (row > 0)]
    return [{"hour": f"{h:02d}:00", "avg": _num(v)} for h, v in row.nsmallest(3).sort_index().items()]
