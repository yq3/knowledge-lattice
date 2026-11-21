/* app.js —— 应用框架（ui-1）：状态 / 渲染循环 / 顶栏与侧栏 / 组织与身份切换 /
 * 连接设置 / 语言切换接线。视图实现见 views/*.js（VIEWS 注册表 + actions/INPUTS 扩展）。
 * 脚本协同（经典脚本，无模块）：i18n.js → api.js → 本文件 → views/login.js →
 * views/*.js；boot 在 DOMContentLoaded 才执行（晚于全部 script 注册）。
 * D25 local（m4-3a）：boot 门 → setup/login/invite 三屏（views/login.js，VIEWS.auth）
 * + 用户菜单/本地组织切换；默认 sso 形态沿用原连接设置/身份 lens 路径。
 */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* 默认落地视图：登录 / 会话恢复 / 首启后落在「业务语义」（知识组第一项）。
 * 首启未建组织的 sysadmin 例外仍先落组织页（applySession 内覆盖）。 */
const DEFAULT_VIEW = "semantic";

/* ---------- 全局状态 ---------- */
const state = {
  view: DEFAULT_VIEW,
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
  /* 用户/邀请管理视图（m4-3b，D25 local；sysadmin 用户表 + org_admin 本组织邀请） */
  users: {
    list: null,                 // GET /api/users（sysadmin）→ [{id,username,...}]
    invites: null,              // GET /api/orgs/{org}/invitations（org_admin）
    err: null,                  // 装载/动作失败文案（普通文案——消费点 esc）
    lastInvite: null,           // {token, username, kind:"invite"|"reset"}——只驻内存（刷新消失）
    busy: false,                // 创建/动作在途
    createOpen: false, invOpen: false,
    form: { username: "", display_name: "", email: "", is_system_admin: false, org_id: "", role: "member" },
    invForm: { username: "", role: "member", display_name: "", email: "" },
  },
  loading: {},
};

/* 渲染周期内标记（防轮询/异步回写触发的不必要重渲） */
let lastViewKey = "";
let booted = false;

const VIEWS = {};   // views/*.js 注册：VIEWS.docs = { render, onEnter }
const INPUTS = {};  // views/*.js 注册：INPUTS.q = (v) => { … }

/* 密码规则提示值（前端仅展示——真正校验在服务端 `LATTICE_PASSWORD_MIN_LEN`：
 * 缺省 10、下限 8；部署调整后本提示的「默认策略」措辞即为此留口）。 */
const PASSWORD_MIN_LEN_HINT = 10;

/* D25 local 认证状态（m4-3a；默认 sso = screen:null、mode:"sso"——零视觉变化）。
 * screen 非空时 render() 只渲染 VIEWS.auth（登录/首启/邀请接受三屏），不渲染 rail。
 * form 跨重渲染保留输入（INPUTS 写这里）；pw* 为用户菜单改密表单。 */
const AUTH = {
  mode: "sso",                 // "sso" | "local"（boot 门按 GET /api/auth/config）
  screen: null,                // null | "setup" | "login" | "accept"
  setupNeeded: false,
  user: null,                  // public_user 投影（id/username/display_name/email/status/is_system_admin/...）
  orgs: [],                    // [{org_id,name,role,status}]（local session payload）
  error: "",                   // 屏幕内联错误（已由 authErrorText 映射为普通文案）
  busy: false,
  form: {
    username: "", password: "", confirm: "", display_name: "",
    org_id: "", org_name: "", init_password: "",
    pwOld: "", pwNew: "", pwConfirm: "",
  },
  invite: null,                // {token, loading, info}（accept 屏）
};

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

/* D25 local 错误文案：优先 body.code（契约 §5 冻结错误码）→ i18n auth.err.*；
 * 未知 code 用服务端 message；离线（status 0）用网络文案；其余 generic。
 * 返回值是普通文案（消费点 esc——authErrorText 不做 HTML 转义）。 */
