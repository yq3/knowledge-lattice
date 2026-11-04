/* views/ops.js —— 任务与审计（ui-1 功能平移自旧薄壳，新设计系统样式）：
 * 任务 ledger（行内取消·非终态）+ 类型/状态中文化 pill + 嵌入覆盖率面板
 * （embed_model/dim/totals/每库 bars/reembed 窗口）+ 重嵌入投递（doc_id +
 * embed_model?——换模型重嵌入 sysadmin 专属，403 由服务端回显）+ 审计表
 * （scope：metadata=系统管理员剥详情）+ stats maintenance kv（11 键；null →
 * 「尚无运行记录」）。 */
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

function viewOps() {
  if (!connected()) return connGate();
  return `
  <header class="head"><h1>${esc(t("ops.title"))}</h1>
    <p class="lede">${t("ops.lede")}</p>
    <div class="head-act"><button class="btn ghost" data-act="opsRefresh">${esc(t("common.refresh"))}</button></div>
  </header>
  ${state.loading.ops ? loadingHTML("ops") : tasksHTML()}
  ${coverageHTML()}
  ${statsHTML()}
  ${auditHTML()}`;
}

async function onEnterOps() {
  if (!connected()) return;
  state.loading.ops = true;
  render();
  await Promise.all([
    loadTasks(),
    loadCoverage().catch(() => { state.ops.coverage = { error: true }; }),
    loadAudit().catch(() => { state.ops.audit = { error: true }; }),
    loadStats().catch(() => { state.ops.stats = { error: true }; }),
  ]);
  state.loading.ops = false;
  render();
}

async function loadTasks() {
  try {
    const body = await listTasks(cfg.org);
    state.ops.tasks = body.tasks || [];
  } catch (e) {
    state.ops.tasks = state.ops.tasks || [];
  }
}

async function loadCoverage() {
  try { state.ops.coverage = await embeddingCoverage(cfg.org); }
  catch (e) { state.ops.coverage = { error: e.status }; }
}

async function loadAudit() {
  try { state.ops.audit = await audit(cfg.org, 50); }
  catch (e) { state.ops.audit = { error: e.status }; }
}

async function loadStats() {
  try { state.ops.stats = await stats(cfg.org); }
  catch (e) { state.ops.stats = { error: e.status }; }
}

/* ---------- 任务 ledger ---------- */

function tasksHTML() {
  const tasks = state.ops.tasks || [];
  return `<table class="ledger">
    <thead><tr><th>${esc(t("ops.col.task"))}</th><th>${esc(t("ops.col.type"))}</th><th>${esc(t("ops.col.doc"))}</th><th>${esc(t("ops.col.status"))}</th><th class="num">${esc(t("ops.col.attempts"))}</th><th>${esc(t("ops.col.note"))}</th><th>${esc(t("ops.col.updated"))}</th><th></th></tr></thead>
    <tbody>${tasks.length ? tasks.map((task) => `<tr>
      <td class="mono tiny">${esc(task.task_id)}</td>
      <td><span class="tag">${esc(taskTypeLabel(task.type))}</span></td>
      <td class="mono tiny">${esc(task.doc_id ?? "—")}</td>
      <td>${stPill(task.status)}${(task.error || "").startsWith("cancelled:") ? ` <span class="tag">${esc(t("ops.cancelled"))}</span>` : ""}</td>
      <td class="num">${esc(task.attempts ?? 0)}</td>
      <td class="tiny muted" title="${esc(task.error || "")}">${esc(task.error ? String(task.error).slice(0, 60) : "—")}</td>
      <td class="mono tiny muted">${esc(short(task.updated_at))}</td>
      <td>${["pending", "leased", "running"].includes(task.status)
        ? `<button class="btn ghost sm" data-act="taskCancel" data-id="${esc(task.task_id)}" title="POST /tasks/${esc(task.task_id)}/cancel">${esc(t("ops.cancel"))}</button>`
        : `<span class="tiny muted">—</span>`}</td>
    </tr>`).join("") : `<tr><td colspan="8" class="tiny muted" style="padding:20px 16px">${esc(t("ops.tasks.empty"))}</td></tr>`}</tbody>
  </table>`;
}

