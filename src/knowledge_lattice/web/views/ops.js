/* views/ops.js —— 任务与审计（四个子分区 tab：任务 / 嵌入覆盖率 / 维护任务计数 /
 * 审计）：
 * 任务 ledger（行内取消·非终态 + 类型/状态中文化 pill）；嵌入覆盖率面板
 * （embed_model/dim/totals/每库 bars/reembed 窗口）+ 重嵌入投递（doc_id +
 * embed_model?——换模型重嵌入 sysadmin 专属，403 由服务端回显）；审计双泳道
 * （scope：metadata=系统管理员剥详情）；stats 维护任务计数（注册表键；null →
 * 「尚无运行记录」）。
 *
 * 2026-11-21 布局修正（用户走查反馈）：四块内容原先纵向堆叠在同一条滚动页上——
 * 覆盖率 / 维护任务计数两个卡片沿用了 .pane，而 .pane 是**侧栏详情面板**
 * （position:sticky + 固定 top + 内滚动）：同一滚动容器里等偏移吸附，后一块会
 * 压住前一块（维护任务计数在 DOM 末尾 → 视觉最顶层）。同时 .pane .kv 的
 * 76px 固定键列容不下 maintenance 的 mono 长键（audit_outbox_trimmed 等），
 * 键文本溢出压到值上；嵌套 dict 又被 JSON.stringify 成单行，整块不可读。
 * 改法（仿「维度与权限」页）：
 * ① 四个分区各占一个 tab（state.sub.ops），互斥渲染，不再纵向堆叠；
 * ② 内容卡片改用静态 .card（无 sticky、无内滚动）；
 * ③ 维护任务计数改用内容自适应 key/value 网格（长键可折行、嵌套 dict/数组
 *    递归展开为子键行，不再出现单行 JSON 与键值重叠）。 */
"use strict";

const TASK_TYPE_KEY = {
  ingest: "ops.type.ingest", reindex: "ops.type.reindex", reembed: "ops.type.reembed",
  maintenance: "ops.type.maintenance", semantic_sync: "ops.type.semanticSync",
  semantic_build: "ops.type.semanticBuild", semantic_retag: "ops.type.semanticRetag",
};
function taskTypeLabel(type) {
  const key = TASK_TYPE_KEY[type];
  return key ? t(key) : type;
}

/* 子分区注册表（顺序 = tab 顺序；label 为 i18n 键） */
const OPS_TABS = [
  ["tasks", "ops.tab.tasks"],
  ["coverage", "ops.tab.coverage"],
  ["stats", "ops.tab.stats"],
  /* 审计拆两道为两个页面级 tab（2026-11-22 用户要求）：共用同一份 audit 数据，
   * 一次请求按 action 前缀分道，切 tab 零请求。 */
  ["audit_query", "ops.audit.queryLane"],
  ["audit_gov", "ops.audit.govLane"],
];

function opsTab() {
  const k = state.sub.ops;
  return OPS_TABS.some(([key]) => key === k) ? k : "tasks";
}

/* 分区独立加载态文案：复用 common.loading（如「嵌入覆盖率加载中…」） */
function opsLoadingHTML(tabKey) {
  return `<div class="loading">${esc(t("common.loading", { what: t(tabKey) }))}</div>`;
}

function viewOps() {
  if (!connected()) return connGate();
  const tab = opsTab();
  return `
  <header class="head"><h1>${esc(t("ops.title"))}</h1>
    <p class="lede">${t("ops.lede")}</p>
    <div class="head-act"><button class="btn ghost" data-act="opsRefresh">${esc(t("common.refresh"))}</button></div>
  </header>
  <nav class="sub-tabs">${OPS_TABS.map(([k, labelKey]) => `<button class="sub-tab ${tab === k ? "on" : ""}" data-act="sub" data-s="ops" data-v="${k}">${esc(t(labelKey))}</button>`).join("")}</nav>
  ${tab === "tasks" ? tasksTabHTML()
    : tab === "coverage" ? coverageTabHTML()
    : tab === "stats" ? statsTabHTML()
    : auditTabHTML(tab === "audit_gov" ? "gov" : "query")}`;
}

