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
      o.value = d.id; o.textContent = `${d.name} (${d.id})`;
      dsSel.appendChild(o);
    });
    const qDs = $("#qDataset");
    qDs.innerHTML = "";
    const all = document.createElement("option");
    all.value = ""; all.setAttribute("data-i18n", "search.all"); all.textContent = t("search.all");
    qDs.appendChild(all);
    (dsRes.datasets || []).forEach((d) => {
      const o = document.createElement("option");
      o.value = d.id; o.textContent = `${d.name} (${d.id})`;
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
    label.textContent = `${dim.name} (${dim.key})${dim.required ? " · " + t("upload.required") : ""}`;
    g.appendChild(label);
    (dim.values || []).forEach((v) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip" + (isPicked(dim.key, v.value) ? " on" : "");
      chip.textContent = `${v.label} (${v.value})`;
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
    [t("status.task"), `${esc(task.status ?? "-")}(${t("status.attempts")} ${task.attempts ?? 0})${task.error ? " · " + esc(task.error) : ""}`],
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

/* ---------- 权限视图（m2-3：grants 管理 / CSV 导入导出 / expires_at） ---------- */

const accessState = { rows: [], members: [], picked: {}, expires: {}, fresh: new Set() };
// fresh：用户本轮显式（重）选中的 key 集——保存时应用输入框 expires；
// 未动过的既有 key（picked 值来自装载原值）沿用库内 expires（R3 P2-2）

async function loadGrants() {
  if (!state.token || !state.org) return;
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/grants/export`);
  if (!resp.ok) { $("#gMsg").textContent = `${resp.status}`; return; }
  const lines = (await resp.text()).trim().split(/\r?\n/);
  accessState.rows = lines.length > 1
    ? lines.slice(1).map((l) => {
        // P3-14/R2：引号形态 CSV 单行解析（值含逗号不错位——split(",") 弃用）
        const cols = l.match(/("([^"]|"")*"|[^,]*)(,|$)/g)
          .slice(0, 4)
          .map((c) => c.replace(/,$/, "").replace(/^"(.*)"$/, "$1").replace(/""/g, '"'));
        return { username: cols[0], dimKey: cols[1], value: cols[2],
                 expiresAt: cols[3] || "" };
      })
    : [];
  accessState.members = [...new Set(accessState.rows.map((r) => r.username))].sort();
  const sel = $("#gMember");
  sel.innerHTML = "";
  if (!accessState.members.length) {
    const o = document.createElement("option");
    o.setAttribute("data-i18n", "access.member.none");
    o.textContent = t("access.member.none");
    sel.appendChild(o);
    $("#gChips").innerHTML = `<span class="muted">${t("access.member.none")}</span>`;
    return;
  }
  accessState.members.forEach((m) => {
    const o = document.createElement("option");
    o.value = m; o.textContent = m;
    sel.appendChild(o);
  });
  renderGrantChips();
}

function renderGrantChips() {
  const member = $("#gMember").value;
  const box = $("#gChips");
  box.innerHTML = "";
  const mine = accessState.rows.filter((r) => r.username === member);
  accessState.picked = {};
  accessState.fresh.clear();  // 装载态=无用户改动（保存沿用库内 expires）
  mine.forEach((r) => { accessState.picked[`${r.dimKey}=${r.value}`] = r.expiresAt; });
  state.dims.forEach((dim) => {
    const g = document.createElement("div");
    g.className = "dim-group";
    const label = document.createElement("div");
    label.className = "dim-label";
    label.textContent = `${dim.name} (${dim.key})`;
    g.appendChild(label);
    (dim.values || []).forEach((v) => {
      const on = `${dim.key}=${v.value}` in accessState.picked;
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip" + (on ? " on" : "");
      chip.textContent = `${v.label} (${v.value})`;
      chip.onclick = () => {
        const key = `${dim.key}=${v.value}`;
        if (key in accessState.picked) {
          delete accessState.picked[key];
          accessState.fresh.delete(key);
        } else {
          accessState.picked[key] = $("#gExpires").value.trim();
          accessState.fresh.add(key);  // 显式新选——保存应用输入框值
        }
        chip.classList.toggle("on", key in accessState.picked);
      };
      g.appendChild(chip);
    });
    box.appendChild(g);
  });
}

async function saveGrants() {
  const member = $("#gMember").value;
  if (!member) return;
  // R3 P2-2：expires 语义——**未动过的既有 key 沿用库内值**（防静默清除既有
  // 临时授权）；仅**本轮显式（重）选中的 key** 应用输入框值（空=永久）。
  const expiresNow = $("#gExpires").value.trim();
  const grants = Object.keys(accessState.picked).map((k) => {
    const [dimKey, value] = k.split("=");
    const expires = accessState.fresh.has(k) ? expiresNow : (accessState.picked[k] || "");
    return { dim_key: dimKey, value, expires_at: expires || null };
  });
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/members/${encodeURIComponent(member)}/grants`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grants }),
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) { $("#gMsg").textContent = `${resp.status}: ${body.detail || body.error || ""}`; return; }
  $("#gMsg").textContent = t("access.saved", body);
  loadGrants();
}

