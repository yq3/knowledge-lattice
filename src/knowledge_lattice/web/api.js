/* api.js —— REST 适配层（ui-1）：全部 fetch 收口。
 * - 连接状态 cfg = {baseToken, activeToken, org, lensUserId}，localStorage `lattice.cfg` 持久化；
 *   baseToken = 连接时粘贴的基 token（重签用）；activeToken = 实际请求用的 token（视角身份）。
 * - apiFetch(path, opts)：注入 Authorization / X-Org-Id / Content-Type；统一错误解析
 *   （body.detail || body.error——HTTPException 与 JSONResponse 两种错误体形态）；
 *   401 → toast + 打开连接设置；403 → toast 服务端 detail；网络异常 → toast。
 * - reissue({org?, userId?})：用 baseToken POST /api/dev/token 重签（dev 形态组织/身份切换）；
 *   给他人代签须系统管理员基 token（403）；生产无 dev 端点（404 → 提示直接粘贴已签 token）。
 * - 领域函数：每端点一函数。四处 contract-first 降级（be-① 文档列表 / m3-1 建库
 *   建维度与组织停用）各收口单函数并注释标记——后端实装后只改此处。
 * - pollTask：任务轮询（interval 1.5s / 终态停止 / 超时 120s / shouldStop 回调
 *   感知上下文切换即停——R2 P1-5，返回 null=已弃）。
 */
"use strict";

const CFG_KEY = "lattice.cfg";
const cfg = { baseToken: "", activeToken: "", org: "", lensUserId: "", baseUserId: "" };

function loadCfg() {
  try {
    const saved = JSON.parse(localStorage.getItem(CFG_KEY) || "{}");
    cfg.baseToken = saved.baseToken || "";
    cfg.activeToken = saved.activeToken || "";
    cfg.org = saved.org || "";
    cfg.lensUserId = saved.lensUserId || "";
    cfg.baseUserId = saved.baseUserId || "";
  } catch (e) { /* 损坏配置忽略——视为未连接 */ }
}
function saveCfg() {
  localStorage.setItem(CFG_KEY, JSON.stringify(cfg));
}