/* ---------- 分区装载（tab 切换 / 进入视图同一入口） ---------- */

/* 按需装载：任务行恒取（导航徽标「N 进行」与任务分区都用它），其余分区
 * 首次进入才取——已有缓存不重复请求（刷新按钮强制重取当前分区）。 */
function opsLoadJobs(tab) {
  const jobs = [];
  if (state.ops.tasks == null) jobs.push(loadTasks());
  if (tab === "coverage" && state.ops.coverage == null) jobs.push(loadCoverage());
  if (tab === "stats" && state.ops.stats == null) jobs.push(loadStats());
  if (tab.startsWith("audit") && state.ops.audit == null) jobs.push(loadAudit());
  return jobs;
}

async function onEnterOps() {
  if (!connected()) return;
  const ep = state.epoch; // P1-5
  // 二次刷新不闪空（ui-3 加载态约定）：仅首装（tasks 尚无缓存）显示整视图 loading，
  // 之后刷新保持既有表渲染，数据到后原位更新。
  state.loading.ops = state.ops.tasks == null;
  render();
  await Promise.all(opsLoadJobs(opsTab()));
  if (ep !== state.epoch) return;
  state.loading.ops = false;
  render();
}

/* 子分区切换（app.js actions.sub 的 onSub 钩子——本页懒装载入口） */
async function onSubOps(tab) {
  if (!connected()) return;
  await Promise.all(opsLoadJobs(tab));
}

async function loadTasks() {
  const ep = state.epoch; // P1-5
  try {
    const body = await listTasks(cfg.org);
    if (ep !== state.epoch) return;
    state.ops.tasks = body.tasks || [];
    state.ops.tasksErr = null;
  } catch (e) {
    if (ep !== state.epoch) return;
    state.ops.tasks = state.ops.tasks || [];
    state.ops.tasksErr = String((e && e.message) || e); // P2-3：失败显错误态（非「暂无任务」空态）
  }
}

async function loadCoverage() {
  const ep = state.epoch;
  try {
    const body = await embeddingCoverage(cfg.org);
    if (ep !== state.epoch) return;
    state.ops.coverage = body;
  } catch (e) {
    if (ep !== state.epoch) return;
    state.ops.coverage = { error: e.status };
  }
}

async function loadAudit() {
  const ep = state.epoch;
  try {
    const body = await audit(cfg.org, state.ops.auditLimit);
    if (ep !== state.epoch) return;
    state.ops.audit = body;
  } catch (e) {
    if (ep !== state.epoch) return;
    state.ops.audit = { error: e.status };
  }
}

async function loadStats() {
  const ep = state.epoch;
  try {
    const body = await stats(cfg.org);
    if (ep !== state.epoch) return;
    state.ops.stats = body;
  } catch (e) {
    if (ep !== state.epoch) return;
    state.ops.stats = { error: e.status };
  }
}

/* ---------- 任务 ledger ---------- */

function tasksTabHTML() {
  if (state.loading.ops) return opsLoadingHTML("ops.tab.tasks");
  return tasksHTML();
}

