/* ============================================================
   # API CONFIG — backend base URL
   Resolved against the current hostname so this works whether
   the dashboard is opened via localhost or a remote host.
   ============================================================ */
const API_BASE = "https://urbandash-7rtr.onrender.com";

const TEAM_LABELS = {
  support: "Support",
  ops: "Ops",
  trust_and_safety: "Trust & Safety",
  finance: "Finance",
  hr_driver_relations: "HR / Driver Relations",
  legal: "Legal",
  none: "Unrouted",
};

const CATEGORY_LABELS = {
  delivery_delay: "Delivery delay",
  food_quality: "Food quality",
  food_safety: "Food safety",
  billing_dispute: "Billing dispute",
  order_mixup: "Order mixup",
  coverage_request: "Coverage request",
  praise: "Praise",
  driver_safety: "Driver safety",
  legal_compliance: "Legal / compliance",
  account_management: "Account management",
  test_noise: "Test / QA noise",
  low_signal: "Low signal",
  other: "Other",
};

/* ============================================================
   # APP STATE — JS-driven UI state
   ============================================================ */
const state = {
  view: "queue", // 'queue' | 'noise' | 'unclassified'
  filters: { status: "", team: "", urgency: "" },
  showNoise: false,
  queueItems: [],
  allComplaints: [],
};

/* ============================================================
   # DOM REFS
   ============================================================ */
const el = {
  queueContainer: document.getElementById("queue-container"),
  emptyState: document.getElementById("empty-state"),
  statsStrip: document.getElementById("stats-strip"),
  apiStatusDot: document.getElementById("api-status-dot"),
  apiStatusText: document.getElementById("api-status-text"),

  filterStatus: document.getElementById("filter-status"),
  filterTeam: document.getElementById("filter-team"),
  filterUrgency: document.getElementById("filter-urgency"),
  filterNoise: document.getElementById("filter-noise"),
  btnResetFilters: document.getElementById("btn-reset-filters"),

  btnOpenIngest: document.getElementById("btn-open-ingest"),
  btnClassifyAll: document.getElementById("btn-classify-all"),

  ingestOverlay: document.getElementById("ingest-modal-overlay"),
  ingestForm: document.getElementById("ingest-form"),
  ingestClose: document.getElementById("ingest-modal-close"),
  ingestCancel: document.getElementById("ingest-cancel"),
  ingestError: document.getElementById("ingest-error"),
  ingestSubmit: document.getElementById("ingest-submit"),

  detailOverlay: document.getElementById("detail-modal-overlay"),
  detailModal: document.getElementById("detail-modal"),

  toast: document.getElementById("toast"),

  viewToggleBtns: Array.from(document.querySelectorAll(".view-toggle-btn")),
};

/* ============================================================
   # UTILITIES
   ============================================================ */
function showToast(message, kind = "default") {
  el.toast.textContent = message;
  el.toast.className = "toast" + (kind === "error" ? " toast-error" : kind === "success" ? " toast-success" : "");
  el.toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { el.toast.hidden = true; }, 3800);
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

