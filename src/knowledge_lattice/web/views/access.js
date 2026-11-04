/* views/access.js —— 权限（ui-1 功能平移，逻辑等价自旧薄壳 app.js，新设计系统样式）：
 * - 授权子标签：loadGrants/renderGrantChips/_rowExpiresInput/saveGrants/downloadCsv/
 *   importCsv 平移——含 B① 逐行独立 expires 语义（每行 input 唯一真值源
 *   accessState.g.expires，初始值=库内值，未编辑保存即沿用）。
 * - 维度子标签：loadGovernanceDims/askDisableValue/askRetireDim/runConfirmed 平移
 *   ——取值停用 dry_run 影响面→确认 / 恢复（会话记忆已停用值）/ 取值新增（真实端点）/
 *   维度退役（影响面→确认）/ 新建维度（m3-1 contract-first，404 降级）。 */
"use strict";

/* ---------- 授权子标签（平移） ---------- */

async function loadGrantsTable() {
  state.loading.grants = true;
  try {
    const text = await exportGrants(cfg.org);
    const lines = text.trim().split(/\r?\n/);
    state.g.rows = lines.length > 1
      ? lines.slice(1).filter((l) => l.trim()).map((l) => {
          // 引号形态 CSV 单行解析（值含逗号不错位）——parseCsvLine 见 app.js
          const cols = parseCsvLine(l);
          return { username: cols[0], dimKey: cols[1], value: cols[2], expiresAt: cols[3] || "" };
        })
      : [];
    state.usernames = [...new Set(state.g.rows.map((r) => r.username))].sort();
    if (!state.g.member || !state.usernames.includes(state.g.member)) {
      state.g.member = state.usernames[0] || "";
    }
    seedGrantEditor();
  } catch (e) {
    state.g.rows = []; // 403 非 org_admin——提示在视图内展示（api.js 已 toast）
  } finally {
    state.loading.grants = false;
  }
}

/* 既有 expires 映射（chip 徽标 + 行内输入框初始值）；缺省（成员切换/装载）重置为装载态 */
function seedGrantEditor(preserve = false) {
  const mine = state.g.rows.filter((r) => r.username === state.g.member);
  state.g.existing = {};
  mine.forEach((r) => { state.g.existing[`${r.dimKey}=${r.value}`] = r.expiresAt; });
  if (!preserve) {
    state.g.picked = { ...state.g.existing };
    state.g.expires = { ...state.g.existing }; // 行内初始值=库内值（未编辑即沿用——B①）
  }
}

function grantsHTML() {
  const g = state.g;
  if (state.loading.grants) return loadingHTML("access");
  if (!isAdmin()) return `<div class="note amber">${t("access.grants.needAdmin")}</div>`;
  if (!g.rows.length) return `<div class="empty" style="margin:0"><h3>${esc(t("access.grants.empty.title"))}</h3><p>${t("access.grants.empty.body")}</p></div>`;
  return `
  <div class="toolbar">
    <label class="tiny muted">${esc(t("access.member"))}</label>
    <select class="sel" data-in="gMember" style="min-width:200px">${g.rows.length
      ? [...new Set(g.rows.map((r) => r.username))].sort().map((m) => `<option value="${esc(m)}" ${g.member === m ? "selected" : ""}>${esc(m)}</option>`).join("")
      : `<option value="">${esc(t("access.grants.none"))}</option>`}</select>
    <label class="tiny muted">${esc(t("access.expires.prefill"))}</label>
    <input class="inp" data-in="gPrefill" style="width:220px" placeholder="${esc(t("access.expires.ph"))}" value="${esc(g.prefill)}">
    <span class="tiny muted">${esc(t("access.expires.prefillNote"))}</span>
  </div>
  ${state.dims.map((dim) => {
    return `<div class="upload" style="margin-bottom:12px;padding:14px 18px;grid-template-columns:1fr">
      <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
        <b>${esc(dim.name)}</b><span class="tiny muted mono">${esc(dim.key)}</span>
        ${dim.required ? `<span class="tag">${esc(t("common.required"))}</span>` : ""}
      </div>
      <div class="chips" style="margin-top:8px">${(dim.values || []).map((v) => {
        const key = `${dim.key}=${v.value}`;
        const on = key in g.picked;
        const existing = g.existing[key];
        return `<span style="display:inline-flex;gap:6px;align-items:center">
          <button class="vchip ${on ? "on" : ""}" data-act="gCell" data-k="${esc(key)}" title="${existing ? esc(t("access.expires.existing")) + ": " + esc(existing) : ""}">${esc(v.label)}<span class="vx">${esc(v.value)}</span></button>
          ${on ? `<input class="chip-exp" data-in="gExp" data-id="${esc(key)}" placeholder="${esc(t("access.expires.rowPh"))}" value="${esc(g.expires[key] || "")}" title="${esc(t("access.expires.rowTitle"))}">` : ""}
        </span>`;
      }).join("")}</div>
    </div>`;
  }).join("")}
  <div class="inline-act" style="margin-top:4px">
    <button class="btn seal-btn" data-act="gSave">${esc(t("access.save"))}</button>
    <span class="tiny muted">${esc(t("access.save.note"))}</span>
  </div>
  <section class="pane" style="margin-top:20px">
    <div class="lane-h"><h3>${esc(t("access.csv.title"))}</h3><span class="tiny muted">${t("access.csv.hint")}</span></div>
    <div class="inline-act" style="margin-bottom:8px">
      <button class="btn ghost sm" data-act="gExport">${esc(t("access.export"))}</button>
    </div>
    <textarea class="csv-box" data-in="gCsv" placeholder="username,dim_key,value,expires_at">${esc(g.csv)}</textarea>
    <div class="inline-act" style="margin-top:8px">
      <button class="btn sm" data-act="gCsvDry">${esc(t("access.csv.dryrun"))}</button>
      <button class="btn seal-btn sm" data-act="gCsvApply">${esc(t("access.csv.apply"))}</button>
      <span class="tiny muted" id="csvMsg">${esc(g.diffMsg || "")}</span>
    </div>
    ${g.diff ? `<pre class="diff-box">${esc(JSON.stringify(g.diff, null, 2))}</pre>` : ""}
  </section>`;
}

