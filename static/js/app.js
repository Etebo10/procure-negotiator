/* ============ ProcureAI frontend ============ */
const $ = (s) => document.querySelector(s);
const state = { vendors: [], invoices: [], negotiations: [], tone: "friendly", chart: null, currentNego: null };

const CATEGORIES = ["General","Office Supplies","SaaS & Software","Telecom & Internet","Shipping & Logistics",
  "Cleaning & Facilities","Marketing Services","IT Hardware","Professional Services"];

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ("Error " + res.status));
  return data;
}

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 3200);
}

const money = (n) => "$" + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ============ navigation ============ */
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    $("#view-" + btn.dataset.view).classList.add("active");
  });
});
document.querySelectorAll("[data-go-view]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelector('[data-view="' + btn.dataset.goView + '"]').click();
  });
});

/* ============ dashboard ============ */
async function loadDashboard() {
  const d = await api("/api/dashboard");
  animateNum($("#st-annual"), d.annual_savings);
  animateNum($("#st-won"), d.savings_won);
  $("#st-active").textContent = d.active_negotiations;
  $("#st-vendors").textContent = d.vendors;
  const chip = $("#mode-chip");
  if (d.ai_mode === "live") {
    chip.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles" aria-hidden="true"></i> LIVE AI';
    chip.classList.add("live");
  } else {
    chip.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles" aria-hidden="true"></i> MOCK MODE';
    chip.classList.remove("live");
  }

  const cats = Object.keys(d.by_category);
  const vals = Object.values(d.by_category);
  const ctx = $("#cat-chart");
  if (state.chart) state.chart.destroy();
  state.chart = new Chart(ctx, {
    type: "bar",
    data: { labels: cats.length ? cats : ["No data yet"], datasets: [{ data: vals.length ? vals : [0],
      backgroundColor: "rgba(104,145,82,.72)", borderColor: "#557d4e", borderWidth: 1, borderRadius: 4, maxBarThickness: 42 }] },
    options: { plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false }, ticks: { color: "#75817a", font: { family: "DM Sans", size: 10 } } },
                y: { beginAtZero: true, grid: { color: "#edf0e9" }, border: { display: false }, ticks: { color: "#8a958d", callback: (v) => "$" + v, font: { family: "DM Sans", size: 10 } } } } }
  });

  const recent = state.negotiations.slice(-5).reverse();
  $("#recent-negos").innerHTML = recent.length ? recent.map((n) =>
    "<div class='row-item'><div class='grow'><b>" + esc(n.vendor_name) + "</b>" +
    "<span class='meta'>" + n.tone + " tone · " + n.round + " round(s)</span></div>" +
    "<span class='pill " + (n.status === "accepted" ? "pill-green" : "pill-gold") + "'>" +
    (n.status === "accepted" ? "won " + money(n.savings) : n.status) + "</span></div>"
  ).join("") : "<p class='muted'>No negotiations yet — analyze an invoice to begin.</p>";
}

function animateNum(el, target) {
  const start = 0, dur = 800, t0 = performance.now();
  function step(t) {
    const p = Math.min((t - t0) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = money(start + (target - start) * eased);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ============ vendors ============ */
async function loadVendors() {
  state.vendors = await api("/api/vendors");
  $("#vendor-list").innerHTML = state.vendors.length ? state.vendors.map((v) =>
    "<div class='row-item'><div class='grow'><b>" + esc(v.name) + "</b>" +
    "<span class='meta'>" + esc(v.category) + (v.contact ? " · " + esc(v.contact) : "") + "</span></div>" +
    "<span class='pill pill-blue'>" + esc(v.category) + "</span></div>"
  ).join("") : "<p class='muted'>No vendors yet — add your first one.</p>";

  const opts = state.vendors.map((v) => "<option value='" + v.id + "'>" + esc(v.name) + "</option>").join("");
  $("#inv-vendor").innerHTML = opts || "<option value=''>— add a vendor first —</option>";
}

function fillCategories() {
  $("#v-category").innerHTML = CATEGORIES.map((c) => "<option>" + c + "</option>").join("");
}

$("#btn-add-vendor").addEventListener("click", async () => {
  try {
    await api("/api/vendors", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("#v-name").value, category: $("#v-category").value,
        contact: $("#v-contact").value, email: $("#v-email").value }) });
    $("#v-name").value = $("#v-contact").value = $("#v-email").value = "";
    toast("Vendor added");
    await loadVendors();
  } catch (e) { toast(e.message, true); }
});