/* JWT payload 只读解码（展示用——dev token 为未加密 JWT；服务端仍是权限唯一权威） */
function decodeJwt(token) {
  try {
    const part = String(token).split(".")[1];
    if (!part) return null;
    const json = decodeURIComponent(atob(part.replace(/-/g, "+").replace(/_/g, "/")).split("").map(c => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join(""));
    return JSON.parse(json);
  } catch (e) { return null; }
}

function connected() { return !!(cfg.activeToken && cfg.org); }

/* ---------- 统一请求与错误语义 ---------- */

class ApiError extends Error {
  constructor(status, message, body) {
    super(message || String(status));
    this.status = status;
    this.body = body || {};
  }
}

async function apiFetch(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (cfg.activeToken) headers["Authorization"] = "Bearer " + cfg.activeToken;
  if (cfg.org) headers["X-Org-Id"] = cfg.org;
  // opts.contentType 覆盖缺省 JSON（R2 P2-4：CSV 等纯文本体走 text/plain）
  if (opts.body != null && !(opts.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = opts.contentType || "application/json";
  }
  let resp;
  try {
    resp = await fetch(path, Object.assign({}, opts, { headers }));
  } catch (e) {
    toast(t("err.network"));
    throw new ApiError(0, t("err.network"));
  }
  if (resp.status === 401) {
    toast(t("err.auth401"));
    if (typeof openConn === "function") openConn();
  }
  return resp;
}

async function _parseBody(resp) {
  const text = await resp.text().catch(() => "");
  if (!text) return {};
  try { return JSON.parse(text); } catch (e) { return {}; }
}

async function apiJson(path, opts = {}) {
  const resp = await apiFetch(path, opts);
  const body = await _parseBody(resp);
  if (!resp.ok) {
    const msg = body.detail || body.error || resp.statusText || String(resp.status);
    if (resp.status === 403) toast(esc(String(msg)));
    throw new ApiError(resp.status, String(msg), body);
  }
  return body;
}

/* ---------- reissue：dev 形态组织/身份切换（POST /api/dev/token） ---------- */

async function reissue({ org, userId } = {}) {
  const body = {};
  if (org) body.org = org;
  if (userId) body.user_id = userId;
  let resp;
  try {
    resp = await fetch("/api/dev/token", {
      method: "POST",
      headers: Object.assign(
        { "Content-Type": "application/json" },
        cfg.baseToken ? { Authorization: "Bearer " + cfg.baseToken } : {},
      ),
      body: JSON.stringify(body),
    });
  } catch (e) {
    toast(t("err.network"));
    throw new ApiError(0, t("err.network"));
  }
  const data = await _parseBody(resp);
  if (!resp.ok) {
    if (resp.status === 403) toast(t("settings.reissue.403"));
    else if (resp.status === 404) toast(t("settings.reissue.404"));
    else toast(resp.status + " · " + esc(String(data.detail || data.error || resp.statusText || "")));
    throw new ApiError(resp.status, String(data.detail || data.error || ""));
  }
  cfg.activeToken = data.token;
  cfg.lensUserId = data.user_id || "";
  if (data.org) cfg.org = data.org;
  saveCfg();
  return data;
}

/* ---------- 领域函数（每端点一函数） ---------- */
const enc = encodeURIComponent;

function listOrgs() { return apiJson("/api/orgs"); }
function listDatasets(org) { return apiJson(`/api/orgs/${enc(org)}/datasets`); }

// m3-1 contract-first：POST /api/orgs/{org}/datasets 未实装（#13）——按自然契约
// 先行实装（POST JSON {name, description?}）；404 → 调用方降级提示「待 m3-1 后端轮次」。
function createDataset(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/datasets`, { method: "POST", body: JSON.stringify(body) });
}
function deleteDataset(org, id) {
  // R2 P1-1：DELETE 收口 apiJson 同款 !ok 抛 ApiError（204 空 body → {} 正常返回）
  return apiJson(`/api/orgs/${enc(org)}/datasets/${enc(id)}`, { method: "DELETE" });
}
function listDimensions(org) { return apiJson(`/api/orgs/${enc(org)}/dimensions`); }

// m3-1 contract-first：POST /api/orgs/{org}/dimensions 未实装（#13）——按自然契约
// 先行实装（POST JSON {key, name, required?}）；404 → 调用方降级提示。
function createDimension(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/dimensions`, { method: "POST", body: JSON.stringify(body) });
}

// be-1 contract-first：GET /api/orgs/{org}/documents 列表端点未实装——按提议契约先行
// （?dataset=&limit=&offset= → {documents:[…], total}）；404 → 调用方降级（横幅 + 会话缓存）。
function listDocuments(org, { dataset, limit = 200, offset = 0 } = {}) {
  const q = new URLSearchParams();
  if (dataset) q.set("dataset", dataset);
  q.set("limit", String(limit)); q.set("offset", String(offset));
  return apiJson(`/api/orgs/${enc(org)}/documents?` + q.toString());
}
function getDocument(org, docId) {
  return apiJson(`/api/orgs/${enc(org)}/documents/${enc(docId)}`);
}
function patchDocumentDims(org, docId, dims) {
  return apiJson(`/api/orgs/${enc(org)}/documents/${enc(docId)}/dimensions`, {
    method: "PATCH", body: JSON.stringify({ dims }),
  });
}
function deleteDocument(org, docId) {
  // R2 P1-1：同 deleteDataset——!ok 抛 ApiError，调用方 catch 分径
  return apiJson(`/api/orgs/${enc(org)}/documents/${enc(docId)}`, { method: "DELETE" });
}
function uploadMultipart(org, { file, dataset, title, dims, docId }) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("dataset", dataset);
  if (title) fd.append("title", title);
  fd.append("dims", JSON.stringify(dims || {}));
  if (docId) fd.append("doc_id", docId);
  return apiJson(`/api/orgs/${enc(org)}/documents`, { method: "POST", body: fd });
}
function getDocumentQuality(org, docId) {
  return apiJson(`/api/orgs/${enc(org)}/documents/${enc(docId)}/quality`);
}
function sampleQualityFlags({ n = 20, seed = "ui1" } = {}) {
  return apiJson(`/api/quality-flags/sample?n=${n}&seed=${enc(seed)}`);
}
function patchQualityFlag(flagId, body) {
  return apiJson(`/api/quality-flags/${enc(flagId)}`, { method: "PATCH", body: JSON.stringify(body) });
}
function listTasks(org) { return apiJson(`/api/orgs/${enc(org)}/tasks`); }
function getTask(org, taskId) { return apiJson(`/api/orgs/${enc(org)}/tasks/${enc(taskId)}`); }
function cancelTask(org, taskId) {
  return apiJson(`/api/orgs/${enc(org)}/tasks/${enc(taskId)}/cancel`, { method: "POST" });
}
async function pollTask(taskId, { interval = 1500, timeout = 120000, onTick, shouldStop } = {}) {
  const started = Date.now();
  for (;;) {
    if (shouldStop && shouldStop()) return null; // R2 P1-5：上下文已换（epoch 变）——静默停轮询
    const task = await getTask(cfg.org, taskId);
    if (onTick) onTick(task);
    if (task.status === "done" || task.status === "failed") return task;
    if (Date.now() - started > timeout) throw new ApiError(0, "poll timeout: " + taskId);
    await new Promise(r => setTimeout(r, interval));
  }
}
function search(body) {
  return apiJson("/api/search", { method: "POST", body: JSON.stringify(body) });
}

