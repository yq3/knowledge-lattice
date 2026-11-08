/* app.js —— 应用框架（ui-1）：状态 / 渲染循环 / 顶栏与侧栏 / 组织与身份切换 /
 * 连接设置 / 语言切换接线。视图实现见 views/*.js（VIEWS 注册表 + actions/INPUTS 扩展）。
 * 脚本协同（经典脚本，无模块）：i18n.js → api.js → 本文件 → views/*.js；
 * boot 在 DOMContentLoaded 才执行（晚于全部 script 注册）。
 */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------- 全局状态 ---------- */
const state = {
  view: "docs",
  /* epoch（R2 P1-5）：组织/身份切换即自增——异步装载函数启动时捕获、写状态与
   * render 前比对，不等即弃（防旧响应写入新视图）；pollTask 感知即停轮询。 */
  epoch: 0,
  sub: { access: "grants", sem: "entities" },
  /* 元数据缓存（组织/身份切换与语言切换时复用，不重取） */
  orgs: [],            // GET /api/orgs（activeToken 视角）——含 role（普通用户面）
  usernames: [],       // grants/export 首列（org_admin 可得）——身份菜单候选
  dims: [],            // GET dimensions（active 维度）
  datasets: [],
  /* 文档视图 */
  docs: { available: null, probed: false, loadError: null, list: [], session: [], explain: null }, // be-① 已实装；explain=选中文档解释卡 {docId, rows?, visible?, loading?, error?}
  ds: "all", selDoc: null, drawer: null, dsAsk: null, delAsk: null,
  newDs: { key: "", title: "", desc: "" },
  up: { ds: "", picked: {}, file: "", fileObj: null, overwrite: null }, // overwrite={docId,title,active} = 覆盖上传锁定（ui-3 C2）
  editDims: false, editPicked: {}, quality: null, qualDraft: {},
  /* 质检抽查面板（ui-3 C1——org_admin；GET /api/quality-flags/sample） */
  qs: { flags: null, loading: false, seed: "ui3" },
  /* 检索视图 */
  q: "", qDs: "", autoEnt: false, lastSearch: null, searching: false,
  /* 权限视图（ui-2：授权格矩阵 + 成员子标签 + 可见性占位） */
  g: { member: "", rows: [], picked: {}, expires: {}, existing: {}, prefill: "", csv: "", diff: null, diffMsg: "", detail: null, saving: "", error: null },
  mem: { addOpen: false, form: { uid: "", role: "member", expires: "" }, ask: null, expAsk: null, expVal: "", expMode: "set", roleSel: null, roleVal: "member", known: {} },
  dimNewOpen: false, dimNew: { key: "", name: "", required: false },
  valAsk: null, valNew: { v: "", l: "" }, govAsk: null, disabledVals: [],
  /* 可见性矩阵（m3-2 ui-be：org_admin members × documents 逐格 explain 取数） */
  vis: { rows: null, members: [], docs: [], cells: {}, error: null, detail: null },
  /* 语义视图（ui-2）：probe null=未探 / "ok" / "noperm" / "notbuilt" */
  sem: {
    probe: null, dictRev: null,
    q: "", entSel: "", searching: false, results: null,
    detail: null, detailId: null, detail404: false, detailErr: null, detailLoading: false, depth: 1, relAll: false,
    describe: null,
    annText: "", fuzzy: false, annResult: null, annBusy: false, annError: "",
    admin: null,               // null=未探 / true / false（semantic:admin≈org_admin）
    syncRuns: null, syncRunsErr: null, syncFilter: "", syncBusy: "", syncRunsLimit: 50, // limit 递增 50→100→200（ui-3 条数与分页）
    builds: null, buildsErr: null, buildReportId: null, buildReportData: null,
    l0: null, l0Err: null,
  },
  /* 组织视图（ui-2） */
  orgView: { list: null, askOrg: null, newOpen: false, form: { id: "", name: "", admin: "" }, loadErr: null },
  /* 运维视图（ops 平移；auditLimit 递增 50→100→200——ui-3 条数与分页） */
  ops: { tasks: null, tasksErr: null, coverage: null, audit: null, auditLimit: 50, stats: null, reembedDoc: "", reembedModel: "" },
  loading: {},
};