function downloadCsv(text) {
  const blob = new Blob([text], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `grants-${state.org}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function importCsv(dryRun) {
  const text = $("#csvText").value.trim();
  if (!text) return;
  const resp = await api(
    `/api/orgs/${encodeURIComponent(state.org)}/grants/import${dryRun ? "?dry_run=1" : ""}`,
    { method: "POST", body: text }
  );
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) { $("#csvMsg").textContent = `${resp.status}: ${body.detail || body.error || ""}`; return; }
  if (dryRun) {
    const d = body.diff;
    $("#csvDiff").hidden = false;
    $("#csvDiff").textContent = JSON.stringify(d, null, 2);
    $("#csvMsg").textContent = `+${d.added.length} / -${d.removed.length} / ~${d.changed.length} / rejected ${body.rejected.length}`;
    return;
  }
  $("#csvDiff").hidden = true;
  $("#csvMsg").textContent = t("access.csv.applied", {
    users: body.applied_users, rejected: body.rejected.length,
  });
  loadGrants();
}

/* ---------- 维度治理视图（m2-3：停用 dry_run / 退役二次确认） ---------- */

const dimsState = { pending: null }; // {action: 'disable'|'retire', dim, value}

async function loadGovernanceDims() {
  await loadMeta();
  renderGovernanceDims();
}

function renderGovernanceDims() {
  const body = $("#dimsBody");
  body.innerHTML = "";
  const dims = state.dims || [];
  $("#dimsTable").hidden = dims.length === 0;
  $("#dimsEmpty").hidden = dims.length > 0;
  dims.forEach((dim) => {
    const tr = document.createElement("tr");
    const vals = (dim.values || []).map((v) => {
      const chip = document.createElement("span");
      chip.className = "chip d";
      chip.textContent = `${v.label} (${v.value})`;
      const btn = document.createElement("button");
      btn.className = "btn ghost sm";
      btn.textContent = t("dims.disable");
      btn.onclick = () => askDisableValue(dim, v);
      const wrap = document.createElement("span");
      wrap.className = "val-item";
      wrap.appendChild(chip); wrap.appendChild(btn);
      return wrap;
    });
    const retireBtn = document.createElement("button");
    retireBtn.className = "btn ghost sm";
    retireBtn.textContent = t("dims.retire");
    retireBtn.onclick = () => askRetireDim(dim);
    const cells = [
      `<td><b>${esc(dim.name)}</b><div class="tiny muted mono">${esc(dim.key)}</div></td>`,
      `<td>${dim.required ? t("upload.required") : "—"}</td>`,
    ];
    tr.innerHTML = cells.join("");
    const tdVals = document.createElement("td");
    vals.forEach((v) => tdVals.appendChild(v));
    tr.appendChild(tdVals);
    const tdAct = document.createElement("td");
    tdAct.appendChild(retireBtn);
    tr.appendChild(tdAct);
    body.appendChild(tr);
  });
}

async function askDisableValue(dim, v) {
  // dry_run 影响面 → 二次确认
  const resp = await api(
    `/api/orgs/${encodeURIComponent(state.org)}/dimensions/${encodeURIComponent(dim.id)}` +
    `/values/${encodeURIComponent(v.id)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "disabled", dry_run: true }) }
  );
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) { alert(`${resp.status}: ${body.detail || ""}`); return; }
  const imp = body.impact;
  showConfirm(
    t("dims.disable.ask", { value: v.value }),
    `${t("dims.impact.docs")}: ${imp.docs} · ${t("dims.impact.grants")}: ${imp.grants}` +
      ` · ${t("dims.impact.users")}: ${imp.users} · ${t("dims.impact.locked")}: ${imp.locked_docs}`,
    { action: "disable", dim, v }
  );
}

