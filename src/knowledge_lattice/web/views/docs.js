/* views/docs.js —— 文档知识（ui-1）：知识库 seg + 文档列表（m3-1 be-① 实装
 * ——m3-2 ui-be 撤降级接真端点）/ multipart 上传抽屉 + 任务轮询 / 详情 pane
 * （版本双态·阶段进度·维度编辑·质检补标·删除·可见性解释卡〔m3-1 be-② 实装
 * ——自解释 GET explain，前端不演算 ACL——issue B5〕）+ org_admin visible 徽标列。
 * 视觉结构沿原型 v0.6 文档页（.upload/.seg/.ledger/.split/.pane）。 */
"use strict";

/* ---------- 数据装载 ---------- */

async function onEnterDocs() {
  if (!connected()) return;
  const ep = state.epoch; // P1-5
  if (!state.docs.probed) {
    state.loading.docsList = true;
    try {
      // be-① 已实装（GET documents——13 字段行 + total）：错误态如实展示
      const body = await listDocuments(cfg.org);
      if (ep !== state.epoch) return;
      state.docs.available = true;
      state.docs.list = body.documents || [];
      state.docs.loadError = null;
    } catch (e) {
      if (ep !== state.epoch) return;
      state.docs.available = false;
      state.docs.loadError = String(e.message || e); // 403/5xx 如实（不再 404 降级）
    } finally {
      if (ep === state.epoch) { state.docs.probed = true; state.loading.docsList = false; }
    }
  }
  if (state.selDoc) refreshSelectedDoc().catch((e) => { errToast(e); }); // 非 403（404 等）也要如实可见（ui-3 错误态盘点）
}

async function refreshSelectedDoc() {
  const ep = state.epoch; // P1-5
  const id = state.selDoc;
  const body = await getDocument(cfg.org, id); // 详情无 dims 字段——维度取列表行缓存（be-①）
  if (ep !== state.epoch) return;
  mergeDocRow({
    doc_id: body.doc_id, title: body.title, dataset: body.dataset,
    dims: rowDims(id), // 保留既有缓存维度
    active_version: body.active_version, active_status: body.active_status, active_error: body.active_error,
    pending_version: body.pending_version, pending_status: body.pending_status, pending_error: body.pending_error,
    source: body.source, updated_at: body.updated_at,
  });
  state.quality = null;
  loadQuality(id).catch(() => { /* 权限/失败在 pane 内如实展示 */ });
}

async function loadQuality(docId) {
  if (docId == null) return; // P2-3 防御：无选中文档不取质检
  const ep = state.epoch; // P1-5
  state.loading.quality = true;
  try {
    const body = await getDocumentQuality(cfg.org, docId);
    if (ep !== state.epoch) return;
    state.quality = body && typeof body === "object" ? body : { flags: [], open_count: 0 }; // P2-3：空/畸形体防御
  } catch (e) {
    if (ep !== state.epoch) return;
    state.quality = { error: e.status, message: String(e.message || e) };
  } finally {
    if (ep === state.epoch) state.loading.quality = false;
  }
}

function rowDims(docId) {
  const row = docRows().find((r) => r.doc_id === docId);
  return row ? row.dims : undefined;
}

function mergeDocRow(partial) {
  const inList = state.docs.list.findIndex((r) => r.doc_id === partial.doc_id);
  const inSession = state.docs.session.findIndex((r) => r.doc_id === partial.doc_id);
  if (inSession >= 0) {
    state.docs.session[inSession] = Object.assign({}, state.docs.session[inSession], partial);
  } else if (inList >= 0) {
    state.docs.list[inList] = Object.assign({}, state.docs.list[inList], partial);
  } else {
    state.docs.session.unshift(partial);
  }
}

function docRows() {
  if (state.docs.available) {
    const map = new Map(state.docs.list.map((d) => [d.doc_id, d]));
    for (const s of state.docs.session) map.set(s.doc_id, Object.assign({}, map.get(s.doc_id) || {}, s));
    return [...map.values()];
  }
  return [...state.docs.session];
}

/* ---------- 视图 ---------- */

function viewDocs() {
  if (!connected()) return connGate();
  const rows = docRows().filter((d) => state.ds === "all" || d.dataset === state.ds);
  return `
  <header class="head">
    <h1>${esc(t("docs.title"))}</h1>
    <p class="lede">${t("docs.lede")}</p>
    <div class="head-act">
      ${isAdmin() ? `<button class="btn ghost" data-act="toggleQs">${state.drawer === "qsampling" ? esc(t("common.collapse")) : esc(t("docs.qs.btn"))}</button>` : ""}
      <button class="btn seal-btn" data-act="toggleUpload">${state.drawer === "upload" ? esc(t("common.collapse")) : esc(t("docs.upload.toggle"))}</button>
    </div>
  </header>
  ${state.drawer === "qsampling" ? `<div>${qsPanelHTML()}</div>` : ""}
  <div class="drawer ${state.drawer === "upload" ? "open" : ""}"><div class="dr-in">${uploadHTML()}</div></div>
  ${state.dsAsk ? dsDelConfirmHTML() : ""}
  ${state.drawer === "newds" ? newDsHTML() : `
  <div class="toolbar">
    <div class="seg" role="tablist">
      <button class="${state.ds === "all" && state.drawer !== "newds" ? "on" : ""}" data-act="ds" data-id="all">${esc(t("docs.seg.all"))} ${docRows().length}</button>
      ${state.datasets.map((d) => `<button class="${state.ds === d.id ? "on" : ""}" data-act="ds" data-id="${esc(d.id)}" title="${esc(d.description || "")}">${esc(d.name)} ${docRows().filter((x) => x.dataset === d.id).length}</button>`).join("")}
      ${isAdmin() ? `<button class="seg-add ${state.drawer === "newds" ? "on" : ""}" data-act="newDsToggle" title="${esc(t("docs.ds.new.title"))}">${esc(t("docs.ds.new"))}</button>` : ""}
      ${state.ds !== "all" && docRows().filter((x) => x.dataset === state.ds).length === 0 && isAdmin()
        ? `<button class="seg-add" data-act="dsDel" data-id="${esc(state.ds)}" style="color:var(--danger)" title="${esc(t("docs.ds.del.hint"))}">${esc(t("docs.ds.del"))}</button>` : ""}
    </div>
    <span style="flex:1"></span>
    <span class="tiny muted">${esc(t("docs.count", { n: rows.length }))}</span>
  </div>
  <div class="split">
    <div>
      ${state.docs.available === false ? docsLoadErrHTML() : ""}
      ${state.loading.docsList ? loadingHTML("docs") : rows.length ? docsTableHTML(rows) : emptyDocsHTML()}
    </div>
    <aside class="pane">${state.selDoc && docRows().find((r) => r.doc_id === state.selDoc) ? docPaneHTML(docRows().find((r) => r.doc_id === state.selDoc)) : docTeachHTML()}</aside>
  </div>`}
  `;
}

