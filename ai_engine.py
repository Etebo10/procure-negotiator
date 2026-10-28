import os
import re
import json
import random
import urllib.request
from datetime import datetime

# ============================================================
#  MARKET BENCHMARK DATABASE (small-business pricing)
# ============================================================
BENCHMARKS = {
    "Office Supplies": [
        {"item": "Printer paper A4 (500 sheets)", "low": 3.50, "high": 6.00},
        {"item": "Ballpoint pens (box of 50)", "low": 8.00, "high": 15.00},
        {"item": "Sticky notes (12 pack)", "low": 6.00, "high": 12.00},
        {"item": "Toner cartridge", "low": 25.00, "high": 60.00},
        {"item": "Envelopes (box of 500)", "low": 12.00, "high": 25.00},
    ],
    "SaaS & Software": [
        {"item": "Project management (per user / month)", "low": 5.00, "high": 12.00},
        {"item": "Cloud storage (per TB / month)", "low": 5.00, "high": 23.00},
        {"item": "Email marketing (per 1k contacts)", "low": 10.00, "high": 30.00},
        {"item": "Video conferencing (per user / month)", "low": 6.00, "high": 15.00},
    ],
    "Telecom & Internet": [
        {"item": "Business broadband (per month)", "low": 40.00, "high": 90.00},
        {"item": "Business mobile line (per month)", "low": 15.00, "high": 35.00},
        {"item": "VoIP phone line (per month)", "low": 10.00, "high": 25.00},
    ],
    "Shipping & Logistics": [
        {"item": "Express parcel national (per kg)", "low": 4.00, "high": 9.00},
        {"item": "Freight pallet (per pallet)", "low": 60.00, "high": 120.00},
        {"item": "Courier same-day (per package)", "low": 12.00, "high": 30.00},
    ],
    "Cleaning & Facilities": [
        {"item": "Office cleaning (per visit)", "low": 60.00, "high": 140.00},
        {"item": "Waste collection (per month)", "low": 25.00, "high": 60.00},
        {"item": "Window cleaning (per visit)", "low": 50.00, "high": 120.00},
    ],
    "Marketing Services": [
        {"item": "Social media management (per month)", "low": 300.00, "high": 800.00},
        {"item": "Blog article (per piece)", "low": 50.00, "high": 200.00},
        {"item": "Logo design refresh", "low": 200.00, "high": 800.00},
    ],
    "IT Hardware": [
        {"item": "Business laptop", "low": 500.00, "high": 1100.00},
        {"item": "24-inch monitor", "low": 100.00, "high": 200.00},
        {"item": "Wireless mouse", "low": 10.00, "high": 30.00},
    ],
    "Professional Services": [
        {"item": "Accounting retainer (per month)", "low": 100.00, "high": 400.00},
        {"item": "Legal consultation (per hour)", "low": 150.00, "high": 350.00},
    ],
    "General": [
        {"item": "Coffee beans (per kg)", "low": 12.00, "high": 28.00},
        {"item": "Bottled water (per crate)", "low": 4.00, "high": 9.00},
    ],
}

SKIP_WORDS = ("total", "subtotal", "tax", "vat", "invoice", "date", "due", "balance",
              "payment", "amount", "bill to", "remit", "page")
STOPWORDS = set("the a an of per pack box sheet sheets month user for with pcs unit units each x".split())

CATEGORIES = list(BENCHMARKS.keys())


# ============================================================
#  INVOICE PARSING & BENCHMARK ANALYSIS
# ============================================================
def parse_line_items(text):
    items = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 4:
            continue
        low = line.lower()
        if any(w in low for w in SKIP_WORDS):
            continue
        m = re.search(r"\$\s*(\d+(?:[,\.]\d{1,2})+)", line) or re.search(r"(\d+(?:\.\d{1,2})?)\s*$", line)
        if not m:
            continue
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if price < 1 or price > 500000:
            continue
        name = re.sub(r"\$\s*\d+(?:[,\.]\d{1,2})+", "", line)
        name = re.sub(r"\d+(?:\.\d{1,2})?\s*$", "", name)
        name = re.sub(r"^\d+[\.\)]\s*", "", name).strip(" .-\t")
        if len(name) < 3:
            continue
        items.append({"name": name[:80], "paid": round(price, 2)})
    return items