/* ---------- 维度子标签（平移） ---------- */

async function loadGovernanceDims() {
  state.loading.govDims = true;
  try {
    const body = await listDimensions(cfg.org);
    state.dims = body.dimensions || [];
  } finally {
    state.loading.govDims = false;
  }
}

function dimsHTML() {
  if (state.loading.govDims) return loadingHTML("access");
  if (!state.dims.length) return `<div class="empty" style="margin:0"><h3>${esc(t("access.dims.empty"))}</h3></div>`;
  const canEdit = isAdmin();
  return `
  ${canEdit ? `<div style="margin-bottom:12px"><button class="btn ghost sm" data-act="dimNewToggle">${state.dimNewOpen ? esc(t("common.collapse")) : esc(t("access.dims.new"))}</button></div>${state.dimNewOpen ? dimNewHTML() : ""}` : ""}
  ${state.govAsk ? govConfirmHTML() : ""}
  <table class="ledger dims-ledger">
    <thead><tr><th>${esc(t("access.dims.col.dim"))}</th><th>${esc(t("access.dims.col.required"))}</th><th>${esc(t("access.dims.col.values"))}</th><th></th></tr></thead>
    <tbody>${state.dims.map((dim) => `<tr>
      <td><div class="t-title">${esc(dim.name)}</div><div class="t-sub mono">${esc(dim.key)}</div></td>
      <td>${dim.required ? esc(t("common.yes")) : `<span class="muted">${esc(t("common.no"))}</span>`}<div class="tiny muted">${esc(t("access.dims.reqNote"))}</div></td>
      <td><div class="vals" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">
        ${(dim.values || []).map((v) => `<span style="display:inline-flex;gap:4px;align-items:center">
          <span class="chip d${dimIdx(dim.key)}" title="${esc(v.value)}">${esc(v.label)} <span class="ck">${esc(v.value)}</span></span>
          ${canEdit ? `<button class="link tiny" data-act="valOff" data-dim="${esc(dim.id)}" data-id="${esc(v.id)}" data-v="${esc(v.value)}" title="${esc(t("access.dims.disable.hint"))}">${esc(t("access.dims.disable"))}</button>` : ""}
        </span>`).join("") || `<span class="tiny muted">—</span>`}
        ${(state.disabledVals || []).filter((x) => x.dimId === dim.id).map((x) => `<span style="display:inline-flex;gap:4px;align-items:center">
          <span class="chip v-off" title="${esc(x.value)} · ${esc(t("access.dims.disabledTip"))}">${esc(x.label || x.value)}</span>
          ${canEdit ? `<button class="link tiny" data-act="valOn" data-dim="${esc(dim.id)}" data-id="${esc(x.id)}" data-v="${esc(x.value)}" title="${esc(t("access.dims.enable.hint"))}">${esc(t("access.dims.enable"))}</button>` : ""}
        </span>`).join("")}
        ${canEdit ? (state.valAsk === dim.id
          ? `<input class="inp" data-in="valKey" placeholder="value" style="height:26px;width:96px;font-family:var(--mono)" value="${esc(state.valNew.v)}"><input class="inp" data-in="valLabel" placeholder="${esc(t("access.dims.valLabelPh"))}" style="height:26px;width:96px" value="${esc(state.valNew.l)}"><button class="btn sm" data-act="valAdd" data-dim="${esc(dim.id)}" title="POST /dimensions/${esc(dim.id)}/values">${esc(t("common.add"))}</button>`
          : `<button class="vchip" data-act="valAsk" data-dim="${esc(dim.id)}" title="POST /dimensions/${esc(dim.id)}/values">＋ ${esc(t("access.dims.addValue"))}</button>`) : ""}
      </div></td>
      <td>${canEdit ? `<button class="btn ghost sm" data-act="dimRetire" data-dim="${esc(dim.id)}" data-key="${esc(dim.key)}">${esc(t("access.dims.retire"))}</button>` : ""}</td>
    </tr>`).join("")}</tbody>
  </table>
  <div class="legend" style="margin-top:12px">
    <span class="lg">${t("access.dims.legend.req")}</span>
    <span class="lg">${t("access.dims.legend.filter")}</span>
    <span class="lg">${t("access.dims.legend.disable")}</span>
    <span class="lg">${t("access.dims.legend.restore")}</span>
  </div>`;
}