/* ============ invoices ============ */
const dz = $("#dropzone"), fileInput = $("#inv-file");
dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over");
  if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; showFileName(); } });
fileInput.addEventListener("change", showFileName);
function showFileName() { $("#file-name").textContent = fileInput.files[0] ? fileInput.files[0].name : "no file selected"; }

$("#btn-upload-inv").addEventListener("click", async () => {
  try {
    const fd = new FormData();
    fd.append("vendor_id", $("#inv-vendor").value);
    if (fileInput.files[0]) fd.append("file", fileInput.files[0]);
    fd.append("text", $("#inv-text").value);
    await api("/api/invoices", { method: "POST", body: fd });
    fileInput.value = ""; $("#inv-text").value = ""; showFileName();
    toast("Invoice saved — analyze it to see the benchmark.");
    await loadInvoices(); await loadDashboard();
  } catch (e) { toast(e.message, true); }
});

async function loadInvoices() {
  state.invoices = await api("/api/invoices");
  $("#invoice-list").innerHTML = state.invoices.length ? state.invoices.map((inv) => {
    const a = inv.analysis;
    return "<div class='row-item'><div class='grow'><b>" + esc(inv.filename) + "</b>" +
      "<span class='meta'>" + inv.created.slice(0, 10) + (a ? " · flagged " + a.flagged + " item(s)" : "") + "</span></div>" +
      (inv.analyzed
        ? "<span class='pill " + (a.flagged ? "pill-red" : "pill-green") + "'>" + money(a.total_overcharge) + " over</span>"
        : "<button class='btn btn-ghost btn-sm' onclick='analyzeInvoice(\"" + inv.id + "\")'><i class='fa-solid fa-magnifying-glass-chart' aria-hidden='true'></i> Analyze</button>") +
      "</div>";
  }).join("") : "<p class='muted'>No invoices yet.</p>";

  const analyzed = state.invoices.filter((i) => i.analyzed);
  $("#ng-invoice").innerHTML = analyzed.length
    ? analyzed.map((i) => "<option value='" + i.id + "'>" + esc(i.filename) + " (" + money(i.analysis.total_overcharge) + " over)</option>").join("")
    : "<option value=''>— analyze an invoice first —</option>";
}

window.analyzeInvoice = async (id) => {
  try {
    const a = await api("/api/invoices/" + id + "/analyze", { method: "POST" });
    renderAnalysis(a);
    toast(a.flagged ? "Found " + money(a.total_overcharge) + " in potential overcharges." : "Pricing looks fair against the available benchmarks.");
    await loadInvoices(); await loadDashboard();
  } catch (e) { toast(e.message, true); }
};

function renderAnalysis(a) {
  $("#analysis-card").classList.remove("hidden");
  $("#an-flagged").textContent = a.flagged + " item(s) overpriced";
  $("#an-overcharge").textContent = money(a.total_overcharge) + " over / invoice";
  $("#an-annual").textContent = money(a.annual_savings) + " / year at stake";
  $("#analysis-body").innerHTML = a.items.map((r) => {
    const badge = { overpriced: "OVERPRICED", fair: "FAIR", good: "GREAT DEAL", unknown: "NO DATA" }[r.status];
    return "<tr><td>" + esc(r.name) + "</td><td>" + money(r.paid) + "</td><td>" +
      (r.benchmark ? esc(r.benchmark) : "—") + "</td><td>" + (r.fair_price ? money(r.fair_price) : "—") +
      "</td><td><span class='verdict " + r.status + "'>" + badge + "</span></td></tr>";
  }).join("");
  $("#analysis-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#btn-to-negotiate").addEventListener("click", () => {
  document.querySelector('[data-view="negotiations"]').click();
});

/* ============ negotiations ============ */
$("#tone-row").addEventListener("click", (e) => {
  const btn = e.target.closest(".tone-btn");
  if (!btn) return;
  document.querySelectorAll(".tone-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  state.tone = btn.dataset.tone;
});

$("#btn-generate").addEventListener("click", async () => {
  const invoiceId = $("#ng-invoice").value;
  if (!invoiceId) return toast("Analyze an invoice first", true);
  try {
    const nego = await api("/api/negotiations", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invoice_id: invoiceId, tone: state.tone, notes: $("#ng-notes").value }) });
    state.currentNego = nego;
    openDeal(nego);
    toast("Draft ready. Review it before sending.");
    await loadNegotiations(); await loadDashboard();
  } catch (e) { toast(e.message, true); }
});

