/* views/semantic.js —— 业务语义（ui-2 新增，nav 知识组第一项）：
 * - 进入探针：GET /semantic/l0 定三态——403 = 无 semantic:read；dict_rev 空 = 未
 *   接入（未构建词典——检索只有词法+向量两路）；正常 = head tag「在用 dict_rev N」。
 * - 实体与关系子标签：搜索（search_entities top_k=20）+ 类型 facet（单选，无计数
 *   ——真实无 counts 端点，诚实差异）+ 类型总览落地页 + 结果表 + 详情（对象图
 *   SVG 客户端布局：关系×方向分组、每组前 3 + +N 占位、点节点重取、深度 1/2；
 *   关系列表；type=table 时 describe_table 透传面板）；404 存在性零泄露如实呈现。
 * - 术语识别子标签：textarea + fuzzy 开关 → POST annotate → 标注渲染（mark
 *   下划线 + 实体名浮标）+ mentions 表 + candidates 表（低信任/多候选）。
 * - 同步与构建子标签（semantic:admin = org_admin 兼任）：五源总览（四可手动
 *   202 / yaml webhook 注记）+ 运行历史 + 词典构建表 + 构建报告 + L0 片段。
 * 契约字段实读结论见本文件内注释与交付报告（nodes={id,type,key,name,depth}、
 * edges={src,rel,dst,source}、annotate={dict_rev,mentions,candidates}…）。 */
"use strict";

const SEM_TYPES = ["concept", "system", "scenario", "template", "template_field",
  "report", "report_item", "table", "column"];
const SEM_REL_COLORS = {   // 连线按关系类型着色（原型口径）
  uses: "#DC6803", has_field: "#444CE7", maps_to: "#6927DA", backed_by: "#0E7090",
  has_item: "#0E9384", child_of: "#15B79E", derived_from: "#079455",
  refers_to: "#DD2590", related_to: "#B438FF", has_column: "#079455",
};
const SEM_GROUP_CAP = 3;   // 每组（关系×方向）最多展示节点数；服务端 fanout_limit 截断置 truncated
const SEM_ADAPTERS = ["template_center", "metadata", "scenario_config", "report_center", "yaml"];

function semTypeLabel(tp) { const s = t("sem.type." + tp); return s === "sem.type." + tp ? tp : s; }
function semPill(st) {
  const cls = { succeeded: "ok", ready: "ok", done: "ok", running: "run", building: "run",
    pending: "idle", failed: "bad", aborted_guard: "bad" }[st] || "idle";
  const key = "sem.st." + st;
  return `<span class="pill ${cls}">${esc(t(key) === key ? st : t(key))}</span>`;
}

/* ---------- 进入探针（三态） ---------- */

async function probeSemantic() {
  try {
    const l0 = await getL0(cfg.org);
    state.sem.l0 = l0;
    state.sem.l0Err = null;
    if (l0.dict_rev == null || l0.dict_rev === 0) state.sem.probe = "notbuilt";
    else { state.sem.probe = "ok"; state.sem.dictRev = l0.dict_rev; }
  } catch (e) {
    if (e.status === 403) state.sem.probe = "noperm";
    else { // 非 403（5xx 等）——视图可用，L0 面板如实展示错误
      state.sem.probe = "ok";
      state.sem.l0Err = String((e && e.message) || e);
    }
  }
  state.sem.admin = isAdmin(); // semantic:admin ≈ org_admin 兼任（§6.3）
}

async function onEnterSemantic() {
  if (!connected()) return;
  if (state.sem.probe === null) await probeSemantic();
  if (state.sub.sem === "sync") await semLoadSyncTab();
}

/* ---------- 视图装配 ---------- */

function viewSemantic() {
  if (!connected()) return connGate();
  if (state.sem.probe === null) return loadingHTML("semantic");
  if (state.sem.probe === "noperm") {
    return `<header class="head"><h1>${esc(t("sem.title"))}</h1><p class="lede">${t("sem.lede")}</p></header>
      <div class="empty"><h3>403 · ${esc(t("sem.noperm.title"))}</h3><p>${t("sem.noperm.body")}</p></div>`;
  }
  if (state.sem.probe === "notbuilt") {
    return `<header class="head"><h1>${esc(t("sem.title"))}</h1><p class="lede">${t("sem.lede")}</p></header>
      <div class="empty"><h3>${esc(t("sem.notbuilt.title"))}</h3><p>${t("sem.notbuilt.body")}</p></div>`;
  }
  const sub = state.sub.sem;
  const building = (state.sem.builds && state.sem.builds.builds || []).some((b) => b.status === "building");
  const tabs = [["entities", t("sem.tab.entities")], ["annotate", t("sem.tab.annotate")], ["sync", t("sem.tab.sync")]];
  return `
  <header class="head"><h1>${esc(t("sem.title"))}</h1>
    <p class="lede">${t("sem.lede")}</p>
    <div class="head-act"><span class="tag moss">${esc(t("sem.dictRev", { rev: state.sem.dictRev }))}</span>${building ? `<span class="tag amber">${esc(t("sem.buildingTag"))}</span>` : ""}</div>
  </header>
  <nav class="sub-tabs">${tabs.map(([k, l]) => `<button class="sub-tab ${sub === k ? "on" : ""}" data-act="sub" data-s="sem" data-v="${k}">${esc(l)}</button>`).join("")}</nav>
  ${sub === "entities" ? entitiesHTML() : sub === "annotate" ? annotateHTML() : syncHTML()}`;
}

/* ---------- 实体与关系子标签 ---------- */

function entToolbarHTML() {
  return `<div class="ent-toolbar">
    <div style="display:flex;gap:8px;align-items:center">
      <input id="semQInput" class="inp" data-in="semQ" value="${esc(state.sem.q)}" placeholder="${esc(t("sem.ent.qPh"))}" style="flex:1;height:36px;font-size:14px" aria-label="${esc(t("sem.ent.qPh"))}" autocomplete="off">
      <button class="btn" data-act="semSearch">${esc(t("sem.ent.go"))}</button>
    </div>
    <div class="ent-chips" role="group" aria-label="${esc(t("sem.ent.facetLabel"))}">
      <button class="facet ${state.sem.entSel ? "" : "on"}" data-act="semFacet" data-t="">${esc(t("sem.ent.all"))}</button>
      ${SEM_TYPES.map((tp) => `<button class="facet ${state.sem.entSel === tp ? "on" : ""}" data-act="semFacet" data-t="${tp}"><span class="tdot" style="background:var(--t-${tp})"></span>${esc(semTypeLabel(tp))}</button>`).join("")}
    </div>
    <div class="tiny muted" style="margin-top:8px">${t("sem.ent.facetNote")}</div>
  </div>`;
}