def match_benchmark(item_name, category=None):
    words = set(re.findall(r"[a-z]+", item_name.lower())) - STOPWORDS
    best, best_score = None, 0
    cats = [category] if category in BENCHMARKS else CATEGORIES
    for cat in cats:
        for b in BENCHMARKS[cat]:
            bw = set(re.findall(r"[a-z]+", b["item"].lower())) - STOPWORDS
            score = len(words & bw)
            if score > best_score:
                best, best_score = dict(b, category=cat), score
    return best if best_score >= 1 else None


def analyze_invoice_text(text, category=None):
    items = parse_line_items(text)
    analyzed = []
    total_paid = total_overcharge = 0.0
    by_category = {}
    for it in items:
        total_paid += it["paid"]
        b = match_benchmark(it["name"], category)
        row = {"name": it["name"], "paid": it["paid"], "benchmark": None,
               "status": "unknown", "fair_price": None, "overcharge": 0.0}
        if b:
            fair = round((b["low"] + b["high"]) / 2, 2)
            over = round(max(0.0, it["paid"] - b["high"]), 2)
            status = "overpriced" if over > 0 else ("fair" if it["paid"] >= b["low"] else "good")
            row.update(benchmark=b["item"], category=b["category"],
                       fair_price=fair, overcharge=over, status=status)
            total_overcharge += over
            if over > 0:
                by_category[b["category"]] = round(by_category.get(b["category"], 0) + over, 2)
        analyzed.append(row)
    return {
        "items": analyzed,
        "total_paid": round(total_paid, 2),
        "total_overcharge": round(total_overcharge, 2),
        "annual_savings": round(total_overcharge * 12, 2),
        "flagged": sum(1 for r in analyzed if r["status"] == "overpriced"),
        "by_category": by_category,
    }