function tasksHTML() {
  const tasks = state.ops.tasks || [];
  if (state.ops.tasksErr) return `<div class="empty" style="margin:0"><h3>${esc(t("ops.tasks.loadErr", { err: esc(state.ops.tasksErr) }))}</h3>
    <div style="margin-top:16px"><button class="btn ghost sm" data-act="opsRefresh">${esc(t("common.retry"))}</button></div></div>`; // P2-3：失败≠空态
  return `<table class="ledger">
    <thead><tr><th>${esc(t("ops.col.task"))}</th><th>${esc(t("ops.col.type"))}</th><th>${esc(t("ops.col.doc"))}</th><th>${esc(t("ops.col.status"))}</th><th class="num">${esc(t("ops.col.attempts"))}</th><th>${esc(t("ops.col.note"))}</th><th>${esc(t("ops.col.updated"))}</th><th></th></tr></thead>
    <tbody>${tasks.length ? tasks.map((task) => `<tr>
      <td class="mono tiny">${esc(task.task_id)}</td>
      <td><span class="tag">${esc(taskTypeLabel(task.type))}</span></td>
      <td class="mono tiny">${esc(task.doc_id ?? "—")}</td>
      <td>${stPill(task.status)}${(task.error || "").startsWith("cancelled:") ? ` <span class="tag">${esc(t("ops.cancelled"))}</span>` : ""}</td>
      <td class="num">${esc(task.attempts ?? 0)}</td>
      <td class="tiny muted" title="${esc(task.error || "")}">${esc(task.error ? String(task.error).slice(0, 60) : "—")}</td>
      <td class="mono tiny muted">${tsHTML(task.updated_at, "mono tiny muted")}</td>
      <td>${["pending", "leased", "running"].includes(task.status)
        ? `<button class="btn ghost sm" data-act="taskCancel" data-id="${esc(task.task_id)}" title="POST /tasks/${esc(task.task_id)}/cancel">${esc(t("ops.cancel"))}</button>`
        : `<span class="tiny muted">—</span>`}</td>
    </tr>`).join("") : `<tr><td colspan="8" class="tiny muted" style="padding:20px 16px">${esc(t("ops.tasks.empty"))}</td></tr>`}</tbody>
  </table>
  <div class="tbl-foot"><span class="tiny muted">${esc(t("ops.tasks.note"))}</span></div>`;
}

/* ---------- 嵌入覆盖率（分区卡片） ---------- */

function coverageTabHTML() {
  const c = state.ops.coverage;
  const panel = (body) => `<section class="card">
    <div class="lane-h"><h3>${esc(t("ops.cover.title"))}</h3><span class="tiny muted">${esc(t("ops.cover.note"))}</span></div>
    ${body}
  </section>`;
  if (!c) return panel(opsLoadingHTML("ops.tab.coverage"));
  if (c.error != null) return panel(`<div class="tiny muted">${esc(t("ops.cover.denied", { status: c.error }))}</div>`);
  return panel(coverageBodyHTML(c));
}

function coverageBodyHTML(c) {
  const pct = (a, b) => (b > 0 ? Math.round((a / b) * 1000) / 10 : 100);
  const reembed = c.reembed && c.reembed.status ? reembedHTML(c.reembed) : `<span class="tiny muted">${esc(t("ops.cover.noReembed"))}</span>`;
  return `<dl class="kv" style="max-width:840px">
      <dt>${esc(t("ops.cover.model"))}</dt><dd><code>${esc(c.embed_model)}</code> · dim <b>${esc(c.dim)}</b></dd>
      <dt>${esc(t("ops.cover.totals"))}</dt><dd><b>${esc(c.totals.done)}</b> / ${esc(c.totals.total)}（${pct(c.totals.done, c.totals.total)}%）</dd>
      <dt>${esc(t("ops.cover.reembed"))}</dt><dd>${reembed}</dd>
    </dl>
    <div class="defn-k" style="margin:16px 0 6px">${esc(t("ops.cover.byDs"))}</div>
    <div class="funnel" style="max-width:840px">${(c.coverage || []).map((x) => `<div class="fn-row" style="grid-template-columns:150px 1fr 64px"><span class="tiny">${esc(x.dataset_name)}</span>
      <div class="fn-bar"><span class="fb-ok" style="width:${pct(x.done, x.total)}%"></span></div>
      <span class="fn-n">${esc(x.done)}/${esc(x.total)}</span></div>`).join("") || `<span class="tiny muted">${esc(t("ops.cover.noDs"))}</span>`}
    </div>
    <div class="inline-act" style="margin-top:16px;padding-top:16px;border-top:1px solid var(--rule)">
      <input class="inp" data-in="reembedDoc" style="width:240px" placeholder="${esc(t("ops.reembed.docPh"))}" value="${esc(state.ops.reembedDoc)}">
      <input class="inp" data-in="reembedModel" style="width:220px" placeholder="${esc(t("ops.reembed.modelPh"))}" value="${esc(state.ops.reembedModel)}">
      <button class="btn sm" data-act="reembedGo">${esc(t("ops.reembed.go"))}</button>
      <span class="tiny muted">${t("ops.reembed.note")}</span>
    </div>`;
}