function entLandingHTML() {
  return `<div class="sec-title" style="margin-top:0">${esc(t("sem.ent.landing"))} <small>${esc(t("sem.ent.landingSub"))}</small></div>
  <div class="type-tiles">${SEM_TYPES.map((tp) => `
    <button class="type-tile" data-act="semFacet" data-t="${tp === state.sem.entSel ? "" : tp}">
      <span class="tt-n"><span class="tdot" style="background:var(--t-${tp})"></span>${esc(semTypeLabel(tp))}</span>
      <span class="tt-s mono">${tp}</span>
      <span class="tt-s">${esc(t("sem.ent.tileHint"))}</span>
    </button>`).join("")}</div>
  <div class="note" style="margin-top:16px">${t("sem.ent.landingNote")}</div>`;
}

function entResultsHTML() {
  const r = state.sem.results;
  if (state.sem.searching) return loadingHTML("semantic");
  const rows = (r && r.entities) || [];
  if (!rows.length) {
    return `<div class="empty" style="padding:28px var(--s5)"><h3>${esc(t("sem.ent.noHit.title"))}</h3>
      <p>${t("sem.ent.noHit.body", { q: esc(r ? r.q : ""), type: esc(state.sem.entSel ? semTypeLabel(state.sem.entSel) : "") })}</p>
      <p style="margin-top:10px"><button class="btn ghost sm" data-act="semFacet" data-t="">${esc(t("sem.ent.clearFacet"))}</button></p></div>`;
  }
  const viaLabel = (via) => {
    const key = "sem.via." + via;
    return t(key) === key ? via : t(key);
  };
  return `<div class="tiny muted" style="margin:2px 0 8px">${t("sem.ent.resultMeta", { n: rows.length, q: esc(r.q) })}</div>
  <table class="ledger"><thead><tr><th>${esc(t("sem.ent.col.name"))}</th><th>${esc(t("sem.ent.col.type"))}</th><th>${esc(t("sem.ent.col.key"))}</th><th>${esc(t("sem.ent.col.brief"))}</th><th class="num">${esc(t("sem.ent.col.score"))}</th><th>${esc(t("sem.ent.col.via"))}</th></tr></thead>
    <tbody>${rows.map((e) => `<tr class="clickable" data-act="semOpen" data-id="${esc(e.id)}">
      <td><span class="tdot" style="background:var(--t-${esc(e.type)})"></span> <b class="t-title">${esc(e.name || e.id)}</b></td>
      <td class="tiny">${esc(semTypeLabel(e.type))}</td>
      <td class="mono tiny">${esc(e.key || "")}</td>
      <td class="tiny muted">${esc(e.brief || "—")}</td>
      <td class="num mono tiny">${esc(Number(e.score || 0).toFixed(2))}</td>
      <td><span class="tag">${esc(viaLabel(e.via))}</span></td>
    </tr>`).join("")}</tbody></table>`;
}

function entitiesHTML() {
  if (state.sem.detailId != null) return semDetailWrapHTML();
  return `${entToolbarHTML()}<div style="margin-top:16px">
    ${state.sem.results ? entResultsHTML() : entLandingHTML()}</div>`;
}

/* ---------- 实体详情（对象图 + 关系列表 + describe_table 透传） ---------- */

function semDetailWrapHTML() {
  if (state.sem.detailLoading) return loadingHTML("semantic");
  if (state.sem.detail404) {
    return `<div class="empty"><h3>404 · ${esc(t("sem.ent.notFound.title"))}</h3><p>${t("sem.ent.notFound.body")}</p>
      <p style="margin-top:10px"><button class="btn ghost sm" data-act="semBack">${esc(t("sem.ent.back"))}</button></p></div>`;
  }
  const d = state.sem.detail;
  if (!d) return loadingHTML("semantic");
  return entDetailHTML(d);
}

function semGraphGroups(d) {
  const focus = d.entity.id;
  const byId = new Map((d.nodes || []).map((n) => [n.id, n]));
  const groups = new Map();
  for (const e of d.edges || []) {
    let dir, other;
    if (e.src === focus) { dir = ">"; other = e.dst; }
    else if (e.dst === focus) { dir = "<"; other = e.src; }
    else continue; // depth 2 的次级边（两端均非焦点）——图布局单独处理
    const gk = e.rel + dir;
    if (!groups.has(gk)) groups.set(gk, { rel: e.rel, dir, all: [] });
    groups.get(gk).all.push({ id: other, node: byId.get(other) || { id: other, type: "?", key: "", name: "?" }, source: e.source });
  }
  for (const g of groups.values()) {
    g.all.sort((a, b) => (b.source === "curated") - (a.source === "curated")); // 人工关系优先展示
    g.shown = g.all.slice(0, SEM_GROUP_CAP);
    g.hidden = g.all.slice(SEM_GROUP_CAP);
  }
  return [...groups.values()];
}