/* ---------- 嵌入覆盖率面板 ---------- */

function coverageHTML() {
  const c = state.ops.coverage;
  if (!c) return "";
  if (c.error) return `<section class="pane" style="margin-top:20px"><div class="lane-h"><h3>${esc(t("ops.cover.title"))}</h3></div><div class="tiny muted">${esc(t("ops.cover.denied", { status: c.error }))}</div></section>`;
  const pct = (a, b) => (b > 0 ? Math.round((a / b) * 1000) / 10 : 100);
  const reembed = c.reembed && c.reembed.status ? reembedHTML(c.reembed) : `<span class="tiny muted">${esc(t("ops.cover.noReembed"))}</span>`;
  return `<section class="pane" style="margin-top:20px">
    <div class="lane-h"><h3>${esc(t("ops.cover.title"))}</h3><span class="tiny muted">${esc(t("ops.cover.note"))}</span></div>
    <dl class="kv">
      <dt>${esc(t("ops.cover.model"))}</dt><dd><code>${esc(c.embed_model)}</code> · dim <b>${esc(c.dim)}</b></dd>
      <dt>${esc(t("ops.cover.totals"))}</dt><dd><b>${esc(c.totals.done)}</b> / ${esc(c.totals.total)}（${pct(c.totals.done, c.totals.total)}%）</dd>
      <dt>${esc(t("ops.cover.reembed"))}</dt><dd>${reembed}</dd>
    </dl>
    <div class="defn-k" style="margin:12px 0 6px">${esc(t("ops.cover.byDs"))}</div>
    <div class="funnel">${(c.coverage || []).map((x) => `<div class="fn-row" style="grid-template-columns:120px 1fr 64px"><span class="tiny">${esc(x.dataset_name)}</span>
      <div class="fn-bar"><span class="fb-ok" style="width:${pct(x.done, x.total)}%"></span></div>
      <span class="fn-n">${esc(x.done)}/${esc(x.total)}</span></div>`).join("") || `<span class="tiny muted">${esc(t("ops.cover.noDs"))}</span>`}
    </div>
    <div class="inline-act" style="margin-top:14px">
      <input class="inp" data-in="reembedDoc" style="width:240px" placeholder="${esc(t("ops.reembed.docPh"))}" value="${esc(state.ops.reembedDoc)}">
      <input class="inp" data-in="reembedModel" style="width:220px" placeholder="${esc(t("ops.reembed.modelPh"))}" value="${esc(state.ops.reembedModel)}">
      <button class="btn sm" data-act="reembedGo">${esc(t("ops.reembed.go"))}</button>
      <span class="tiny muted">${t("ops.reembed.note")}</span>
    </div>
  </section>`;
}

function reembedHTML(r) {
  return `<span class="pill run">${esc(stLabel(r.status) || r.status)}</span> · <b>${esc(r.done)}</b> / ${esc(r.total)}${r.target_model ? ` → <code>${esc(r.target_model)}</code>` : ""} <span class="tiny muted">${esc(t("ops.cover.blueGreen"))}</span>`;
}

/* ---------- stats / 审计 ---------- */

