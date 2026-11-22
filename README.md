# QueueLess

**Take a number. Take a walk.**

QueueLess is a walk-in queue and scan-to-order system built with FastAPI. Customers scan a QR code, order or take a ticket on their phone, walk away, and get buzzed when it's their turn or their order is ready. Businesses get a live order screen, their own counters and their own door QR code. Managers get live analytics and a full admin panel.

Built for a hackathon (Advanced Python track): FastAPI + WebSockets + SQLite + pandas, with plain HTML/JS front ends.

---

## Contents

- [Quick start](#quick-start)
- [Where to go — every page](#where-to-go--every-page)
- [Business screens and PINs](#business-screens-and-pins)
- [Admin](#admin)
- [How it works](#how-it-works)
- [Using it with phones](#using-it-with-phones)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Notes on payments, data and security](#notes-on-payments-data-and-security)

---

## Quick start

Requires **Python 3.11+** (developed on 3.12). On Windows PowerShell:

```powershell
cd queueless
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy admin.env.example admin.env      # then edit admin.env and choose your admin login
.\.venv\Scripts\python.exe run.py
```

On macOS / Linux use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe` and `cp` instead of `copy`.

Open **http://localhost:8000**. The terminal prints every link, including the address phones on the same Wi-Fi should use.

- **Different port:** `$env:PORT = "8010"; .\.venv\Scripts\python.exe run.py`
- **VS Code:** open the folder and press **Ctrl+Shift+B** (task "Run QueueLess").
- The server **reloads itself when you save a file**, and pages are served with `no-cache`, so a browser refresh always shows the latest version.

**First time with demo data:** sign in at `/admin` → **Data** tab → **Simulate history** (two weeks of realistic traffic for the dashboards) and **Add a rush** (customers waiting right now).

---

## Where to go — every page

Replace `localhost` with your laptop's network address (printed on startup) when opening pages on a phone.

### For customers

| Page | Address | What it's for |
|---|---|---|
| Home | `http://localhost:8000/` | Landing page with the main QR code and links |
| **Take a number** | `http://localhost:8000/join` | Directory of every place, each with its logo, name and own QR code: **Food**, **Shopping**, **Payments**, **Services** |
| Restaurant / store | `http://localhost:8000/b/<business>` | That business only: menu or products, cart, pay by **card** or **cash at pickup**. Example: `/b/kfc` |
| Mall | `http://localhost:8000/m/<mall>` | A mall's stores, each with its own QR. `/m/royal-mall`, `/m/albi-mall`, `/m/prishtina-mall` |
| Pay a bill | `http://localhost:8000/pay/<biller>` | Name, bill number and amount, then a queue ticket. `/pay/keds`, `/pay/kru-prishtina`, `/pay/ipko` |
| Get a service | `http://localhost:8000/service/<type>` | Name only, then a queue ticket. `/service/customer-support`, `/service/repairs-warranty`, `/service/returns-exchanges`, `/service/contracts-accounts`, `/service/other` |
| Order tracking | `/o/<token>` | Opens automatically after ordering: pickup code, live status, rings when ready |
| Queue ticket | `/t/<token>` | Opens automatically after taking a number: place in line, estimated wait, buzzes when close and when called |
| Scanned door sticker | `/s/<code>` | Short link inside each business's generated QR; redirects to that business |

### For staff and managers

| Page | Address | Sign-in | What it's for |
|---|---|---|---|
| For businesses | `http://localhost:8000/business` | — | List of every business with a **Sign in** button |
| **Business screen** | `http://localhost:8000/biz/<business>` | Staff PIN | Orders board, the business's own counters, generate/print its door QR |
| Business sticker | `http://localhost:8000/biz/<business>/sticker` | Staff PIN | Printable door sticker with that business's QR |
| Queue desk (staff console) | `http://localhost:8000/staff` | — | Payment and service counters: call next, start, complete, re-announce, no-show (keys **N S C R X**, **1–9** switch counter) |
| Display board (TV) | `http://localhost:8000/tv` | — | Wall screen with split-flap numbers, chime and spoken calls (click **Start the board** once to allow sound) |
| Operations dashboard | `http://localhost:8000/dashboard` | — | Peak-hour heatmap, waits, daily volume, forecast accuracy |
| **Admin** | `http://localhost:8000/admin` | Admin login | Controls everything — see [Admin](#admin) |
| All stickers | `http://localhost:8000/admin/stickers` | Admin login | Print every business's sticker at once |
| API docs | `http://localhost:8000/docs` | — | Interactive FastAPI documentation |

---

## Business screens and PINs

Every business signs in at `/biz/<business>` with its staff PIN (or from `/business` → **Sign in**).

**Demo PIN for every business: `4321`**

| Business | Where | Business screen | Customer page | PIN |
|---|---|---|---|---|
| Heb's | Restaurant | `/biz/hebs` | `/b/hebs` | `4321` |
| KFC | Restaurant | `/biz/kfc` | `/b/kfc` | `4321` |
| Pano Pizza | Restaurant | `/biz/pano-pizza` | `/b/pano-pizza` | `4321` |
| Neptun | Royal Mall | `/biz/neptun-royal-mall` | `/b/neptun-royal-mall` | `4321` |
| Zara | Albi Mall | `/biz/zara-albi-mall` | `/b/zara-albi-mall` | `4321` |
| Nike | Albi Mall | `/biz/nike-albi-mall` | `/b/nike-albi-mall` | `4321` |
| Mango | Albi Mall | `/biz/mango-albi-mall` | `/b/mango-albi-mall` | `4321` |
| Levi's | Albi Mall | `/biz/levis-albi-mall` | `/b/levis-albi-mall` | `4321` |
| Bershka | Albi Mall | `/biz/bershka-albi-mall` | `/b/bershka-albi-mall` | `4321` |
| Tommy Hilfiger | Albi Mall | `/biz/tommy-hilfiger-albi-mall` | `/b/tommy-hilfiger-albi-mall` | `4321` |
| H&M | Prishtina Mall | `/biz/h-m-prishtina-mall` | `/b/h-m-prishtina-mall` | `4321` |
| Intersport | Prishtina Mall | `/biz/intersport-prishtina-mall` | `/b/intersport-prishtina-mall` | `4321` |
| Hamleys | Prishtina Mall | `/biz/hamleys-prishtina-mall` | `/b/hamleys-prishtina-mall` | `4321` |
| Diesel | Prishtina Mall | `/biz/diesel-prishtina-mall` | `/b/diesel-prishtina-mall` | `4321` |

How the demo PIN is set: `QL_DEMO_PIN=4321` in `admin.env` gives every business **that has no PIN yet** this PIN when the server starts. To give a business its own PIN, sign in at `/admin` → **Businesses & orders** → type a new 4–8 digit PIN → **Change**. PINs are stored hashed in the local database. Signed-in admins can open every business screen without a PIN.

### What a business does on its screen

- **Orders tab** — three live columns:
  - **New** — pick a ready time (5–45 min) → **Accept**, or **Decline** with a reason the customer sees. New orders chime and flash the tab title.
  - **Preparing** — countdown to the promised time (turns red when late), choose the counter to collect at → **Mark ready · ring customer**.
  - **Ready for pickup** — **Ring again**, then **Collected** (for cash orders the button reads **Cash €X received**).
  - Today's list with totals and cash received; an open/closed switch at the top.
- **Counters tab** — the business's own pickup points (every business has its own set, e.g. KFC *Pickup 1–3*, Pano Pizza *Counter*, Zara *Till 1–2*). Add, rename, open/close, remove.
- **QR code tab** — **Generate QR code** creates a code that only ever opens this business. Shows scans and date, **Print sticker**, **Download QR image**. **Generate a new code** retires every older sticker immediately.

---

## Admin

`http://localhost:8000/admin` — the login is whatever you put in `admin.env` (`QL_ADMIN_USER` / `QL_ADMIN_PASS`; see `admin.env.example`). It isn't linked from public pages. Sessions last 12 hours; 5 wrong attempts lock that device out for 5 minutes.

| Tab | What you can do |
|---|---|
| Overview | Live numbers, value collected today, every queue counter with call / start / **recall** / no-show / complete / open-close, waiting line |
| Tickets | Every queue ticket with filters and search; call to a counter, move to front, prioritise, complete, requeue, cancel, delete; full customer details; CSV export |
| Businesses & orders | Every business: open/closed, QR status and scans, counters, orders and money today, cash received, set/change staff PIN, links to its screens, **Print QR stickers** |
| Counters | The walk-in queue's counters: add, rename, open/close, remove |
| Services & rules | Category names, descriptions, default minutes; no-show timeout, priority head start, missed calls before expiry |
| Data | Simulate history, add a rush, export all tickets, reset everything (type `RESET`) |

---

## How it works

### Two ways in

1. **Order ahead** (Food and Shopping) — scan a business's QR or tap it in **Take a number**, add items, give your name, pay **by card now** or **cash at pickup**. You get a 4-character **pickup code** and a live tracking page: *Sent → Accepted (ready in ~N min) → Ready → Collected*. When the business marks it ready, your phone **rings**: popup, shake, vibration, chime, spoken message and notification, telling you which counter to go to and whether to pay cash.
2. **Take a number** (Payments and Services) — fill a two-field form, get a ticket like `P-006`, and leave. Your phone buzzes at **3 ahead** and again when you're **called**, with the counter. If staff **recall** you, your phone rings again with a "we're calling you again" popup and a fresh hold timer.

### Smart parts

- **Wait estimates that learn.** Each service's duration comes from its last 3 hours of real service times (weighted towards the most recent), falling back to the same hour on previous days, then to a default. The queue is simulated across open counters to give a range (e.g. *8–12 min*) with a confidence level. The dashboard shows how far off past forecasts were (MAE).
- **Fair priority.** Priority customers get a 10-minute head start — not a permanent jump — so nobody waits forever.
- **No-show handling.** A called customer who doesn't respond in 60 s moves to the back once, then expires.
- **Live everywhere.** One WebSocket pushes changes to every screen instantly.
- **Server-side truth.** Cart totals are recalculated on the server from catalogue prices; card numbers are checked (Luhn, expiry, CVV) and then discarded.

---

## Using it with phones

- Phones must be on the **same Wi-Fi** as the laptop. Use the network address printed on startup (e.g. `http://192.168.1.42:8000/join`).
- Windows may ask to allow Python through the firewall the first time — choose **Allow**.
- **If the Wi-Fi blocks devices from reaching each other**, run `ngrok http 8000` and start the server with the public address so all QR codes point at it:
  ```powershell
  $env:PUBLIC_URL = "https://your-ngrok-address"; .\.venv\Scripts\python.exe run.py
  ```
  HTTPS also lets phone notifications work.
- QR codes encode the laptop's **current** address. If you change Wi-Fi or port, re-print stickers (or use `PUBLIC_URL`).
- Tap **Turn on alerts** on a ticket or order page: phones only allow sound and vibration after a tap. iPhones never vibrate from a website (popup, sound and notification still work). Keep the tab open.

---

## Project structure

```
queueless/
├── run.py            # starts the server (auto-reload), prints all links
├── main.py           # FastAPI app: pages, REST API, WebSocket hub, QR codes
├── core.py           # queue: tickets, counters, learning wait-time model, settings
├── orders.py         # scan-to-order: businesses, orders, counters, PINs, generated QR codes
├── forms.py          # per-category validation (card checks, carts, billers)
├── catalog.py        # restaurant menus (from Wolt, Nov 2026), store products (samples), billers
├── analytics.py      # pandas: KPIs, heatmap, trends, forecast error
├── simulate.py       # realistic demo traffic
├── auth.py           # admin login, business sessions, brute-force throttle
├── admin.env.example # copy to admin.env (not committed)
├── requirements.txt
└── static/
    ├── index.html        # home
    ├── join.html         # Take a number directory
    ├── order.html        # a business's order page  (/b/...)
    ├── myorder.html      # order tracking           (/o/...)
    ├── mall.html         # a mall's stores          (/m/...)
    ├── quick.html        # bill / service ticket    (/pay/..., /service/...)
    ├── ticket.html       # queue ticket             (/t/...)
    ├── business.html     # For businesses list
    ├── biz.html          # business screen          (/biz/...)
    ├── stickers.html     # printable QR stickers
    ├── staff.html, tv.html, dashboard.html, admin.html
    ├── style.css, common.js
    ├── brands/           # restaurant, store and biller logos
    └── malls/            # mall logos
```

Data lives in `queueless.db` (SQLite, created on first run, not committed).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| I don't see my latest changes | Make sure only **one** server is running (stop old ones with **Ctrl+C**). The server auto-reloads on save; refresh the page. |
| Phone can't open the link / QR | Same Wi-Fi? Firewall allowed? Address changed? Use the address printed on startup, or `PUBLIC_URL` with ngrok. |
| "Admin sign-in is disabled" | Create `admin.env` from `admin.env.example`. |
| Business PIN doesn't work | Set it in `/admin` → **Businesses & orders**, or set `QL_DEMO_PIN` in `admin.env` (applies only to businesses without a PIN) and restart. |
| Dashboard charts are empty | Charts load Plotly from the internet; also add data via `/admin` → **Data** → **Simulate history**. |
| Port already in use | `$env:PORT = "8010"; .\.venv\Scripts\python.exe run.py` |

---

## Notes on payments, data and security

- **No real money moves.** Card payments are validated (checksum, expiry, CVV length) but not charged; only the brand, last four digits and expiry are stored — never the full number or CVV.
- **Demo credentials:** the shared PIN `4321` and any admin password in `admin.env` are for demos. Before real use, give every business its own PIN in `/admin` and remove `QL_DEMO_PIN`.
- Restaurant menus and prices come from each brand's Prishtina listing on Wolt (Nov 2026). Store product lists are illustrative samples.
- Logos of malls, restaurants, stores and billers are trademarks of their owners, included for this prototype only.