function entDetailHTML(d) {
  const ent = d.entity;
  const curated = ent.curated || {};
  const attrs = ent.attrs || {};
  const aliases = ent.aliases || [];
  const groups = semGraphGroups(d);
  const relTotal = (d.edges || []).length;
  const relHidden = groups.reduce((a, g) => a + g.hidden.length, 0);
  const attrKeys = Object.entries(attrs).filter(([k, v]) => v != null && v !== "" && k !== "definition" && k !== "comment");
  return `<div class="ent-detail">
  <button class="btn ghost sm ent-back" data-act="semBack">← ${esc(t("sem.ent.back"))}</button>
  <div class="ent-head">
    <div style="flex:1;min-width:0">
      <span class="ent-type" style="background:var(--t-${esc(ent.type)})">${esc(semTypeLabel(ent.type))}</span>
      <h2>${esc(ent.name)}</h2>
      <div class="ent-key">${esc(ent.type)}:${esc(ent.key)} · id=${esc(ent.id)}</div>
      <div class="chips" style="margin-top:8px">
        <span class="tag">${esc(t("sem.st." + ent.status) === "sem.st." + ent.status ? ent.status : t("sem.st." + ent.status))}</span>
        ${curated.definition ? `<span class="tag moss">${esc(t("sem.ent.curatedTag"))}</span>` : `<span class="tag">${esc(t("sem.ent.syncOnlyTag"))}</span>`}
        ${d.dict_rev != null ? `<span class="tag">${esc(t("sem.dictRev", { rev: d.dict_rev }))}</span>` : ""}
      </div>
    </div>
    <div style="text-align:right"><div class="tiny muted" style="margin-bottom:4px">${esc(t("sem.ent.depth"))}</div>
      <div class="seg">${[1, 2].map((x) => `<button class="${state.sem.depth === x ? "on" : ""}" data-act="semDepth" data-v="${x}">${x}</button>`).join("")}</div>
      <div class="tiny muted" style="margin-top:4px">${esc(t("sem.ent.depthNote"))}</div></div>
  </div>
  <div class="ent-cols">
    <div>
      ${curated.definition ? `<div class="defn-k" style="margin-top:0">${esc(t("sem.ent.defn"))}</div><div class="defn">${esc(curated.definition)}</div>` : `<div class="tiny muted">${t("sem.ent.noCurated")}</div>`}
      ${curated.caliber ? `<div class="defn-k">${esc(t("sem.ent.caliber"))}</div><div class="defn" style="font-size:.94rem">${esc(curated.caliber)}</div>` : ""}
      ${curated.disamb ? `<div class="defn-k">${esc(t("sem.ent.disamb"))}</div><div class="defn" style="font-size:.94rem">${esc(curated.disamb)}</div>` : ""}
      ${curated.why ? `<div class="defn-k">${esc(t("sem.ent.why"))}</div><div class="defn" style="font-size:.94rem">${esc(curated.why)}</div>` : ""}
      ${attrKeys.length ? `<div class="defn-k">${esc(t("sem.ent.attrs"))}</div><div class="kv" style="grid-template-columns:110px 1fr">${attrKeys.map(([k, v]) => `<dt class="mono tiny">${esc(k)}</dt><dd class="tiny">${esc(typeof v === "object" ? JSON.stringify(v) : String(v))}</dd>`).join("")}</div>` : ""}
      <div class="defn-k">${esc(t("sem.ent.aliases"))} · ${aliases.length}</div>
      <div>${aliases.length ? aliases.map((a) => `<span class="alias">${esc(a)}</span>`).join("") : `<span class="tiny muted">${esc(t("sem.ent.noAlias"))}</span>`}</div>
      <div class="defn-k">${esc(t("sem.ent.rels"))} · ${relTotal} <span class="muted" style="font-weight:400">· ${groups.length} ${esc(t("sem.ent.relGroups"))}${relHidden && !state.sem.relAll ? ` · ${esc(t("sem.ent.groupCap", { n: SEM_GROUP_CAP }))}` : ""}${d.truncated ? ` · ${esc(t("sem.ent.truncated"))}` : ""}</span></div>
      <div class="rel-list">${groups.length ? groups.map((g) => `
        <div class="rl-h"><code style="color:${SEM_REL_COLORS[g.rel] || "inherit"}">${g.dir === "<" ? "← " : ""}${esc(g.rel)}${g.dir === ">" ? " →" : ""}</code><span class="tiny muted">${g.all.length}${g.hidden.length && !state.sem.relAll ? ` · ${esc(t("sem.ent.showFirst", { n: SEM_GROUP_CAP }))}` : ""}</span></div>
        ${(state.sem.relAll ? g.all : g.shown).map((n) => `<div class="rl g"><button data-act="semOpen" data-id="${esc(n.id)}"><span class="tdot" style="background:var(--t-${esc(n.node.type)})"></span> ${esc(n.node.name)}</button>
          <span class="tiny muted">${n.source === "curated" ? esc(t("sem.src.curated")) : esc(t("sem.src.sync"))}</span></div>`).join("")}`).join("") : `<div class="tiny muted">${esc(t("sem.ent.isolated"))}</div>`}
        ${relHidden ? `<div class="rel-more"><button class="link tiny" data-act="semRelMore">${state.sem.relAll ? esc(t("sem.ent.relCollapse")) : esc(t("sem.ent.relMore", { n: relHidden }))}</button><span class="tiny muted">${t("sem.ent.relMoreNote")}</span></div>` : ""}</div>
    </div>
    <div>${semGraphSVG(d)}
      <div class="tiny muted" style="margin-top:6px">${t("sem.ent.graphNote", { n: SEM_GROUP_CAP })}</div></div>
  </div>
  ${ent.type === "table" ? semDescribeHTML(d) : ""}
  <div class="tiny muted" style="margin-top:16px"><code>GET /api/orgs/${esc(cfg.org)}/semantic/entities/${esc(ent.id)}?depth=${state.sem.depth}</code> ≡ MCP <code>get_entity</code></div>
  </div>`;
}

/* 对象图 SVG：客户端布局沿原型 graphSVG 思路——一圈槽位按组排布（组内前 3 +
 * +N 占位），depth 2 时沿已展示邻居再展开一圈（每组 ≤ GROUP_CAP，去重防环） */