/* 列表装载失败错误态（be-① 已实装——不再有 404 降级横幅；失败如实可重试） */
function docsLoadErrHTML() {
  return `<div class="empty" style="margin:0"><h3>${esc(t("docs.list.loadErr", { err: esc(state.docs.loadError || "") }))}</h3>
    <div style="margin-top:16px"><button class="btn ghost sm" data-act="docsRetry">${esc(t("common.retry"))}</button></div></div>`;
}

/* org_admin 面：visible 徽标（管理面对账——member 行恒可见不显示列） */
function visibleCellHTML(d) {
  if (d.visible === false) return `<span class="pill bad" title="${esc(t("docs.vis.notVisibleTip"))}">✗</span>`;
  if (d.visible === true) return `<span class="pill ok" title="${esc(t("docs.vis.visibleTip"))}">✓</span>`;
  return `<span class="tiny muted">—</span>`;
}

function docsTableHTML(rows) {
  return `<table class="ledger">
    <thead><tr><th style="width:36%">${esc(t("docs.col.doc"))}</th><th>${esc(t("docs.col.dims"))}</th><th>${esc(t("docs.col.ver"))}</th>${isAdmin() ? `<th>${esc(t("docs.col.visible"))}</th>` : ""}<th class="num">${esc(t("docs.col.chunks"))}</th><th>${esc(t("docs.col.quality"))}</th><th>${esc(t("docs.col.updated"))}</th></tr></thead>
    <tbody>${rows.map((d) => {
      return `<tr class="clickable ${state.selDoc === d.doc_id ? "on" : ""}" data-act="selDoc" data-id="${esc(d.doc_id)}">
        <td><div class="t-title">${esc(d.title || d.doc_id)}</div><div class="t-sub">${esc(dsName(d.dataset))} · ${esc(d.doc_id)}</div></td>
        <td>${d.dims == null ? dimChipsHTML({}, { showEmpty: true }) : dimChipsHTML(d.dims)}</td>
        <td><div class="ver">
          ${d.active_version ? `<span class="vl"><span class="vn">v${esc(d.active_version)}</span>${stPill(d.active_status)}</span>` : `<span class="vl muted"><span class="vn">—</span>${esc(t("docs.ver.none"))}</span>`}
          ${d.pending_version ? `<span class="vl"><span class="vn">v${esc(d.pending_version)}</span>${stPill(d.pending_status)}<span class="tiny muted">${esc(t("docs.ver.pending"))}</span></span>` : ""}
        </div></td>
        ${isAdmin() ? `<td>${visibleCellHTML(d)}</td>` : ""}
        <td class="num">${d.chunk_count != null ? esc(d.chunk_count) : "—"}</td>
        <td>${d.quality_open != null && d.quality_open > 0 ? `<span class="tag amber">${esc(t("docs.quality.openCount", { n: d.quality_open }))}</span>` : `<span class="tiny muted">—</span>`}</td>
        <td class="tiny muted">${tsHTML(d.updated_at, "mono tiny muted")}</td></tr>`;
    }).join("")}</tbody>
  </table>`;
}

function emptyDocsHTML() {
  const scoped = state.ds !== "all";
  return `<div class="empty" style="margin:0">
    <h3>${scoped ? esc(t("docs.empty.ds", { name: dsName(state.ds) })) : esc(t("docs.empty.org"))}</h3>
    <p>${t("docs.empty.body")}</p>
    <div style="margin-top:16px"><button class="btn seal-btn" data-act="emptyUpload">${esc(t("docs.empty.upload"))}</button></div>
  </div>`;
}

function dsDelConfirmHTML() {
  return `<div class="confirm"><b>${esc(t("docs.ds.del.confirm", { name: dsName(state.dsAsk) }))}</b> ${t("docs.ds.del.body")}
    <div class="cf-act"><button class="btn danger-btn sm" data-act="dsDelOk" data-id="${esc(state.dsAsk)}">${esc(t("common.confirm"))}</button>
    <button class="btn ghost sm" data-act="dsDelCancel">${esc(t("common.cancel"))}</button>
    <span class="tiny muted" style="align-self:center"><code>DELETE /api/orgs/${esc(cfg.org)}/datasets/${esc(state.dsAsk)}</code></span></div></div>`;
}

