import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from ai_engine import analyze_invoice_text, generate_negotiation_email, simulate_vendor_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


# ---------------- storage helpers ----------------
def load_json(name, default):
    p = os.path.join(DATA_DIR, name)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_settings():
    s = load_json("settings.json", {})
    s.setdefault("api_key", "")
    s.setdefault("base_url", "https://api.openai.com/v1")
    s.setdefault("model", "gpt-4o-mini")
    s.setdefault("mock", True)
    return s


def llm_cfg():
    s = get_settings()
    return {"api_key": s["api_key"], "base_url": s["base_url"],
            "model": s["model"], "mock": s["mock"] or not s["api_key"]}


def find_by_id(lst, item_id):
    return next((x for x in lst if x.get("id") == item_id), None)


# ---------------- frontend ----------------
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------------- settings ----------------
@app.get("/api/settings")
def get_settings_api():
    s = get_settings()
    s["has_key"] = bool(s["api_key"])
    s["api_key"] = ""
    return jsonify(s)


@app.post("/api/settings")
def save_settings_api():
    s = get_settings()
    d = request.json or {}
    for k in ("base_url", "model", "mock"):
        if k in d:
            s[k] = d[k]
    if d.get("api_key"):
        s["api_key"] = d["api_key"]
    save_json("settings.json", s)
    return jsonify({"ok": True})


# ---------------- vendors ----------------
@app.get("/api/vendors")
def get_vendors():
    return jsonify(load_json("vendors.json", []))


@app.post("/api/vendors")
def add_vendor():
    d = request.json or {}
    if not d.get("name", "").strip():
        return jsonify({"error": "Vendor name is required"}), 400
    vendors = load_json("vendors.json", [])
    v = {"id": uuid.uuid4().hex[:8], "name": d["name"].strip(),
         "category": d.get("category", "General"), "contact": d.get("contact", ""),
         "email": d.get("email", ""), "notes": d.get("notes", ""),
         "created": datetime.now().isoformat(timespec="seconds")}
    vendors.append(v)
    save_json("vendors.json", vendors)
    return jsonify(v)


# ---------------- invoices ----------------
@app.get("/api/invoices")
def get_invoices():
    invoices = load_json("invoices.json", [])
    for inv in invoices:
        inv.pop("raw_text", None)
    return jsonify(invoices)


@app.post("/api/invoices")
def upload_invoice():
    vendor_id = request.form.get("vendor_id", "")
    file = request.files.get("file")
    pasted = request.form.get("text", "").strip()
    filename = "pasted-text.txt"
    text = pasted

    if file and file.filename:
        filename = secure_filename(file.filename)
        if filename.lower().endswith(".txt"):
            text = file.read().decode("utf-8", errors="ignore")
        elif filename.lower().endswith(".pdf"):
            saved = os.path.join(UPLOAD_DIR, filename)
            file.save(saved)
            try:
                from pypdf import PdfReader
                reader = PdfReader(saved)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                text = ""
                return jsonify({"error": "PDF text extraction needs pypdf. Run: pip install pypdf - or paste the invoice text instead."}), 422
        else:
            return jsonify({"error": "Please upload a .txt or .pdf file (or paste the text)."}), 422

    if not text.strip():
        return jsonify({"error": "No invoice text found."}), 400

    invoices = load_json("invoices.json", [])
    inv = {"id": uuid.uuid4().hex[:8], "vendor_id": vendor_id, "filename": filename,
           "raw_text": text[:20000], "created": datetime.now().isoformat(timespec="seconds"),
           "analyzed": False, "analysis": None}
    invoices.append(inv)
    save_json("invoices.json", invoices)
    inv.pop("raw_text", None)
    return jsonify(inv)


@app.post("/api/invoices/<invoice_id>/analyze")
def analyze_invoice(invoice_id):
    invoices = load_json("invoices.json", [])
    inv = find_by_id(invoices, invoice_id)
    if not inv:
        return jsonify({"error": "Invoice not found"}), 404
    vendors = load_json("vendors.json", [])
    vendor = find_by_id(vendors, inv.get("vendor_id", "")) or {}
    analysis = analyze_invoice_text(inv.get("raw_text", ""), vendor.get("category"))
    inv["analyzed"] = True
    inv["analysis"] = analysis
    save_json("invoices.json", invoices)
    return jsonify(analysis)


# ---------------- negotiations ----------------
@app.get("/api/negotiations")
def get_negotiations():
    return jsonify(load_json("negotiations.json", []))