function semGraphSVG(d) {
  const W = 680, H = 420, cx = W / 2, cy = H / 2;
  const focus = d.entity.id;
  const byId = new Map((d.nodes || []).map((n) => [n.id, n]));
  const groups = semGraphGroups(d);
  const slots = groups.flatMap((g) => [...g.shown.map((n) => ({ kind: "n", n, g })), ...(g.hidden.length ? [{ kind: "+", g, id: "+:" + g.rel + g.dir }] : [])]);
  const pos = new Map([[focus, { x: cx, y: cy }]]);
  const tw = (s) => [...String(s)].reduce((w, ch) => w + (/[\x00-\x7f]/.test(ch) ? 6.6 : 11.6), 18);
  const lbl = (s) => { s = String(s); return [...s].length > 14 ? [...s].slice(0, 13).join("") + "…" : s; };
  const [rx1, ry1] = state.sem.depth === 1 ? [230, 142] : [152, 94];
  slots.forEach((s, i) => {
    const a = -Math.PI / 2 + (i + 0.5) / slots.length * 2 * Math.PI;
    pos.set(s.kind === "n" ? s.n.id : s.id, { x: cx + rx1 * Math.cos(a), y: cy + ry1 * Math.sin(a) });
  });
  // depth 2：只沿「已展示」的邻居展开（服务端 edges 里两端均在图内的次级边）
  const placed = new Set([focus, ...groups.flatMap((g) => g.shown.map((n) => n.id))]);
  const r2 = [];
  if (state.sem.depth === 2) {
    for (const s of slots) {
      if (s.kind !== "n") continue;
      let c = 0;
      for (const e of d.edges || []) {
        if (c >= SEM_GROUP_CAP) break;
        let other = null;
        if (e.src === s.n.id) other = e.dst;
        else if (e.dst === s.n.id) other = e.src;
        if (other == null || other === focus || placed.has(other)) continue;
        placed.add(other);
        r2.push({ from: s.n.id, to: other, rel: e.rel });
        c++;
      }
    }
  }
  r2.forEach((x, i) => {
    const a = -Math.PI / 2 + (i + 0.5) / r2.length * 2 * Math.PI;
    pos.set(x.to, { x: cx + 268 * Math.cos(a), y: cy + 178 * Math.sin(a) });
  });
  const clampX = (x, w) => Math.max(w / 2 + 4, Math.min(W - w / 2 - 4, x));
  const nodes = [...pos.keys()].map((x) => {
    const isChip = String(x).startsWith("+:");
    const g = isChip ? groups.find((gr) => gr.rel + gr.dir === String(x).slice(2)) : null;
    const n = isChip ? null : (x === focus ? d.entity : byId.get(x));
    const text = isChip ? `+${g.hidden.length} ${t("sem.ent.more")}` : lbl(n.name);
    const w = Math.min(176, tw(text));
    const p = pos.get(x);
    return { x, g, n, isChip, text, w, px: clampX(p.x, w), py: p.y };
  });
  const np = new Map(nodes.map((n) => [n.x, n]));
  const edges = [];
  for (const g of groups) g.shown.forEach((n, i) => edges.push({ a: focus, b: n.id, g, lab: i === 0 }));
  for (const g of groups) if (g.hidden.length) edges.push({ a: focus, b: "+:" + g.rel + g.dir, g, dash: true });
  for (const r of r2) edges.push({ a: r.from, b: r.to, g: { rel: r.rel, dir: ">" } });
  return `<svg class="graph" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(d.entity.name)} ${esc(t("sem.ent.graphAria", { n: groups.length, cap: SEM_GROUP_CAP, depth: state.sem.depth }))}">
    ${edges.map((e2) => {
      const A = np.get(e2.a), B = np.get(e2.b);
      if (!A || !B) return "";
      const col = SEM_REL_COLORS[e2.g.rel] || "#D0D5DD";
      return `<line class="edge" style="stroke:${col}${e2.dash ? ";stroke-dasharray:4 3;opacity:.8" : ""}" x1="${A.px.toFixed(1)}" y1="${A.py.toFixed(1)}" x2="${B.px.toFixed(1)}" y2="${B.py.toFixed(1)}"></line>${e2.lab ? `<text class="elabel" style="fill:${col}" x="${((A.px + B.px) / 2).toFixed(1)}" y="${((A.py + B.py) / 2 - 3).toFixed(1)}" text-anchor="middle">${esc(e2.g.dir === "<" ? "← " : "")}${esc(e2.g.rel)}${esc(e2.g.dir === ">" ? " →" : "")}</text>` : ""}`;
    }).join("")}
    ${nodes.map((n) => {
      if (n.isChip) return `<g class="node more" data-act="semMore" data-n="${n.g.hidden.length}" transform="translate(${n.px.toFixed(1)},${n.py.toFixed(1)})">
        <title>${esc(t("sem.ent.moreTitle", { n: n.g.hidden.length, rel: n.g.rel }))}</title>
        <rect x="${-n.w / 2}" y="-13" width="${n.w}" height="26" rx="7" style="fill:var(--paper-2);stroke:${SEM_REL_COLORS[n.g.rel] || "#D0D5DD"};stroke-dasharray:5 3"></rect>
        <text text-anchor="middle" dy="4">+${n.g.hidden.length} ${esc(t("sem.ent.more"))}</text></g>`;
      const tp = n.x === focus ? d.entity.type : n.n.type;
      const c = n.x === focus;
      return `<g class="node ${c ? "center" : ""}" data-act="semOpen" data-id="${esc(n.x)}" transform="translate(${n.px.toFixed(1)},${n.py.toFixed(1)})">
        <title>${esc(semTypeLabel(tp))} · ${esc(n.n.name)} · ${esc(n.n.key || "")}</title>
        <rect x="${-n.w / 2}" y="-13" width="${n.w}" height="26" rx="7" style="fill:${c ? `var(--t-${tp})` : `color-mix(in oklch, var(--t-${tp === "?" ? "system" : tp}) 16%, var(--paper))`}"></rect>
        <text text-anchor="middle" dy="4" ${c ? `style="fill:var(--paper)"` : ""}>${esc(n.text)}</text></g>`;
    }).join("")}
  </svg>`;
}

/* describe_table 透传面板（type=table 时）——契约：{table,name,columns[{name,
 * type?,comment?,sample?}],degraded}；列与 has_column 端点（column 实体）对齐 */
