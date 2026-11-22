# QueueLess

**Take a number. Take a walk.**

QueueLess is a smart queue and scan-to-order system for places where people wait: food courts, shopping malls, bill-payment desks and service counters. Instead of standing in line, a customer scans a QR code, orders or takes a number on their phone, walks away, and gets buzzed when it's their turn or their order is ready.

It has three sides that work together live:

| Who | What they get |
|---|---|
| **Customers** | Take a number or order ahead from their phone. No app, no account. Live place in line, honest wait estimate, and a phone ring when it's time. |
| **Businesses** | Their own order screen (signed in with a PIN), their own counters, and their own door QR code. Accept orders, set ready times, ring customers, take cash at pickup. |
| **Admin** | Full control and moderation of everything: every ticket and order, every business, PINs, counters, queue rules, analytics and data. |

Built for a hackathon (Advanced Python track): FastAPI, WebSockets, SQLite and pandas, with plain HTML/JS front ends.

---

## Contents

- [The idea](#the-idea)
- [Quick start](#quick-start)
- [Logins at a glance](#logins-at-a-glance)
- [The customer experience](#the-customer-experience)
- [The business side](#the-business-side)
- [The admin side — control and moderation](#the-admin-side--control-and-moderation)
- [Queue desk, display board and dashboard](#queue-desk-display-board-and-dashboard)
- [Every page and its address](#every-page-and-its-address)
- [Business screens and PINs](#business-screens-and-pins)
- [How the smart parts work](#how-the-smart-parts-work)
- [Using it with phones](#using-it-with-phones)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Notes on payments, data and security](#notes-on-payments-data-and-security)

---

## The idea

Waiting in line wastes time and crowds waiting areas. QueueLess turns every line into a digital one:

- **Every place has its own QR code.** Each restaurant, store, mall, bill company and service has a QR. Scanning it opens a page for that place only.
- **Two ways to be served:**
  - **Order ahead** (Food and Shopping): pick items, pay by card now or choose cash at pickup, and collect when your phone rings.
  - **Take a number** (Payments and Services): get a queue ticket, leave, and come back when your phone buzzes.
- **Businesses run their own operation.** Each business signs in with its PIN, sees orders arrive live, decides when they'll be ready, chooses which of its counters to hand them over at, and prints its own door sticker.
- **The admin oversees and moderates everything.** One panel to see, change, fix or remove anything in the system.

The demo is set in Prishtina, Kosovo, with real places: **Heb's, KFC and Pano Pizza**; **Royal Mall, Albi Mall and Prishtina Mall** and their stores; and **KEDS, KRU Prishtina and IPKO** bills.

---

## Quick start

Requires **Python 3.11+** (developed on 3.12). In Windows PowerShell:

```powershell
cd queueless
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy admin.env.example admin.env
.\.venv\Scripts\python.exe run.py
```

On macOS or Linux, use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`, and `cp` instead of `copy`.

Open **http://localhost:8000**. The terminal prints every link, including the address phones on the same Wi-Fi should use.

- **Different port:** `$env:PORT = "8010"; .\.venv\Scripts\python.exe run.py`
- **VS Code:** open the folder and press **Ctrl+Shift+B** (the "Run QueueLess" task).
- **Auto-reload:** the server reloads itself whenever you save a Python file, and pages are served with `no-cache`, so refreshing always shows the latest version. If you change `admin.env`, restart the server.

**Demo data:** sign in at `/admin`, open the **Data** tab, and click **Simulate history** (two weeks of realistic traffic for the charts) and **Add a rush** (customers waiting right now).

---

## Logins at a glance

| What | Where | Login |
|---|---|---|
| **Admin panel** | `http://localhost:8000/admin` | Username **`admin`**, password **`admin`** |
| **Any business screen** | `http://localhost:8000/biz/<business>` (or `/business` → **Sign in**) | PIN **`4321`** |
| Customer pages, queue desk, display board, dashboard | see [Every page](#every-page-and-its-address) | No login |

These logins live in `admin.env` (`QL_ADMIN_USER`, `QL_ADMIN_PASS`, `QL_DEMO_PIN`). They're demo values: change them before real use (see [security notes](#notes-on-payments-data-and-security)).

---

## The customer experience

A customer never needs an app or an account, only their phone's camera and browser.

### 1. Take a number

Open **Take a number** (`/join`) on the waiting-area screen or a phone, or scan the QR on the home page. It's a directory with four sections, and every place shows its **logo, name and its own QR code**:

| Section | Places | Tapping or scanning opens |
|---|---|---|
| **Food** | Heb's, KFC, Pano Pizza | That restaurant's menu (`/b/kfc`) |
| **Shopping** | Royal Mall, Albi Mall, Prishtina Mall | That mall's page (`/m/albi-mall`), listing its stores, each with its own QR |
| **Payments** | KEDS (electricity), KRU Prishtina (water), IPKO (phone & internet) | A short bill form (`/pay/keds`) |
| **Services** | Customer support, Repairs & warranty, Returns & exchanges, Contracts & accounts, Other | A short service form (`/service/repairs-warranty`) |

### 2a. Order ahead (Food and Shopping)

1. **Select your order.** Add items with **+ Add** and the −/+ buttons. The bar at the bottom shows the item count and live total.
2. **Give your name.**
3. **Choose how to pay:**
   - **Pay now by card:** card number, expiry and CVV, checked on the spot.
   - **Pay cash at pickup:** pay at the counter when you collect.
4. **Check out.** You get a **pickup code** (e.g. `WAFF`) and a tracking page (`/o/...`).
5. **Wait for it to be processed.** The tracking page moves live through **Sent → Accepted ("ready in about 10 min") → Ready → Collected**, and shows how many orders are ahead of yours. You can walk away.
6. **Your phone rings when it's ready:** a popup, shake, vibration, chime, spoken message and notification saying **"Collect at Pickup 2"**, with your code and either "Already paid by card" or "Please pay €9.37 in cash". The business can ring you again.
7. **Collect.** Show your code. Cash orders are paid now, and the ticket is stamped **Collected**.

If the business declines the order, you see why (e.g. "Sold out"). You can also cancel an order while it's still "Sent".

### 2b. Take a number (Payments and Services)

1. **Fill in the short form:** first and last name, plus bill number and amount for payments.
2. **Take a number.** You get a ticket like **`P-006`** (`/t/...`) showing your **place in line**, an **estimated wait range** with a confidence level, and the counters now serving.
3. **Wait for your turn.** Tap **Turn on alerts**, then walk away. Your phone buzzes when you're **3 people away**.
4. **You're called.** The ticket turns vermilion: **"Please go to Counter 2"**, with a countdown holding your place. Tap **I'm on my way** so staff know you're coming.
5. **Recalled?** If staff call you again, your phone rings with a **"we're calling you again"** popup and a fresh hold timer.
6. **Served.** The ticket is stamped **Served** and shows your actual wait next to the predicted one.

You can leave the line at any time. If you miss a call, your ticket moves to the back once, then expires.

---

## The business side

Every restaurant and store has its own **business screen** at `/biz/<business>`. Staff open it from **For businesses** (`/business`) → **Sign in**, using the business's PIN (demo: **4321**). A PIN only opens that one business.

### Orders tab: process orders

Orders arrive live with a chime and a flashing tab title. There are three columns:

| Column | What staff do |
|---|---|
| **New** | Pick a ready time (5–45 min), then **Accept**. Or **Decline**, with a reason the customer sees. |
| **Preparing** | A countdown to the promised time, which turns red when late. Choose the counter, then **Mark ready · ring customer**. |
| **Ready for pickup** | **Ring again** if the customer hasn't come. Then **Collected**, or **Cash €X received** for cash orders. |

Below the columns: today's orders with how each was paid, and totals including **cash received**. An **open/closed** switch at the top stops new orders; the customer page then says it isn't taking orders.

### Counters tab: the business's own counters

Every business has **its own pickup points**, separate from the queue desk and from other businesses. For example, KFC has *Pickup 1–3*, Heb's *Pickup 1–2*, Pano Pizza *Counter*, Zara and H&M *Till 1–2*, and Neptun *Collection desk* and *Till 1*. Staff can add, rename, open/close and remove counters. Closed counters can't be chosen when marking an order ready.

### QR code tab: the business's door sticker

- **Generate QR code** creates a code that **only ever opens this business**, as a short link like `/s/m6wF2yt5`.
- The tab shows the code, its link, how many times it's been scanned, and when it was generated.
- **Print sticker** (a door or counter sticker with logo, QR and "Scan to order here") and **Download QR image**.
- **Generate a new code** replaces a lost or old sticker. Every older sticker stops working at once, and scanning one shows "This sticker has been replaced".

---

## The admin side: control and moderation

The admin panel is at **`/admin`** (login **`admin` / `admin`**). It isn't linked from public pages, sessions last 12 hours, and 5 wrong attempts lock that device out for 5 minutes. The admin can also open any business screen without its PIN.

| Tab | Control and moderation |
|---|---|
| **Overview** | Live numbers (waiting, at counters, served, no-shows, cancelled, money taken today). Every queue counter with **Call next / Start / Recall / No-show / Complete / Open-Close**. Per-category totals, and the waiting line. |
| **Tickets** | Every queue ticket, filtered by today, active or 28 days, by status and category, with search by number, name or reference. Click a row to see everything the customer entered. Per ticket: **call to a counter, move to front, prioritise, complete, requeue, cancel, delete**. CSV export. |
| **Businesses & orders** | Every business: open/closed, **QR code status and scans**, its counters, orders, sales and **cash received** today. **Set or change its staff PIN**, **Generate** a QR, **open or close** it, and open its business screen or customer page. **Print QR stickers** prints all businesses' stickers at once. |
| **Counters** | The queue desk's counters for Payments and Services: add, rename, open/close, remove. |
| **Services & rules** | Category names, descriptions and default service minutes, plus queue rules: **no-show timeout**, **priority head start**, and **missed calls before expiry**. |
| **Data** | **Simulate history**, **Add a rush**, **export** all tickets, and **Reset all data** (you must type `RESET`). |

All moderation actions show up instantly on every customer phone, business screen and display board.

---

## Queue desk, display board and dashboard

| Screen | Address | What it does |
|---|---|---|
| **Queue desk** (staff console) | `/staff` | For the Payments and Services counters. **Call next (N)**, **Start (S)**, **Complete (C)**, **Re-announce/Recall (R)**, **No-show (X)**, and **1–9** to switch counter. Shows the customer's details (bill, amount, service), the waiting list with expected call times, and the live service-time model. |
| **Display board** (TV) | `/tv` | A wall screen for the waiting area: split-flap ticket numbers per counter, the next six in line, a QR to join, a chime and a spoken "Ticket P 6, please go to Counter 2". Click **Start the board** once to allow sound. |
| **Operations dashboard** | `/dashboard` | Queue analytics with pandas and Plotly: a heatmap of arrivals by weekday and hour, busiest and quietest times, wait by hour, daily volume and wait, service mix, and **forecast error**. |

---

## Every page and its address

Replace `localhost` with the laptop's network address (printed on startup) when opening pages on a phone.

### Customers

| Page | Address |
|---|---|
| Home | `/` |
| Take a number (directory) | `/join` |
| Restaurant or store | `/b/<business>`, e.g. `/b/kfc` |
| Mall | `/m/royal-mall`, `/m/albi-mall`, `/m/prishtina-mall` |
| Pay a bill | `/pay/keds`, `/pay/kru-prishtina`, `/pay/ipko` |
| Get a service | `/service/customer-support`, `/service/repairs-warranty`, `/service/returns-exchanges`, `/service/contracts-accounts`, `/service/other` |
| Order tracking | `/o/<token>` (opens after ordering) |
| Queue ticket | `/t/<token>` (opens after taking a number) |
| Scanned door sticker | `/s/<code>` (redirects to the business) |

### Staff, businesses and admin

| Page | Address | Login |
|---|---|---|
| For businesses | `/business` | — |
| Business screen | `/biz/<business>` | PIN `4321` |
| Business sticker | `/biz/<business>/sticker` | PIN `4321` |
| Queue desk | `/staff` | — |
| Display board | `/tv` | — |
| Operations dashboard | `/dashboard` | — |
| Admin | `/admin` | `admin` / `admin` |
| All stickers | `/admin/stickers` | `admin` / `admin` |
| API docs | `/docs` | — |

---

## Business screens and PINs

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

`QL_DEMO_PIN=4321` in `admin.env` gives every business **without a PIN** this PIN when the server starts. To give a business its own PIN: `/admin` → **Businesses & orders** → type a 4–8 digit PIN → **Change**. PINs are stored hashed in the local database.

---

## How the smart parts work

- **Wait estimates that learn.** Each service's duration is learned from its last 3 hours of real service times, weighted towards the most recent. When there isn't enough recent data, it falls back to the same hour on previous days, then to a default. The queue is simulated across open counters to give an honest range (e.g. *8–12 min*) and a confidence level. The dashboard shows how far off past predictions were.
- **Fair priority.** Priority customers (age, pregnancy, disability) get a 10-minute head start, not a permanent jump, so nobody waits forever.
- **No-show handling.** A called customer who doesn't respond in 60 seconds moves to the back once, then expires. A recall gives a fresh hold window.
- **Live everywhere.** One WebSocket pushes every change to all phones and screens instantly.
- **Server-side truth.** Order totals are recalculated on the server from catalogue prices, and card details are validated, then discarded.
- **Per-business isolation.** Each business has its own orders, counters, PIN and QR code. A business's PIN or QR can't reach another business.

---

## Using it with phones

- Phones must be on the **same Wi-Fi** as the laptop. Use the network address printed on startup, e.g. `http://192.168.1.42:8000/join`.
- Windows may ask to allow Python through the firewall the first time. Choose **Allow**.
- **If the Wi-Fi blocks devices from reaching each other**, run `ngrok http 8000` and start the server with the public address, so every QR code points there:
  ```powershell
  $env:PUBLIC_URL = "https://your-ngrok-address"; .\.venv\Scripts\python.exe run.py
  ```
  HTTPS also makes phone notifications work.
- QR codes encode the laptop's **current** address. If you change Wi-Fi or port, re-print stickers, or use `PUBLIC_URL`.
- Customers should tap **Turn on alerts**, because phones only allow sound and vibration after a tap. iPhones never vibrate from a website; the popup, sound and notification still work. Keep the tab open.

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
├── admin.env.example # copy to admin.env (admin.env is not committed)
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

Data lives in `queueless.db`, a SQLite file created on first run and not committed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| I don't see my latest changes | Make sure only **one** server is running (stop old ones with **Ctrl+C**). The server reloads on save; refresh the page. Restart after editing `admin.env`. |
| Phone can't open the link or QR | Same Wi-Fi? Firewall allowed? Address changed? Use the address printed on startup, or `PUBLIC_URL` with ngrok. |
| "Admin sign-in is disabled" | Create `admin.env` from `admin.env.example`. |
| Business PIN doesn't work | Set it in `/admin` → **Businesses & orders**, or set `QL_DEMO_PIN` in `admin.env` (only applies to businesses without a PIN) and restart. |
| Dashboard charts are empty | The charts load Plotly from the internet. Also add data: `/admin` → **Data** → **Simulate history**. |
| Port already in use | `$env:PORT = "8010"; .\.venv\Scripts\python.exe run.py` |

---

## Notes on payments, data and security

- **No real money moves.** Card payments are validated (checksum, expiry, CVV length) but not charged. Only the brand, last four digits and expiry are stored, never the full number or CVV.
- **Demo logins are public.** `admin` / `admin` and the shared PIN `4321` are written in this README. Before any real use, change `QL_ADMIN_USER` and `QL_ADMIN_PASS` in `admin.env`, remove `QL_DEMO_PIN`, and give every business its own PIN in `/admin`.
- **Data sources:** restaurant menus and prices come from each brand's Prishtina listing on Wolt (Nov 2026). Store product lists are illustrative samples.
- **Trademarks:** logos of malls, restaurants, stores and bill companies belong to their owners and are included for this prototype only.
