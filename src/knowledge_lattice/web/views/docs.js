/* views/docs.js —— 文档知识（ui-1）：知识库 seg + be-① 文档列表（contract-first
 * 降级）/ multipart 上传抽屉 + 任务轮询 / 详情 pane（版本双态·阶段进度·维度编辑·
 * 质检补标·删除）/ 可见性解释 = 待 be-② 占位（前端不演算 ACL——issue B5）。
 * 视觉结构沿原型 v0.6 文档页（.upload/.seg/.ledger/.split/.pane）。 */
"use strict";

/* ---------- 数据装载 ---------- */

async function onEnterDocs() {
  if (!connected()) return;
  if (!state.docs.probed) {
    state.loading.docsList = true;
    try {
      // be-1 contract-first：列表端点未实装——404 降级（横幅 + 会话缓存），其余错误如实展示
      const body = await listDocuments(cfg.org);
      state.docs.available = true;
      state.docs.list = body.documents || [];
    } catch (e) {
      state.docs.available = false;
      state.docs.loadError = e.status === 404 ? null : String(e.message || e);
    } finally {
      state.docs.probed = true;
      state.loading.docsList = false;
    }
  }
  if (state.selDoc) refreshSelectedDoc().catch(() => { /* 已 toast */ });
}

async function refreshSelectedDoc() {
  const id = state.selDoc;
  const body = await getDocument(cfg.org, id); // 详情无 dims 字段——维度取列表行缓存（be-①）
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
  state.loading.quality = true;
  try {
    state.quality = await getDocumentQuality(cfg.org, docId);
  } catch (e) {
    state.quality = { error: e.status, message: String(e.message || e) };
  } finally {
    state.loading.quality = false;
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
      <button class="btn seal-btn" data-act="toggleUpload">${state.drawer === "upload" ? esc(t("common.collapse")) : esc(t("docs.upload.toggle"))}</button>
    </div>
  </header>
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
      ${state.docs.available === false ? be1BannerHTML() : ""}
      ${state.loading.docsList ? loadingHTML("docs") : rows.length ? docsTableHTML(rows) : emptyDocsHTML()}
    </div>
    <aside class="pane">${state.selDoc && docRows().find((r) => r.doc_id === state.selDoc) ? docPaneHTML(docRows().find((r) => r.doc_id === state.selDoc)) : docTeachHTML()}</aside>
  </div>`}
  `;
}

function be1BannerHTML() {
  return `<div class="banner">${state.docs.loadError
    ? t("docs.list.loadErr", { err: esc(state.docs.loadError) })
    : t("docs.list.be1")} ${t("docs.list.be1.session")}</div>`;
}

function docsTableHTML(rows) {
  return `<table class="ledger">
    <thead><tr><th style="width:36%">${esc(t("docs.col.doc"))}</th><th>${esc(t("docs.col.dims"))}</th><th>${esc(t("docs.col.ver"))}</th><th class="num">${esc(t("docs.col.chunks"))}</th><th>${esc(t("docs.col.quality"))}</th><th>${esc(t("docs.col.updated"))}</th></tr></thead>
    <tbody>${rows.map((d) => {
      return `<tr class="clickable ${state.selDoc === d.doc_id ? "on" : ""}" data-act="selDoc" data-id="${esc(d.doc_id)}">
        <td><div class="t-title">${esc(d.title || d.doc_id)}</div><div class="t-sub">${esc(dsName(d.dataset))} · ${esc(d.doc_id)}</div></td>
        <td>${d.dims == null ? `<span class="tiny muted">${esc(t("docs.dims.pendingBe1"))}</span>` : dimChipsHTML(d.dims)}</td>
        <td><div class="ver">
          ${d.active_version ? `<span class="vl"><span class="vn">v${esc(d.active_version)}</span>${stPill(d.active_status)}</span>` : `<span class="vl muted"><span class="vn">—</span>${esc(t("docs.ver.none"))}</span>`}
          ${d.pending_version ? `<span class="vl"><span class="vn">v${esc(d.pending_version)}</span>${stPill(d.pending_status)}<span class="tiny muted">${esc(t("docs.ver.pending"))}</span></span>` : ""}
        </div></td>
        <td class="num">${d.chunk_count != null ? esc(d.chunk_count) : "—"}</td>
        <td>${d.quality_open != null && d.quality_open > 0 ? `<span class="tag amber">${esc(t("docs.quality.openCount", { n: d.quality_open }))}</span>` : `<span class="tiny muted">—</span>`}</td>
        <td class="tiny muted">${esc(short(d.updated_at))}</td></tr>`;
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
  const ok = state.newDs.name.trim().length > 0;
  return `<div class="upload">
    <div style="grid-column:1/-1"><b style="font-size:15px">${esc(t("docs.ds.new"))}</b>
      <span class="tiny muted">—— ${t("docs.ds.new.note")}</span></div>
    <div class="u-row"><label>${esc(t("docs.ds.name"))}<span class="req">*</span></label>
      <input class="inp" data-in="dsName" placeholder="${esc(t("docs.ds.name.ph"))}" value="${esc(state.newDs.name)}"></div>
    <div class="u-row"><label>${esc(t("docs.ds.desc"))}<span class="tiny muted"> ${esc(t("common.optional"))}</span></label>
      <input class="inp" data-in="dsDesc" placeholder="${esc(t("docs.ds.desc.ph"))}" value="${esc(state.newDs.desc)}"></div>
    <div class="u-foot">
      <button class="btn seal-btn" data-act="dsCreate" ${ok ? "" : "disabled"}>${esc(t("common.create"))}</button>
      <button class="btn ghost" data-act="newDsToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny ${ok ? "" : "muted"}">${ok ? esc(t("docs.ds.new.ok")) : esc(t("docs.ds.name.ph"))}</span>
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
  return `<div class="upload">
    <div class="u-row"><label>${esc(t("docs.dataset"))}<span class="req">*</span></label>
      <select class="sel" data-in="upDs">${state.datasets.map((d) => `<option value="${esc(d.id)}" ${state.up.ds === d.id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select></div>
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
    <dt>${esc(t("docs.updated"))}</dt><dd>${esc(short(d.updated_at))}</dd>
    <dt>${esc(t("docs.source"))}</dt><dd class="mono tiny">${esc(d.source || "—")}</dd></dl>
    <div class="pane-sec"><div class="ps-h">${esc(t("docs.ver.title"))}</div>
      ${d.active_version ? `<div class="ver"><span class="vl"><span class="vn">v${esc(d.active_version)}</span>${esc(t("docs.ver.active"))} · ${stPill(d.active_status)}${d.active_error ? ` <span class="tiny" style="color:var(--danger)">${esc(d.active_error)}</span>` : ""}</span></div>` : `<div class="tiny muted">${esc(t("docs.ver.noneFirst"))}</div>`}
      ${d.pending_version ? `<div style="margin-top:10px"><span class="vl tiny"><span class="vn">v${esc(d.pending_version)}</span> ${esc(t("docs.ver.pending"))}</span>
        ${d.pending_status ? stagesHTML(d.pending_status) : ""}
        ${d.pending_error ? `<div class="tiny" style="color:var(--danger);margin-top:4px">${esc(d.pending_error)}</div>` : ""}
        <div class="tiny muted" style="margin-top:6px">${firstUpload ? t("docs.ver.first") : t("docs.ver.overwrite", { v: d.active_version })}</div></div>` : ""}
      ${d.active_status === "searchable_lexical" && !d.pending_version ? `<div class="tiny muted" style="margin-top:6px">${t("docs.ver.lexical")}</div>` : ""}
    </div>
    <div class="pane-sec"><div class="ps-h">${esc(t("docs.dims.title"))}</div>
      ${d.dims == null ? `<div class="tiny muted">${esc(t("docs.dims.pendingBe1"))}</div>` : dimChipsHTML(d.dims, { showEmpty: true })}
      ${state.editDims ? editDimsHTML(d) : `
      <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
        <button class="btn ghost sm" data-act="editDims" data-id="${esc(d.doc_id)}" ${d.pending_version ? "disabled" : ""}>${esc(t("docs.dims.edit"))}</button>
        ${d.pending_version ? `<span class="tiny muted">${esc(t("docs.dims.pending409"))}</span>` : `<span class="tiny muted">${esc(t("docs.dims.editNote"))}</span>`}
      </div>`}
    </div>
    ${qualityHTML(d)}
    <div class="pane-sec"><div class="ps-h">${esc(t("docs.vis.title"))}</div>
      <div class="tiny muted">${t("docs.vis.pendingBe2")}</div>
    </div>
    <div class="pane-sec">
      ${state.delAsk === d.doc_id ? `<div class="confirm"><b>${esc(t("docs.del.confirm", { title: d.title || d.doc_id }))}</b> ${t("docs.del.body")}
        <div class="cf-act"><button class="btn danger-btn sm" data-act="delDocOk" data-id="${esc(d.doc_id)}">${esc(t("common.confirm"))}</button>
        <button class="btn ghost sm" data-act="delDocCancel">${esc(t("common.cancel"))}</button></div></div>`
      : `<button class="btn ghost sm" data-act="delDoc" data-id="${esc(d.doc_id)}" style="color:var(--danger)">${esc(t("docs.del.btn"))}</button> <span class="tiny muted">${esc(t("docs.del.note"))}</span>`}
    </div>`;
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
    const reason = QUAL_CN[f.reason] ? t(QUAL_CN[f.reason]) : f.reason;
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

/* ---------- 动作与输入 ---------- */

Object.assign(actions, {
  toggleUpload() { state.drawer = state.drawer === "upload" ? null : "upload"; },
  newDsToggle() { state.drawer = state.drawer === "newds" ? null : "newds"; },
  emptyUpload() { if (state.ds !== "all") state.up.ds = state.ds; state.drawer = "upload"; },
  ds(el) { state.ds = el.dataset.id; if (state.drawer === "newds") state.drawer = null; },
  selDoc(el) {
    state.selDoc = state.selDoc === el.dataset.id ? null : el.dataset.id;
    state.editDims = false; state.quality = null; state.qualDraft = {};
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
    const dims = {};
    state.dims.forEach((d) => { dims[d.key] = [...(state.up.picked[d.key] || [])]; });
    toast(esc(t("docs.upload.uploading", { name: file.name })));
    let body;
    try {
      body = await uploadMultipart(cfg.org, { file, dataset: state.up.ds, dims, title: file.name });
    } catch (e) {
      // 400 维度取值不在授权内 / 403 / 409 pending 已存在——服务端语义内联回显（不做前端预判）
      errToast(e);
      return false;
    }
    const row = {
      doc_id: body.doc_id, title: file.name, dataset: state.up.ds, dims,
      active_version: 0, active_status: null, active_error: null,
      pending_version: body.pending_version || 1, pending_status: "uploaded", pending_error: null,
      chunk_count: 0, quality_open: 0, updated_at: null,
    };
    state.docs.session.unshift(row);
    state.selDoc = body.doc_id; state.ds = "all"; state.drawer = null;
    state.up = { ds: state.up.ds, picked: {}, file: "", fileObj: null };
    toast(t("docs.upload.queued", { title: esc(file.name), task: esc(body.task_id) }));
    render();
    pollDocTask(body.doc_id, body.task_id, file.name);
    return false;
  },
  dsDel(el) { state.dsAsk = el.dataset.id; },
  dsDelCancel() { state.dsAsk = null; },
  async dsDelOk(el) {
    const id = el.dataset.id;
    const name = dsName(id);
    let resp;
    try { resp = await deleteDataset(cfg.org, id); }
    catch (e) { state.dsAsk = null; render(); return false; } // 401：已 toast + 打开连接设置
    if (resp.status === 204) {
      state.datasets = state.datasets.filter((x) => x.id !== id);
      state.dsAsk = null;
      if (state.ds === id) state.ds = "all";
      if (state.up.ds === id) state.up.ds = "";
      toast(t("docs.ds.deleted", { name: esc(name) }));
    } else {
      const body = await resp.json().catch(() => ({}));
      const msg = body.detail || body.error || resp.statusText || resp.status;
      state.dsAsk = null;
      if (resp.status === 409) toast(t("docs.ds.del.conflict409", { msg: esc(String(msg)) }));
      else toast(resp.status + " · " + esc(String(msg)));
    }
    render();
    return false;
  },
  async dsCreate() {
    const name = state.newDs.name.trim();
    if (!name) return false;
    let body;
    try {
      // m3-1 contract-first：POST datasets 未实装——404 由 api.js 抛出，此处降级提示
      body = await createDataset(cfg.org, { name, description: state.newDs.desc.trim() || null });
    } catch (e) {
      if (e.status === 404) toast(t("degrade.m31"));
      return false;
    }
    const id = body.id || (body.dataset && body.dataset.id) || name;
    state.datasets.push({ id, name, description: state.newDs.desc.trim() });
    state.ds = id; state.up.ds = id; state.drawer = null; state.newDs = { name: "", desc: "" };
    toast(t("docs.ds.created", { name: esc(name) }));
    render();
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
    loadQuality(state.selDoc).then(() => render()).catch(() => {});
    return false;
  },
  async qualIgnore(el) {
    const id = el.dataset.id;
    try { await patchQualityFlag(id, { state: "ignored" }); }
    catch (e) { errToast(e); return false; }
    toast(t("docs.qual.ignored"));
    loadQuality(state.selDoc).then(() => render()).catch(() => {});
    return false;
  },
});

Object.assign(INPUTS, {
  upDs: (v) => { state.up.ds = v; },
  upFile: (v, el) => { state.up.fileObj = (el.files && el.files[0]) || null; state.up.file = state.up.fileObj ? state.up.fileObj.name : ""; },
  dsName: (v) => { state.newDs.name = v; },
  dsDesc: (v) => { state.newDs.desc = v; },
  qualKw: (v, el) => { const d = state.qualDraft[el.dataset.id] || { kw: "", tags: "" }; d.kw = v; state.qualDraft[el.dataset.id] = d; return false; },
  qualTags: (v, el) => { const d = state.qualDraft[el.dataset.id] || { kw: "", tags: "" }; d.tags = v; state.qualDraft[el.dataset.id] = d; return false; },
});

/* ---------- 上传后任务轮询（pollTask → 阶段推进 toast，终态停止） ---------- */

async function pollDocTask(docId, taskId, title) {
  let lastStage = null;
  try {
    const task = await pollTask(taskId, {
      onTick: async (tk) => {
        try {
          const doc = await getDocument(cfg.org, docId);
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
        if (state.view === "docs") render();
      },
    });
    const doc = await getDocument(cfg.org, docId).catch(() => null);
    if (doc) mergeDocRow({ doc_id: docId, active_version: doc.active_version, active_status: doc.active_status, pending_version: doc.pending_version, pending_status: doc.pending_status, pending_error: doc.pending_error, updated_at: doc.updated_at });
    if (task.status === "done") toast(t("docs.task.done", { title: esc(title) }));
    else toast(t("docs.task.failed", { title: esc(title), err: esc(task.error || "") }));
  } catch (e) {
    toast(t("docs.task.pollTimeout", { title: esc(title) }));
  }
  if (state.view === "docs") render();
  // 终态后刷新质检（摄取管线 quality 阶段产物）
  if (state.selDoc === docId) loadQuality(docId).then(() => render()).catch(() => {});
}

VIEWS.docs = { render: viewDocs, onEnter: onEnterDocs };