function semDescribeHTML(d) {
  const desc = state.sem.describe;
  const tableKey = d.entity.key;
  const colNodes = new Map();
  for (const e of d.edges || []) {
    if (e.src === d.entity.id && e.rel === "has_column") {
      const n = (d.nodes || []).find((x) => x.id === e.dst);
      if (n) colNodes.set(n.key.slice(n.key.lastIndexOf(".") + 1), n);
    }
  }
  let bodyHTML = "";
  if (!desc) {
    bodyHTML = `<div style="padding:12px"><button class="btn sm" data-act="semDescribe">${esc(t("sem.desc.load"))}</button>
      <span class="tiny muted" style="margin-left:8px">${t("sem.desc.note")}</span></div>`;
  } else if (desc.loading) {
    bodyHTML = `<div style="padding:12px">${esc(t("common.loading", { what: "describe_table" }))}</div>`;
  } else if (desc.error) {
    bodyHTML = `<div style="padding:12px"><div class="note seal" style="margin:0">${t("sem.desc.denied", { status: desc.error })}</div></div>`;
  } else {
    const cols = desc.columns || [];
    bodyHTML = `
      <dl class="kv" style="padding:10px 12px 0;grid-template-columns:76px 1fr">
        <dt>${esc(t("sem.desc.table"))}</dt><dd class="mono tiny">${esc(desc.table)}</dd>
        <dt>${esc(t("sem.desc.name"))}</dt><dd>${esc(desc.name || "—")}</dd>
        <dt>${esc(t("sem.desc.degraded"))}</dt><dd>${desc.degraded ? `<span class="pill bad">${esc(t("sem.desc.degradedYes"))}</span>` : `<span class="pill ok">${esc(t("sem.desc.degradedNo"))}</span>`}</dd>
      </dl>
      <table class="ledger"><thead><tr><th>${esc(t("sem.desc.col"))}</th><th>${esc(t("sem.desc.type"))}</th><th>${esc(t("sem.desc.comment"))}</th><th>${esc(t("sem.desc.sample"))}</th><th>${esc(t("sem.desc.entity"))}</th></tr></thead>
        <tbody>${cols.length ? cols.map((c) => {
          const ce = colNodes.get(c.name);
          return `<tr><td class="mono">${esc(c.name)}</td><td class="mono tiny">${esc(c.type || "—")}</td><td class="tiny">${esc(c.comment || "—")}</td><td class="mono tiny">${esc(c.sample || "—")}</td>
            <td>${ce ? `<button class="link" data-act="semOpen" data-id="${esc(ce.id)}">${esc(t("sem.desc.registered"))}</button>` : `<span class="tiny muted">—</span>`}</td></tr>`;
        }).join("") : `<tr><td colspan="5" class="tiny muted" style="padding:16px">${esc(t("sem.desc.noCols"))}</td></tr>`}</tbody></table>
      ${desc.degraded ? `<div style="padding:0 12px 12px"><div class="note amber" style="margin:0">${t("sem.desc.degradedNote")}</div></div>` : ""}`;
  }
  return `<div class="passthru">
    <div class="pt-h"><b>describe_table</b><span class="tiny muted">${t("sem.desc.headNote")}</span></div>
    ${bodyHTML}
  </div>`;
}

/* ---------- 术语识别子标签 ---------- */

function annMarkHTML(text, mentions) {
  let out = "", p = 0;
  for (const m of mentions) {
    const s = m.span[0], e = m.span[1];
    if (s < p) continue; // 防御：重叠按服务端契约不应出现
    out += esc(text.slice(p, s));
    const cls = m.matched_by === "context" ? "L2" : "L1";
    out += `<mark class="${cls}" style="color:var(--t-${esc(m.type)})" title="${esc(semTypeLabel(m.type))} · ${esc(m.name)}"><span class="mt">${esc(m.name)}</span>${esc(m.surface)}</mark>`;
    p = e;
  }
  return out + esc(text.slice(p));
}

function annResultHTML() {
  const r = state.sem.annResult;
  if (!r) return "";
  const mentions = r.mentions || [];
  const candidates = r.candidates || [];
  const layerCn = (m) => m.matched_by === "context"
    ? t("sem.ann.layerContext")
    : (t("sem.ann.layerExact") + " · " + (m.matched_by || ""));
  return `<div class="ann-out"><div class="annot" style="font-size:15px;line-height:2.4">${mentions.length ? annMarkHTML(state.sem.annText, mentions) : `<span class="muted">${esc(t("sem.ann.noMention"))}</span>`}</div></div>
  <div class="layer-key"><span><i></i>${esc(t("sem.ann.l1"))}</span><span><i class="L2"></i>${esc(t("sem.ann.l2"))}</span></div>
  <table class="ledger" style="margin-top:16px"><thead><tr><th>${esc(t("sem.ann.col.surface"))}</th><th>${esc(t("sem.ann.col.entity"))}</th><th>${esc(t("sem.ann.col.type"))}</th><th>${esc(t("sem.ann.col.layer"))}</th><th>${esc(t("sem.ann.col.basis"))}</th></tr></thead>
    <tbody>${mentions.length ? mentions.map((m) => `<tr>
      <td><b>${esc(m.surface)}</b></td>
      <td><button class="link" data-act="semOpenTab" data-id="${esc(m.entity_id)}">${esc(m.name)}</button><div class="t-sub mono">${esc(m.entity_key || "")}</div></td>
      <td><span class="tdot" style="background:var(--t-${esc(m.type)})"></span> ${esc(semTypeLabel(m.type))}</td>
      <td class="tiny">${esc(layerCn(m))}${m.ambiguous ? ` <span class="tag amber">${esc(t("sem.ann.ambiguous"))}</span>` : ""}</td>
      <td class="tiny muted">${esc(t("sem.ann.basis", { conf: m.confidence, by: m.resolved_by || "" }))}${m.brief ? `<div>${esc(m.brief)}</div>` : ""}</td>
    </tr>`).join("") : `<tr><td colspan="5" class="tiny muted" style="padding:16px">${esc(t("sem.ann.noMention"))}</td></tr>`}
    ${candidates.length ? candidates.map((c) => `<tr style="opacity:.6">
      <td>${esc(c.surface || c.name || "")}</td>
      <td><button class="link" data-act="semOpenTab" data-id="${esc(c.entity_id)}">${esc(c.name)}</button></td>
      <td><span class="tdot" style="background:var(--t-${esc(c.type)})"></span> ${esc(semTypeLabel(c.type))}</td>
      <td class="tiny">${esc(t("sem.ann.candidate"))}</td>
      <td class="tiny muted">${c.via === "fuzzy"
        ? esc(t("sem.ann.fuzzyBasis", { layer: c.fuzzy_layer || "", term: c.term || "", conf: c.confidence }))
        : esc(t("sem.ann.acCandidate"))}</td>
    </tr>`).join("") : ""}</tbody></table>`;
}