function authErrorText(err) {
  const body = (err && err.body) || {};
  const code = body.code || "";
  const byCode = {
    invalid_credentials: "auth.err.invalid_credentials",
    login_locked: "auth.err.login_locked",
    invalid_init_password: "auth.err.invalid_init_password",
    weak_password: "auth.err.weak_password",
    invalid_username: "auth.err.invalid_username",
    invalid_org: "auth.err.invalid_org",
    setup_completed: "auth.err.setup_completed",
    invite_invalid: "auth.err.invite_invalid",
    invite_expired: "auth.err.invite_expired",
    invite_consumed: "auth.err.invite_consumed",
    invite_revoked: "auth.err.invite_revoked",
    username_taken: "auth.err.username_taken",
    email_taken: "auth.err.email_taken",
  };
  if (code && byCode[code]) return t(byCode[code]);
  if (!err || !err.status) return t("auth.err.network");
  if (err.status === 429) return t("auth.err.login_locked");
  const msg = err.message ? String(err.message) : "";
  return msg || t("auth.err.generic");
}

/* ---------- 共享片段（视图复用） ---------- */

const ICONS = {
  docs: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  access: '<path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6z"/><path d="m9.2 12 2 2 3.8-3.8"/>',
  semantic: '<circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="8" r="2.4"/><circle cx="9" cy="18" r="2.4"/><path d="M8.2 7 15.7 7.6M7 8.2l1.4 7.5M16.6 10 10.8 16.3"/>',
  ops: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  orgs: '<path d="M3 21h18M5 21V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v16M14 9h4a1 1 0 0 1 1 1v11"/><path d="M8 8h3M8 12h3M8 16h3M17 13h.01M17 17h.01"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3.6 19.5c.6-3.1 2.8-4.9 5.4-4.9s4.8 1.8 5.4 4.9"/><circle cx="17.4" cy="10.6" r="2.2"/><path d="m19 12.1 2.4 2.4M15.4 14.8l3.9 3.9"/><path d="M17.4 8.4v2.2"/>',
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
  /* D25 local：角色真源 = 会话 payload 的成员关系（GET /api/orgs 对 sysadmin 是
   * 全部组织、无 role 列——直接读 state.orgs 会丢掉 setup 管理员的 org_admin）。
   * AUTH.orgs 为空时回落 state.orgs；sso 形态始终 state.orgs（零变化）。 */
  const source = AUTH.mode === "local" && (AUTH.orgs || []).length ? AUTH.orgs : state.orgs;
  const o = source.find((x) => x.org_id === orgId);
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
  /* D25 local：会话成员关系会漂移（sysadmin 在组织页新建组织后 GET /api/orgs
   * 返回无 role 的全量组织，不能作 AUTH.orgs 真源）——每次装载前用
   * /api/auth/me 刷新 AUTH.user/AUTH.orgs，组织 picker 与 roleOf/isAdmin 即时
   * 可见新组织/新角色，不必重新登录。401 → 会话失效回登录屏；网络/其他错误
   * 忽略（沿用现有 AUTH 缓存降级）。sso 形态不进入本分支（零变化）。 */
  if (AUTH.mode === "local") {
    try {
      const me = await authMe();
      AUTH.user = (me && me.user) || AUTH.user;
      AUTH.orgs = (me && me.orgs) || [];
    } catch (e) {
      if (e && e.status === 401) { handleAuthExpired(); return; }
      /* 网络/其它错误：沿用当前会话缓存，不阻塞元数据装载 */
    }
  }
  /* D25 local 无组织：只同步会话里的组织清单，清空 org 路径缓存（datasets/dims/
   * 成员名单），绝不发 /api/orgs//... 请求。有组织时走 sso 同款装载。 */
  if (AUTH.mode === "local" && !cfg.org) {
    state.orgs = AUTH.orgs || [];
    state.datasets = [];
    state.dims = [];
    state.usernames = [];
    return;
  }
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
  state.users = {
    list: null, invites: null, err: null, lastInvite: null, busy: false,
    createOpen: false, invOpen: false,
    form: { username: "", display_name: "", email: "", is_system_admin: false, org_id: "", role: "member" },
    invForm: { username: "", role: "member", display_name: "", email: "" },
  };
}

async function reloadAfterIdentityChange() {
  state.epoch += 1; // 双保险：resetOrgState 未先行时（直连模式 B 等）也作废旧装载
  await loadMeta();
  const view = VIEWS[state.view];
  if (view && view.onEnter) { try { await view.onEnter(); } catch (e) { /* 已 toast */ } }
  render();
}

/* 组织切换（D25 local：成员关系已在会话 orgs——只换当前组织，不重签/不 reissue）；
 * sso 形态 = reissue({org})（本人身份进新组织）+ 元数据与视图数据重载。 */