function reembedHTML(r) {
  return `<span class="pill run">${esc(stLabel(r.status) || r.status)}</span> · <b>${esc(r.done)}</b> / ${esc(r.total)}${r.target_model ? ` → <code>${esc(r.target_model)}</code>` : ""} <span class="tiny muted">${esc(t("ops.cover.blueGreen"))}</span>`;
}

/* ---------- 维护任务计数（分区卡片） ---------- */

function statsTabHTML() {
  const s = state.ops.stats;
  const panel = (body) => `<section class="card">
    <div class="lane-h"><h3>${esc(t("ops.stats.title"))}</h3><span class="tiny muted">${esc(t("ops.stats.note"))}</span></div>
    ${body}
  </section>`;
  if (!s) return panel(opsLoadingHTML("ops.tab.stats"));
  if (s.error != null) return panel(`<div class="tiny muted">${esc(t("ops.stats.denied", { status: s.error }))}</div>`);
  return panel(statsBodyHTML(s.maintenance));
}

/* 维护计数键名 → 界面文案（后端注册表的英文标识，直接显示等于全英文页）。
 * 未知键回落原始键名——后端新增任务体时不至于空白（前向兼容）。 */
const STAT_KEY_I18N = {
  /* 顶层（worker/maintenance.py 的 MAINTENANCE_BODIES 注册名） */
  credentials_purged: "ops.stats.k.credentialsPurged",
  memberships_purged: "ops.stats.k.membershipsPurged",
  tombstones_purged: "ops.stats.k.tombstonesPurged",
  task_rows_trimmed: "ops.stats.k.taskRowsTrimmed",
  audit_shipped: "ops.stats.k.auditShipped",
  audit_months_sealed: "ops.stats.k.auditMonthsSealed",
  audit_months_pruned: "ops.stats.k.auditMonthsPruned",
  backup_snapshot: "ops.stats.k.backupSnapshot",
  audit_outbox_trimmed: "ops.stats.k.auditOutboxTrimmed",
  semantic_daily_sync: "ops.stats.k.semanticDailySync",
  semantic_reconcile: "ops.stats.k.semanticReconcile",
  /* 嵌套子键（后端返回 dict 的字段） */
  shipped: "ops.stats.k.shipped",
  sealed: "ops.stats.k.sealed",
  skipped_pending: "ops.stats.k.skippedPending",
  pruned: "ops.stats.k.pruned",
  database: "ops.stats.k.database",
  objects: "ops.stats.k.objects",
  audit_months: "ops.stats.k.auditMonths",
  created_at: "ops.stats.k.createdAt",
  enqueued: "ops.stats.k.enqueued",
  sources: "ops.stats.k.sources",
  orgs: "ops.stats.k.orgs",
  retag_enqueued: "ops.stats.k.retagEnqueued",
  retag_throttled: "ops.stats.k.retagThrottled",
};

function statLabel(key) {
  const ik = STAT_KEY_I18N[key];
  if (!ik) return key;
  const label = t(ik);
  return label === ik ? key : label; // 缺键回落原始键名
}

/* 值渲染（递归）：数/字符串/布尔 → 叶子；数组 → chips；dict → 子键行（ops-sub）。
 * 长键/长值一律可折行（CSS overflow-wrap）——固定窄列溢出压值的老问题不再存在。 */
function statValueHTML(v) {
  if (Array.isArray(v)) {
    return v.length
      ? `<span class="chips">${v.map((x) => `<span class="chip">${esc(statLeafText(x))}</span>`).join("")}</span>`
      : `<span class="muted">—</span>`;
  }
  if (v != null && typeof v === "object") {
    return `<dl class="ops-sub">${Object.entries(v).map(([k, vv]) =>
      `<dt>${esc(statLabel(k))}</dt><dd>${statValueHTML(vv)}</dd>`).join("")}</dl>`;
  }
  if (v == null || v === "") return `<span class="muted">—</span>`;
  if (typeof v === "number") return `<b>${esc(String(v))}</b>`;
  if (typeof v === "boolean") return esc(v ? t("common.yes") : t("common.no"));
  return esc(String(v));
}