function annotateHTML() {
  return `<div>
    <div class="toolbar" style="margin-bottom:8px"><span class="tiny muted">${t("sem.ann.head", { rev: state.sem.dictRev })}</span><span style="flex:1"></span>
      <label class="switch"><input type="checkbox" data-in="semFuzzy" ${state.sem.fuzzy ? "checked" : ""}><span>${esc(t("sem.ann.fuzzy"))}</span></label></div>
    <textarea class="ann-in" data-in="semAnn" aria-label="${esc(t("sem.ann.ph"))}" placeholder="${esc(t("sem.ann.ph"))}">${esc(state.sem.annText)}</textarea>
    <div class="inline-act" style="margin:8px 0">
      <button class="btn seal-btn" data-act="semAnnotate" ${state.sem.annBusy ? "disabled" : ""}>${esc(t("sem.ann.go"))}</button>
      <span class="tiny muted">${t("sem.ann.note")}</span>
    </div>
    ${state.sem.annResult ? annResultHTML() : ""}
    <div class="note" style="margin-top:16px">${t("sem.ann.foot")}</div>
  </div>`;
}

/* ---------- 同步与构建子标签（semantic:admin） ---------- */

function semRunStatsSummary(statsJson) {
  let s = {};
  try { s = JSON.parse(statsJson || "{}"); } catch (e) { return ""; }
  const parts = [];
  if (s.inserted != null) parts.push(t("sem.sync.statIns") + " " + s.inserted);
  if (s.updated != null) parts.push(t("sem.sync.statUpd") + " " + s.updated);
  if (s.missing != null) parts.push(t("sem.sync.statMiss") + " " + s.missing);
  if (s.retired != null) parts.push(t("sem.sync.statRet") + " " + s.retired);
  return parts.join(" · ");
}

function syncHTML() {
  const admin = state.sem.admin;
  const runs = (state.sem.syncRuns && state.sem.syncRuns.runs) || [];
  const latestOf = (a) => runs.find((r) => r.adapter === a);
  return `
  ${!admin ? `<div class="note amber" style="margin-bottom:16px">${t("sem.sync.needAdmin")}</div>` : ""}
  <div class="sec-title">${esc(t("sem.sync.title"))} <small>${esc(t("sem.sync.titleSub"))}</small></div>
  <table class="ledger"><thead><tr><th>${esc(t("sem.sync.col.adapter"))}</th><th>${esc(t("sem.sync.col.last"))}</th><th>${esc(t("sem.sync.col.status"))}</th><th>${esc(t("sem.sync.col.stats"))}</th><th></th><th>${esc(t("sem.sync.col.note"))}</th></tr></thead>
    <tbody>${SEM_ADAPTERS.map((a) => {
      if (a === "yaml") return `<tr><td class="mono">yaml<div class="tiny muted" style="font-weight:400">${esc(t("sem.sync.ad.yaml"))}</div></td>
        <td><span class="tiny muted">—</span></td><td><span class="tag">webhook</span></td>
        <td><span class="tiny muted">—</span></td><td><span class="tiny muted">—</span></td>
        <td class="tiny">${t("sem.sync.yamlNote")}</td></tr>`;
      const r = latestOf(a);
      return `<tr><td class="mono">${a}<div class="tiny muted" style="font-weight:400">${esc(t("sem.sync.ad." + a))}</div></td>
        <td>${r ? `<span class="mono tiny">${esc(short(r.started_at))}</span>` : `<span class="tiny muted">—</span>`}</td>
        <td>${r ? semPill(r.status) : `<span class="tiny muted">—</span>`}</td>
        <td class="tiny muted">${r ? esc(semRunStatsSummary(r.stats_json)) : ""}</td>
        <td><button class="btn ghost sm" data-act="semSync" data-a="${a}" ${admin && state.sem.syncBusy !== a ? "" : "disabled"} title="POST /semantic/sync/${a}">↻ ${esc(t("sem.sync.manual"))}</button></td>
        <td class="tiny" title="${esc((r && r.error) || "")}">${r && r.error ? esc(String(r.error).slice(0, 60)) : `<span class="muted">—</span>`}</td></tr>`;
    }).join("")}</tbody></table>
  <div class="note" style="margin-top:12px">${t("sem.sync.foot")}</div>

  <div class="sec-title">${esc(t("sem.sync.history"))} <small>${esc(t("sem.sync.historySub"))}</small></div>
  <div class="inline-act" style="margin-bottom:8px">
    <label class="tiny muted">${esc(t("sem.sync.filter"))}</label>
    <select class="sel" data-in="semSyncFilter" style="min-width:180px">
      <option value="">${esc(t("sem.sync.filterAll"))}</option>
      ${SEM_ADAPTERS.map((a) => `<option value="${a}" ${state.sem.syncFilter === a ? "selected" : ""}>${a}</option>`).join("")}
    </select>
  </div>
  ${state.sem.syncRunsErr ? `<div class="tiny muted">${esc(t("sem.sync.runsDenied", { status: state.sem.syncRunsErr }))}</div>` : `
  <table class="ledger"><thead><tr><th>${esc(t("sem.run.col.time"))}</th><th>${esc(t("sem.run.col.adapter"))}</th><th>${esc(t("sem.run.col.status"))}</th><th>${esc(t("sem.run.col.stats"))}</th><th>${esc(t("sem.run.col.note"))}</th></tr></thead>
    <tbody>${runs.length ? runs.map((r) => `<tr>
      <td class="mono tiny">${esc(short(r.started_at))}</td>
      <td class="mono tiny">${esc(r.adapter)}</td>
      <td>${semPill(r.status)}</td>
      <td class="tiny muted">${esc(semRunStatsSummary(r.stats_json))}</td>
      <td class="tiny muted">${esc(r.error ? String(r.error).slice(0, 80) : "—")}</td>
    </tr>`).join("") : `<tr><td colspan="5" class="tiny muted" style="padding:16px">${esc(t("sem.sync.noRuns"))}</td></tr>`}</tbody></table>`}

  <div class="sec-title">${esc(t("sem.build.title"))} <small>${esc(t("sem.build.titleSub"))}</small></div>
  ${state.sem.buildsErr ? `<div class="tiny muted">${esc(t("sem.sync.runsDenied", { status: state.sem.buildsErr }))}</div>` : semBuildsHTML()}
  <div class="inline-act" style="margin-top:10px">
    <button class="btn" data-act="semBuild" ${admin ? "" : "disabled"}>POST /semantic/builds</button>
    <span class="tiny muted">${t("sem.build.triggerNote")}</span>
  </div>
  ${state.sem.buildReportData ? semBuildReportHTML(state.sem.buildReportData) : ""}

  <div class="sec-title">${esc(t("sem.l0.title"))} <small>GET /semantic/l0</small></div>
  ${semL0HTML()}
  `;
}

