/* 静态页壳行为（无构建链——原生 fetch；UI 永远是薄壳，API 契约先行）。 */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const CFG_KEY = "lattice.cfg";
const state = { token: "", org: "", view: "upload", dims: [], picked: {}, docId: null, taskId: null };

/* ---------- 配置 ---------- */
function loadCfg() {
  try {
    const cfg = JSON.parse(localStorage.getItem(CFG_KEY) || "{}");
    state.token = cfg.token || "";
    state.org = cfg.org || "";
  } catch (e) { /* ignore */ }
  $("#cfgToken").value = state.token;
  $("#cfgOrg").value = state.org;
}
function saveCfg() {
  state.token = $("#cfgToken").value.trim();
  state.org = $("#cfgOrg").value.trim();
  localStorage.setItem(CFG_KEY, JSON.stringify({ token: state.token, org: state.org }));
  loadMeta(); // 重连后刷新知识库/维度
}

function api(path, opts) {
  const headers = Object.assign(
    { Authorization: "Bearer " + (state.token || "") },
    state.org ? { "X-Org-Id": state.org } : {},
    (opts && opts.headers) || {}
  );
  return fetch(path, Object.assign({}, opts, { headers }));
}

/* ---------- 元数据（datasets / dimensions——上传表单与检索过滤） ---------- */
async function loadMeta() {
  if (!state.token || !state.org) return;
  try {
    const [dsRes, dimRes] = await Promise.all([
      api(`/api/orgs/${encodeURIComponent(state.org)}/datasets`).then((r) => r.json()),
      api(`/api/orgs/${encodeURIComponent(state.org)}/dimensions`).then((r) => r.json()),
    ]);
    const dsSel = $("#upDataset");
    dsSel.innerHTML = "";
    (dsRes.datasets || []).forEach((d) => {
      const o = document.createElement("option");
      o.value = d.id; o.textContent = `${d.name}（${d.id}）`;
      dsSel.appendChild(o);
    });
    const qDs = $("#qDataset");
    qDs.innerHTML = "";
    const all = document.createElement("option");
    all.value = ""; all.setAttribute("data-i18n", "search.all"); all.textContent = t("search.all");
    qDs.appendChild(all);
    (dsRes.datasets || []).forEach((d) => {
      const o = document.createElement("option");
      o.value = d.id; o.textContent = `${d.name}（${d.id}）`;
      qDs.appendChild(o);
    });
    state.dims = dimRes.dimensions || [];
    renderDimChips();
  } catch (e) {
    console.warn("loadMeta failed", e);
  }
}

function renderDimChips() {
  const box = $("#upDims");
  box.innerHTML = "";
  state.dims.forEach((dim) => {
    const g = document.createElement("div");
    g.className = "dim-group";
    const label = document.createElement("div");
    label.className = "dim-label";
    label.textContent = `${dim.name}（${dim.key}）${dim.required ? " · " + t("upload.required") : ""}`;
    g.appendChild(label);
    (dim.values || []).forEach((v) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip" + (isPicked(dim.key, v.value) ? " on" : "");
      chip.textContent = `${v.label}（${v.value}）`;
      chip.onclick = () => togglePick(dim.key, v.value, chip);
      g.appendChild(chip);
    });
    box.appendChild(g);
  });
}
function isPicked(key, value) { return (state.picked[key] || []).includes(value); }
function togglePick(key, value, chip) {
  const list = state.picked[key] || [];
  const i = list.indexOf(value);
  if (i >= 0) list.splice(i, 1); else list.push(value);
  state.picked[key] = list;
  chip.classList.toggle("on", i < 0);
}