/* 叶子文本（chips 内用）：对象压成 k=v · k=v，数组压成逗号分隔——仍走 esc()。 */
function statLeafText(v) {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.map(statLeafText).join(t("common.sep")) : "—";
  if (typeof v === "object") {
    return Object.entries(v).map(([k, vv]) => `${statLabel(k)}=${statLeafText(vv)}`).join(" · ");
  }
  return String(v);
}

function statsBodyHTML(m) {
  if (!m) return `<div class="tiny muted">${esc(t("ops.stats.none"))}</div>`;
  const errors = m.errors == null ? [] : (Array.isArray(m.errors) ? m.errors : [String(m.errors)]);
  const rowsHTML = Object.entries(m).filter(([k]) => k !== "errors").map(([k, v]) => {
    // dict 与「对象元素数组」占满整行（子键行放得下）；标量与标量数组留在两列网格里
    const wide = v != null && typeof v === "object"
      && (!Array.isArray(v) || v.some((x) => x != null && typeof x === "object"));
    return `<div class="ops-stat${wide ? " wide" : ""}">
      <dt class="os-k">${esc(statLabel(k))}</dt><dd class="os-v">${statValueHTML(v)}</dd>
    </div>`;
  }).join("");
  if (!rowsHTML && !errors.length) return `<div class="tiny muted">${esc(t("ops.stats.none"))}</div>`;
  return `${errors.length ? `<div class="note seal"><b>${esc(t("ops.stats.errors", { n: errors.length }))}</b>
      <ul class="ops-errs">${errors.map((e) => `<li>${esc(String(e))}</li>`).join("")}</ul></div>` : ""}
    ${rowsHTML ? `<dl class="ops-stats">${rowsHTML}</dl>` : ""}`;
}

/* ---------- 审计双道（查询类 vs 治理类——按 action 前缀分流） ----------
 * 版式：2026-11-22 起两道分别是**页面级 tab**（OPS_TABS 的 audit_query / audit_gov），
 * 一次只渲染一道。演进：原型 v0.6 左右并排（半宽下 detail 换行过密、两道条数不等
 * 高度差悬殊、独立倒序时间线无法对齐）→ 纵向堆叠（页面过长）→ 页面级 tab（用户要求）。
 * 两道共用一次 GET audit：前端按 action 前缀分道，切 tab 零请求。
 * 事件名实读（domain/audit_events.py + search 审计写点）：查询类 = search. 前缀
 * （search.acl_intercept / search.degraded）与 semantic.restricted_access（读路径
 * 权限事件）；治理类 = document./upload./task.cancel/dataset./org.created/
 * grants.replace/dimension./member./maintenance.run/semantic.{sync,build,yaml_merge}/auth.。
 * scope=metadata（系统管理员）时 detail_json 缺失——只显元数据行。 */
const AUDIT_QUERY_PREFIXES = ["search.", "semantic.restricted_access"];

/* 审计两道元数据（lane 键 = OPS_TABS 的 audit_query / audit_gov） */
const AUDIT_LANES = [
  ["query", "ops.audit.queryLane", "ops.audit.queryNote", "ops.audit.queryEmpty"],
  ["gov", "ops.audit.govLane", "ops.audit.govNote", "ops.audit.govEmpty"],
];


function auditEventLane(action) {
  const a = String(action || "");
  return AUDIT_QUERY_PREFIXES.some((p) => a.startsWith(p)) ? "query" : "gov";
}

function auditEvHTML(e) {
  const detail = e.detail_json != null ? String(e.detail_json) : null;
  return `<div class="ev"><span class="ev-t">${tsHTML(e.created_at, "mono")}</span><div>
    <div class="ev-a">${esc(e.actor ?? "")} · ${esc(e.action ?? "")}</div>
    ${detail ? `<div class="ev-d mono tiny" style="word-break:break-all" title="${esc(detail)}">${esc(detail.slice(0, 240))}${detail.length > 240 ? "…" : ""}</div>` : ""}
    <div class="ev-m">${e.outcome === "refused" ? `<span class="pill bad">refused</span>` : `<span class="pill ok">${esc(e.outcome || "accepted")}</span>`}</div>
  </div></div>`;
}