function semBuildsHTML() {
  const data = state.sem.builds || {};
  const builds = data.builds || [];
  const current = data.current;
  return `<table class="ledger"><thead><tr><th>dict_rev</th><th>${esc(t("sem.build.col.status"))}</th><th>${esc(t("sem.build.col.time"))}</th><th>${esc(t("sem.build.col.yamlRev"))}</th><th></th></tr></thead>
    <tbody>${builds.length ? builds.map((b) => `<tr class="${current && b.id === current.id ? "on" : ""}">
      <td class="mono"><b>${esc(b.dict_rev)}</b>${current && b.id === current.id ? ` <span class="tag moss">${esc(t("sem.build.current"))}</span>` : ""}</td>
      <td>${semPill(b.status)}</td>
      <td class="mono tiny">${esc(short(b.created_at))}</td>
      <td class="mono tiny">${esc(b.yaml_rev || "—")}</td>
      <td><button class="btn ghost sm" data-act="semReport" data-id="${esc(b.id)}">${esc(t("sem.build.report"))}</button></td>
    </tr>`).join("") : `<tr><td colspan="5" class="tiny muted" style="padding:16px">${esc(t("sem.build.noBuilds"))}</td></tr>`}</tbody></table>`;
}

function semBuildReportHTML(rep) {
  const counts = rep.counts || {};
  const byType = counts.entities_by_type || {};
  const ac = rep.ac_automaton || {};
  const conflicts = rep.conflicts || {};
  const conflictCount = Object.values(conflicts).reduce((a, x) => a + x.length, 0);
  return `<details style="margin-top:12px" open>
    <summary>${esc(t("sem.build.reportTitle", { id: rep.build_id, rev: rep.dict_rev }))}</summary>
    <dl class="kv" style="margin-top:10px;grid-template-columns:140px 1fr">
      <dt class="mono tiny">counts.entities</dt><dd class="tiny"><b>${esc(counts.entities ?? "—")}</b>${Object.keys(byType).length ? `（${Object.entries(byType).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(t("common.sep"))}）` : ""}</dd>
      <dt class="mono tiny">counts.aliases</dt><dd class="tiny">${esc(counts.aliases ?? "—")}</dd>
      <dt class="mono tiny">counts.relations</dt><dd class="tiny">${esc(counts.relations ?? "—")}</dd>
      <dt class="mono tiny">ac_automaton</dt><dd class="tiny mono">${ac.keys != null ? `keys=${esc(ac.keys)} · words=${esc(ac.words)} · build_ms=${esc(ac.build_ms)}` : "—"}</dd>
      <dt class="mono tiny">ambiguous_aliases</dt><dd class="tiny">${rep.ambiguous_aliases != null ? esc(JSON.stringify(rep.ambiguous_aliases).slice(0, 200)) : "—"}</dd>
      <dt class="mono tiny">orphan_nodes</dt><dd class="tiny">${rep.orphan_nodes != null ? esc(JSON.stringify(rep.orphan_nodes).slice(0, 200)) : "—"}</dd>
      <dt class="mono tiny">broken_relations</dt><dd class="tiny">${rep.broken_relations != null ? esc(JSON.stringify(rep.broken_relations).slice(0, 200)) : "—"}</dd>
      <dt class="mono tiny">missing_sources</dt><dd class="tiny">${rep.missing_sources != null ? esc(JSON.stringify(rep.missing_sources).slice(0, 200)) : "—"}</dd>
      <dt class="mono tiny">conflicts</dt><dd class="tiny">${conflictCount ? `<span class="tag amber">${conflictCount}</span> ${esc(Object.keys(conflicts).join(t("common.sep")))}` : "—"}</dd>
    </dl>
  </details>`;
}

function semL0HTML() {
  if (state.sem.l0Err) return `<div class="note seal" style="margin:0">${esc(state.sem.l0Err)}</div>`;
  const l0 = state.sem.l0;
  if (!l0) return "";
  const frags = l0.fragments || [];
  return `<div class="tiny muted" style="margin-bottom:8px">${t("sem.l0.meta", { n: frags.length, tokens: l0.token_estimate ?? 0 })}</div>
  ${frags.length ? `<div class="sql" style="white-space:pre-wrap">${esc(frags.map((f) => f.text).join("\n"))}</div>` : `<div class="tiny muted">${esc(t("sem.l0.empty"))}</div>`}
  <div class="chips" style="margin-top:8px">${frags.map((f) => `<button class="chip" data-act="semOpenTab" data-key="${esc(f.entity_key)}" style="color:var(--t-${esc(f.type)})">${esc(f.name)}</button>`).join("")}</div>`;
}

/* ---------- 数据装载 ---------- */

async function semLoadSyncTab() {
  if (state.sem.admin) {
    if (state.sem.syncRuns == null || state.sem.syncRunsErr) {
      try {
        state.sem.syncRuns = await listSyncRuns(cfg.org, { limit: 50 });
        state.sem.syncRunsErr = null;
      } catch (e) { state.sem.syncRunsErr = e.status || 0; }
    }
    if (state.sem.builds == null || state.sem.buildsErr) {
      try {
        state.sem.builds = await listBuilds(cfg.org, { limit: 50 });
        state.sem.buildsErr = null;
      } catch (e) { state.sem.buildsErr = e.status || 0; }
    }
  } else {
    // 非 admin：数据面探针 403 如实回显（语义侧只读注记 + 运行历史不可用）
    try {
      state.sem.syncRuns = await listSyncRuns(cfg.org, { limit: 50 });
      state.sem.syncRunsErr = null;
    } catch (e) { state.sem.syncRunsErr = e.status || 0; }
  }
  try {
    state.sem.l0 = await getL0(cfg.org);
    state.sem.l0Err = null;
    if (state.sem.l0.dict_rev != null) state.sem.dictRev = state.sem.l0.dict_rev;
  } catch (e) { state.sem.l0Err = e.status ? (String(e.status) + " · " + String((e && e.message) || "")) : String(e); }
}