function openDeal(nego) {
  $("#deal-empty").classList.add("hidden");
  $("#deal-live").classList.remove("hidden");
  $("#deal-win").classList.add("hidden");
  $("#deal-controls").classList.add("hidden");
  $("#email-subject").textContent = "Subject: " + nego.subject;
  $("#email-body").textContent = nego.email_body;
  $("#email-source").textContent = nego.email_source === "ai" ? "Drafted by live AI" : "Drafted by mock engine";
  $("#btn-send").disabled = nego.status !== "draft";
  renderChat(nego);
  if (nego.status === "accepted") showWin(nego);
  else if (nego.status === "counter") $("#deal-controls").classList.remove("hidden");
}

function renderChat(nego) {
  const c = $("#chat");
  c.innerHTML = "";
  nego.history.forEach((h) => {
    const div = document.createElement("div");
    div.className = "bubble " + h.role;
    div.textContent = h.message;
    if (h.offer != null && h.role === "vendor") {
      const tag = document.createElement("span");
      tag.className = "offer-tag";
      tag.textContent = "Offers: " + money(h.offer);
      div.appendChild(document.createElement("br"));
      div.appendChild(tag);
    }
    c.appendChild(div);
  });
  c.scrollTop = c.scrollHeight;
}

$("#btn-send").addEventListener("click", async () => {
  try {
    const nego = await api("/api/negotiations/" + state.currentNego.id + "/send", { method: "POST" });
    state.currentNego = nego;
    openDeal(nego);
    toast(nego.status === "accepted" ? "Vendor accepted immediately." : "Vendor replied. See the deal room.");
    await loadNegotiations(); await loadDashboard();
  } catch (e) { toast(e.message, true); }
});

$("#btn-counter").addEventListener("click", async () => {
  try {
    const nego = await api("/api/negotiations/" + state.currentNego.id + "/counter", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
    state.currentNego = nego;
    openDeal(nego);
    if (nego.status === "accepted") { toast("Your full ask was accepted."); await loadDashboard(); }
    await loadNegotiations();
  } catch (e) { toast(e.message, true); }
});

$("#btn-accept").addEventListener("click", async () => {
  try {
    const nego = await api("/api/negotiations/" + state.currentNego.id + "/accept", { method: "POST" });
    state.currentNego = nego;
    openDeal(nego);
    toast("Deal closed.");
    await loadNegotiations(); await loadDashboard();
  } catch (e) { toast(e.message, true); }
});

function showWin(nego) {
  $("#deal-controls").classList.add("hidden");
  $("#deal-win").classList.remove("hidden");
  $("#win-amount").textContent = money(nego.savings);
}

async function loadNegotiations() {
  state.negotiations = await api("/api/negotiations");
  $("#nego-history").innerHTML = state.negotiations.length ? state.negotiations.slice().reverse().map((n) =>
    "<div class='row-item'><div class='grow'><b>" + esc(n.vendor_name) + "</b>" +
    "<span class='meta'>" + n.tone + " · " + n.round + " round(s) · " + n.created.slice(0, 10) + "</span></div>" +
    "<span class='pill " + (n.status === "accepted" ? "pill-green" : n.status === "draft" ? "pill-grey" : "pill-gold") + "'>" +
    (n.status === "accepted" ? "won " + money(n.savings) : n.status) + "</span></div>"
  ).join("") : "<p class='muted'>No negotiations yet.</p>";
  await loadDashboard();
}

/* ============ settings ============ */
async function loadSettings() {
  const s = await api("/api/settings");
  $("#set-mock").checked = s.mock;
  $("#set-model").value = s.model;
  $("#set-base").value = s.base_url;
  $("#settings-status").textContent = s.has_key
    ? "API key saved on server. Turn mock mode off to use live AI."
    : "No API key saved — mock mode is active (works great, zero cost).";
}

$("#btn-save-settings").addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: $("#set-key").value, model: $("#set-model").value,
        base_url: $("#set-base").value, mock: $("#set-mock").checked }) });
    $("#set-key").value = "";
    toast("Settings saved.");
    await loadSettings(); await loadDashboard();
  } catch (e) { toast(e.message, true); }
});

/* ============ helpers & boot ============ */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

(async function boot() {
  fillCategories();
  try {
    await loadSettings();
    await loadVendors();
    await loadInvoices();
    await loadNegotiations();
  } catch (e) { toast("Backend not reachable — is app.py running?", true); }
})();