/* 渲染周期内标记（防轮询/异步回写触发的不必要重渲） */
let lastViewKey = "";
let booted = false;

const VIEWS = {};   // views/*.js 注册：VIEWS.docs = { render, onEnter }
const INPUTS = {};  // views/*.js 注册：INPUTS.q = (v) => { … }

function toast(html) {
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = html;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, 4200);
}
function closeMenus() { document.querySelectorAll(".menu.open").forEach((x) => x.classList.remove("open")); }

/* 动作侧错误 toast（401/403 已由 api.js 统一 toast——此处不重复） */
function errToast(e) {
  if (e && (e.status === 403 || e.status === 401)) return;
  toast((e && e.status ? e.status + " · " : "") + esc(String((e && e.message) || e || "")));
}

/* ---------- 共享片段（视图复用） ---------- */

const ICONS = {
  docs: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  access: '<path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6z"/><path d="m9.2 12 2 2 3.8-3.8"/>',
  semantic: '<circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="8" r="2.4"/><circle cx="9" cy="18" r="2.4"/><path d="M8.2 7 15.7 7.6M7 8.2l1.4 7.5M16.6 10 10.8 16.3"/>',
  ops: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  orgs: '<path d="M3 21h18M5 21V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v16M14 9h4a1 1 0 0 1 1 1v11"/><path d="M8 8h3M8 12h3M8 16h3M17 13h.01M17 17h.01"/>',
};
const ic = (k) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[k]}</svg>`;
const CARET = `<svg class="ic" viewBox="0 0 24 24" style="width:14px;height:14px" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>`;

/* UTC 时间显示约定（ui-3）：列表位一律 short()（MM-DD HH:mm）+ title 悬停完整
 * UTC 原文；时间列表头/pane 时间行在 i18n 值上标注 (UTC)。服务端时间串本身即
 * UTC（SQLite CURRENT_TIMESTAMP 同款格式），short()/title 均为纯展示截取。 */
function tsHTML(ts, cls) {
  const raw = ts ? String(ts) : "";
  return `<span class="${cls || ""}" title="${esc(raw ? raw + " UTC" : "")}">${esc(short(ts))}</span>`;
}

const AV_COLOR = ["#2970FF", "#7A5AF8", "#EE46BC", "#0E9384", "#F79009", "#16B364", "#6172F3"];
function avatar(uid, size) {
  const h = String(uid).split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const s = size ? `;width:${size}px;height:${size}px;font-size:${Math.round(size * .45)}px` : "";
  return `<span class="avatar" style="background:${AV_COLOR[h % AV_COLOR.length]}${s}">${esc(String(uid).slice(0, 1).toUpperCase())}</span>`;
}

const STAGES = ["uploaded", "parsing", "chunked", "searchable_lexical", "searchable_full"];
function stLabel(st) { const key = "st." + st; const s = t(key); return s === key ? st : s; }
function stPill(st) {
  const cls = { searchable_full: "ok", done: "ok", searchable_lexical: "run", chunked: "run", parsing: "run", running: "run", leased: "run",
    uploaded: "idle", pending: "idle", failed: "bad", degraded: "bad" }[st] || "idle";
  return `<span class="pill ${cls}">${esc(stLabel(st))}</span>`;
}
function stagesHTML(st) {
  const idx = STAGES.indexOf(st);
  return `<div class="stages">${STAGES.map((s, i) => `<i class="${i <= idx ? "done" : ""} ${i === idx + 1 ? "cur" : ""}"></i>`).join("")}</div>
  <div class="stage-labels">${STAGES.map((s) => `<span>${esc(stLabel(s))}</span>`).join("")}</div>`;
}

function dimIdx(key) { return Math.max(0, state.dims.findIndex((d) => d.key === key)) % 4; }
function valLabel(key, value) {
  const d = state.dims.find((x) => x.key === key);
  const v = d && (d.values || []).find((x) => x.value === value);
  return v && v.label ? v.label : value;
}
function dimChipsHTML(dims, { showEmpty = false } = {}) {
  const parts = [];
  for (const d of state.dims) {
    const vals = (dims && dims[d.key]) || [];
    if (!vals.length) {
      if (showEmpty) parts.push(`<span class="chip empty" title="${esc(d.name)} · ${esc(d.key)}">${esc(d.name)} · ${esc(t("common.emptyVal"))}</span>`);
      continue;
    }
    vals.forEach((v) => parts.push(`<span class="chip d${dimIdx(d.key)}" title="${esc(d.name)} · ${esc(d.key)}=${esc(v)}">${esc(valLabel(d.key, v))}</span>`));
  }
  return `<span class="chips">${parts.join("")}</span>`;
}
function dsName(id) { const d = state.datasets.find((x) => x.id === id); return d ? d.name : id; }

/* 引号形态 CSV 单行解析（access 平移——值含逗号不错位） */
function parseCsvLine(line) {
  return (String(line).match(/("([^"]|"")*"|[^,]*)(,|$)/g) || [])
    .slice(0, 4)
    .map((c) => c.replace(/,$/, "").replace(/^"(.*)"$/, "$1").replace(/""/g, '"'));
}

/* ---------- 身份与角色（展示口径——服务端仍是权限唯一权威） ---------- */

function roleOf(orgId) {
  const o = state.orgs.find((x) => x.org_id === orgId);
  return o && o.role ? o.role : null;
}
function roleLabel(orgId) {
  const r = roleOf(orgId);
  if (r === "org_admin") return t("role.org_admin");
  if (r === "member") return t("role.member");
  return t("role.none");
}
function isAdmin() { return roleOf(cfg.org) === "org_admin"; }
function lensUser() { return cfg.lensUserId || cfg.baseUserId || "?"; }

function connGate() {
  return `<div class="empty"><h3>${esc(t("conn.need.title"))}</h3><p>${t("conn.need.body")}</p>
  <div style="margin-top:16px"><button class="btn" data-act="openConn">${esc(t("conn.need.btn"))}</button></div></div>`;
}
function loadingHTML(key) {
  return `<div class="loading">${esc(t("common.loading", { what: t("nav." + key) }))}</div>`;
}

/* ---------- 元数据装载 ---------- */

/* 会话成员注册表（R2 P1-3）：username → {role?, expiresAt?}——m3-2 ui-be 起
 * **GET members 真源化**：org_admin 面 loadMembers() 以服务端成员行回填
 * （零授权成员持久可见 + 成员行 role/到期补全）；POST/PATCH 响应仍即时维护
 * （乐观更新，下次 loadMembers 校正）、DELETE 成功移除、resetOrgState 清空。 */
function knownMembers() { return Object.keys(state.mem.known || {}); }
function knownUser(u) { return (state.mem.known || {})[u] || null; }
function setKnownUser(u, row) { state.mem.known[u] = row; }
function dropKnownUser(u) { delete state.mem.known[u]; }

/* GET members 真源装载（m3-2 ui-be——org_admin；非管理员静默退化会话注册表）：
 * 服务端行回填 known（role/expiresAt 如实——成员子标签与身份菜单名单源），
 * 返回成员 user_id 列表。 */
async function loadMembers() {
  const ep = state.epoch;
  try {
    const body = await listMembers(cfg.org);
    if (ep !== state.epoch) return [];
    const rows = (body && body.members) || [];
    for (const m of rows) {
      setKnownUser(m.user_id, {
        role: m.role != null ? m.role : undefined,
        expiresAt: m.expires_at != null ? m.expires_at : undefined,
      });
    }
    return rows.map((m) => m.user_id);
  } catch (e) {
    if (ep !== state.epoch) return [];
    return null; // 403（非 org_admin）等——退化 export-CSV 单源
  }
}

async function loadUsernames() {
  const ep = state.epoch;
  const memberIds = await loadMembers();
  if (ep !== state.epoch) return;
  let exportNames = [];
  try {
    const text = await exportGrants(cfg.org);
    if (ep !== state.epoch) return;
    exportNames = text.trim().split(/\r?\n/).slice(1).filter((l) => l.trim())
      .map((l) => parseCsvLine(l)[0]);
  } catch (e) { /* 非 org_admin——export 不可得 */ }
  // 名单源 = GET members ∪ export 用户名 ∪ 会话注册表（m3-2：members 真源
  // + export 合并保留——P1-3 会话新增成员仍即时的兜底面）
  state.usernames = [...new Set([
    ...(memberIds || []),
    ...exportNames,
    ...knownMembers(),
  ])].filter(Boolean).sort();
}

async function loadMeta() {
  if (!connected()) return;
  const ep = state.epoch;
  const [orgsRes, dsRes, dimRes] = await Promise.all([
    listOrgs().catch(() => ({ orgs: [] })),
    listDatasets(cfg.org).catch(() => ({ datasets: [] })),
    listDimensions(cfg.org).catch(() => ({ dimensions: [] })),
  ]);
  if (ep !== state.epoch) return;
  state.orgs = orgsRes.orgs || [];
  state.datasets = dsRes.datasets || [];
  state.dims = dimRes.dimensions || [];
  await loadUsernames();
}

/* 组织/身份切换后：可见性相关缓存全重置（检索结果/文档列表/授权编辑/运维面板）；
 * epoch 自增使在途异步装载全部作废（P1-5），loading 标志一并清零（新上下文自管）。 */
function resetOrgState() {
  state.epoch += 1;
  state.loading = {};
  state.docs = { available: null, probed: false, loadError: null, list: [], session: [], explain: null };
  state.ds = "all"; state.selDoc = null; state.drawer = null; state.dsAsk = null; state.delAsk = null;
  state.newDs = { key: "", title: "", desc: "" };
  state.up = { ds: "", picked: {}, file: "", fileObj: null, overwrite: null };
  state.editDims = false; state.editPicked = {}; state.quality = null; state.qualDraft = {};
  state.qs = { flags: null, loading: false, seed: "ui3" };
  state.q = ""; state.qDs = ""; state.autoEnt = false; state.lastSearch = null; state.searching = false;
  state.g = { member: "", rows: [], picked: {}, expires: {}, existing: {}, prefill: "", csv: "", diff: null, diffMsg: "", detail: null, saving: "", error: null };
  state.mem = { addOpen: false, form: { uid: "", role: "member", expires: "" }, ask: null, expAsk: null, expVal: "", expMode: "set", roleSel: null, roleVal: "member", known: {} };
  state.dimNewOpen = false; state.dimNew = { key: "", name: "", required: false };
  state.valAsk = null; state.valNew = { v: "", l: "" }; state.govAsk = null; state.disabledVals = [];
  state.vis = { rows: null, members: [], docs: [], cells: {}, error: null, detail: null };
  state.sem = {
    probe: null, dictRev: null,
    q: "", entSel: "", searching: false, results: null,
    detail: null, detailId: null, detail404: false, detailErr: null, detailLoading: false, depth: 1, relAll: false,
    describe: null,
    annText: "", fuzzy: false, annResult: null, annBusy: false, annError: "",
    admin: null, syncRuns: null, syncRunsErr: null, syncFilter: "", syncBusy: "", syncRunsLimit: 50,
    builds: null, buildsErr: null, buildReportId: null, buildReportData: null,
    l0: null, l0Err: null,
  };
  state.orgView = { list: null, askOrg: null, newOpen: false, form: { id: "", name: "", admin: "" }, loadErr: null };
  state.ops = { tasks: null, tasksErr: null, coverage: null, audit: null, auditLimit: 50, stats: null, reembedDoc: "", reembedModel: "" };
}

async function reloadAfterIdentityChange() {
  state.epoch += 1; // 双保险：resetOrgState 未先行时（直连模式 B 等）也作废旧装载
  await loadMeta();
  const view = VIEWS[state.view];
  if (view && view.onEnter) { try { await view.onEnter(); } catch (e) { /* 已 toast */ } }
  render();
}

/* 组织切换 = reissue({org})（本人身份进新组织）+ 元数据与视图数据重载 */
async function switchOrg(orgId) {
  if (!orgId || orgId === cfg.org) return;
  if (!cfg.baseToken) { toast(esc(t("org.switch.needBase"))); openConn(); return; }
  closeMenus();
  try {
    await reissue({ org: orgId });
  } catch (e) { return; } // 403 代签 / 404 生产无 dev 端点——toast 已给降级口径
  cfg.lensUserId = cfg.baseUserId;
  saveCfg();
  resetOrgState();
  toast(t("org.switched", { org: esc(cfg.org), user: esc(lensUser()) }));
  await reloadAfterIdentityChange();
}

/* 身份切换 = reissue({userId, org})；userId 空 = 回本人 */
async function switchLens(userId) {
  if (!cfg.baseToken) { toast(esc(t("org.switch.needBase"))); openConn(); return; }
  closeMenus();
  try {
    await reissue({ userId: userId || undefined, org: cfg.org });
  } catch (e) { return; }
  resetOrgState();
  toast(t("lens.switched", { user: esc(lensUser()), org: esc(cfg.org) }));
  await reloadAfterIdentityChange();
}

/* ---------- 侧栏与顶栏渲染 ---------- */

function orgName(orgId) { const o = state.orgs.find((x) => x.org_id === orgId); return o ? o.name : orgId; }

function renderRail() {
  /* 组织 picker（GET /api/orgs 菜单） */
  $("#orgPicker").innerHTML = connected() ? `
    <button class="picker-btn" data-act="menu" data-m="org" aria-haspopup="true">
      <span class="pk-main"><span class="pk-t">${esc(orgName(cfg.org))}</span><span class="pk-s mono">${esc(cfg.org)}</span></span><span class="caret">${CARET}</span>
    </button>
    <div class="menu" id="menu-org">
      <div class="tiny muted" style="padding:6px 10px 4px;font-weight:500">${esc(t("org.menuTitle"))}</div>
      ${state.orgs.map((x) => `<button class="menu-item ${x.org_id === cfg.org ? "on" : ""}" data-act="org" data-id="${esc(x.org_id)}">
        <span>${esc(x.name)}<span class="mono tiny muted" style="display:block;font-weight:400">${esc(x.org_id)}</span></span>
        <small>${esc(roleLabel(x.org_id))}${x.expires_at ? ` · <span title="${esc(x.expires_at)} UTC">${esc(short(x.expires_at))}</span>` : ""}</small></button>`).join("")}
      <div class="menu-note">${t("org.menuNote")}</div>
    </div>` : `
    <button class="picker-btn" data-act="openConn"><span class="pk-main"><span class="pk-t">${esc(t("rail.offline"))}</span></span><span class="caret">${CARET}</span></button>`;

  /* 身份 picker（名单源 = GET members ∪ export 用户名 ∪ 会话注册表——m3-2
   * ui-be 真源化；非 org_admin 退化为「自己 + 手动输入」） */
  const lu = lensUser();
  $("#lensPicker").innerHTML = connected() ? `
    <button class="picker-btn" data-act="menu" data-m="lens" aria-haspopup="true">
      ${avatar(lu)}<span class="pk-main"><span class="pk-t">${esc(lu)}</span><span class="pk-s">${esc(roleLabel(cfg.org))}</span></span><span class="caret">${CARET}</span>
    </button>
    <div class="menu" id="menu-lens">
      <div class="tiny muted" style="padding:6px 10px 4px;font-weight:500">${esc(t("lens.menuTitle"))}</div>
      <button class="menu-item ${lu === cfg.baseUserId ? "on" : ""}" data-act="lens" data-id="">${avatar(cfg.baseUserId || "?", 24)}<span>${esc(cfg.baseUserId || "?")}</span><small>${esc(t("lens.self"))}</small></button>
      ${state.usernames.filter((u) => u && u !== cfg.baseUserId).map((u) =>
        `<button class="menu-item ${u === lu ? "on" : ""}" data-act="lens" data-id="${esc(u)}">${avatar(u, 24)}<span>${esc(u)}</span><small>${esc(t("role.member"))}</small></button>`).join("")}
      <div class="menu-item" style="display:grid;grid-template-columns:1fr auto;gap:6px;align-items:center">
        <input class="inp" id="lensManualInput" placeholder="${esc(t("lens.manual.ph"))}" style="height:28px;font-size:12.5px">
        <button class="btn sm" data-act="lensGo" title="${esc(t("lens.go"))}">→</button>
      </div>
      <div class="menu-note">${t("lens.note")}</div>
    </div>` : "";

  /* 导航（带计数）——知识组语义第一项（ui-2），运维组含组织 */
  const docsN = state.docs.available ? state.docs.list.length : state.docs.session.length;
  const runN = (state.ops.tasks || []).filter((x) => ["pending", "leased", "running"].includes(x.status)).length;
  const groups = [
    [t("nav.group.knowledge"), [
      ["semantic", t("nav.semantic"), state.sem.dictRev ? "rev " + state.sem.dictRev : ""],
      ["docs", t("nav.docs"), String(docsN || "")],
      ["search", t("nav.search"), ""],
    ]],
    [t("nav.group.admin"), [
      ["access", t("nav.access"), state.dims.length ? t("nav.accessCount", { n: state.dims.length }) : ""],
    ]],
    [t("nav.group.ops"), [
      ["ops", t("nav.ops"), runN ? t("nav.opsCount", { n: runN }) : ""],
      ["orgs", t("nav.orgs"), state.orgs.length ? t("nav.orgsCount", { n: state.orgs.length }) : ""],
    ]],
  ];
  $("#nav").innerHTML = groups.map(([g, items]) => `<div class="nav-group">${esc(g)}</div>` + items.map(([k, name, c]) =>
    `<button class="nav-item ${state.view === k ? "on" : ""}" data-act="view" data-v="${k}"><span class="ni-k">${ic(k)}</span><span>${esc(name)}</span><span class="ni-c">${esc(c)}</span></button>`).join("")).join("");

  $("#railFoot").innerHTML = connected()
    ? `<div class="rf-h"><i></i>${t("rail.connected", { org: esc(cfg.org) })}</div>${t("rail.note")}`
    : `<div class="rf-h" style="color:var(--danger)"><i style="background:var(--danger);box-shadow:0 0 0 3px var(--danger-w)"></i>${esc(t("rail.offline"))}</div>${t("rail.note")}`;
}

/* ---------- 主渲染循环 ---------- */

function render() {
  const a = document.activeElement;
  const key = a && a.dataset && a.dataset.in;
  const sel = key && "selectionStart" in a ? [a.selectionStart, a.selectionEnd] : null;
  renderRail();
  const vk = state.view + "/" + (state.view === "access" ? state.sub.access
    : state.view === "semantic" ? state.sub.sem : "");
  const view = VIEWS[state.view];
  const body = view ? view.render() : "";
  $("#main").innerHTML = `<section class="${vk !== lastViewKey ? "view" : ""}">${body}</section>`;
  lastViewKey = vk;
  if (key) {
    const el = document.querySelector(`[data-in="${key}"]`);
    if (el && el.type !== "checkbox" && el.tagName !== "SELECT") {
      el.focus();
      if (sel) { try { el.setSelectionRange(sel[0], sel[1]); } catch (_) { /* number 等 input 不支持 */ } }
    }
  }
}

/* ---------- 连接设置 ---------- */

function openConn() {
  const m = $("#menu-conn");
  if (m) m.classList.add("open");
  refreshConnStatus();
}
function refreshConnStatus() {
  const el = $("#connStatus");
  if (!el) return;
  if (!connected()) { el.textContent = t("settings.status.offline"); return; }
  el.textContent = t("settings.status.on", { user: lensUser(), org: cfg.org, role: roleLabel(cfg.org) });
}

/* ---------- 动作基表（views/*.js 经 Object.assign 扩展） ---------- */

const actions = {
  menu(el) {
    const mn = $("#menu-" + el.dataset.m);
    const open = mn.classList.contains("open");
    closeMenus();
    if (!open) mn.classList.add("open");
    if (el.dataset.m === "conn") refreshConnStatus();
    return false;
  },
  mcpMenu() {
    const mn = $("#menu-mcp");
    const open = mn.classList.contains("open");
    closeMenus();
    if (!open) mn.classList.add("open");
    return false;
  },
  connMenu() {
    const mn = $("#menu-conn");
    const open = mn.classList.contains("open");
    closeMenus();
    if (!open) { mn.classList.add("open"); refreshConnStatus(); }
    return false;
  },
  openConn() { openConn(); return false; },
  apiDocs() { window.open("/docs", "_blank"); return false; },

  view(el) {
    const v = el.dataset.v;
    state.view = v;
    render();
    const view = VIEWS[v];
    if (view && view.onEnter) view.onEnter().then(() => render()).catch(() => { /* 已 toast */ });
    return false;
  },
  sub(el) { state.sub[el.dataset.s] = el.dataset.v; render(); return false; },

  org(el) { switchOrg(el.dataset.id); return false; },
  lens(el) { switchLens(el.dataset.id); return false; },
  lensGo() {
    const inp = $("#lensManualInput");
    const v = inp ? inp.value.trim() : "";
    if (!v) { toast(esc(t("lens.manual.empty"))); return false; }
    switchLens(v);
    return false;
  },

  /* 连接：模式 A——基 token 重签（dev） */
  async connReissue() {
    const baseToken = $("#connBaseToken").value.trim();
    const org = $("#connOrg").value.trim();
    const lens = $("#connLens").value.trim();
    if (!baseToken || !org) { toast(esc(t("settings.needBase"))); return false; }
    cfg.baseToken = baseToken;
    cfg.baseUserId = (decodeJwt(baseToken) || {}).sub || "";
    try {
      const data = await reissue({ org, userId: lens || undefined });
      if (!cfg.baseUserId) cfg.baseUserId = data.user_id || "";
      saveCfg();
    } catch (e) { refreshConnStatus(); return false; }
    resetOrgState();
    await reloadAfterIdentityChange();
    refreshConnStatus();
    closeMenus(); // 连接成功收起弹层——浮层不遮挡页面（否则 elementFromPoint 命中菜单）
    toast(t("settings.connected", { user: esc(lensUser()), org: esc(cfg.org) }));
    return false;
  },
  /* 连接：模式 B——直接使用已签 token（生产可用） */
  async connUseSigned() {
    const token = $("#connToken").value.trim();
    if (!token) { toast(esc(t("settings.needToken"))); return false; }
    const claims = decodeJwt(token) || {};
    const org = $("#connOrg").value.trim() || claims.org || "";
    if (!org) { toast(esc(t("settings.needOrg"))); return false; }
    cfg.baseToken = token;
    cfg.activeToken = token;
    cfg.org = org;
    cfg.baseUserId = claims.sub || "";
    cfg.lensUserId = claims.sub || "";
    saveCfg();
    resetOrgState();
    await reloadAfterIdentityChange();
    refreshConnStatus();
    closeMenus(); // 同上——成功即收起
    toast(t("settings.connected", { user: esc(lensUser()), org: esc(cfg.org) }));
    return false;
  },
  connDisconnect() {
    cfg.baseToken = ""; cfg.activeToken = ""; cfg.org = ""; cfg.lensUserId = ""; cfg.baseUserId = "";
    saveCfg();
    resetOrgState();
    state.orgs = []; state.usernames = []; state.dims = []; state.datasets = [];
    render();
    refreshConnStatus();
    toast(esc(t("settings.disconnected")));
    openConn();
    return false;
  },
};

/* ---------- 事件委托 ---------- */

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-act]");
  if (!el) {
    if (!ev.target.closest(".menu") && !ev.target.closest(".picker")) closeMenus();
    return;
  }
  if (el.disabled) return;
  if (!el.closest(".menu") && el.dataset.act !== "mcpMenu" && el.dataset.act !== "menu" && el.dataset.act !== "connMenu") closeMenus();
  const fn = actions[el.dataset.act];
  if (!fn) return;
  const out = fn(el);
  if (out && typeof out.then === "function") return; // async 动作自管渲染
  if (out !== false) render();
});

function onInput(ev) {
  const el = ev.target;
  const k = el.dataset && el.dataset.in;
  if (!k || ev.isComposing) return;
  const fn = INPUTS[k];
  if (!fn) return;
  const v = el.type === "checkbox" ? el.checked : el.value;
  if (fn(v, el) !== false) render();
}
document.addEventListener("input", (ev) => { if (ev.target.type !== "checkbox" && ev.target.tagName !== "SELECT") onInput(ev); });
document.addEventListener("change", (ev) => { if (ev.target.type === "checkbox" || ev.target.tagName === "SELECT") onInput(ev); });
document.addEventListener("compositionend", onInput);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && ev.target.id === "qInput" && !ev.isComposing) {
    const fn = actions.doSearch;
    if (fn) { const out = fn(ev.target); if (out && typeof out.then === "function") return; if (out !== false) render(); }
  }
  if (ev.key === "Enter" && ev.target.id === "semQInput" && !ev.isComposing) {
    const fn = actions.semSearch;
    if (fn) { const out = fn(ev.target); if (out && typeof out.then === "function") return; if (out !== false) render(); }
  }
  if (ev.key === "Enter" && ev.target.id === "lensManualInput" && !ev.isComposing) { actions.lensGo(); }
  if (ev.key === "Escape") closeMenus();
});

/* ---------- boot（DOMContentLoaded——晚于全部 views/*.js 注册） ---------- */

function boot() {
  loadCfg();
  if (!cfg.baseUserId && cfg.baseToken) cfg.baseUserId = (decodeJwt(cfg.baseToken) || {}).sub || "";
  if (!cfg.lensUserId && cfg.activeToken) cfg.lensUserId = (decodeJwt(cfg.activeToken) || {}).sub || "";

  setLang(currentLang()); // 初始化 <html lang>/<title>/静态文案 + 触发 langchange（boot 前无害）
  document.querySelectorAll("#langSwitch button").forEach((b) => {
    b.classList.toggle("on", b.dataset.lang === currentLang());
    b.addEventListener("click", () => {
      setLang(b.dataset.lang);
      document.querySelectorAll("#langSwitch button").forEach((x) => x.classList.toggle("on", x.dataset.lang === currentLang()));
    });
  });
  document.addEventListener("langchange", () => {
    refreshConnStatus();
    if (booted) render(); // 全视图重渲染——缓存数据复用，仅文案换
  });

  render();
  booted = true;
  if (connected()) {
    loadMeta().then(() => render()).catch(() => render());
    const view = VIEWS[state.view];
    if (view && view.onEnter) view.onEnter().then(() => render()).catch(() => { /* 已 toast */ });
  } else {
    openConn();
  }
}
document.addEventListener("DOMContentLoaded", boot);