async function semLoadEntity(id) {
  state.sem.detailId = id;
  state.sem.detail = null;
  state.sem.detail404 = false;
  state.sem.detailLoading = true;
  state.sem.relAll = false;
  state.sem.describe = null;
  render();
  try {
    state.sem.detail = await getSemanticEntity(cfg.org, id, {
      depth: state.sem.depth, include: ["curated", "attrs", "aliases"],
    });
  } catch (e) {
    if (e.status === 404) state.sem.detail404 = true; // 不存在/无权/非 active——存在性零泄露
    else errToast(e);
  } finally {
    state.sem.detailLoading = false;
    render();
  }
}

/* ---------- 动作与输入 ---------- */

Object.assign(actions, {
  /* ----- 实体与关系 ----- */
  async semSearch() {
    const q = state.sem.q.trim();
    if (!q || state.sem.searching) return false;
    state.sem.searching = true;
    state.sem.detailId = null; state.sem.detail = null;
    render();
    try {
      const body = await searchSemanticEntities(cfg.org, {
        q, types: state.sem.entSel ? [state.sem.entSel] : [], top_k: 20,
      });
      state.sem.results = { q, entities: body.entities || [] };
    } catch (e) {
      errToast(e);
      state.sem.results = null;
    } finally {
      state.sem.searching = false;
      render();
    }
    return false;
  },
  semFacet(el) {
    const tp = el.dataset.t;
    state.sem.entSel = tp || null;
    state.sem.detailId = null; state.sem.detail = null;
    if (state.sem.q.trim()) return actions.semSearch(); // 有关键词 = 立即按新 facet 重搜
    state.sem.results = null; // 无关键词 = 回落地页（type-only 浏览无契约——诚实差异）
    return false;
  },
  semOpen(el) { semLoadEntity(Number(el.dataset.id)); return false; },
  semOpenTab(el) {
    state.sub.sem = "entities";
    if (el.dataset.id) semLoadEntity(Number(el.dataset.id));
    else if (el.dataset.key) {
      // key 形如 type:name——REST 路径只有 {entity_id}（int）：先经搜索直达
      const tp = String(el.dataset.key).split(":")[0];
      const q = String(el.dataset.key).split(":").slice(1).join(":");
      state.sem.q = q; state.sem.entSel = tp;
      actions.semSearch();
    }
    return false;
  },
  semBack() {
    state.sem.detailId = null; state.sem.detail = null; state.sem.detail404 = false;
    state.sem.describe = null;
  },
  semDepth(el) {
    const v = Number(el.dataset.v);
    if (v === state.sem.depth) return false;
    state.sem.depth = v;
    if (state.sem.detailId != null) semLoadEntity(state.sem.detailId); // 深度切换 = refetch
    return false;
  },
  semMore(el) {
    state.sem.relAll = true;
    toast(t("sem.ent.moreToast", { n: el.dataset.n }));
    // 不 return false——落回默认 render 展开全量关系列表
  },
  semRelMore() { state.sem.relAll = !state.sem.relAll; },
  async semDescribe() {
    const d = state.sem.detail;
    if (!d) return false;
    state.sem.describe = { loading: true };
    render();
    try {
      state.sem.describe = await describeTable(cfg.org, d.entity.key);
    } catch (e) {
      state.sem.describe = { error: e.status || 0 };
    }
    render();
    return false;
  },

  /* ----- 术语识别 ----- */
  async semAnnotate() {
    const text = state.sem.annText.trim();
    if (!text) { toast(esc(t("sem.ann.needText"))); return false; }
    state.sem.annBusy = true;
    render();
    try {
      state.sem.annResult = await annotateText(cfg.org, { text, fuzzy: !!state.sem.fuzzy });
    } catch (e) {
      if (e.status === 400) toast(esc(String((e && e.message) || e)));
      else errToast(e);
      state.sem.annResult = null;
    } finally {
      state.sem.annBusy = false;
      render();
    }
    return false;
  },

  /* ----- 同步与构建 ----- */
  async semSync(el) {
    const a = el.dataset.a;
    state.sem.syncBusy = a;
    render();
    try {
      const body = await triggerSync(cfg.org, a);
      toast(t("sem.sync.queued", { adapter: esc(a), task: esc(body.task_id) }));
    } catch (e) {
      if (e.status === 400) toast(esc(String((e && e.message) || e))); // 源未配置 fail-fast（P3-7）
      else errToast(e);
    } finally {
      state.sem.syncBusy = "";
      state.sem.syncRuns = null; state.sem.syncRunsErr = null; // 重载运行历史
      await semLoadSyncTab();
      render();
    }
    return false;
  },
  async semSyncFilterRun() {
    const f = state.sem.syncFilter;
    try {
      state.sem.syncRuns = await listSyncRuns(cfg.org, { limit: 50, adapter: f || undefined });
      state.sem.syncRunsErr = null;
    } catch (e) { state.sem.syncRunsErr = e.status || 0; }
    render();
    return false;
  },
  async semBuild() {
    try {
      const body = await triggerBuild(cfg.org);
      toast(t("sem.build.queued", { task: esc(body.task_id) }));
    } catch (e) { errToast(e); return false; }
    state.sem.builds = null; state.sem.buildsErr = null;
    await semLoadSyncTab();
    render();
    return false;
  },
  async semReport(el) {
    const id = Number(el.dataset.id);
    try {
      state.sem.buildReportData = await buildReport(cfg.org, id);
    } catch (e) {
      if (e.status === 404) toast(t("sem.build.report404", { id }));
      else errToast(e);
      return false;
    }
    render();
    return false;
  },
});

Object.assign(INPUTS, {
  semQ: (v) => { state.sem.q = v; state.sem.detailId = null; state.sem.detail = null; },
  semAnn: (v) => { state.sem.annText = v; return false; },
  semFuzzy: (v) => { state.sem.fuzzy = v; },
  semSyncFilter: (v) => { state.sem.syncFilter = v; actions.semSyncFilterRun(); return false; },
});

VIEWS.semantic = { render: viewSemantic, onEnter: onEnterSemantic };

/* 子标签懒装载（沿 access.js 的 actions.sub 包装惯例） */
const _semSubPrev = actions.sub;
actions.sub = (el) => {
  _semSubPrev(el);
  if (el.dataset.s === "sem" && el.dataset.v === "sync") {
    semLoadSyncTab().then(() => render()).catch(() => { /* 已 toast */ });
  }
};