@app.post("/api/negotiations")
def create_negotiation():
    d = request.json or {}
    invoices = load_json("invoices.json", [])
    inv = find_by_id(invoices, d.get("invoice_id", ""))
    if not inv or not inv.get("analysis"):
        return jsonify({"error": "Analyze the invoice first"}), 400
    vendors = load_json("vendors.json", [])
    vendor = find_by_id(vendors, inv.get("vendor_id", "")) or {"name": "Vendor"}
    tone = d.get("tone", "friendly")

    email = generate_negotiation_email(vendor, inv["analysis"], tone, llm_cfg(), d.get("notes", ""))
    ask = inv["analysis"]["total_overcharge"]
    nego = {"id": uuid.uuid4().hex[:8], "invoice_id": inv["id"], "vendor_id": inv.get("vendor_id", ""),
            "vendor_name": vendor.get("name", "Vendor"), "tone": tone, "status": "draft",
            "ask": ask, "conceded": 0.0, "round": 0,
            "subject": email["subject"], "email_body": email["body"], "email_source": email["source"],
            "history": [], "savings": 0.0,
            "created": datetime.now().isoformat(timespec="seconds")}
    negotiations = load_json("negotiations.json", [])
    negotiations.append(nego)
    save_json("negotiations.json", negotiations)
    return jsonify(nego)


@app.post("/api/negotiations/<nego_id>/send")
def send_negotiation(nego_id):
    negotiations = load_json("negotiations.json", [])
    nego = find_by_id(negotiations, nego_id)
    if not nego:
        return jsonify({"error": "Not found"}), 404
    if nego["status"] in ("accepted", "declined"):
        return jsonify(nego)
    resp = simulate_vendor_response(nego, "send", llm_cfg())
    nego["round"] = resp["round"]
    nego["conceded"] = resp["offer"] if resp["status"] == "accepted" else nego["conceded"]
    nego["status"] = resp["status"]
    if resp["status"] == "accepted":
        nego["savings"] = resp["offer"]
    nego["history"].append({"role": "you", "message": nego["email_body"], "offer": None})
    nego["history"].append({"role": "vendor", "message": resp["message"], "offer": resp["offer"]})
    save_json("negotiations.json", negotiations)
    return jsonify(nego)


@app.post("/api/negotiations/<nego_id>/counter")
def counter_negotiation(nego_id):
    d = request.json or {}
    negotiations = load_json("negotiations.json", [])
    nego = find_by_id(negotiations, nego_id)
    if not nego or nego["status"] in ("accepted", "declined"):
        return jsonify(nego if nego else {"error": "Not found"}), 200 if nego else 404
    msg = d.get("message") or "Thanks - we appreciate that. To keep the partnership strong, we need to get closer to our original ask."
    resp = simulate_vendor_response(nego, "counter", llm_cfg())
    nego["round"] = resp["round"]
    nego["status"] = resp["status"]
    if resp["status"] == "accepted":
        nego["conceded"] = resp["offer"]
        nego["savings"] = resp["offer"]
    nego["history"].append({"role": "you", "message": msg, "offer": None})
    nego["history"].append({"role": "vendor", "message": resp["message"], "offer": resp["offer"]})
    save_json("negotiations.json", negotiations)
    return jsonify(nego)


@app.post("/api/negotiations/<nego_id>/accept")
def accept_negotiation(nego_id):
    negotiations = load_json("negotiations.json", [])
    nego = find_by_id(negotiations, nego_id)
    if not nego:
        return jsonify({"error": "Not found"}), 404
    last_offer = 0.0
    for h in reversed(nego["history"]):
        if h["role"] == "vendor" and h.get("offer"):
            last_offer = h["offer"]
            break
    nego["status"] = "accepted"
    nego["savings"] = last_offer
    save_json("negotiations.json", negotiations)
    return jsonify(nego)


# ---------------- dashboard ----------------
@app.get("/api/dashboard")
def dashboard():
    invoices = load_json("invoices.json", [])
    vendors = load_json("vendors.json", [])
    negotiations = load_json("negotiations.json", [])
    annual_savings = sum((inv.get("analysis") or {}).get("annual_savings", 0) for inv in invoices)
    won = sum(n.get("savings", 0) for n in negotiations if n.get("status") == "accepted")
    active = sum(1 for n in negotiations if n.get("status") == "counter")
    by_cat = {}
    for inv in invoices:
        for cat, amt in ((inv.get("analysis") or {}).get("by_category", {})).items():
            by_cat[cat] = round(by_cat.get(cat, 0) + amt, 2)
    return jsonify({"annual_savings": round(annual_savings, 2), "savings_won": round(won, 2),
                    "active_negotiations": active, "vendors": len(vendors),
                    "invoices": len(invoices), "by_category": by_cat,
                    "ai_mode": "live" if not llm_cfg()["mock"] else "mock"})


if __name__ == "__main__":
    print("\n  ProcureAI running ->  http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