function dimNewHTML() {
  const d = state.dimNew;
  const ok = d.key.trim().length > 0 && d.name.trim().length > 0;
  return `<div class="upload" style="margin-bottom:16px">
    <div style="grid-column:1/-1"><b style="font-size:15px">${esc(t("access.dims.new"))}</b>
      <span class="tiny muted">—— ${t("access.dims.new.note")}</span></div>
    <div class="u-row"><label>key<span class="req">*</span></label>
      <input class="inp" data-in="dimKey" placeholder="region / biz_line" value="${esc(d.key)}" style="font-family:var(--mono)"></div>
    <div class="u-row"><label>${esc(t("access.dims.col.name"))}<span class="req">*</span></label>
      <input class="inp" data-in="dimName" placeholder="${esc(t("access.dims.namePh"))}" value="${esc(d.name)}"></div>
    <div class="u-row"><label>${esc(t("access.dims.col.required"))}</label>
      <label class="switch"><input type="checkbox" data-in="dimReq" ${d.required ? "checked" : ""}><span class="tiny muted">${esc(t("access.dims.reqNote"))}</span></label></div>
    <div class="u-foot">
      <button class="btn seal-btn" data-act="dimCreate" ${ok ? "" : "disabled"}>${esc(t("common.create"))}</button>
      <button class="btn ghost" data-act="dimNewToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny ${ok ? "" : "muted"}">${ok ? esc(t("access.dims.new.ok")) : esc(t("access.dims.new.need"))}</span>
      <span style="flex:1"></span>
      <span class="tiny muted">${t("access.dims.new.foot")}</span>
    </div></div>`;
}

function govConfirmHTML() {
  const a = state.govAsk;
  const imp = a.impact || {};
  const impactText = a.type === "disable"
    ? `${t("access.dims.impact.docs")}: <b>${esc(imp.docs ?? "—")}</b> · ${t("access.dims.impact.grants")}: <b>${esc(imp.grants ?? "—")}</b> · ${t("access.dims.impact.users")}: <b>${esc(imp.users ?? "—")}</b> · ${t("access.dims.impact.locked")}: <b>${esc(imp.locked_docs ?? "—")}</b>`
    : `${t("access.dims.impact.docs")}: <b>${esc(imp.docs ?? "—")}</b> · ${t("access.dims.impact.grants")}: <b>${esc(imp.grants ?? "—")}</b> · ${t("access.dims.impact.values")}: <b>${esc(imp.values ?? "—")}</b>`;
  const title = a.type === "disable"
    ? t("access.dims.disable.ask", { value: a.value })
    : t("access.dims.retire.ask", { key: a.dimKey });
  return `<div class="confirm"><b>${title}</b> ${a.type === "disable" ? t("access.dims.disable.body") : t("access.dims.retire.body")}
    <div>${impactText}</div>
    <div class="cf-act">
      <button class="btn danger-btn sm" data-act="govOk">${esc(t("common.confirm"))}</button>
      <button class="btn ghost sm" data-act="govCancel">${esc(t("common.cancel"))}</button>
      <span class="tiny muted" style="align-self:center">${a.type === "disable"
        ? `<code>PATCH /dimensions/${esc(a.dimId)}/values/${esc(a.valueId)}</code>`
        : `<code>POST /dimensions/${esc(a.dimId)}/retire?confirm=1</code>`}</span>
    </div></div>`;
}