async function apiFetch(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (err) {
    throw new Error(`Could not reach the API at ${API_BASE}. Is the backend container running?`);
  }
  let body = null;
  const text = await res.text();
  if (text) {
    try { body = JSON.parse(text); } catch (_) { body = text; }
  }
  if (!res.ok) {
    const detail = (body && body.detail) ? body.detail : `Request failed with status ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

/* ============================================================
   # API STATUS CHECK
   ============================================================ */
async function checkApiHealth() {
  try {
    await apiFetch("/health");
    el.apiStatusDot.className = "status-dot is-ok";
    el.apiStatusText.textContent = "API connected";
  } catch (err) {
    el.apiStatusDot.className = "status-dot is-error";
    el.apiStatusText.textContent = "API unreachable";
  }
}

/* ============================================================
   # DATA LOADING
   ============================================================ */
async function loadStats() {
  try {
    const all = await apiFetch("/queue?include_noise=true");
    state.allQueueRaw = all;
    const openTickets = all.filter(i => !i.is_noise);
    const critical = openTickets.filter(i => i.urgency === "critical" && i.status !== "resolved").length;
    const openCount = openTickets.filter(i => i.status !== "resolved").length;

    const complaints = await apiFetch("/complaints");
    state.allComplaints = complaints;
    const unclassified = complaints.filter(c => c.classifications.length === 0).length;

    el.statsStrip.innerHTML = `
      <div class="stat-tile is-brand">
        <div class="stat-tile-value">${openCount}</div>
        <div class="stat-tile-label">Open issues</div>
      </div>
      <div class="stat-tile is-critical">
        <div class="stat-tile-value">${critical}</div>
        <div class="stat-tile-label">Critical</div>
      </div>
      <div class="stat-tile">
        <div class="stat-tile-value">${unclassified}</div>
        <div class="stat-tile-label">Unclassified</div>
      </div>
      <div class="stat-tile">
        <div class="stat-tile-value">${complaints.length}</div>
        <div class="stat-tile-label">Total in</div>
      </div>
    `;
  } catch (err) {
    // Stats are non-critical; fail quietly, main queue load will surface errors.
  }
}

async function loadQueue() {
  el.queueContainer.classList.add("is-loading");
  try {
    if (state.view === "unclassified") {
      const complaints = await apiFetch("/complaints");
      const unclassified = complaints.filter(c => c.classifications.length === 0);
      renderUnclassified(unclassified);
      return;
    }

    const params = new URLSearchParams();
    if (state.filters.status) params.set("status", state.filters.status);
    if (state.filters.team) params.set("team", state.filters.team);
    if (state.filters.urgency) params.set("urgency", state.filters.urgency);
    params.set("include_noise", state.view === "noise" ? "true" : (state.showNoise ? "true" : "false"));

    const items = await apiFetch(`/queue?${params.toString()}`);
    const filtered = state.view === "noise" ? items.filter(i => i.is_noise) : items.filter(i => !i.is_noise);

    state.queueItems = filtered;
    renderQueue(filtered);
  } catch (err) {
    showToast(err.message, "error");
    el.queueContainer.innerHTML = "";
    el.emptyState.hidden = false;
    el.emptyState.querySelector("p").textContent = "Couldn't load the queue — check the API connection.";
  } finally {
    el.queueContainer.classList.remove("is-loading");
  }
}

/* ============================================================
   # RENDERING — queue cards
   ============================================================ */
function renderQueue(items) {
  el.queueContainer.innerHTML = "";

  if (items.length === 0) {
    el.emptyState.hidden = false;
    el.emptyState.querySelector("p").textContent =
      state.view === "noise" ? "No filtered / noise items right now." : "Queue is clear. Nice work.";
    return;
  }
  el.emptyState.hidden = true;

  // Group by complaint_id to show a multi-issue badge count.
  const countByComplaint = {};
  items.forEach(i => { countByComplaint[i.complaint_id] = (countByComplaint[i.complaint_id] || 0) + 1; });

  items.forEach(item => {
    const card = document.createElement("div");
    card.className = "ticket-card" + (item.overridden ? " is-overridden" : "");
    card.dataset.urgency = item.urgency;
    card.dataset.classificationId = item.classification_id;
    card.dataset.complaintId = item.complaint_id;

    const multiCount = countByComplaint[item.complaint_id];
    const multiBadge = multiCount > 1
      ? `<span class="multi-issue-badge">1 of ${multiCount} issues</span>`
      : "";

    card.innerHTML = `
      <div>
        <div class="ticket-meta-row">
          <span>${escapeHtml(item.customer_identifier)}</span>
          <span class="dot-sep">${item.complainant_type === "driver" ? "Driver" : "Customer"}</span>
          <span class="dot-sep">${escapeHtml(item.channel.replace("_", " "))}</span>
          <span class="dot-sep">${fmtTime(item.created_at)}</span>
          <span class="status-pill status-${item.status}">${item.status.replace("_", " ")}</span>
          ${multiBadge}
        </div>
        <div class="ticket-message">${escapeHtml(item.raw_message)}</div>
        <div class="ticket-tags">
          <span class="tag tag-team">${TEAM_LABELS[item.routed_team] || item.routed_team}</span>
          <span class="tag">${CATEGORY_LABELS[item.category] || item.category}</span>
        </div>
      </div>
      <div class="stamp${item.is_noise ? " stamp-noise" : ""}">${item.is_noise ? "filtered" : item.urgency}</div>
    `;

    card.addEventListener("click", () => openDetailModal(item.complaint_id));
    el.queueContainer.appendChild(card);
  });
}

function renderUnclassified(complaints) {
  el.queueContainer.innerHTML = "";
  if (complaints.length === 0) {
    el.emptyState.hidden = false;
    el.emptyState.querySelector("p").textContent = "Everything has been classified.";
    return;
  }
  el.emptyState.hidden = true;

  complaints.forEach(c => {
    const card = document.createElement("div");
    card.className = "ticket-card";
    card.dataset.urgency = "";
    card.innerHTML = `
      <div>
        <div class="ticket-meta-row">
          <span>${escapeHtml(c.customer_identifier)}</span>
          <span class="dot-sep">${c.complainant_type === "driver" ? "Driver" : "Customer"}</span>
          <span class="dot-sep">${escapeHtml(c.channel.replace("_", " "))}</span>
          <span class="dot-sep">${fmtTime(c.created_at)}</span>
        </div>
        <div class="ticket-message">${escapeHtml(c.raw_message)}</div>
      </div>
      <button class="btn btn-primary btn-sm classify-btn" type="button" data-id="${c.id}">Classify</button>
    `;
    card.querySelector(".classify-btn").addEventListener("click", async (ev) => {
      ev.stopPropagation();
      await classifyComplaint(c.id, ev.target);
    });
    card.addEventListener("click", () => openDetailModal(c.id));
    el.queueContainer.appendChild(card);
  });
}

/* ============================================================
   # ACTIONS — classify / status / override
   ============================================================ */
async function classifyComplaint(complaintId, triggerBtn) {
  if (triggerBtn) { triggerBtn.disabled = true; triggerBtn.textContent = "Classifying…"; }
  try {
    await apiFetch(`/complaints/${complaintId}/classify`, { method: "POST" });
    showToast("Complaint classified.", "success");
    await refreshAll();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    if (triggerBtn) { triggerBtn.disabled = false; triggerBtn.textContent = "Classify"; }
  }
}

async function classifyAllUnclassified() {
  const complaints = await apiFetch("/complaints");
  const targets = complaints.filter(c => c.classifications.length === 0);
  if (targets.length === 0) {
    showToast("Nothing to classify — all complaints already have classifications.");
    return;
  }
  el.btnClassifyAll.disabled = true;
  el.btnClassifyAll.textContent = `Classifying 0 / ${targets.length}…`;
  let done = 0;
  let failures = 0;
  for (const c of targets) {
    try {
      await apiFetch(`/complaints/${c.id}/classify`, { method: "POST" });
    } catch (err) {
      failures += 1;
    }
    done += 1;
    el.btnClassifyAll.textContent = `Classifying ${done} / ${targets.length}…`;
  }
  el.btnClassifyAll.disabled = false;
  el.btnClassifyAll.textContent = "Classify all unclassified";
  showToast(
    failures > 0
      ? `Classified ${done - failures} / ${targets.length}. ${failures} failed — check API key / logs.`
      : `Classified ${done} complaints.`,
    failures > 0 ? "error" : "success"
  );
  await refreshAll();
}

async function updateStatus(complaintId, status) {
  try {
    await apiFetch(`/complaints/${complaintId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    showToast(`Status set to "${status.replace("_", " ")}".`, "success");
    await refreshAll();
    closeDetailModal();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function overrideClassification(classificationId, payload) {
  try {
    await apiFetch(`/classifications/${classificationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    showToast("Classification updated.", "success");
    await refreshAll();
  } catch (err) {
    showToast(err.message, "error");
  }
}

/* ============================================================
   # DETAIL / OVERRIDE MODAL
   ============================================================ */
async function openDetailModal(complaintId) {
  let complaint;
  try {
    complaint = await apiFetch(`/complaints/${complaintId}`);
  } catch (err) {
    showToast(err.message, "error");
    return;
  }

  const issuesHtml = complaint.classifications.length === 0
    ? `<div class="issue-card"><p style="color:var(--text-muted); margin:0;">Not yet classified.</p>
         <button class="btn btn-primary btn-sm" id="detail-classify-btn">Classify now</button>
       </div>`
    : complaint.classifications.map(cls => `
        <div class="issue-card" data-classification-id="${cls.id}">
          <div class="issue-card-header">
            <span class="stamp${cls.is_noise ? " stamp-noise" : ""}" style="transform:none;">${cls.is_noise ? "filtered" : cls.urgency}</span>
            ${cls.overridden ? '<span class="tag" style="border-color:var(--accent-brand); color:var(--accent-brand);">overridden</span>' : ""}
          </div>
          <p class="issue-reasoning">"${escapeHtml(cls.reasoning)}"</p>
          <div class="override-grid">
            <div class="form-row">
              <label>Category</label>
              <select class="ov-category">
                ${Object.entries(CATEGORY_LABELS).map(([k, v]) =>
                  `<option value="${k}" ${cls.category === k ? "selected" : ""}>${v}</option>`).join("")}
              </select>
            </div>
            <div class="form-row">
              <label>Urgency</label>
              <select class="ov-urgency">
                ${["low", "medium", "high", "critical"].map(u =>
                  `<option value="${u}" ${cls.urgency === u ? "selected" : ""}>${u}</option>`).join("")}
              </select>
            </div>
            <div class="form-row">
              <label>Routed team</label>
              <select class="ov-team">
                ${Object.entries(TEAM_LABELS).map(([k, v]) =>
                  `<option value="${k}" ${cls.routed_team === k ? "selected" : ""}>${v}</option>`).join("")}
              </select>
            </div>
            <div class="form-row">
              <label>Filtered (noise)</label>
              <select class="ov-noise">
                <option value="false" ${!cls.is_noise ? "selected" : ""}>No — route normally</option>
                <option value="true" ${cls.is_noise ? "selected" : ""}>Yes — filter out</option>
              </select>
            </div>
          </div>
          <button class="btn btn-secondary btn-sm ov-save-btn" type="button">Save override</button>
        </div>
      `).join("");

  el.detailModal.innerHTML = `
    <div class="detail-header">
      <h2>${escapeHtml(complaint.customer_identifier)} <span style="color:var(--text-muted); font-weight:400; font-size: var(--fs-sm);">· ${complaint.complainant_type} · ${complaint.channel.replace("_"," ")}</span></h2>
      <p style="margin:6px 0 0; color:var(--text-muted); font-size:var(--fs-xs); font-family:var(--font-mono);">${fmtTime(complaint.created_at)} · id ${complaint.id}</p>
    </div>
    <div class="detail-body">
      <div class="detail-message-block">${escapeHtml(complaint.raw_message)}</div>

      <div>
        <div class="panel-block-label" style="margin-bottom:8px;">Classified issues</div>
        <div style="display:flex; flex-direction:column; gap:12px;">${issuesHtml}</div>
      </div>

      <div>
        <div class="panel-block-label" style="margin-bottom:8px;">Complaint status</div>
        <div class="status-actions">
          <button class="btn btn-sm ${complaint.status === "open" ? "btn-primary" : "btn-secondary"}" data-status="open">Open</button>
          <button class="btn btn-sm ${complaint.status === "in_progress" ? "btn-primary" : "btn-secondary"}" data-status="in_progress">In progress</button>
          <button class="btn btn-sm ${complaint.status === "resolved" ? "btn-primary" : "btn-secondary"}" data-status="resolved">Resolved</button>
        </div>
      </div>
    </div>
  `;

  el.detailModal.querySelectorAll("[data-status]").forEach(btn => {
    btn.addEventListener("click", () => updateStatus(complaint.id, btn.dataset.status));
  });

  const classifyBtn = el.detailModal.querySelector("#detail-classify-btn");
  if (classifyBtn) {
    classifyBtn.addEventListener("click", async () => {
      await classifyComplaint(complaint.id, classifyBtn);
      openDetailModal(complaint.id);
    });
  }

  el.detailModal.querySelectorAll(".issue-card").forEach(card => {
    const saveBtn = card.querySelector(".ov-save-btn");
    if (!saveBtn) return;
    saveBtn.addEventListener("click", () => {
      const classificationId = card.dataset.classificationId;
      const payload = {
        category: card.querySelector(".ov-category").value,
        urgency: card.querySelector(".ov-urgency").value,
        routed_team: card.querySelector(".ov-team").value,
        is_noise: card.querySelector(".ov-noise").value === "true",
      };
      overrideClassification(classificationId, payload).then(() => openDetailModal(complaint.id));
    });
  });

  el.detailOverlay.hidden = false;
  el.detailOverlay.classList.add("active");
}

function closeDetailModal() {
  el.detailOverlay.classList.remove("active");
  el.detailOverlay.hidden = true;
  el.detailModal.innerHTML = "";
}





/* ============================================================
   # INGEST MODAL
   ============================================================ */
function openIngestModal() {
  el.ingestForm.reset();
  el.ingestError.hidden = true;
  el.ingestOverlay.hidden = false;
  el.ingestOverlay.classList.add("active");
}
function closeIngestModal() {
  el.ingestOverlay.classList.remove("active");
  el.ingestOverlay.hidden = true;
}

el.ingestForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  el.ingestError.hidden = true;
  el.ingestSubmit.disabled = true;
  el.ingestSubmit.textContent = "Ingesting…";

  const payload = {
    channel: document.getElementById("in-channel").value,
    complainant_type: document.getElementById("in-complainant-type").value,
    customer_identifier: document.getElementById("in-customer-id").value.trim(),
    raw_message: document.getElementById("in-message").value.trim(),
  };
  const classifyNow = document.getElementById("in-classify-now").checked;

  try {
    const complaint = await apiFetch("/complaints/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (classifyNow) {
      el.ingestSubmit.textContent = "Classifying via Groq…";
      try {
        await apiFetch(`/complaints/${complaint.id}/classify`, { method: "POST" });
      } catch (err) {
        showToast(`Ingested, but classification failed: ${err.message}`, "error");
      }
    }
    showToast("Complaint ingested.", "success");
    closeIngestModal();
    await refreshAll();
  } catch (err) {
    el.ingestError.textContent = err.message;
    el.ingestError.hidden = false;
  } finally {
    el.ingestSubmit.disabled = false;
    el.ingestSubmit.textContent = "Ingest complaint";
  }
});

/* ============================================================
   # EVENT WIRING
   ============================================================ */
el.btnOpenIngest.addEventListener("click", openIngestModal);
el.ingestClose.addEventListener("click", closeIngestModal);
el.ingestCancel.addEventListener("click", closeIngestModal);
el.ingestOverlay.addEventListener("click", (e) => { if (e.target === el.ingestOverlay) closeIngestModal(); });

el.detailOverlay.addEventListener("click", (e) => { if (e.target === el.detailOverlay) closeDetailModal(); });

el.btnClassifyAll.addEventListener("click", classifyAllUnclassified);

el.filterStatus.addEventListener("change", (e) => { state.filters.status = e.target.value; loadQueue(); });
el.filterTeam.addEventListener("change", (e) => { state.filters.team = e.target.value; loadQueue(); });
el.filterUrgency.addEventListener("change", (e) => { state.filters.urgency = e.target.value; loadQueue(); });
el.filterNoise.addEventListener("change", (e) => { state.showNoise = e.target.checked; loadQueue(); });

el.btnResetFilters.addEventListener("click", () => {
  state.filters = { status: "", team: "", urgency: "" };
  state.showNoise = false;
  el.filterStatus.value = "";
  el.filterTeam.value = "";
  el.filterUrgency.value = "";
  el.filterNoise.checked = false;
  loadQueue();
});

el.viewToggleBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    el.viewToggleBtns.forEach(b => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    state.view = btn.dataset.view;
    loadQueue();
  });
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeIngestModal(); closeDetailModal(); }
});

/* ============================================================
   # BOOTSTRAP
   ============================================================ */
async function refreshAll() {
  await Promise.all([loadStats(), loadQueue()]);
}

(async function init() {
  await checkApiHealth();
  await refreshAll();
  setInterval(checkApiHealth, 15000);
})();