/* ---------- 权限/治理（access/ops 平移） ---------- */

async function exportGrants(org) {
  const resp = await apiFetch(`/api/orgs/${enc(org)}/grants/export`);
  if (!resp.ok) {
    const body = await _parseBody(resp);
    const msg = body.detail || body.error || resp.statusText || String(resp.status);
    if (resp.status === 403) toast(esc(String(msg)));
    throw new ApiError(resp.status, String(msg), body);
  }
  return resp.text();
}
function importGrants(org, csvText, dryRun) {
  // R2 P2-4：CSV 文本体显式 text/plain（缺省会误标 application/json）
  return apiJson(`/api/orgs/${enc(org)}/grants/import${dryRun ? "?dry_run=1" : ""}`, {
    method: "POST", body: csvText, contentType: "text/plain",
  });
}
function putGrants(org, userId, grants) {
  return apiJson(`/api/orgs/${enc(org)}/members/${enc(userId)}/grants`, {
    method: "PUT", body: JSON.stringify({ grants }),
  });
}
function patchValueStatus(org, dimId, valueId, body) {
  return apiJson(`/api/orgs/${enc(org)}/dimensions/${enc(dimId)}/values/${enc(valueId)}`, {
    method: "PATCH", body: JSON.stringify(body),
  });
}
function createValue(org, dimId, body) {
  return apiJson(`/api/orgs/${enc(org)}/dimensions/${enc(dimId)}/values`, {
    method: "POST", body: JSON.stringify(body),
  });
}
function retireDimension(org, dimId, confirm) {
  const q = confirm ? "?confirm=1" : "";
  return apiJson(`/api/orgs/${enc(org)}/dimensions/${enc(dimId)}/retire${q}`, { method: "POST" });
}
function reindex(org, docId, embedModel) {
  const q = embedModel ? `?embed_model=${enc(embedModel)}` : "";
  return apiJson(`/api/orgs/${enc(org)}/documents/${enc(docId)}/reindex${q}`, { method: "POST" });
}
function embeddingCoverage(org) { return apiJson(`/api/orgs/${enc(org)}/embedding-coverage`); }
function audit(org, limit = 50) {
  return apiJson(`/api/orgs/${enc(org)}/audit?limit=${limit}`);
}
function stats(org) { return apiJson(`/api/orgs/${enc(org)}/stats`); }