function auditLaneHTML(note, events, emptyKey) {
  return `<section><div class="lane-note">${esc(note)}</div>
    ${events.length ? events.map(auditEvHTML).join("") : `<div class="tiny muted" style="padding:16px 0">${esc(t(emptyKey))}</div>`}
  </section>`;
}

function auditTabHTML(lane) {
  const a = state.ops.audit;
  const meta = AUDIT_LANES.find(([k]) => k === lane) || AUDIT_LANES[0];
  const [, labelKey, noteKey, emptyKey] = meta;
  if (!a) return `<section class="card"><div class="lane-h"><h3>${esc(t(labelKey))}</h3></div>${opsLoadingHTML(labelKey)}</section>`;
  if (a.error != null) return `<section class="card"><div class="lane-h"><h3>${esc(t(labelKey))}</h3></div><div class="tiny muted">${esc(t("ops.audit.denied", { status: a.error }))}</div></section>`;
  const events = a.events || [];
  const mine = events.filter((e) => auditEventLane(e.action) === lane);
  return `<div class="lanes">${auditLaneHTML(t(noteKey), mine, emptyKey)}</div>
  <div class="tbl-foot" style="margin-top:var(--s4)">
    <span class="tiny muted">${t("ops.audit.foot", { org: esc(cfg.org) })}${a.scope === "full" ? "" : " · " + esc(t("ops.audit.metadata"))} · ${esc(t("common.recentN", { n: state.ops.auditLimit }))}</span>
    ${state.ops.auditLimit < 200
      ? `<button class="btn ghost sm" data-act="auditMore">${esc(t("common.loadMoreN", { a: state.ops.auditLimit, b: Math.min(state.ops.auditLimit * 2, 200) }))}</button>`
      : `<span class="tiny muted">${esc(t("ops.audit.limitCap"))}</span>`}
  </div>`;
}

/* ---------- 动作与输入 ---------- */

Object.assign(actions, {
  /* 刷新当前分区（任务行恒刷新——导航徽标口径；其余按需） */
  async opsRefresh() {
    const tab = opsTab();
    state.loading.ops = state.ops.tasks == null;
    render();
    await Promise.all([
      loadTasks(),
      tab === "coverage" ? loadCoverage() : Promise.resolve(),
      tab === "stats" ? loadStats() : Promise.resolve(),
      tab === "audit" ? loadAudit() : Promise.resolve(),
    ]);
    state.loading.ops = false;
    render();
    return false;
  },
  /* 审计「加载更多」（ui-3 条数与分页约定）：limit 阶梯 50→100→200，上限 200 停 */
  async auditMore() {
    if (state.ops.auditLimit >= 200) return false;
    state.ops.auditLimit = Math.min(state.ops.auditLimit * 2, 200);
    await loadAudit();
    render();
    return false;
  },
  async taskCancel(el) {
    const id = el.dataset.id;
    try {
      const task = await cancelTask(cfg.org, id);
      toast(task.cancelled ? t("ops.cancel.done") : t("ops.cancel.idle", { status: esc(task.status) }));
    } catch (e) { errToast(e); }
    await loadTasks();
    render();
    return false;
  },
  async reembedGo() {
    const docId = state.ops.reembedDoc.trim();
    if (!docId) { toast(esc(t("ops.reembed.needDoc"))); return false; }
    const model = state.ops.reembedModel.trim();
    try {
      const body = await reindex(cfg.org, docId, model || undefined);
      toast(t("ops.reembed.ok", { type: esc(body.type), task: esc(body.task_id) }));
    } catch (e) { errToast(e); return false; }
    state.ops.reembedDoc = ""; state.ops.reembedModel = "";
    await Promise.all([loadTasks(), loadCoverage().catch(() => {})]);
    render();
    return false;
  },
});

Object.assign(INPUTS, {
  reembedDoc: (v) => { state.ops.reembedDoc = v; return false; },
  reembedModel: (v) => { state.ops.reembedModel = v; return false; },
});

VIEWS.ops = { render: viewOps, onEnter: onEnterOps, onSub: onSubOps };
