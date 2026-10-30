# ⚡ ProcureAI — AI Procurement Negotiator for Small Business

Visit at https://gidominah.pythonanywhere.com/

A web app that reads your invoices, benchmarks every line item against market
prices, flags overcharges, and drafts + simulates a negotiation with the vendor
until you win money back.

- **Backend:** Python (Flask) — no database needed, everything is stored as JSON files
- **Frontend:** HTML / CSS / JS (dark glassmorphism UI, Chart.js)
- **AI:** Works out of the box in **MOCK MODE** (smart templates, zero cost, no key).
  Optionally plug in any OpenAI-compatible API key in Settings for real LLM drafts.

---

## 🚀 Setup (super simple)

### Step 0 — get Python
Install Python 3.10 or newer from https://www.python.org/downloads
(On Windows, tick **"Add Python to PATH"** during install.)

### Step 1 — open a terminal in this folder
- Windows: Shift + Right-click the folder → "Open PowerShell window here"
- Mac/Linux: `cd` into the folder

### Step 2 — create a virtual environment (one time)
```
python -m venv venv
```
Activate it:
- Windows: `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

### Step 3 — install dependencies
```
pip install -r requirements.txt
```
(Optional, only if you want PDF upload): `pip install pypdf`

### Step 4 — run the app
```
python app.py
```

### Step 5 — open in your browser
Go to: **http://127.0.0.1:5000**

---

## 🧭 Try it in 3 minutes

1. **Vendors** tab → add a vendor (e.g. *Acme Office Supplies*, category *Office Supplies*)
2. **Invoices** tab → upload `sample-data/sample-invoice.txt` → click **🔍 Analyze**
   → watch it flag the overpriced lines vs market benchmarks
3. **Negotiations** tab → pick the invoice, choose a tone (Friendly / Firm / Hardball)
   → **Generate email** → **Send to vendor** → counter-offer until they accept 🎉

## 🧠 Optional: real AI mode
Settings tab → paste an OpenAI (or any OpenAI-compatible) API key,
turn **Mock OFF**, Save. Emails and vendor replies are then written by a real LLM.

## 📁 Project structure
```
procure-negotiator/
├── app.py               ← Flask server (all API routes)
├── ai_engine.py         ← benchmarks, invoice parsing, email generator, vendor simulator
├── requirements.txt
├── static/
│   ├── index.html       ← the web app
│   ├── css/style.css    ← all the visual polish
│   └── js/app.js        ← frontend logic
├── sample-data/sample-invoice.txt
└── data/                ← created automatically (your vendors, invoices, deals)
```

## 💡 Business tips
- Sell it as "$ saved or you don't pay" — the dashboard proves ROI instantly
- The benchmark DB in `ai_engine.py` is yours to expand per niche
- Next upgrades: real email sending (SMTP), PDF parsing by default, multi-currency