/* ---------- 业务语义（ui-2——§6.2 L1136-1143；契约字段实读 core/semantic） ---------- */

function searchSemanticEntities(org, { q, types, top_k = 20 } = {}) {
  const s = new URLSearchParams({ q, top_k: String(top_k) });
  (types || []).forEach((tp) => s.append("types", tp));
  return apiJson(`/api/orgs/${enc(org)}/semantic/entities?` + s.toString());
}
function getSemanticEntity(org, entityId, { expand, depth = 1, fanout_limit = 50, include } = {}) {
  const s = new URLSearchParams({ depth: String(depth), fanout_limit: String(fanout_limit) });
  (expand || []).forEach((x) => s.append("expand", x));
  (include || ["curated", "attrs", "aliases"]).forEach((x) => s.append("include", x));
  return apiJson(`/api/orgs/${enc(org)}/semantic/entities/${enc(entityId)}?` + s.toString());
}
function annotateText(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/semantic/annotate`, {
    method: "POST", body: JSON.stringify(body),
  });
}
function getL0(org) { return apiJson(`/api/orgs/${enc(org)}/semantic/l0`); }
function describeTable(org, tableKey, { columns } = {}) {
  const s = new URLSearchParams();
  (columns || []).forEach((c) => s.append("columns", c));
  const qs = s.toString();
  return apiJson(`/api/orgs/${enc(org)}/semantic/tables/${enc(tableKey)}/describe${qs ? "?" + qs : ""}`);
}
function listSyncRuns(org, { limit = 50, adapter, status } = {}) {
  const s = new URLSearchParams({ limit: String(limit) });
  if (adapter) s.set("adapter", adapter);
  if (status) s.set("status", status);
  return apiJson(`/api/orgs/${enc(org)}/semantic/sync-runs?` + s.toString());
}
function triggerSync(org, adapter) {
  return apiJson(`/api/orgs/${enc(org)}/semantic/sync/${enc(adapter)}`, { method: "POST" });
}
function listBuilds(org, { limit = 50 } = {}) {
  return apiJson(`/api/orgs/${enc(org)}/semantic/builds?limit=${limit}`);
}
function triggerBuild(org) {
  return apiJson(`/api/orgs/${enc(org)}/semantic/builds`, { method: "POST" });
}
function buildReport(org, buildId) {
  return apiJson(`/api/orgs/${enc(org)}/semantic/builds/${enc(buildId)}/report`);
}

/* ---------- 成员三方法（m2-6 A3——POST/PATCH/DELETE；无 GET members（m3-1 #13）） ---------- */

function addMember(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/members`, { method: "POST", body: JSON.stringify(body) });
}
function patchMember(org, userId, body) {
  return apiJson(`/api/orgs/${enc(org)}/members/${enc(userId)}`, {
    method: "PATCH", body: JSON.stringify(body),
  });
}
function deleteMember(org, userId) {
  // R2 P1-1：同 deleteDataset——!ok 抛 ApiError（409 最后管理员 / 404 如实）
  return apiJson(`/api/orgs/${enc(org)}/members/${enc(userId)}`, { method: "DELETE" });
}

/* ---------- 组织管理（ui-2——POST /api/orgs 实装；PATCH 停用 m3-1 contract-first） ---------- */

function createOrg(body) {
  return apiJson("/api/orgs", { method: "POST", body: JSON.stringify(body) });
}
// m3-1 contract-first：PATCH /api/orgs/{org}（组织停用/恢复 #14）未实装——按自然契约
// 先行实装（body {status: "active"|"disabled"}）；404/405 → 调用方降级提示「待 m3-1」。
function setOrgStatus(org, status) {
  return apiJson(`/api/orgs/${enc(org)}`, { method: "PATCH", body: JSON.stringify({ status }) });
}

/* ---------- 时间显示（沿原型：UTC 字符串切 MM-DD HH:mm） ---------- */
function short(ts) { return ts ? String(ts).slice(5, 16) : "—"; }
