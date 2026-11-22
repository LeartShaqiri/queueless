"""Per-category intake forms: what each queue needs from the customer, and how it's validated.

Card handling: the full card number is checked (Luhn) and then discarded. Only the brand,
last four digits and expiry are ever stored. CVV is never requested.
Cart totals are always recomputed on the server from catalogue prices.
"""
import json
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation

from catalog import BILLERS, RESTAURANTS, STORES

MALLS = ["Royal Mall", "Albi Mall", "Prishtina Mall"]
MALL_LOGOS = {
    "Royal Mall": "/static/malls/royal.svg",
    "Albi Mall": "/static/malls/albi.svg",
    "Prishtina Mall": "/static/malls/prishtina.png",
}
SERVICE_TYPES = ["Customer support", "Repairs & warranty", "Returns & exchanges", "Contracts & accounts", "Other"]
BILLER_TYPES = {b["value"]: b["type"] for b in BILLERS}
ORDER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

FIRST = {"key": "first_name", "label": "First name", "type": "text", "width": "half", "autocomplete": "given-name", "maxlength": 40}
LAST = {"key": "last_name", "label": "Last name", "type": "text", "width": "half", "autocomplete": "family-name", "maxlength": 40}

RESTAURANT_OPTIONS = [{"value": k, "logo": v["logo"], "sub": v["sub"]} for k, v in RESTAURANTS.items()]
MALL_OPTIONS = [{"value": m, "logo": MALL_LOGOS[m]} for m in MALLS]
STORE_OPTIONS = {m: [{"value": s["name"], "logo": s["logo"], "sub": s["sub"]} for s in stores] for m, stores in STORES.items()}
MENUS = {k: v["menu"] for k, v in RESTAURANTS.items()}
PRODUCTS = {f"{m}|{s['name']}": s["products"] for m, stores in STORES.items() for s in stores}

FORMS = {
    "F": [
        {"key": "full_name", "label": "Your name", "type": "text", "autocomplete": "name", "maxlength": 60,
         "hint": "We'll give you an order code when you check out."},
        {"key": "restaurant", "label": "Restaurant", "type": "choice", "options": RESTAURANT_OPTIONS},
        {"key": "order", "label": "Your order", "type": "cart", "depends": ["restaurant"], "catalog": MENUS},
    ],
    "S": [
        FIRST, LAST,
        {"key": "service", "label": "Service you need", "type": "select", "options": SERVICE_TYPES},
    ],
    "M": [
        FIRST, LAST,
        {"key": "mall", "label": "Mall", "type": "choice", "options": MALL_OPTIONS},
        {"key": "store", "label": "Store", "type": "choice", "depends": ["mall"], "options_by": STORE_OPTIONS},
        {"key": "basket", "label": "Your basket", "type": "cart", "depends": ["mall", "store"], "catalog": PRODUCTS},
        {"key": "card_number", "label": "Card number", "type": "cardnumber", "group": "card"},
        {"key": "card_expiry", "label": "Expiry", "type": "expiry", "width": "half", "group": "card"},
    ],
    "P": [
        FIRST, LAST,
        {"key": "biller", "label": "What are you paying?", "type": "choice", "options": BILLERS},
        {"key": "reference", "label": "Customer or bill no.", "type": "text", "width": "half", "maxlength": 30,
         "pattern": r"[A-Za-z0-9 /-]{4,30}", "pattern_msg": "Use the number printed on your bill"},
        {"key": "amount", "label": "Amount", "type": "money", "width": "half"},
    ],
}


class FormError(Exception):
    def __init__(self, errors: dict):
        super().__init__("Please check the highlighted fields")
        self.errors = errors


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def card_brand(digits: str) -> str:
    if digits.startswith("4"):
        return "Visa"
    if digits[:2] in {"51", "52", "53", "54", "55"} or 2221 <= int(digits[:4]) <= 2720:
        return "Mastercard"
    if digits[:2] in {"34", "37"}:
        return "Amex"
    return "Card"


def _dep_key(f, out):
    return "|".join(out.get(d, "") for d in f.get("depends", []))


def choice_options(f, out):
    return f["options"] if "options" in f else f["options_by"].get(_dep_key(f, out), [])


def _cart(f, v, out):
    catalog = f["catalog"].get(_dep_key(f, out))
    if catalog is None:
        return None, None
    try:
        raw = json.loads(v)
        assert isinstance(raw, dict)
    except (ValueError, AssertionError):
        return None, "Add at least one item"
    by_id = {i["id"]: i for i in catalog}
    lines, total = [], Decimal("0")
    for item_id, qty in raw.items():
        if item_id not in by_id or not isinstance(qty, int) or not 0 <= qty <= 20:
            return None, "Something in your order isn't available"
        if qty:
            item = by_id[item_id]
            lines.append(f"{qty}× {item['name']}")
            total += Decimal(item["price"]) * qty
    if not lines:
        return None, "Add at least one item"
    return {"items": "\n".join(lines), "total": f"{total:.2f}"}, None