async function switchOrg(orgId) {
  if (!orgId || orgId === cfg.org) return;
  if (AUTH.mode === "local") {
    /* local session 绑定用户身份；组织仅决定 X-Org-Id 与可见成员关系，
     * 切换零服务端重签（不 reissue、不依赖 baseToken/dev 端点）。 */
    closeMenus();
    cfg.org = orgId;
    saveCfg();
    resetOrgState();
    toast(t("org.switched", { org: esc(orgId), user: esc(AUTH.user ? AUTH.user.username : "") }));
    await reloadAfterIdentityChange();
    return;
  }
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

/* 身份切换 = reissue({userId, org})；userId 空 = 回本人。D25 local 无代签面——直接忽略。 */
async function switchLens(userId) {
  if (AUTH.mode === "local") return;
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

function orgName(orgId) {
  /* D25 local：优先会话成员关系里的组织名（AUTH.orgs）；未命中再回落 GET /api/orgs
   * 列表（sysadmin 的全部组织）；sso 形态仍只读 state.orgs（零变化）。 */
  let o = null;
  if (AUTH.mode === "local") o = (AUTH.orgs || []).find((x) => x.org_id === orgId) || null;
  if (!o) o = state.orgs.find((x) => x.org_id === orgId);
  return o ? o.name : orgId;
}

function renderRail() {
  /* 组织 picker（GET /api/orgs 菜单；D25 local 无组织 → 「未加入组织」引导入口） */
  if (AUTH.mode === "local" && AUTH.user && !cfg.org) {
    $("#orgPicker").innerHTML = `
    <button class="picker-btn" data-act="view" data-v="orgs">
      <span class="pk-main"><span class="pk-t">${esc(t("org.none"))}</span><span class="pk-s">${esc(t("org.noneHint"))}</span></span><span class="caret">${CARET}</span>
    </button>`;
  } else {
    /* local 菜单源 = 会话成员关系（AUTH.orgs）——sysadmin 的 GET /api/orgs 是
     * 「全部组织」口径（含无成员关系的组织），直接作工作空间切换会切进无权限组织；
     * sso 形态保持 state.orgs（GET /api/orgs 现有语义）不变。 */
    const menuOrgs = AUTH.mode === "local" ? (AUTH.orgs || []) : state.orgs;
    $("#orgPicker").innerHTML = connected() ? `
    <button class="picker-btn" data-act="menu" data-m="org" aria-haspopup="true">
      <span class="pk-main"><span class="pk-t">${esc(orgName(cfg.org))}</span><span class="pk-s mono">${esc(cfg.org)}</span></span><span class="caret">${CARET}</span>
    </button>
    <div class="menu" id="menu-org">
      <div class="tiny muted" style="padding:6px 10px 4px;font-weight:500">${esc(t("org.menuTitle"))}</div>
      ${menuOrgs.map((x) => `<button class="menu-item ${x.org_id === cfg.org ? "on" : ""}" data-act="org" data-id="${esc(x.org_id)}">
        <span>${esc(x.name)}<span class="mono tiny muted" style="display:block;font-weight:400">${esc(x.org_id)}</span></span>
        <small>${esc(roleLabel(x.org_id))}${x.expires_at ? ` · <span title="${esc(x.expires_at)} UTC">${esc(short(x.expires_at))}</span>` : ""}</small></button>`).join("")}
      <div class="menu-note">${t("org.menuNote")}</div>
    </div>` : `
    <button class="picker-btn" data-act="openConn"><span class="pk-main"><span class="pk-t">${esc(t("rail.offline"))}</span></span><span class="caret">${CARET}</span></button>`;
  }

  /* 身份 picker（名单源 = GET members ∪ export 用户名 ∪ 会话注册表——m3-2
   * ui-be 真源化；非 org_admin 退化为「自己 + 手动输入」） */
  const lu = lensUser();
  $("#lensPicker").innerHTML = AUTH.mode === "local" ? "" : connected() ? `
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

  /* 导航（带计数）——知识组语义第一项（ui-2），运维组含组织。
   * D25 local（m4-3b）：用户/邀请管理仅对 sysadmin 或当前组织 org_admin 显示
   * （sso 形态恒不出现——AUTH.mode/AUTH.user 双重门，零视觉变化）。 */
  const docsN = state.docs.available ? state.docs.list.length : state.docs.session.length;
  const runN = (state.ops.tasks || []).filter((x) => ["pending", "leased", "running"].includes(x.status)).length;
  const adminItems = [
    ["access", t("nav.access"), state.dims.length ? t("nav.accessCount", { n: state.dims.length }) : ""],
  ];
  if (AUTH.mode === "local" && AUTH.user && (AUTH.user.is_system_admin || isAdmin())) {
    adminItems.push(["users", t("nav.users"), state.users.list ? String(state.users.list.length) : ""]);
  }
  const groups = [
    [t("nav.group.knowledge"), [
      ["semantic", t("nav.semantic"), state.sem.dictRev ? "rev " + state.sem.dictRev : ""],
      ["docs", t("nav.docs"), String(docsN || "")],
      ["search", t("nav.search"), ""],
    ]],
    [t("nav.group.admin"), adminItems],
    [t("nav.group.ops"), [
      ["ops", t("nav.ops"), runN ? t("nav.opsCount", { n: runN }) : ""],
      ["orgs", t("nav.orgs"), state.orgs.length ? t("nav.orgsCount", { n: state.orgs.length }) : ""],
    ]],
  ];
  $("#nav").innerHTML = groups.map(([g, items]) => `<div class="nav-group">${esc(g)}</div>` + items.map(([k, name, c]) =>
    `<button class="nav-item ${state.view === k ? "on" : ""}" data-act="view" data-v="${k}"><span class="ni-k">${ic(k)}</span><span>${esc(name)}</span><span class="ni-c">${esc(c)}</span></button>`).join("")).join("");

  renderUserMenu();

  $("#railFoot").innerHTML = connected()
    ? `<div class="rf-h"><i></i>${t("rail.connected", { org: esc(cfg.org || t("org.none")) })}</div>${t("rail.note")}`
    : `<div class="rf-h" style="color:var(--danger)"><i style="background:var(--danger);box-shadow:0 0 0 3px var(--danger-w)"></i>${esc(t("rail.offline"))}</div>${t("rail.note")}`;
}

/* D25 local 用户菜单（#userPicker）：头像/username/角色 + 改密表单 + 退出登录；
 * sso 形态恒隐藏（连接设置/身份 lens 原路径不变）。菜单表单值存 AUTH.form.pw*；
 * INPUTS 返回 false 不触发整壳重渲（否则弹层 innerHTML 重建即收起）。 */
function renderUserMenu() {
  const el = $("#userPicker");
  if (!el) return;
  const show = AUTH.mode === "local" && !!AUTH.user && !!cfg.activeToken;
  if (!show) { el.style.display = "none"; el.innerHTML = ""; return; }
  el.style.display = "";
  const u = AUTH.user;
  const uname = u.username || "?";
  const dname = u.display_name || uname;
  const role = u.is_system_admin ? t("user.menu.sysadmin")
    : (cfg.org ? roleLabel(cfg.org) : t("org.none"));
  const f = AUTH.form;
  el.innerHTML = `
    <button class="picker-btn" data-act="menu" data-m="user" aria-haspopup="true">
      ${avatar(uname)}<span class="pk-main"><span class="pk-t">${esc(dname)}</span><span class="pk-s">${esc(role)}${u.is_system_admin ? ` · <span class="mono">${esc(uname)}</span>` : ""}</span></span><span class="caret">${CARET}</span>
    </button>
    <div class="menu" id="menu-user">
      <div class="tiny muted" style="padding:6px 10px 4px;font-weight:500">${esc(t("user.menu.title"))}</div>
      <div class="menu-item"><span>${avatar(uname, 24)}<span style="display:block;font-weight:600">${esc(dname)}</span><span class="mono tiny muted" style="display:block;font-weight:400">${esc(uname)}</span></span><small>${esc(role)}</small></div>
      <div class="menu-form">
        <div class="mf-sec">${esc(t("user.menu.password"))}</div>
        <div class="mf-row"><label for="userPwOld">${esc(t("user.menu.oldPassword"))}</label>
          <input class="inp" id="userPwOld" type="password" autocomplete="current-password" data-in="userPwOld" placeholder="${esc(t("user.menu.oldPasswordPh"))}" value="${esc(f.pwOld)}"></div>
        <div class="mf-row"><label for="userPwNew">${esc(t("user.menu.newPassword"))}</label>
          <input class="inp" id="userPwNew" type="password" autocomplete="new-password" data-in="userPwNew" placeholder="${esc(t("user.menu.newPasswordPh"))}" value="${esc(f.pwNew)}"></div>
        <div class="mf-row"><label for="userPwConfirm">${esc(t("user.menu.confirmPassword"))}</label>
          <input class="inp" id="userPwConfirm" type="password" autocomplete="new-password" data-in="userPwConfirm" placeholder="${esc(t("user.menu.confirmPasswordPh"))}" value="${esc(f.pwConfirm)}"></div>
        <div class="mf-act">
          <button class="btn sm" data-act="userPassword">${esc(t("user.menu.changePassword"))}</button>
        </div>
        <div class="menu-note">${esc(t("auth.policy.password", { n: PASSWORD_MIN_LEN_HINT }))}<br>${esc(t("user.menu.passwordNote"))}</div>
        <button class="menu-item" data-act="userLogout" style="color:var(--danger)">${esc(t("user.menu.logout"))}</button>
      </div>
    </div>`;
}

/* ---------- 主渲染循环 ---------- */

/* 输入焦点/光标恢复（每次 INPUTS 触发重渲染后按 data-in 找回输入框；auth 屏同用） */
function restoreInputFocus(key, sel) {
  if (!key) return;
  const el = document.querySelector(`[data-in="${key}"]`);
  if (el && el.type !== "checkbox" && el.tagName !== "SELECT") {
    el.focus();
    if (sel) { try { el.setSelectionRange(sel[0], sel[1]); } catch (_) { /* number 等 input 不支持 */ } }
  }
}

function render() {
  const a = document.activeElement;
  const key = a && a.dataset && a.dataset.in;
  const sel = key && "selectionStart" in a ? [a.selectionStart, a.selectionEnd] : null;
  /* D25 local：认证屏只渲染 VIEWS.auth 到 #main（rail/topbar 交互件由 body.auth-screen
   * CSS 隐藏），不渲染 rail；登录成功 applySession 清 screen 后回到整壳。 */
  if (AUTH.screen) {
    const authView = VIEWS.auth;
    const authKey = "auth/" + AUTH.screen;
    /* 同一屏的输入重渲染不加 .view（避免每次击键重放 viewIn 动画——闪烁） */
    const cls = authKey !== lastViewKey ? "view auth-view" : "auth-view";
    $("#main").innerHTML = `<section class="${cls}">${authView ? authView.render() : ""}</section>`;
    lastViewKey = authKey;
    restoreInputFocus(key, sel);
    return;
  }
  renderRail();
  const vk = state.view + "/" + (state.view === "access" ? state.sub.access
    : state.view === "semantic" ? state.sub.sem : "");
  const view = VIEWS[state.view];
  const body = view ? view.render() : "";
  $("#main").innerHTML = `<section class="${vk !== lastViewKey ? "view" : ""}">${body}</section>`;
  lastViewKey = vk;
  restoreInputFocus(key, sel);
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

/* ---------- D25 local 认证状态机（m4-3a） ----------
 * boot 门（GET /api/auth/config 匿名）→ setup / invite / login / resume 四路；
 * 认证屏复用 VIEWS.auth（views/login.js），render() 在 AUTH.screen 非空时只渲染该视图。
 * sso 形态完全不进入本区（AUTH.mode="sso"、screen 恒 null），原有连接设置路径零变化。 */

/* 邀请 token 只从 URL fragment/query 取（不放路径、不进 Referer——D25 线下交付口径）：
 * `#invite=<token>` 优先，其次 `?invite=<token>`。 */
function parseInviteToken() {
  try {
    const h = new URLSearchParams(String(location.hash || "").replace(/^#/, ""));
    if (h.get("invite")) return h.get("invite");
    const q = new URLSearchParams(String(location.search || "").replace(/^\?/, ""));
    return q.get("invite") || "";
  } catch (e) { return ""; }
}

/* 切到认证屏（不渲染 rail）。kind: "setup" | "login" | "accept"；error 为普通文案。 */
function showAuthScreen(kind, { error } = {}) {
  AUTH.mode = "local";
  AUTH.screen = kind;
  AUTH.busy = false;
  AUTH.error = error || "";
  if (kind !== "accept") AUTH.invite = null;
  AUTH.form.password = "";
  AUTH.form.confirm = "";
  document.body.classList.add("auth-screen", "auth-local");
  closeMenus();
  booted = true;
  render();
  return false;
}

/* 邀请接受屏：先 lookup（匿名）再出表单；lookup 失败（无效/过期/已用/撤销/
 * 网络错）→ 错误文案 + 回登录屏。 */
async function openInvite(token) {
  AUTH.mode = "local";
  AUTH.screen = "accept";
  AUTH.busy = false;
  AUTH.error = "";
  AUTH.invite = { token, loading: true, info: null };
  AUTH.form.password = "";
  AUTH.form.confirm = "";
  AUTH.form.display_name = "";
  document.body.classList.add("auth-screen", "auth-local");
  closeMenus();
  booted = true;
  render();
  try {
    const info = await lookupInvitation(token);
    if (!AUTH.invite || AUTH.invite.token !== token) return; // 屏幕已被替换/取消
    AUTH.invite = { token, loading: false, info };
    AUTH.form.display_name = info.display_name || "";
    render();
  } catch (e) {
    showAuthScreen("login", { error: authErrorText(e) });
  }
}

/* 选组织：preferred（当前/登录前组织）→ 现有 cfg.org → 首个 active → 首个；
 * 无成员关系 → cfg.org 置空（local 允许未加入组织，renderRail 给引导入口）。 */
function pickSessionOrg(orgs, preferred) {
  const list = orgs || [];
  const byId = (id) => (id ? list.find((o) => o.org_id === id) : null);
  return byId(preferred) || byId(cfg.org) ||
    list.find((o) => o.status !== "disabled") || list[0] || null;
}

/* 登录/首启/邀请接受成功 → 本地会话落地：token/baseUserId/lensUserId、AUTH、orgs
 * 与组织选择、saveCfg、清缓存、整壳渲染 + 元数据/当前视图装载。
 * data 形如 {token, expires_at, user, orgs}（authMe 调用时由 bootLocal 补 token）。 */
async function applySession(data, preferredOrg) {
  const user = (data && data.user) || {};
  const orgs = (data && data.orgs) || [];
  cfg.authMode = "local";
  cfg.activeToken = (data && data.token) || cfg.activeToken || "";
  cfg.baseToken = ""; // 本地会话无基 token/重签面（dev lens 入口在 local 隐藏）
  cfg.baseUserId = user.id || "";
  cfg.lensUserId = user.id || "";
  AUTH.user = user;
  AUTH.orgs = orgs;
  AUTH.screen = null;
  AUTH.error = "";
  AUTH.busy = false;
  AUTH.invite = null;
  AUTH.form.password = "";
  AUTH.form.confirm = "";
  AUTH.form.init_password = "";
  AUTH.form.pwOld = "";
  AUTH.form.pwNew = "";
  AUTH.form.pwConfirm = "";
  state.orgs = orgs;
  const picked = pickSessionOrg(orgs, preferredOrg);
  cfg.org = picked ? picked.org_id : "";
  saveCfg();
  resetOrgState();
  state.orgs = orgs;
  state.usernames = [];
  state.dims = [];
  state.datasets = [];
  state.view = DEFAULT_VIEW; // 登录/恢复会话后回默认落地视图（不沿用上一会话停留的视图）
  if (!cfg.org && user.is_system_admin) state.view = "orgs"; // 首启未建组织 → 先落组织页
  document.body.classList.remove("auth-screen");
  document.body.classList.add("auth-local");
  booted = true;
  render();
  try { await loadMeta(); } catch (e) { /* 已按视图降级/403 toast */ }
  const view = VIEWS[state.view];
  if (view && view.onEnter) { try { await view.onEnter(); } catch (e) { /* 已 toast */ } }
  render();
}

/* 会话失效（401/登出）：清 token 与用户态、缓存；local → 登录屏（默认「已过期」文案，
 * 登出用普通文案），sso → 原连接设置弹层。 */
function handleAuthExpired(reason) {
  const local = AUTH.mode === "local";
  cfg.activeToken = "";
  cfg.baseToken = "";
  cfg.org = "";
  cfg.lensUserId = "";
  cfg.baseUserId = "";
  saveCfg();
  AUTH.user = null;
  AUTH.orgs = [];
  AUTH.busy = false;
  AUTH.invite = null;
  state.orgs = [];
  state.usernames = [];
  state.dims = [];
  state.datasets = [];
  resetOrgState();
  if (!local) {
    AUTH.screen = null;
    document.body.classList.remove("auth-screen", "auth-local");
    render();
    openConn();
    return;
  }
  AUTH.form.username = "";
  AUTH.form.pwOld = "";
  AUTH.form.pwNew = "";
  AUTH.form.pwConfirm = "";
  showAuthScreen("login", { error: reason || t("auth.err.expired") });
}

/* local boot：setup 屏 → 邀请接受 → 无 token 登录屏 → 有 token 恢复会话（/api/auth/me）。 */
async function bootLocal(config) {
  AUTH.mode = "local";
  AUTH.setupNeeded = !!(config && config.setup_needed);
  document.body.classList.add("auth-local");
  if (AUTH.setupNeeded) { showAuthScreen("setup"); return; }
  const invite = parseInviteToken();
  if (invite) { await openInvite(invite); return; }
  showAuthScreen("login"); // 先出登录屏，避免恢复会话期间空白；成功后整壳替换
  if (!cfg.activeToken) return;
  try {
    const me = await authMe();
    await applySession({ token: cfg.activeToken, user: me.user, orgs: me.orgs }, cfg.org);
  } catch (e) {
    if (e && e.status === 401) { handleAuthExpired(); return; }
    showAuthScreen("login", { error: authErrorText(e) });
  }
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

  /* D25 local 用户菜单：改密（旧密错 401 不清会话——只提示；会话过期才回登录屏） */
  async userPassword() {
    const f = AUTH.form;
    const domVal = (id) => { const el = $("#" + id); return el && typeof el.value === "string" ? el.value : ""; };
    const oldPw = domVal("userPwOld") || f.pwOld || "";
    const newPw = domVal("userPwNew") || f.pwNew || "";
    const confirmPw = domVal("userPwConfirm") || f.pwConfirm || "";
    if (!oldPw || !newPw) { toast(esc(t("user.menu.pwNeed"))); return false; }
    if (newPw !== confirmPw) { toast(esc(t("user.menu.pwMismatch"))); return false; }
    let body;
    try {
      body = await changePassword(oldPw, newPw);
    } catch (e) {
      if (e && e.status === 401 && e.body && e.body.code === "invalid_credentials") {
        toast(esc(t("user.menu.pwOldWrong")));
      } else if (e && e.status === 401) {
        handleAuthExpired(); // 会话本身失效（非旧密错——AuthError 体无 code）
      } else if (e && e.status === 400) {
        toast(esc(authErrorText(e)));
      } else {
        errToast(e);
      }
      return false;
    }
    cfg.activeToken = body.token || cfg.activeToken;
    saveCfg();
    AUTH.form.pwOld = ""; AUTH.form.pwNew = ""; AUTH.form.pwConfirm = "";
    toast(t("user.menu.pwDone"));
    closeMenus();
    render();
    return false;
  },
  async userLogout() {
    try { await authLogout(); } catch (e) { /* 无状态登出——服务端失败忽略（G-34） */ }
    closeMenus();
    handleAuthExpired(t("user.menu.loggedOut"));
    return false;
  },
};

Object.assign(INPUTS, {
  /* 用户菜单在顶栏动态渲染：改密输入不触发整壳重渲（返回 false），否则菜单
   * innerHTML 重建会收起弹层/丢焦点；值仍写 AUTH.form 供动作读取。 */
  userPwOld: (v) => { AUTH.form.pwOld = v; return false; },
  userPwNew: (v) => { AUTH.form.pwNew = v; return false; },
  userPwConfirm: (v) => { AUTH.form.pwConfirm = v; return false; },
});

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

/* ---------- boot（DOMContentLoaded——晚于全部 views/*.js 注册） ----------
 * D25 local（m4-3a）：先取匿名 /api/auth/config 过 boot 门——
 *  - local_login_enabled/auth_mode=local → AUTH.mode=local → bootLocal
 *    （setup 屏 / 邀请接受 / 登录屏 / 已存 token 恢复会话）；
 *  - 否则（sso，含 config 不可达/404 的 fail-safe）→ 原 sso boot 逻辑零变化。 */
async function boot() {
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

  let config = null;
  try { config = await authConfig(); } catch (e) { config = null; /* 失败/404 → sso 分支 */ }
  const local = !!(config && (config.local_login_enabled === true || config.auth_mode === "local"));
  if (local) {
    AUTH.mode = "local";
    cfg.authMode = "local";
    saveCfg();
    document.body.classList.add("auth-local");
    await bootLocal(config);
    return;
  }

  /* sso 形态（默认）——原有路径原样保留：render + loadMeta/onEnter 或 openConn。 */
  AUTH.mode = "sso";
  AUTH.screen = null;
  cfg.authMode = "sso";
  saveCfg();
  document.body.classList.remove("auth-local", "auth-screen");
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