/* ---------- 视图装配 ---------- */

function viewAccess() {
  if (!connected()) return connGate();
  const sub = state.sub.access;
  return `
  <header class="head"><h1>${esc(t("access.title"))}</h1>
    <p class="lede">${t("access.lede")}</p>
  </header>
  <nav class="sub-tabs">
    <button class="sub-tab ${sub === "grants" ? "on" : ""}" data-act="sub" data-s="access" data-v="grants">${esc(t("access.tab.grants"))}</button>
    <button class="sub-tab ${sub === "dims" ? "on" : ""}" data-act="sub" data-s="access" data-v="dims">${esc(t("access.tab.dims"))}</button>
  </nav>
  ${!isAdmin() ? `<div class="note amber" style="margin-bottom:16px">${t("access.readonly", { user: esc(lensUser()) })}</div>` : ""}
  ${sub === "grants" ? grantsHTML() : dimsHTML()}`;
}

async function onEnterAccess() {
  if (!connected()) return;
  if (state.sub.access === "grants") {
    if (isAdmin() && !state.g.rows.length && !state.loading.grants) {
      await loadGrantsTable();
    }
  } else if (!state.dims.length && !state.loading.govDims) {
    await loadGovernanceDims();
  }
}

/* ---------- 动作与输入 ---------- */