/* ---------- 上传 ---------- */
async function upload() {
  const file = $("#upFile").files[0];
  if (!file) { $("#upMsg").textContent = t("upload.file.required"); return; }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("dataset", $("#upDataset").value);
  fd.append("dims", JSON.stringify(state.picked));
  $("#upMsg").textContent = "…";
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/documents`, { method: "POST", body: fd });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    $("#upMsg").textContent = `${resp.status}: ${body.error || resp.statusText}`;
    return;
  }
  state.docId = body.doc_id; state.taskId = body.task_id;
  $("#upMsg").textContent = t("upload.ok");
  $("#upStatus").hidden = false;
  refreshStatus();
}

async function refreshStatus() {
  if (!state.docId) return;
  const [docRes, taskRes] = await Promise.all([
    api(`/api/orgs/${encodeURIComponent(state.org)}/documents/${state.docId}`),
    api(`/api/orgs/${encodeURIComponent(state.org)}/tasks/${state.taskId}`),
  ]);
  const doc = await docRes.json().catch(() => ({}));
  const task = await taskRes.json().catch(() => ({}));
  const kv = $("#upStatusKv");
  kv.innerHTML = [
    [t("status.doc"), esc(state.docId)],
    [t("status.active"), `v${doc.active_version ?? "-"} · ${esc(doc.active_status ?? "-")}${doc.active_error ? " · " + esc(doc.active_error) : ""}`],
    [t("status.pending"), doc.pending_version ? `v${doc.pending_version} · ${esc(doc.pending_status)}` : "—"],
    [t("status.task"), `${esc(task.status ?? "-")}（${t("status.attempts")} ${task.attempts ?? 0}）${task.error ? " · " + esc(task.error) : ""}`],
  ].map(([k, v]) => `<dt>${k}</dt><dd class="mono">${v}</dd>`).join("");
}

/* ---------- 检索 ---------- */
async function doSearch() {
  const q = $("#qInput").value.trim();
  if (!q) return;
  const payload = { query: q, top_k: 8 };
  if ($("#qDataset").value) payload.datasets = [$("#qDataset").value];
  const resp = await api("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.status === 403) {
    $("#hitsTable").hidden = true; $("#hitsEmpty").hidden = false;
    $("#searchMsg").textContent = t("search.denied");
    return;
  }
  const body = await resp.json().catch(() => ({ results: [] }));
  const rows = body.results || [];
  $("#searchMsg").textContent = `${rows.length} ${t("search.results")}` +
    ((body.notice && body.notice.degraded && body.notice.degraded.length)
      ? ` · ${t("search.degraded")}: ${body.notice.degraded.join(",")}` : "");
  $("#hitsTable").hidden = rows.length === 0;
  $("#hitsEmpty").hidden = rows.length > 0;
  $("#hitsBody").innerHTML = rows.map((r) => `<tr>
      <td>${r.rank}</td>
      <td class="mono tiny">${esc(r.chunk_id)}</td>
      <td><b>${esc(r.title ?? r.doc_id)}</b><div class="tiny muted mono">${esc(r.doc_id)}</div></td>
      <td class="tiny">${esc(r.sheet_name ?? r.page_no ?? "—")}</td>
      <td class="mono">${r.score}</td>
      <td class="tiny">${esc(Object.entries(r.dims || {}).map(([k, v]) => k + "=" + v.join("/")).join(" ") || "—")}</td>
      <td class="tiny mono">${esc(r.source ?? "—")}</td>
    </tr>`).join("");
}

/* ---------- 视图切换 / 语言切换 / 装配 ---------- */
function switchView(view) {
  state.view = view;
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + view));
}

document.addEventListener("DOMContentLoaded", () => {
  // 语言初始化：默认中文 + localStorage 持久化（TC-UI-01）
  setLang(currentLang());
  document.querySelectorAll("#langSwitch button").forEach((b) => {
    b.addEventListener("click", () => setLang(b.dataset.lang));
  });
  document.addEventListener("langchange", () => {
    renderDimChips(); // chips 内的动态文案随语言重渲染
  });

  loadCfg();
  document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $("#cfgSave").addEventListener("click", saveCfg);
  $("#upSubmit").addEventListener("click", upload);
  $("#upRefresh").addEventListener("click", refreshStatus);
  $("#qGo").addEventListener("click", doSearch);
  $("#qInput").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.isComposing) doSearch(); });
  if (state.token && state.org) loadMeta();
});