function newDsHTML() {
  if (!isAdmin()) return `<div class="upload"><div class="note seal" style="grid-column:1/-1;margin:0">${t("docs.ds.new.needAdmin")}</div></div>`;
  const ok = state.newDs.key.trim().length > 0;
  return `<div class="upload">
    <div style="grid-column:1/-1"><b style="font-size:15px">${esc(t("docs.ds.new"))}</b>
      <span class="tiny muted">—— ${t("docs.ds.new.note")}</span></div>
    <div class="u-row"><label>key<span class="req">*</span></label>
      <input class="inp" data-in="dsKey" placeholder="${esc(t("docs.ds.key.ph"))}" value="${esc(state.newDs.key)}" style="font-family:var(--mono)"></div>
    <div class="u-row"><label>${esc(t("docs.ds.title"))}<span class="tiny muted"> ${esc(t("common.optional"))}</span></label>
      <input class="inp" data-in="dsTitle" placeholder="${esc(t("docs.ds.title.ph"))}" value="${esc(state.newDs.title)}"></div>
    <div class="u-row"><label>${esc(t("docs.ds.desc"))}<span class="tiny muted"> ${esc(t("common.optional"))}</span></label>
      <input class="inp" data-in="dsDesc" placeholder="${esc(t("docs.ds.desc.ph"))}" value="${esc(state.newDs.desc)}"></div>
    <div class="u-foot">
      <button class="btn seal-btn" data-act="dsCreate" ${ok ? "" : "disabled"}>${esc(t("common.create"))}</button>
      <button class="btn ghost" data-act="newDsToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny ${ok ? "" : "muted"}">${ok ? esc(t("docs.ds.new.ok")) : esc(t("docs.ds.key.ph"))}</span>
      <span style="flex:1"></span>
      <span class="tiny muted">${t("docs.ds.new.foot")}</span>
    </div></div>`;
}