def validate(code: str, data: dict):
    """Returns (details_to_store, display_name). Raises FormError with per-field messages."""
    if code not in FORMS:
        raise FormError({"_": "Unknown category"})
    data = data or {}
    errors, out = {}, {}
    for f in FORMS[code]:
        key, kind = f["key"], f["type"]
        v = str(data.get(key) or "").strip()
        if any(d in errors for d in f.get("depends", [])):
            continue
        if not v:
            errors[key] = "Add at least one item" if kind == "cart" else "Required"
            continue
        if kind in ("text", "textarea"):
            if len(v) > f.get("maxlength", 200):
                errors[key] = "Too long"
            elif f.get("pattern") and not re.fullmatch(f["pattern"], v):
                errors[key] = f.get("pattern_msg", "Invalid format")
            else:
                out[key] = v.upper() if f.get("upper") else v
        elif kind == "select":
            if v not in f["options"]:
                errors[key] = "Choose an option"
            else:
                out[key] = v
        elif kind == "choice":
            if v not in {o["value"] for o in choice_options(f, out)}:
                errors[key] = "Choose one"
            else:
                out[key] = v
        elif kind == "cart":
            result, err = _cart(f, v, out)
            if err or result is None:
                errors[key] = err or "Choose where you're ordering from first"
            else:
                out.update(result)
        elif kind == "money":
            try:
                amount = Decimal(v.replace("€", "").replace(",", ".").strip())
            except InvalidOperation:
                errors[key] = "Enter an amount like 24.90"
                continue
            if not (Decimal("0.01") <= amount <= Decimal("100000")):
                errors[key] = "Enter an amount between €0.01 and €100,000"
            else:
                out[key] = f"{amount:.2f}"
        elif kind == "cardnumber":
            digits = re.sub(r"[\s-]", "", v)
            if not digits.isdigit() or not 12 <= len(digits) <= 19 or not luhn_ok(digits):
                errors[key] = "That card number isn't valid"
            else:
                out["card_brand"] = card_brand(digits)
                out["card_last4"] = digits[-4:]
        elif kind == "expiry":
            m = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{2})", v)
            if not m or not 1 <= int(m.group(1)) <= 12:
                errors[key] = "Use MM/YY"
                continue
            mm, yy = int(m.group(1)), int(m.group(2))
            today = date.today()
            if (2000 + yy, mm) < (today.year, today.month):
                errors[key] = "This card has expired"
            else:
                out[key] = f"{mm:02d}/{yy:02d}"
    if errors:
        raise FormError(errors)

    if code == "F":
        out["order_code"] = "".join(secrets.choice(ORDER_ALPHABET) for _ in range(4))
        return out, out["full_name"]
    if code == "P":
        out["payment"] = BILLER_TYPES[out["biller"]]
    return out, f"{out['first_name']} {out['last_name']}"


def _option_for(f, value, details):
    if f["type"] != "choice":
        return None
    return next((o for o in choice_options(f, details) if o["value"] == value), None)


def display_rows(code: str, details: dict):
    rows = []
    if details.get("order_code"):
        rows.append({"label": "Order code", "value": details["order_code"], "strong": True})
    for f in FORMS.get(code, []):
        key, kind = f["key"], f["type"]
        if key in ("first_name", "last_name", "full_name") or kind == "expiry":
            continue
        if kind == "cardnumber":
            if details.get("card_last4"):
                rows.append({"label": "Card", "value": f"{details.get('card_brand', 'Card')} •••• {details['card_last4']}"})
        elif kind == "cart":
            if details.get("items"):
                rows.append({"label": "Items", "value": details["items"], "lines": True})
                rows.append({"label": "Total", "value": f"€{details['total']}", "strong": True})
        elif key in details:
            value = details[key]
            if kind == "money":
                value = f"€{value}"
            row = {"label": f["label"] if key != "biller" else "Paying", "value": value}
            opt = _option_for(f, value, details)
            if opt:
                row["logo"] = opt["logo"]
                if opt.get("bg"):
                    row["logo_bg"] = opt["bg"]
            rows.append(row)
            if key == "biller" and details.get("payment"):
                rows.append({"label": "Bill type", "value": details["payment"]})
    return rows