async function askRetireDim(dim) {
  const resp = await api(
    `/api/orgs/${encodeURIComponent(state.org)}/dimensions/${encodeURIComponent(dim.id)}/retire`,
    { method: "POST" }
  );
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) { alert(`${resp.status}: ${body.detail || ""}`); return; }
  const imp = body.impact;
  showConfirm(
    t("dims.retire.ask", { key: dim.key }),
    `${t("dims.impact.docs")}: ${imp.docs} · ${t("dims.impact.grants")}: ${imp.grants} · ${t("dims.impact.values")}: ${imp.values}`,
    { action: "retire", dim }
  );
}

function showConfirm(title, detail, pending) {
  dimsState.pending = pending;
  $("#dimsConfirmTitle").textContent = title;
  $("#dimsConfirmBody").textContent = detail;
  $("#dimsConfirm").hidden = false;
}

async function runConfirmed() {
  const p = dimsState.pending;
  if (!p) return;
  let resp;
  if (p.action === "disable") {
    resp = await api(
      `/api/orgs/${encodeURIComponent(state.org)}/dimensions/${encodeURIComponent(p.dim.id)}` +
      `/values/${encodeURIComponent(p.v.id)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "disabled" }) }
    );
  } else {
    resp = await api(
      `/api/orgs/${encodeURIComponent(state.org)}/dimensions/${encodeURIComponent(p.dim.id)}/retire?confirm=1`,
      { method: "POST" }
    );
  }
  $("#dimsConfirm").hidden = true;
  dimsState.pending = null;
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    alert(`${resp.status}: ${body.detail || ""}`);
  }
  loadGovernanceDims();
}

/* ---------- 任务与审计视图（m2-3：取消 / 重嵌入 / 覆盖率 / 审计 / stats） ---------- */

async function loadOps() {
  if (!state.token || !state.org) return; // 未连接早退（防 404 噪音）
  await Promise.all([loadTasks(), loadCoverage(), loadAudit(), loadStats()]);
}

async function loadTasks() {
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/tasks`);
  const body = await resp.json().catch(() => ({ tasks: [] }));
  const tasks = body.tasks || [];
  $("#tasksTable").hidden = tasks.length === 0;
  $("#tasksBody").innerHTML = tasks.map((task) => `<tr>
      <td class="mono tiny">${esc(task.task_id)}</td>
      <td class="tiny">${esc(task.type)}</td>
      <td class="mono tiny">${esc(task.doc_id ?? "—")}</td>
      <td class="tiny">${esc(task.status)}${(task.error || "").startsWith("cancelled:") ? ` · ${t("ops.cancelled")}` : ""}</td>
      <td class="tiny muted">${esc(task.error || "")}</td>
      <td>${["pending", "leased", "running"].includes(task.status)
        ? `<button class="btn ghost sm" data-cancel="${esc(task.task_id)}">${t("ops.cancel")}</button>` : ""}</td>
    </tr>`).join("");
  $("#tasksBody").querySelectorAll("[data-cancel]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/orgs/${encodeURIComponent(state.org)}/tasks/${b.dataset.cancel}/cancel`, { method: "POST" });
      loadTasks();
    };
  });
}