function statsHTML() {
  const s = state.ops.stats;
  if (!s) return "";
  const m = s.maintenance;
  if (s.error) return `<section class="pane" style="margin-top:20px"><div class="lane-h"><h3>${esc(t("ops.stats.title"))}</h3></div><div class="tiny muted">${esc(t("ops.stats.denied", { status: s.error }))}</div></section>`;
  if (!m) return `<section class="pane" style="margin-top:20px"><div class="lane-h"><h3>${esc(t("ops.stats.title"))}</h3><span class="tiny muted">${esc(t("ops.stats.note"))}</span></div><div class="tiny muted">${esc(t("ops.stats.none"))}</div></section>`;
  return `<section class="pane" style="margin-top:20px">
    <div class="lane-h"><h3>${esc(t("ops.stats.title"))}</h3><span class="tiny muted">${esc(t("ops.stats.note"))}</span></div>
    <dl class="kv">${Object.entries(m).map(([k, v]) =>
      `<dt class="mono tiny">${esc(k)}</dt><dd class="tiny">${esc(typeof v === "object" ? JSON.stringify(v) : String(v))}</dd>`).join("")}</dl>
  </section>`;
}

/* ---------- 审计双泳道（原型 .lanes：查询类 vs 治理类——按 action 前缀分流） ----------
 * 事件名实读（domain/audit_events.py + search 审计写点）：查询类 = search. 前缀
 * （search.acl_intercept / search.degraded）与 semantic.restricted_access（读路径
 * 权限事件）；治理类 = document./upload./task.cancel/dataset./org.created/
 * grants.replace/dimension./member./maintenance.run/semantic.{sync,build,yaml_merge}/auth.。
 * scope=metadata（系统管理员）时 detail_json 缺失——只显元数据行。 */
const AUDIT_QUERY_PREFIXES = ["search.", "semantic.restricted_access"];

function auditEventLane(action) {
  const a = String(action || "");
  return AUDIT_QUERY_PREFIXES.some((p) => a.startsWith(p)) ? "query" : "gov";
}

function auditEvHTML(e) {
  const detail = e.detail_json != null ? String(e.detail_json) : null;
  return `<div class="ev"><span class="ev-t">${esc(short(e.created_at))}</span><div>
    <div class="ev-a">${esc(e.actor ?? "")} · ${esc(e.action ?? "")}</div>
    ${detail ? `<div class="ev-d mono tiny" style="word-break:break-all">${esc(detail.slice(0, 240))}${detail.length > 240 ? "…" : ""}</div>` : ""}
    <div class="ev-m">${e.outcome === "refused" ? `<span class="pill bad">refused</span>` : `<span class="pill ok">${esc(e.outcome || "accepted")}</span>`}</div>
  </div></div>`;
}

function auditLaneHTML(title, note, events, emptyKey) {
  return `<section><div class="lane-h"><h3>${esc(title)}</h3><span class="tiny muted">${esc(note)}</span></div>
    ${events.length ? events.map(auditEvHTML).join("") : `<div class="tiny muted" style="padding:16px 0">${esc(t(emptyKey))}</div>`}
  </section>`;
}

function auditHTML() {
  const a = state.ops.audit;
  if (!a) return "";
  if (a.error) return `<section class="pane" style="margin-top:20px"><div class="lane-h"><h3>${esc(t("ops.audit.title"))}</h3></div><div class="tiny muted">${esc(t("ops.audit.denied", { status: a.error }))}</div></section>`;
  const events = a.events || [];
  const query = events.filter((e) => auditEventLane(e.action) === "query");
  const gov = events.filter((e) => auditEventLane(e.action) === "gov");
  return `<div class="lanes" style="margin-top:24px">
    ${auditLaneHTML(t("ops.audit.queryLane"), t("ops.audit.queryNote"), query, "ops.audit.queryEmpty")}
    ${auditLaneHTML(t("ops.audit.govLane"), t("ops.audit.govNote"), gov, "ops.audit.govEmpty")}
  </div>
  <div class="tiny muted" style="margin-top:12px">${t("ops.audit.foot", { org: esc(cfg.org) })}${a.scope === "full" ? "" : " · " + esc(t("ops.audit.metadata"))}</div>`;
}

/* ---------- 动作与输入 ---------- */

Object.assign(actions, {
  async opsRefresh() {
    await onEnterOps();
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

VIEWS.ops = { render: viewOps, onEnter: onEnterOps };