# ============================================================
#  LLM INTEGRATION (OpenAI-compatible) with MOCK fallback
# ============================================================
def llm_chat(messages, cfg, max_tokens=900):
    key = (cfg or {}).get("api_key", "")
    if not key or (cfg or {}).get("mock", True):
        return None
    base = ((cfg or {}).get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (cfg or {}).get("model") or "gpt-4o-mini"
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({"model": model, "messages": messages,
                         "max_tokens": max_tokens, "temperature": 0.7}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


TONES = {
    "friendly": {
        "opener": "I hope you are doing well! We genuinely enjoy working with your team.",
        "ask": "Would you be open to adjusting these line items to the market range? It would mean a lot as we plan this year's budget.",
        "closer": "Thank you so much for considering this - happy to jump on a quick call anytime.",
    },
    "firm": {
        "opener": "I am writing regarding the pricing on our recent invoices.",
        "ask": "We need these items brought in line with market rates. We are asking for an adjustment to the levels outlined below.",
        "closer": "Please confirm by the end of the week so we can plan accordingly.",
    },
    "hardball": {
        "opener": "Our recent invoice audit flagged significant overpricing on several line items.",
        "ask": "We expect these corrected immediately, along with a credit note for the overcharged amounts. Otherwise we will need to re-tender this contract.",
        "closer": "We await your confirmation within 5 business days.",
    },
}


def generate_negotiation_email(vendor, analysis, tone, cfg, notes=""):
    tone = tone if tone in TONES else "friendly"
    flagged = [r for r in analysis["items"] if r["status"] == "overpriced"]
    ask_amount = analysis["total_overcharge"]
    pct = round((ask_amount / analysis["total_paid"] * 100), 1) if analysis["total_paid"] else 0
    vendor_name = vendor.get("name", "Vendor")
    contact = vendor.get("contact") or "there"

    prompt = [
        {"role": "system", "content": "You are a world-class procurement negotiator. Write a short, persuasive, professional negotiation email."},
        {"role": "user", "content":
         "Vendor: " + vendor_name + "\nTone: " + tone +
         "\nOverpriced items:\n" + "\n".join(
             "- " + r["name"] + ": paying $" + str(r["paid"]) + " vs market $" + str(r["benchmark"]) +
             " (fair ~$" + str(r["fair_price"]) + ")" for r in flagged) +
         "\nTotal overcharge per invoice: $" + str(ask_amount) + " (" + str(pct) + "% of invoice)" +
         "\nExtra notes: " + (notes or "none") +
         "\n\nWrite: subject line, then the email body. Ask for a price adjustment to fair market rates and a credit for past overcharges."},
    ]
    ai_text = llm_chat(prompt, cfg)
    if ai_text:
        if "\n" in ai_text:
            subject, body = ai_text.split("\n", 1)
        else:
            subject, body = "Pricing review - " + vendor_name, ai_text
        return {"subject": subject.strip(), "body": body.strip(), "source": "ai"}

    t = TONES[tone]
    def _fm(x):
        return "{:,.2f}".format(float(x))
    bullets = "\n".join(
        "  - {name}: we pay ${paid} vs market range ${lo} - ${hi} (fair ~${fair})".format(
            name=r["name"], paid=_fm(r["paid"]),
            lo=_fm(BENCH_LOOKUP(r["benchmark"])[0]) if r["benchmark"] else "?",
            hi=_fm(BENCH_LOOKUP(r["benchmark"])[1]) if r["benchmark"] else "?",
            fair=_fm(r["fair_price"]))
        for r in flagged) if flagged else "  - (benchmark data matched no line items)"
    body = (
        "Hi " + contact + ",\n\n" + t["opener"] + "\n\n"
        "We have benchmarked our recent invoices against current market rates and found the following items priced above the going range:\n\n"
        + bullets + "\n\n"
        "In total this is about $" + str(ask_amount) + " per invoice (" + str(pct) + "%). "
        + t["ask"] + "\n\n"
        "Specifically, we propose:\n"
        "  1. Unit prices adjusted to the fair market rates above\n"
        "  2. A one-time credit of $" + str(ask_amount) + " covering recent overcharges\n\n"
        + (("Additional context: " + notes.strip() + "\n\n") if notes.strip() else "")
        + t["closer"] + "\n\nBest regards,\nProcurement\n"
    )
    return {"subject": "Pricing review - " + vendor_name + " (" + str(pct) + "% above market)",
            "body": body, "source": "template"}


_BENCH_FLAT = []
for _cat in CATEGORIES:
    for _b in BENCHMARKS[_cat]:
        _BENCH_FLAT.append((_b["item"], _b["low"], _b["high"]))


def BENCH_LOOKUP(item_name):
    for it, lo, hi in _BENCH_FLAT:
        if it == item_name:
            return (lo, hi)
    return (0, 0)


# ============================================================
#  VENDOR RESPONSE SIMULATION
# ============================================================
def simulate_vendor_response(nego, action, cfg):
    rnd = nego.get("round", 0) + 1
    ask = max(float(nego.get("ask", 0)), 1.0)
    conceded = float(nego.get("conceded", 0))
    tone = nego.get("tone", "friendly")

    prompt = [
        {"role": "system", "content": "You are a vendor replying to a procurement negotiation email. Be realistic, slightly defensive at first, willing to compromise over rounds."},
        {"role": "user", "content":
         "Ask: $" + str(ask) + " total adjustment. Already conceded: $" + str(conceded) +
         ". Round: " + str(rnd) + ". Customer action: " + action +
         ". Tone of their emails: " + tone + ".\nReply in 3-5 sentences as the vendor, stating a concession amount in dollars."},
    ]
    ai_text = llm_chat(prompt, cfg, max_tokens=400)

    gap = ask - conceded
    if action == "counter":
        factor = 0.50 if rnd < 3 else 0.85
    else:
        factor = 0.30
    offer = round(conceded + gap * factor * random.uniform(0.85, 1.15), 2)

    if rnd >= 4 or offer >= ask * 0.97 or (action == "counter" and rnd >= 3 and gap / ask < 0.2):
        offer = ask
        status = "accepted"
    else:
        status = "counter"

    if status == "accepted":
        msg = ("Understood - you drive a hard bargain. We agree to the full adjustment of $"
               + str(ask) + ". You will see revised pricing on your next invoice plus the credit note this week.")
    else:
        if ai_text:
            msg = ai_text
        else:
            templates = [
                "Thanks for flagging this. These rates reflect our service quality, but we can offer a concession of ${offer} to keep your business.",
                "We have reviewed internally. Our margins are tight, however we can move to ${offer} as a goodwill gesture.",
                "Let us meet you partway: we can concede ${offer} and lock that in for 12 months.",
            ]
            msg = templates[min(rnd - 1, len(templates) - 1)].replace("${offer}", str(offer))
    return {"round": rnd, "offer": min(offer, ask), "status": status, "message": msg}