function uploadHTML() {
  if (!state.datasets.length) return `<div class="upload"><div class="note amber" style="grid-column:1/-1;margin:0">${t("docs.upload.noDs")}</div></div>`;
  if (!state.up.ds) state.up.ds = state.datasets[0].id;
  const dims = state.dims;
  const missing = dims.filter((d) => d.required && !(state.up.picked[d.key] || []).length);
  const ok = !missing.length && !!state.up.fileObj;
  const hint = !state.up.fileObj ? t("docs.upload.needFile") : missing.length ? t("docs.upload.needDims", { dims: missing.map((d) => d.name).join(t("common.sep")) }) : t("docs.upload.ready");
  const ow = state.up.overwrite;
  return `<div class="upload">
    ${ow ? `<div class="note amber" style="grid-column:1/-1;margin:0"><b>${esc(t("docs.up.overwriteTag"))}</b> ${esc(ow.title)} <span class="mono tiny">${esc(ow.docId)}</span>
      — ${t("docs.up.overwriteNote", { v: ow.active || 0 })} <button class="link tiny" data-act="overwriteOff">${esc(t("docs.up.overwriteOff"))}</button></div>` : ""}
    <div class="u-row"><label>${esc(t("docs.dataset"))}<span class="req">*</span></label>
      ${ow ? `<span style="display:flex;gap:8px;align-items:center;padding-top:4px"><span class="chip">${esc(dsName(state.up.ds))}</span><span class="tiny muted">${esc(t("docs.up.dsLocked"))}</span></span>`
        : `<select class="sel" data-in="upDs">${state.datasets.map((d) => `<option value="${esc(d.id)}" ${state.up.ds === d.id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>`}</div>
    <div class="u-row"><label>${esc(t("docs.file"))}<span class="req">*</span></label>
      <div class="filebox"><input type="file" data-in="upFile" accept=".docx,.xlsx,.pptx,.pdf,.txt,.html,.htm,.md">
      <span class="tiny muted">${state.up.fileObj ? esc(t("docs.upload.picked", { name: state.up.file })) : esc(t("docs.upload.fileTypes"))}</span></div></div>
    ${dims.map((d) => {
      const picked = state.up.picked[d.key] || [];
      return `<div class="u-row"><label>${esc(d.name)}${d.required ? `<span class="req">*</span>` : `<span class="tiny muted"> ${esc(t("common.optional"))}</span>`}</label>
        <div class="chips">${(d.values || []).map((v) => `<button class="vchip ${picked.includes(v.value) ? "on" : ""}" data-act="pick" data-k="${esc(d.key)}" data-v="${esc(v.value)}">${esc(v.label)}<span class="vx">${esc(v.value)}</span></button>`).join("")}
        ${!d.required ? `<span class="tiny muted" style="align-self:center">${esc(t("docs.upload.optionalNote"))}</span>` : ""}</div></div>`;
    }).join("")}
    <div class="u-foot">
      <button class="btn seal-btn" data-act="uploadSubmit" ${ok ? "" : "disabled"}>${esc(t("docs.upload.submit"))}</button>
      <span class="tiny ${ok ? "" : "muted"}" id="upHint">${esc(hint)}</span>
      <span style="flex:1"></span>
      <span class="tiny muted">${t("docs.upload.agentNote")}</span>
    </div></div>`;
}

/* ---------- 详情 pane ---------- */

function docTeachHTML() {
  return `<div class="teach"><b style="font-size:15px">${esc(t("docs.teach.title"))}</b>
    <ol><li><b>${esc(t("docs.teach.v1"))}</b>${t("docs.teach.v1b")}</li>
    <li><b>${esc(t("docs.teach.v2"))}</b>${t("docs.teach.v2b")}</li>
    <li><b>${esc(t("docs.teach.v3"))}</b>${t("docs.teach.v3b")}</li></ol>
    <p style="margin-top:12px">${t("docs.teach.foot")}</p></div>`;
}

const QUAL_CN = { vector_crowding: "docs.qual.crowding", low_idf: "docs.qual.lowIdf", both: "docs.qual.both" };

function docPaneHTML(d) {
  const firstUpload = !d.active_version;
  return `
    <h2>${esc(d.title || d.doc_id)}</h2>
    <dl class="kv"><dt>${esc(t("docs.dataset"))}</dt><dd>${esc(dsName(d.dataset))}</dd>
    <dt>${esc(t("docs.docId"))}</dt><dd class="mono">${esc(d.doc_id)}</dd>
    <dt>${esc(t("docs.updated"))}</dt><dd>${tsHTML(d.updated_at, "mono tiny")}</dd>
    <dt>${esc(t("docs.source"))}</dt><dd class="mono tiny">${esc(d.source || "—")}</dd></dl>
    <div class="pane-sec"><div class="ps-h">${esc(t("docs.ver.title"))}</div>
      ${d.active_version ? `<div class="ver"><span class="vl"><span class="vn">v${esc(d.active_version)}</span>${esc(t("docs.ver.active"))} · ${stPill(d.active_status)}${d.active_error ? ` <span class="tiny" style="color:var(--danger)">${esc(d.active_error)}</span>` : ""}</span></div>` : `<div class="tiny muted">${esc(t("docs.ver.noneFirst"))}</div>`}
      ${d.pending_version ? `<div style="margin-top:10px"><span class="vl tiny"><span class="vn">v${esc(d.pending_version)}</span> ${esc(t("docs.ver.pending"))}</span>
        ${d.pending_status ? stagesHTML(d.pending_status) : ""}
        ${d.pending_error ? `<div class="tiny" style="color:var(--danger);margin-top:4px">${esc(d.pending_error)}</div>` : ""}
        <div class="tiny muted" style="margin-top:6px">${firstUpload ? t("docs.ver.first") : t("docs.ver.overwrite", { v: d.active_version })}</div></div>` : ""}
      ${d.active_status === "searchable_lexical" && !d.pending_version ? `<div class="tiny muted" style="margin-top:6px">${t("docs.ver.lexical")}</div>` : ""}
      <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button class="btn ghost sm" data-act="overwriteAsk" data-id="${esc(d.doc_id)}" ${d.pending_version ? "disabled" : ""}>↥ ${esc(t("docs.ver.uploadNew"))}</button>
        ${d.pending_version ? `<span class="tiny muted">${esc(t("docs.up.pending409"))}</span>` : `<span class="tiny muted">${esc(t("docs.ver.uploadNote"))}</span>`}
      </div>
    </div>
    <div class="pane-sec"><div class="ps-h">${esc(t("docs.dims.title"))}</div>
      ${d.dims == null ? dimChipsHTML({}, { showEmpty: true }) : dimChipsHTML(d.dims, { showEmpty: true })}
      ${state.editDims ? editDimsHTML(d) : `
      <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
        <button class="btn ghost sm" data-act="editDims" data-id="${esc(d.doc_id)}" ${d.pending_version ? "disabled" : ""}>${esc(t("docs.dims.edit"))}</button>
        ${d.pending_version ? `<span class="tiny muted">${esc(t("docs.dims.pending409"))}</span>` : `<span class="tiny muted">${esc(t("docs.dims.editNote"))}</span>`}
      </div>`}
    </div>
    ${qualityHTML(d)}
    ${explainCardHTML(d)}
    <div class="pane-sec">
      ${state.delAsk === d.doc_id ? `<div class="confirm"><b>${esc(t("docs.del.confirm", { title: d.title || d.doc_id }))}</b> ${t("docs.del.body")}
        <div class="cf-act"><button class="btn danger-btn sm" data-act="delDocOk" data-id="${esc(d.doc_id)}">${esc(t("common.confirm"))}</button>
        <button class="btn ghost sm" data-act="delDocCancel">${esc(t("common.cancel"))}</button></div></div>`
      : `<button class="btn ghost sm" data-act="delDoc" data-id="${esc(d.doc_id)}" style="color:var(--danger)">${esc(t("docs.del.btn"))}</button> <span class="tiny muted">${esc(t("docs.del.note"))}</span>`}
    </div>`;
}

/* 可见性解释卡（m3-1 be-② 实装——m3-2 ui-be 接真端点）：自解释 GET explain；
 * 前端不演算 ACL（issue B5）——只呈现服务端解释行（只解释不裁定）。 */
const VERDICT_PILL = {
  allow: '<span class="pill ok">allow</span>',
  deny: '<span class="pill bad">deny</span>',
  skip: '<span class="pill idle">skip</span>',
};

function explainCardHTML(d) {
  const ex = state.docs.explain && state.docs.explain.docId === d.doc_id
    ? state.docs.explain : null;
  let body;
  if (!ex) {
    body = `<div style="margin-top:6px"><button class="btn ghost sm" data-act="explainDoc" data-id="${esc(d.doc_id)}">${esc(t("docs.vis.explainBtn"))}</button>
      <span class="tiny muted" style="margin-left:8px">${t("docs.vis.explainNote")}</span></div>`;
  } else if (ex.loading) {
    body = `<div class="loading">${esc(t("common.loading", { what: t("docs.vis.title") }))}</div>`;
  } else if (ex.error) {
    body = `<div class="tiny" style="color:var(--danger);margin-top:4px">${esc(t("docs.vis.explainErr", { status: ex.error }))}</div>
      <div style="margin-top:6px"><button class="btn ghost sm" data-act="explainDoc" data-id="${esc(d.doc_id)}">${esc(t("common.retry"))}</button></div>`;
  } else {
    body = `<div style="margin-top:6px" class="explain-rows">
      ${(ex.rows || []).map((r) => `<div class="explain-row">
        <span>${VERDICT_PILL[r.verdict] || esc(r.verdict || "—")}</span>
        <b>${esc(r.kind === "membership" ? t("docs.vis.membership") : (r.label || r.key || r.kind))}</b>
        <span class="tiny muted">${esc(r.detail || "")}</span>
      </div>`).join("")}
      <div class="tiny" style="margin-top:6px">${ex.visible
        ? `<span class="pill ok">${esc(t("docs.vis.visible"))}</span> ${t("docs.vis.visibleNote")}`
        : `<span class="pill bad">${esc(t("docs.vis.notVisible"))}</span> ${t("docs.vis.notVisibleNote")}`}</div>
    </div>`;
  }
  return `<div class="pane-sec"><div class="ps-h">${esc(t("docs.vis.title"))}</div>${body}</div>`;
}

async function loadExplain(docId) {
  const ep = state.epoch; // P1-5
  state.docs.explain = { docId, loading: true };
  render();
  try {
    const body = await explainDocument(cfg.org, docId);
    if (ep !== state.epoch) return;
    state.docs.explain = { docId, rows: body.rows || [], visible: !!body.visible };
  } catch (e) {
    if (ep !== state.epoch) return;
    state.docs.explain = { docId, error: e.status || 0 };
  }
  render();
}

function editDimsHTML(d) {
  return `<div style="margin-top:8px">
    ${state.dims.map((dim) => {
      const picked = state.editPicked[dim.key] || [];
      return `<div style="margin-bottom:6px"><div class="tiny muted">${esc(dim.name)}${dim.required ? '<span class="req">*</span>' : ""} <span class="mono">${esc(dim.key)}</span></div>
      <div class="chips" style="margin-top:2px">${(dim.values || []).map((v) => `<button class="vchip ${picked.includes(v.value) ? "on" : ""}" data-act="editPick" data-k="${esc(dim.key)}" data-v="${esc(v.value)}">${esc(v.label)}</button>`).join("")}</div></div>`;
    }).join("")}
    <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
      <button class="btn sm" data-act="editDimsSave" data-id="${esc(d.doc_id)}">${esc(t("common.save"))}</button>
      <button class="btn ghost sm" data-act="editDimsCancel">${esc(t("common.cancel"))}</button>
      <span class="tiny muted">${esc(t("docs.dims.editNote"))}</span>
    </div></div>`;
}

function qualityHTML(d) {
  const q = state.quality;
  let inner;
  if (state.loading.quality) inner = `<div class="loading">${esc(t("common.loading", { what: t("docs.quality.title") }))}</div>`;
  else if (!q) inner = `<div class="tiny muted">${esc(t("docs.quality.none"))}</div>`;
  else if (q.error) inner = `<div class="tiny muted">${esc(t("docs.quality.denied"))}（${esc(q.status)}）</div>`;
  else if (!(q.flags || []).length) inner = `<div class="tiny muted">${esc(t("docs.quality.noFlags"))}</div>`;
  else inner = (q.flags || []).map((f) => {
    const reason = QUAL_CN[f.reason] ? t(QUAL_CN[f.reason]) : (f.reason || "—"); // P2-3：未知/缺失 reason 防御
    const draft = state.qualDraft[f.flag_id] || { kw: "", tags: "" };
    return `<div class="flag ${f.state !== "open" ? "resolved" : ""}">
      <div class="f-act"><span class="tag ${f.reason === "both" ? "seal" : "amber"}">${esc(reason)}</span>
        <span class="tiny muted">mean_sim ${f.mean_sim != null ? esc(Number(f.mean_sim).toFixed(3)) : "—"} · avg_idf ${f.avg_idf != null ? esc(Number(f.avg_idf).toFixed(2)) : "—"}</span>
        ${f.state !== "open" ? `<span class="pill idle">${esc(t("docs.qual." + f.state) || f.state)}</span>` : ""}</div>
      ${f.state === "open" ? `
      <div class="f-act" style="margin-top:6px">
        <input class="inp" style="height:26px;width:150px" data-in="qualKw" data-id="${esc(f.flag_id)}" placeholder="${esc(t("docs.qual.kwPh"))}" value="${esc(draft.kw)}">
        <input class="inp" style="height:26px;width:150px" data-in="qualTags" data-id="${esc(f.flag_id)}" placeholder="${esc(t("docs.qual.tagsPh"))}" value="${esc(draft.tags)}">
        <button class="btn sm" data-act="qualResolve" data-id="${esc(f.flag_id)}">${esc(t("docs.qual.resolve"))}</button>
        <button class="btn ghost sm" data-act="qualIgnore" data-id="${esc(f.flag_id)}">${esc(t("docs.qual.ignore"))}</button>
      </div>`
      : `<div class="tiny muted" style="margin-top:4px">${f.manual_tags ? esc(f.manual_tags) : esc(t("docs.qual." + f.state) || f.state)}</div>`}
    </div>`;
  }).join("");
  return `<div class="pane-sec"><div class="ps-h">${esc(t("docs.quality.title"))}${q && !q.error ? ` · ${esc(t("docs.quality.openCount", { n: q.open_count || 0 }))}` : ""}</div>${inner}
  <div class="tiny muted" style="margin-top:6px">${t("docs.quality.note")}</div></div>`;
}

/* ---------- 质检抽查面板（ui-3 C1——org_admin：GET /api/quality-flags/sample + PATCH 行内补标） ---------- */

async function loadQs(resample) {
  const ep = state.epoch; // P1-5
  state.qs.loading = true;
  if (resample) state.qs.seed = "ui3-" + Math.random().toString(36).slice(2, 8); // 确定性抽样——换 seed = 换一批
  render();
  try {
    const body = await sampleQualityFlags({ n: 20, seed: state.qs.seed });
    if (ep !== state.epoch) return;
    state.qs.flags = (body && body.flags) || [];
  } catch (e) {
    if (ep !== state.epoch) return;
    state.qs.flags = []; // 403 等——api.js 已 toast detail；面板内呈现计数为零
  } finally {
    if (ep === state.epoch) { state.qs.loading = false; render(); }
  }
}

function qsPanelHTML() {
  const q = state.qs;
  let body;
  if (q.loading && q.flags == null) body = `<div class="loading">${esc(t("common.loading", { what: t("docs.qs.btn") }))}</div>`;
  else if (!(q.flags || []).length) body = `<div class="empty" style="margin:0;padding:var(--s5)"><h3>${esc(t("docs.qs.empty.title"))}</h3><p>${t("docs.qs.empty.body")}</p></div>`;
  else body = `<table class="ledger">
    <thead><tr><th>${esc(t("docs.qs.col.flag"))}</th><th>${esc(t("docs.qs.col.doc"))}</th><th>${esc(t("docs.qs.col.reason"))}</th><th class="num">${esc(t("docs.qs.col.sim"))}</th><th class="num">${esc(t("docs.qs.col.idf"))}</th><th>${esc(t("docs.quality.title"))}</th></tr></thead>
    <tbody>${q.flags.map((f) => {
      const reason = QUAL_CN[f.reason] ? t(QUAL_CN[f.reason]) : (f.reason || "—"); // P2-3 防御
      return `<tr>
        <td class="mono tiny"><span class="cut" style="max-width:150px" title="${esc(f.flag_id)}">${esc(f.flag_id)}</span></td>
        <td class="mono tiny"><span class="cut" style="max-width:170px" title="${esc(f.doc_id)}">${esc(f.doc_id)}</span></td>
        <td><span class="tag ${f.reason === "both" ? "seal" : "amber"}">${esc(reason)}</span></td>
        <td class="num mono tiny">${f.mean_sim != null ? esc(Number(f.mean_sim).toFixed(3)) : "—"}</td>
        <td class="num mono tiny">${f.avg_idf != null ? esc(Number(f.avg_idf).toFixed(2)) : "—"}</td>
        <td><div class="f-act">
          <input class="inp" style="height:26px;width:140px" data-in="qsKw" data-id="${esc(f.flag_id)}" placeholder="${esc(t("docs.qual.kwPh"))}">
          <input class="inp" style="height:26px;width:140px" data-in="qsTags" data-id="${esc(f.flag_id)}" placeholder="${esc(t("docs.qual.tagsPh"))}">
          <button class="btn sm" data-act="qsResolve" data-id="${esc(f.flag_id)}">${esc(t("docs.qual.resolve"))}</button>
          <button class="btn ghost sm" data-act="qsIgnore" data-id="${esc(f.flag_id)}">${esc(t("docs.qual.ignore"))}</button>
        </div></td>
      </tr>`;
    }).join("")}</tbody>
  </table>
  <div class="tbl-foot"><span>${esc(t("docs.qs.count", { n: q.flags.length }))}</span><span class="tiny muted">${t("docs.qs.note")}</span></div>`;
  return `<div class="upload" style="grid-template-columns:1fr">
    <div style="grid-column:1/-1;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
      <b style="font-size:15px">${esc(t("docs.qs.title"))}</b>
      <span class="tiny muted">${t("docs.qs.note")}</span>
      <span style="flex:1"></span>
      <button class="btn ghost sm" data-act="qsResample">${esc(t("docs.qs.resample"))}</button>
    </div>
    ${body}
  </div>`;
}

/* ---------- 动作与输入 ---------- */

Object.assign(actions, {
  toggleUpload() {
    state.drawer = state.drawer === "upload" ? null : "upload";
    if (state.drawer === "upload") state.up.overwrite = null; // 普通上传入口 = 解除覆盖锁定
  },
  toggleQs() {
    state.drawer = state.drawer === "qsampling" ? null : "qsampling";
    if (state.drawer === "qsampling" && state.qs.flags == null) loadQs(false);
  },
  async qsResample() { await loadQs(true); return false; },
  async qsResolve(el) {
    const id = el.dataset.id;
    const kw = document.querySelector(`[data-in="qsKw"][data-id="${CSS.escape(id)}"]`);
    const tg = document.querySelector(`[data-in="qsTags"][data-id="${CSS.escape(id)}"]`);
    const body = {};
    const kwV = kw ? kw.value.trim() : "";
    const tgV = tg ? tg.value.trim() : "";
    if (kwV) body.keywords = kwV;
    if (tgV) body.tags = tgV;
    body.state = "resolved";
    try { await patchQualityFlag(id, body); }
    catch (e) { errToast(e); return false; }
    toast(t("docs.qual.done"));
    if (state.qs.flags) state.qs.flags = state.qs.flags.filter((f) => f.flag_id !== id); // 已解决行移出 open 抽样
    if (state.selDoc) loadQuality(state.selDoc).then(() => render()).catch(() => {});
    render();
    return false;
  },
  async qsIgnore(el) {
    const id = el.dataset.id;
    try { await patchQualityFlag(id, { state: "ignored" }); }
    catch (e) { errToast(e); return false; }
    toast(t("docs.qual.ignored"));
    if (state.qs.flags) state.qs.flags = state.qs.flags.filter((f) => f.flag_id !== id);
    if (state.selDoc) loadQuality(state.selDoc).then(() => render()).catch(() => {});
    render();
    return false;
  },
  newDsToggle() { state.drawer = state.drawer === "newds" ? null : "newds"; },
  emptyUpload() { if (state.ds !== "all") state.up.ds = state.ds; state.up.overwrite = null; state.drawer = "upload"; },
  ds(el) { state.ds = el.dataset.id; if (state.drawer === "newds") state.drawer = null; },
  selDoc(el) {
    state.selDoc = state.selDoc === el.dataset.id ? null : el.dataset.id;
    state.editDims = false; state.quality = null; state.qualDraft = {};
    state.docs.explain = null; // 切换文档清解释卡
    if (state.selDoc) refreshSelectedDoc().then(() => render()).catch(() => { /* 已 toast */ });
    return false;
  },
  pick(el) {
    const k = el.dataset.k, v = el.dataset.v;
    const p = state.up.picked[k] || [];
    state.up.picked[k] = p.includes(v) ? p.filter((x) => x !== v) : [...p, v];
  },
  async uploadSubmit() {
    const file = state.up.fileObj;
    if (!file) return false;
    const ow = state.up.overwrite;
    const dims = {};
    state.dims.forEach((d) => { dims[d.key] = [...(state.up.picked[d.key] || [])]; });
    toast(esc(t("docs.upload.uploading", { name: file.name })));
    let body;
    try {
      body = await uploadMultipart(cfg.org, { file, dataset: state.up.ds, dims, title: file.name, docId: ow ? ow.docId : undefined });
    } catch (e) {
      // 400 维度取值不在授权内 / 403 / 409 pending 已存在——服务端语义内联回显（不做前端预判）
      if (e.status === 409) toast(t("docs.up.conflict409", { msg: esc(String((e && e.message) || "")) }));
      else errToast(e);
      return false;
    }
    if (ow) {
      // 覆盖上传：同一 doc_id，pending_version = max+1；不新增列表行，合并进既有行
      mergeDocRow({
        doc_id: body.doc_id, title: file.name, dataset: state.up.ds, dims,
        pending_version: body.pending_version || null, pending_status: "uploaded", pending_error: null,
      });
    } else {
      state.docs.session.unshift({
        doc_id: body.doc_id, title: file.name, dataset: state.up.ds, dims,
        active_version: 0, active_status: null, active_error: null,
        pending_version: body.pending_version || 1, pending_status: "uploaded", pending_error: null,
        chunk_count: 0, quality_open: 0, updated_at: null,
      });
    }
    state.selDoc = body.doc_id; state.ds = "all"; state.drawer = null;
    state.up = { ds: state.up.ds, picked: {}, file: "", fileObj: null, overwrite: null };
    toast(ow ? t("docs.upload.queuedOverwrite", { title: esc(file.name), v: ow.active || 0, task: esc(body.task_id) })
            : t("docs.upload.queued", { title: esc(file.name), task: esc(body.task_id) }));
    render();
    pollDocTask(body.doc_id, body.task_id, file.name);
    return false;
  },
  /* ----- 覆盖上传入口（ui-3 C2）：详情 pane「上传新版本」→ 抽屉锁定该 doc ----- */
  overwriteAsk(el) {
    const id = el.dataset.id;
    const row = docRows().find((r) => r.doc_id === id);
    if (!row) return false;
    state.up.overwrite = { docId: id, title: row.title || id, active: row.active_version || 0 };
    state.up.ds = row.dataset || state.up.ds; // 库随之锁定（覆盖上传不换库）
    state.up.picked = {};                     // 维度预填 = 在用版本维度（可改，随新版本落库）
    if (row.dims) for (const [k, v] of Object.entries(row.dims)) state.up.picked[k] = [...v];
    state.up.file = ""; state.up.fileObj = null;
    state.drawer = "upload";
  },
  overwriteOff() { state.up.overwrite = null; state.up.picked = {}; },
  dsDel(el) { state.dsAsk = el.dataset.id; },
  dsDelCancel() { state.dsAsk = null; },
  async dsDelOk(el) {
    const id = el.dataset.id;
    const name = dsName(id);
    try { await deleteDataset(cfg.org, id); } // R2 P1-1：204 正常返回 / !ok 抛 ApiError
    catch (e) {
      state.dsAsk = null;
      if (e.status === 409) toast(t("docs.ds.del.conflict409", { msg: esc(String(e.message || "")) })); // 库内仍有文档 RESTRICT
      else errToast(e); // 403/404/500 如实（403/401 已由 api.js 统一 toast）
      render();
      return false;
    }
    state.datasets = state.datasets.filter((x) => x.id !== id);
    state.dsAsk = null;
    if (state.ds === id) state.ds = "all";
    if (state.up.ds === id) state.up.ds = "";
    toast(t("docs.ds.deleted", { name: esc(name) }));
    render();
    return false;
  },
  async dsCreate() {
    const key = state.newDs.key.trim();
    if (!key) return false;
    let body;
    try {
      // m3-2 ui-be 对账：真契约 {key, title?}（description 仅 PATCH——
      // createDatasetWithDesc 承载两步）
      body = await createDatasetWithDesc(cfg.org, {
        key, title: state.newDs.title.trim() || undefined,
        description: state.newDs.desc.trim() || undefined,
      });
    } catch (e) {
      if (e.status === 409) toast(esc(String(e.message || ""))); // key/name 冲突文案如实
      else errToast(e);
      return false;
    }
    const id = body.id || key;
    const name = body.name || state.newDs.title.trim() || key;
    state.datasets.push({ id, name, description: state.newDs.desc.trim() || "" });
    state.ds = id; state.up.ds = id; state.drawer = null;
    state.newDs = { key: "", title: "", desc: "" };
    toast(t("docs.ds.created", { name: esc(name) }));
    render();
    return false;
  },
  /* 列表装载失败重试（be-① 实装后的错误态——重新探针） */
  async docsRetry() {
    state.docs.probed = false;
    state.docs.available = null;
    render();
    await onEnterDocs();
    render();
    return false;
  },
  explainDoc(el) {
    loadExplain(el.dataset.id).catch(() => { /* 已在卡内呈现错误态 */ });
    return false;
  },
  editDims(el) {
    const row = docRows().find((r) => r.doc_id === el.dataset.id);
    state.editPicked = {};
    if (row && row.dims) for (const [k, v] of Object.entries(row.dims)) state.editPicked[k] = [...v];
    state.editDims = true;
  },
  editDimsCancel() { state.editDims = false; },
  editPick(el) {
    const k = el.dataset.k, v = el.dataset.v;
    const p = state.editPicked[k] || [];
    state.editPicked[k] = p.includes(v) ? p.filter((x) => x !== v) : [...p, v];
  },
  async editDimsSave(el) {
    const id = el.dataset.id;
    const dims = {};
    state.dims.forEach((d) => { dims[d.key] = [...(state.editPicked[d.key] || [])]; });
    try {
      const body = await patchDocumentDims(cfg.org, id, dims);
      mergeDocRow({ doc_id: id, dims: body.dims });
      state.editDims = false;
      toast(t("docs.dims.saved"));
    } catch (e) {
      if (e.status === 409) toast(t("docs.dims.conflict409"));
      else errToast(e);
      return false;
    }
    render();
    return false;
  },
  delDoc(el) { state.delAsk = el.dataset.id; },
  delDocCancel() { state.delAsk = null; },
  async delDocOk(el) {
    const id = el.dataset.id;
    try { await deleteDocument(cfg.org, id); }
    catch (e) { state.delAsk = null; errToast(e); render(); return false; }
    state.docs.list = state.docs.list.filter((r) => r.doc_id !== id);
    state.docs.session = state.docs.session.filter((r) => r.doc_id !== id);
    state.selDoc = null; state.quality = null; state.delAsk = null;
    toast(t("docs.deleted"));
    render();
    return false;
  },
  async qualResolve(el) {
    const id = el.dataset.id;
    const draft = state.qualDraft[id] || { kw: "", tags: "" };
    const body = {};
    if (draft.kw.trim()) body.keywords = draft.kw.trim();
    if (draft.tags.trim()) body.tags = draft.tags.trim();
    body.state = "resolved";
    try { await patchQualityFlag(id, body); }
    catch (e) { errToast(e); return false; }
    toast(t("docs.qual.done"));
    if (state.selDoc) loadQuality(state.selDoc).then(() => render()).catch(() => {}); // P2-3：空选防御
    return false;
  },
  async qualIgnore(el) {
    const id = el.dataset.id;
    try { await patchQualityFlag(id, { state: "ignored" }); }
    catch (e) { errToast(e); return false; }
    toast(t("docs.qual.ignored"));
    if (state.selDoc) loadQuality(state.selDoc).then(() => render()).catch(() => {});
    return false;
  },
});

Object.assign(INPUTS, {
  upDs: (v) => { state.up.ds = v; },
  upFile: (v, el) => { state.up.fileObj = (el.files && el.files[0]) || null; state.up.file = state.up.fileObj ? state.up.fileObj.name : ""; },
  dsKey: (v) => { state.newDs.key = v; },
  dsTitle: (v) => { state.newDs.title = v; },
  dsDesc: (v) => { state.newDs.desc = v; },
  qualKw: (v, el) => { const d = state.qualDraft[el.dataset.id] || { kw: "", tags: "" }; d.kw = v; state.qualDraft[el.dataset.id] = d; return false; },
  qualTags: (v, el) => { const d = state.qualDraft[el.dataset.id] || { kw: "", tags: "" }; d.tags = v; state.qualDraft[el.dataset.id] = d; return false; },
});

/* ---------- 上传后任务轮询（pollTask → 阶段推进 toast，终态停止） ---------- */

async function pollDocTask(docId, taskId, title) {
  const ep = state.epoch; // P1-5：组织/身份切换即停轮询、旧响应不写入新视图
  let lastStage = null;
  try {
    const task = await pollTask(taskId, {
      shouldStop: () => ep !== state.epoch,
      onTick: async (tk) => {
        try {
          const doc = await getDocument(cfg.org, docId);
          if (ep !== state.epoch) return;
          const stage = doc.pending_status || doc.active_status;
          mergeDocRow({
            doc_id: docId,
            active_version: doc.active_version, active_status: doc.active_status, active_error: doc.active_error,
            pending_version: doc.pending_version, pending_status: doc.pending_status, pending_error: doc.pending_error,
            updated_at: doc.updated_at,
          });
          if (stage && stage !== lastStage) {
            if (lastStage !== null) toast(t("docs.task.stage", { title: esc(title), stage: esc(stLabel(stage)) }));
            lastStage = stage;
          }
        } catch (e) { /* 单跳详情失败不中断轮询 */ }
        if (ep === state.epoch && state.view === "docs") render();
      },
    });
    if (!task) return; // shouldStop 触发（上下文已换）——静默停，不再写状态
    const doc = await getDocument(cfg.org, docId).catch(() => null);
    if (ep !== state.epoch) return;
    if (doc) mergeDocRow({ doc_id: docId, active_version: doc.active_version, active_status: doc.active_status, pending_version: doc.pending_version, pending_status: doc.pending_status, pending_error: doc.pending_error, updated_at: doc.updated_at });
    if (task.status === "done") toast(t("docs.task.done", { title: esc(title) }));
    else toast(t("docs.task.failed", { title: esc(title), err: esc(task.error || "") }));
  } catch (e) {
    if (ep === state.epoch) toast(t("docs.task.pollTimeout", { title: esc(title) }));
  }
  if (ep === state.epoch && state.view === "docs") render();
  // 终态后刷新质检（摄取管线 quality 阶段产物）
  if (ep === state.epoch && state.selDoc === docId) loadQuality(docId).then(() => render()).catch(() => {});
}

VIEWS.docs = { render: viewDocs, onEnter: onEnterDocs };
