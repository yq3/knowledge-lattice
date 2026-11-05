/* views/search.js —— 检索测试（ui-1）：与 agent 调 MCP search 同一条管线。
 * qbar + qopts（知识库 select / auto_entities 开关 M2-S3）→ POST /api/search；
 * hit 卡沿原型 .hits/.hit 结构（rank / snippet / title·页·sheet·库 / dims chips /
 * score bar / matched_entities 计数徽标 / source）。
 * 契约内空态：无结果 / 403 denied / 加载态——被过滤计数不在契约，不显示；
 * 无逐块路归标记与漏斗图（ui-2 视契约再议）。右 pane：notice 展示 + 管线说明 +
 * 当前连接身份提示。 */
"use strict";

function viewSearch() {
  if (!connected()) return connGate();
  const r = state.lastSearch;
  return `
  <header class="head"><h1>${esc(t("search.title"))}</h1><p class="lede">${t("search.lede")}</p></header>
  <div class="qbar"><input id="qInput" data-in="q" value="${esc(state.q)}" placeholder="${esc(t("search.q.ph"))}" aria-label="${esc(t("search.q.ph"))}" autocomplete="off"><button class="btn" data-act="doSearch">${esc(t("search.go"))} <span class="kbd" style="color:inherit;border-color:currentColor">↵</span></button></div>
  <div class="qopts">
    <label>${esc(t("search.dataset"))} <select class="sel" data-in="qDs"><option value="">${esc(t("search.all"))}</option>${state.datasets.map((d) => `<option value="${esc(d.id)}" ${state.qDs === d.id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select></label>
    <label class="switch"><input type="checkbox" data-in="autoEnt" ${state.autoEnt ? "checked" : ""}><span>${esc(t("search.autoEnt"))}</span> <span class="tag">M2-S3</span></label>
    <span style="flex:1"></span>
    <span class="tiny muted">${esc(t("search.identity", { user: lensUser(), org: cfg.org }))}</span>
  </div>
  <div class="split">
    <div>${!state.lastSearch ? searchTeachHTML() : state.lastSearch.denied ? deniedHTML() : state.searching ? loadingHTML("search") : hitsHTML(state.lastSearch)}</div>
    <aside class="pane">${searchPaneHTML(state.lastSearch)}</aside>
  </div>`;
}

function searchTeachHTML() {
  return `<div class="empty"><h3>${esc(t("search.teach.title"))}</h3><p>${t("search.teach.body")}</p></div>`;
}

function deniedHTML() {
  return `<div class="empty"><h3>${esc(t("search.denied.title"))}</h3><p>${t("search.denied.body")}</p></div>`;
}

function hitsHTML(r) {
  const rows = r.body.results || [];
  if (!rows.length) return `<div class="empty"><h3>${esc(t("search.empty.title"))}</h3><p>${t("search.empty.body")}</p></div>`;
  const max = Math.max(...rows.map((x) => Number(x.score) || 0), 1e-9);
  return `<div class="hits">${rows.map((h, i) => `
    <article class="hit" style="animation-delay:${i * 40}ms">
      <div class="h-rank">${esc(h.rank ?? i + 1)}</div>
      <div>
        <div class="h-text">${esc(h.snippet || "")}</div>
        <div class="h-meta">
          <span class="h-src" title="${esc(h.title || h.doc_id)}">${esc(h.title || h.doc_id)}</span>
          ${h.page_no != null ? `<span>${esc(t("search.page"))} ${esc(h.page_no)}</span>` : ""}
          ${h.sheet_name ? `<span>${esc(h.sheet_name)}</span>` : ""}
          <span>${esc(h.dataset || h.dataset_id || "")}</span>
          ${dimChipsHTML(h.dims)}
          ${h.matched_entities && h.matched_entities.length ? `<span class="tag moss" title="${esc(t("search.matchedEnt.tip"))}">${esc(t("search.matchedEnt", { n: h.matched_entities.length }))}</span>` : ""}
          <span><span class="score-bar"><i style="width:${Math.min(100, ((Number(h.score) || 0) / max) * 100).toFixed(0)}%"></i></span> <span class="mono tiny">${esc(Number(h.score || 0).toFixed(3))}</span></span>
          ${h.source ? `<span class="mono tiny" title="${esc(h.source)}">${esc(String(h.source).split("/").pop())}</span>` : ""}
        </div>
      </div>
    </article>`).join("")}</div>`;
}

function searchPaneHTML(r) {
  const n = r && r.body && r.body.notice;
  return `
    <div class="pane-sec" style="margin-top:0"><div class="ps-h">${esc(t("search.notice.title"))}</div>
      ${n && n.vector_pending ? `<div class="note amber" style="margin-top:0"><b>${esc(t("search.notice.vectorPending"))}</b>${t("search.notice.vectorPendingB")}</div>` : ""}
      ${n && (n.degraded || []).length ? `<div class="note seal" style="margin-top:8px"><b>${esc(t("search.notice.degraded"))}</b> ${(n.degraded || []).map((d) => `<code>${esc(d)}</code>`).join(" ")}</div>` : ""}
      ${!n || (!n.vector_pending && !(n.degraded || []).length) ? `<div class="tiny muted">${esc(t("search.notice.none"))}</div>` : ""}
    </div>
    <div class="pane-sec"><div class="ps-h">${esc(t("search.pipeline.title"))}</div>
      <div class="teach">${t("search.pipeline.body")}</div>
    </div>
    <div class="pane-sec"><div class="ps-h">${esc(t("search.identity.title"))}</div>
      <div class="tiny">${esc(t("search.identity.line", { user: lensUser(), org: cfg.org, role: roleLabel(cfg.org) }))}</div>
      <div class="tiny muted" style="margin-top:4px">${t("search.identity.note")}</div>
    </div>`;
}

Object.assign(actions, {
  async doSearch() {
    const q = state.q.trim();
    if (!q || state.searching) return false;
    const ep = state.epoch; // P1-5：身份切换后旧检索结果不写入新视图
    state.searching = true;
    state.lastSearch = { q };
    render();
    const payload = { query: q, top_k: 8 };
    if (state.qDs) payload.datasets = [state.qDs];
    if (state.autoEnt) payload.auto_entities = true; // 实体路开关（M2-S3）
    try {
      const body = await search(payload);
      if (ep !== state.epoch) return false;
      state.lastSearch = { q, body };
    } catch (e) {
      if (ep !== state.epoch) return false;
      state.lastSearch = e.status === 403 ? { q, denied: true } : null; // 403 → denied 空态（api.js 已 toast detail）
      if (e.status !== 403 && e.status !== 401) errToast(e);
    } finally {
      if (ep === state.epoch) state.searching = false;
    }
    render();
    return false;
  },
});

Object.assign(INPUTS, {
  q: (v) => { state.q = v; },
  qDs: (v) => { state.qDs = v; },
  autoEnt: (v) => { state.autoEnt = v; },
});

VIEWS.search = { render: viewSearch };