async function loadCoverage() {
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/embedding-coverage`);
  if (!resp.ok) { $("#covKv").innerHTML = `<dd>${resp.status}</dd>`; return; }
  const body = await resp.json();
  const pct = body.totals.total ? Math.round((body.totals.done / body.totals.total) * 1000) / 10 : 100;
  const reembed = body.reembed
    ? `${body.reembed.status} · ${body.reembed.done}/${body.reembed.total}`
    : "—";
  $("#covKv").innerHTML = [
    [t("ops.cover.model"), `<span class="mono">${esc(body.embed_model)}</span>`],
    [t("ops.cover.dim"), esc(body.dim)],
    [t("ops.cover.ratio"), `${body.totals.done}/${body.totals.total} (${pct}%)`],
    [t("ops.cover.progress"), esc(reembed)],
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  $("#covBars").innerHTML = (body.coverage || []).map((c) => {
    const p = c.total ? Math.round((c.done / c.total) * 100) : 100;
    return `<div class="fn-row">
      <span class="tiny">${esc(c.dataset_name)}</span>
      <div class="fn-bar"><span class="fb-ok" style="width:${p}%"></span></div>
      <span class="tiny mono">${c.done}/${c.total}</span>
    </div>`;
  }).join("");
}

async function enqueueReembed() {
  const docId = $("#reembedDoc").value.trim();
  if (!docId) return;
  const model = $("#reembedModel").value.trim();
  const q = model ? `?embed_model=${encodeURIComponent(model)}` : "";
  const resp = await api(
    `/api/orgs/${encodeURIComponent(state.org)}/documents/${encodeURIComponent(docId)}/reindex${q}`,
    { method: "POST" }
  );
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) { $("#reembedMsg").textContent = `${resp.status}: ${body.detail || ""}`; return; }
  $("#reembedMsg").textContent = t("ops.reembed.ok", { type: body.type, task: body.task_id });
  loadTasks(); loadCoverage();
}

async function loadAudit() {
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/audit?limit=50`);
  if (!resp.ok) { $("#auditEmpty").hidden = false; return; }
  const body = await resp.json();
  $("#auditScope").textContent = body.scope === "full" ? "" : t("ops.audit.metadata");
  const events = body.events || [];
  $("#auditTable").hidden = events.length === 0;
  $("#auditEmpty").hidden = events.length > 0;
  $("#auditBody").innerHTML = events.map((e) => `<tr>
      <td class="mono tiny">${esc(e.created_at ?? "")}</td>
      <td class="tiny">${esc(e.actor ?? "")}</td>
      <td class="tiny mono">${esc(e.action ?? "")}</td>
      <td class="tiny muted">${esc(e.detail_json ? String(e.detail_json).slice(0, 160) : "—")}</td>
    </tr>`).join("");
}

async function loadStats() {
  const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/stats`);
  if (!resp.ok) { $("#statsKv").innerHTML = ""; return; }
  const body = await resp.json();
  const m = body.maintenance || {};
  $("#statsKv").innerHTML = Object.entries(m).map(([k, v]) =>
    `<dt class="mono tiny">${esc(k)}</dt><dd class="tiny">${esc(typeof v === "object" ? JSON.stringify(v) : String(v))}</dd>`
  ).join("");
}

/* ---------- 视图切换 / 语言切换 / 装配 ---------- */
function switchView(view) {
  state.view = view;
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + view));
  if (view === "access") loadGrants();
  if (view === "dims") loadGovernanceDims();
  if (view === "ops") loadOps();
}

document.addEventListener("DOMContentLoaded", () => {
  // 语言初始化：默认中文 + localStorage 持久化（TC-UI-01）
  setLang(currentLang());
  document.querySelectorAll("#langSwitch button").forEach((b) => {
    b.addEventListener("click", () => setLang(b.dataset.lang));
  });
  document.addEventListener("langchange", () => {
    renderDimChips(); // chips 内的动态文案随语言重渲染
    renderGovernanceDims(); // 治理视图按钮文案
    if (state.view === "access" && accessState.members.length) renderGrantChips();
  });

  loadCfg();
  document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $("#cfgSave").addEventListener("click", saveCfg);
  $("#upSubmit").addEventListener("click", upload);
  $("#upRefresh").addEventListener("click", refreshStatus);
  $("#qGo").addEventListener("click", doSearch);
  $("#qInput").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.isComposing) doSearch(); });
  // 管理面三视图（m2-3）
  $("#gMember").addEventListener("change", renderGrantChips);
  $("#gSave").addEventListener("click", saveGrants);
  $("#grantsExport").addEventListener("click", async () => {
    const resp = await api(`/api/orgs/${encodeURIComponent(state.org)}/grants/export`);
    if (resp.ok) downloadCsv(await resp.text());
  });
  $("#csvDryRun").addEventListener("click", () => importCsv(true));
  $("#csvApply").addEventListener("click", () => importCsv(false));
  $("#dimsRefresh").addEventListener("click", loadGovernanceDims);
  $("#dimsConfirmOk").addEventListener("click", runConfirmed);
  $("#dimsConfirmCancel").addEventListener("click", () => {
    $("#dimsConfirm").hidden = true; dimsState.pending = null;
  });
  $("#opsRefresh").addEventListener("click", loadOps);
  $("#reembedGo").addEventListener("click", enqueueReembed);
  if (state.token && state.org) loadMeta();
});