function downloadCsv(text) {
  const blob = new Blob([text], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `grants-${cfg.org}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

Object.assign(actions, {
  /* ----- 授权格（平移） ----- */
  gCell(el) {
    const key = el.dataset.k;
    if (key in state.g.picked) {
      delete state.g.picked[key];
      delete state.g.expires[key];
    } else {
      state.g.picked[key] = "";
      // 新选行预填：全局输入框值优先（显式意图），否则库内既有值
      state.g.expires[key] = state.g.prefill.trim() || state.g.existing[key] || "";
    }
  },
  async gSave() {
    const member = state.g.member;
    if (!member) return false;
    // B①：逐行独立 expires——每行取自身输入框值（初始值=库内值；空=永久）
    const grants = Object.keys(state.g.picked).map((k) => {
      const [dimKey, value] = k.split("=");
      const expires = state.g.expires[k] ?? state.g.existing[k] ?? "";
      return { dim_key: dimKey, value, expires_at: expires || null };
    });
    try {
      const res = await putGrants(cfg.org, member, grants);
      toast(t("access.saved", { removed: res.removed, inserted: res.inserted }));
    } catch (e) { errToast(e); return false; }
    await loadGrantsTable();
    render();
    return false;
  },
  async gExport() {
    try {
      const text = await exportGrants(cfg.org);
      downloadCsv(text);
    } catch (e) { errToast(e); }
    return false;
  },
  async gCsvDry() { return importCsvRun(true); },
  async gCsvApply() { return importCsvRun(false); },

  /* ----- 维度治理（平移） ----- */
  dimNewToggle() { state.dimNewOpen = !state.dimNewOpen; },
  async dimCreate() {
    const d = state.dimNew;
    const key = d.key.trim(), name = d.name.trim();
    if (!key || !name) return false;
    let body;
    try {
      // m3-1 contract-first：POST dimensions 未实装——404 降级提示
      body = await createDimension(cfg.org, { key, name, required: !!d.required });
    } catch (e) {
      if (e.status === 404) toast(t("degrade.m31"));
      else errToast(e);
      return false;
    }
    state.dimNewOpen = false;
    state.dimNew = { key: "", name: "", required: false };
    toast(t("access.dims.created", { key: esc(key) }));
    await loadGovernanceDims();
    render();
    return false;
  },
  valAsk(el) {
    const dim = el.dataset.dim;
    state.valAsk = state.valAsk === dim ? null : dim;
    state.valNew = { v: "", l: "" };
  },
  async valAdd(el) {
    const dimId = el.dataset.dim;
    const v = state.valNew.v.trim(), l = state.valNew.l.trim();
    if (!v) { toast(esc(t("access.dims.valNeed"))); return false; }
    try {
      await createValue(cfg.org, dimId, { value: v, label: l || null }); // retired 409 → api 统一语义
    } catch (e) {
      if (e.status === 409) toast(t("access.dims.val409", { v: esc(v) }));
      else errToast(e);
      return false;
    }
    state.valNew = { v: "", l: "" };
    toast(t("access.dims.valAdded", { v: esc(v) }));
    await loadGovernanceDims();
    render();
    return false;
  },
  async valOff(el) {
    const dimId = el.dataset.dim, valueId = el.dataset.id, value = el.dataset.v;
    let body;
    try {
      body = await patchValueStatus(cfg.org, dimId, valueId, { status: "disabled", dry_run: true });
    } catch (e) { errToast(e); return false; }
    state.govAsk = { type: "disable", dimId, valueId, value, impact: body.impact };
    render();
    return false;
  },
  async valOn(el) {
    const dimId = el.dataset.dim, valueId = el.dataset.id;
    try {
      await patchValueStatus(cfg.org, dimId, valueId, { status: "active" }); // D19 恢复路径
    } catch (e) { errToast(e); return false; }
    state.disabledVals = (state.disabledVals || []).filter((x) => x.id !== valueId);
    toast(t("access.dims.enabled"));
    await loadGovernanceDims();
    render();
    return false;
  },
  async dimRetire(el) {
    const dimId = el.dataset.dim, dimKey = el.dataset.key;
    let body;
    try {
      body = await retireDimension(cfg.org, dimId, false); // 无 confirm = 影响面预估
    } catch (e) { errToast(e); return false; }
    state.govAsk = { type: "retire", dimId, dimKey, impact: body.impact };
    render();
    return false;
  },
  govCancel() { state.govAsk = null; },
  async govOk() {
    const a = state.govAsk;
    if (!a) return false;
    state.govAsk = null;
    try {
      if (a.type === "disable") {
        await patchValueStatus(cfg.org, a.dimId, a.valueId, { status: "disabled" });
        const dim = state.dims.find((d) => d.id === a.dimId);
        const val = dim && (dim.values || []).find((v) => v.id === a.valueId);
        state.disabledVals = state.disabledVals || [];
        state.disabledVals.push({ dimId: a.dimId, id: a.valueId, value: a.value, label: val ? val.label : a.value });
        toast(t("access.dims.disabled", { v: esc(a.value) }));
      } else {
        await retireDimension(cfg.org, a.dimId, true);
        toast(t("access.dims.retired", { key: esc(a.dimKey) }));
      }
    } catch (e) { errToast(e); }
    await loadGovernanceDims();
    render();
    return false;
  },
});

async function importCsvRun(dryRun) {
  const text = state.g.csv.trim();
  if (!text) { toast(esc(t("access.csv.empty"))); return false; }
  let body;
  try {
    body = await importGrants(cfg.org, text, dryRun);
  } catch (e) { errToast(e); return false; }
  if (dryRun) {
    const d = body.diff;
    state.g.diff = d;
    state.g.diffMsg = t("access.csv.diffMsg", { a: d.added.length, r: d.removed.length, c: d.changed.length, j: (body.rejected || []).length });
  } else {
    state.g.diff = null;
    state.g.diffMsg = "";
    toast(t("access.csv.applied", { users: body.applied_users, rejected: (body.rejected || []).length }));
    await loadGrantsTable();
  }
  render();
  return false;
}

Object.assign(INPUTS, {
  gMember: (v) => { state.g.member = v; seedGrantEditor(); },
  gPrefill: (v) => { state.g.prefill = v; },
  gExp: (v, el) => { state.g.expires[el.dataset.id] = v.trim(); return false; },
  gCsv: (v) => { state.g.csv = v; return false; },
  dimKey: (v) => { state.dimNew.key = v; },
  dimName: (v) => { state.dimNew.name = v; },
  dimReq: (v) => { state.dimNew.required = v; },
  valKey: (v) => { state.valNew.v = v; },
  valLabel: (v) => { state.valNew.l = v; },
});

VIEWS.access = { render: viewAccess, onEnter: onEnterAccess };

/* 子标签切换也走懒装载（onEnter 只覆盖整视图进入——首切「授权」时补载） */
const _subBase = actions.sub;
actions.sub = (el) => {
  _subBase(el);
  if (el.dataset.s === "access" && el.dataset.v === "grants"
      && isAdmin() && !state.g.rows.length && !state.loading.grants) {
    loadGrantsTable().then(() => render()).catch(() => { /* 已 toast */ });
  }
};
