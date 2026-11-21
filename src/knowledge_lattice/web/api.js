/* api.js —— REST 适配层（ui-1）：全部 fetch 收口。
 * - 连接状态 cfg = {baseToken, activeToken, org, lensUserId, baseUserId, authMode}，
 *   localStorage `lattice.cfg` 持久化（D25：旧值无 authMode 仍兼容，boot 门按服务端
 *   /api/auth/config 校正）；baseToken = 连接时粘贴的基 token（重签用）；
 *   activeToken = 实际请求用的 token（视角身份）；authMode = sso|local（本地会话时
 *   connected() 还要求 AUTH.user 在场）。
 * - apiFetch(path, opts)：注入 Authorization / X-Org-Id / Content-Type；统一错误解析
 *   （body.detail || body.error——HTTPException 与 JSONResponse 两种错误体形态）；
 *   401：sso → toast + 打开连接设置（原逻辑）；local → handleAuthExpired()（清会话回登录屏，
 *   见 app.js——不 toast/openConn）；403 → toast 服务端 detail；网络异常 → toast。
 * - apiPublic(path, opts)：匿名端点（auth config/setup/login/invite lookup·accept）专用——
 *   不带 Authorization / X-Org-Id、不触发 401 连接设置；错误统一抛 ApiError。
 * - reissue({org?, userId?})：用 baseToken POST /api/dev/token 重签（dev 形态组织/身份切换）；
 *   给他人代签须系统管理员基 token（403）；生产无 dev 端点（404 → 提示直接粘贴已签 token）。
 * - 领域函数：每端点一函数。原 contract-first 降级四处（be-① 文档列表 /
 *   建库 / 建维度 / 组织停用）已随 m3-1 后端实装全部接真端点（m3-2 对账）。
 * - D25 local（m4-3a）：authConfig/setupStatus/setupInstance/authLogin/authMe/
 *   changePassword/authLogout/lookupInvitation/acceptInvitation——本地会话只 Web/REST。
 * - D25 local（m4-3b）：listUsers/createUser/patchUser/resetUser +
 *   listInvitations/createInvitation/revokeInvitation——用户/邀请管理页（views/users.js）；
 *   邀请链接统一 inviteLink(token)（#invite= fragment——token 不进路径/Referer）。
 * - pollTask：任务轮询（interval 1.5s / 终态停止 / 超时 120s / shouldStop 回调
 *   感知上下文切换即停——R2 P1-5，返回 null=已弃）。
 */
"use strict";

const CFG_KEY = "lattice.cfg";
const cfg = { baseToken: "", activeToken: "", org: "", lensUserId: "", baseUserId: "", authMode: "" };

function loadCfg() {
  try {
    const saved = JSON.parse(localStorage.getItem(CFG_KEY) || "{}");
    cfg.baseToken = saved.baseToken || "";
    cfg.activeToken = saved.activeToken || "";
    cfg.org = saved.org || "";
    cfg.lensUserId = saved.lensUserId || "";
    cfg.baseUserId = saved.baseUserId || "";
    cfg.authMode = saved.authMode === "local" ? "local" : saved.authMode === "sso" ? "sso" : "";
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

/* 连接判定：sso = 已粘贴 token + 组织；local = 本地会话 token + AUTH.user 已恢复
 * （D25——组织可为空，由用户菜单/组织页引导；AUTH 在 app.js 定义，脚本按序加载，
 * 调用时恒已就绪，typeof 防御仅防加载顺序意外）。 */
function connected() {
  if (typeof AUTH !== "undefined" && AUTH.mode === "local") {
    return !!(cfg.activeToken && AUTH.user);
  }
  return !!(cfg.activeToken && cfg.org);
}

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
  // X-Org-Id：调用方显式指定（跨组织行操作按路径对齐——D18 路径/头一致性，
  // m3-2 ui-be：PATCH orgs 等跨组织行不得恒发 cfg.org 头）优先；缺省注入当前组织
  if (cfg.org && !("X-Org-Id" in headers)) headers["X-Org-Id"] = cfg.org;
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
    if (typeof AUTH !== "undefined" && AUTH.mode === "local") {
      // D25 local：会话过期/被撤销 → 清 token 回登录屏（不弹连接设置——local 无粘贴 token 路径）
      if (typeof handleAuthExpired === "function") handleAuthExpired();
    } else {
      toast(t("err.auth401"));
      if (typeof openConn === "function") openConn();
    }
  }
  return resp;
}

/* 匿名请求（D25 auth config / setup / login / invite）：不带 Authorization 与
 * X-Org-Id，不触发 401 连接设置；错误只抛 ApiError（登录屏自行内联展示——
 * 不 toast，避免与表单错误条重复）。 */
async function apiPublic(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (opts.body != null && !(opts.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = opts.contentType || "application/json";
  }
  let resp;
  try {
    resp = await fetch(path, Object.assign({}, opts, { headers }));
  } catch (e) {
    throw new ApiError(0, t("err.network"));
  }
  const body = await _parseBody(resp);
  if (!resp.ok) {
    const msg = body.error || body.detail || resp.statusText || String(resp.status);
    throw new ApiError(resp.status, String(msg), body);
  }
  return body;
}

/* 本地会话请求（带当前 activeToken，不带 X-Org-Id）：401 只抛 ApiError——
 * 调用方决定是「改密旧密码错」（不清会话）还是「会话过期」（handleAuthExpired）。
 * authMe / changePassword / authLogout 三处共用。 */
async function _authedJson(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (cfg.activeToken) headers["Authorization"] = "Bearer " + cfg.activeToken;
  if (opts.body != null && !(opts.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = opts.contentType || "application/json";
  }
  let resp;
  try {
    resp = await fetch(path, Object.assign({}, opts, { headers }));
  } catch (e) {
    throw new ApiError(0, t("err.network"));
  }
  const body = await _parseBody(resp);
  if (!resp.ok) {
    const msg = body.error || body.detail || resp.statusText || String(resp.status);
    throw new ApiError(resp.status, String(msg), body);
  }
  return body;
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

/* ---------- D25 local：boot 门 / 首启 / 会话 / 邀请接受（m4-3a） ----------
 * 契约见 `_m4-impl-contract.md` §5：错误体 {error, code}；setup/login/accept 返回
 * {token, expires_at, user, orgs}；me 返回 {user, orgs}；改密返回 {token, expires_at}。
 * 用户/邀请管理（GET/POST /api/users、/api/orgs/{org}/invitations）归 m4-3b。 */

function authConfig() { return apiPublic("/api/auth/config"); }
function setupStatus() { return apiPublic("/api/setup/status"); }

function setupInstance(body) {
  return apiPublic("/api/setup", { method: "POST", body: JSON.stringify(body) });
}

function authLogin(username, password) {
  return apiPublic("/api/auth/login", {
    method: "POST", body: JSON.stringify({ username, password }),
  });
}

/* 恢复本地会话：带当前 activeToken 的 fetch；401/网络错误都只抛 ApiError
 * （bootLocal 自行分流：401 → handleAuthExpired；网络错 → 登录屏错误文案）。 */
function authMe() { return _authedJson("/api/auth/me"); }

function changePassword(oldPassword, newPassword) {
  return _authedJson("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
}

function authLogout() { return _authedJson("/api/auth/logout", { method: "POST" }); }

function lookupInvitation(token) {
  return apiPublic("/api/auth/invitations/lookup", {
    method: "POST", body: JSON.stringify({ token }),
  });
}

function acceptInvitation({ token, password, display_name }) {
  const body = { token, password };
  if (display_name) body.display_name = display_name;
  return apiPublic("/api/auth/invitations/accept", {
    method: "POST", body: JSON.stringify(body),
  });
}

/* ---------- D25 local：用户 / 邀请管理（m4-3b，契约 §5） ----------
 * sysadmin：GET/POST /api/users、PATCH /api/users/{id}、POST /api/users/{id}/reset；
 * org_admin：GET/POST /api/orgs/{org}/invitations、DELETE …/{id}。
 * 邀请明文 token 只在创建响应中出现一次（库内只存 sha256）——调用方立即展示、
 * 不落 localStorage（刷新即消失）。 */

function listUsers() { return apiJson("/api/users"); }

function createUser(body) {
  return apiJson("/api/users", { method: "POST", body: JSON.stringify(body) });
}
function patchUser(id, body) {
  return apiJson(`/api/users/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) });
}
function resetUser(id) {
  return apiJson(`/api/users/${enc(id)}/reset`, { method: "POST" });
}
function listInvitations(org) {
  return apiJson(`/api/orgs/${enc(org)}/invitations`);
}
function createInvitation(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/invitations`, {
    method: "POST", body: JSON.stringify(body),
  });
}
function revokeInvitation(org, id) {
  return apiJson(`/api/orgs/${enc(org)}/invitations/${enc(id)}`, { method: "DELETE" });
}

/* 邀请链接唯一生成口径（login.js parseInviteToken 吃 #invite=<token>）：
 * origin + pathname + fragment——token 不进服务端路径/查询串/Referer。 */
function inviteLink(token) {
  return location.origin + location.pathname + "#invite=" + encodeURIComponent(token || "");
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

// m3-2 ui-be 对账：POST /api/orgs/{org}/datasets 真契约 {key, title?}（m3-1
// #13 实装——description 仅 PATCH 承载；调用方 docs.js 建库表单 key+title，
// 描述经 createDatasetThenDesc 补 PATCH）。
function createDataset(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/datasets`, { method: "POST", body: JSON.stringify(body) });
}
/* 建库 + 可选描述（描述走 PATCH description——契约字面） */
async function createDatasetWithDesc(org, { key, title, description }) {
  const created = await createDataset(org, { key, title: title || undefined });
  if (description) {
    try {
      await patchDataset(org, created.id || key, { description });
    } catch (e) { /* 建库已成——描述失败仅 toast，不回滚 */ }
  }
  return created;
}
function patchDataset(org, id, body) {
  return apiJson(`/api/orgs/${enc(org)}/datasets/${enc(id)}`, {
    method: "PATCH", body: JSON.stringify(body),
  });
}
function deleteDataset(org, id) {
  // R2 P1-1：DELETE 收口 apiJson 同款 !ok 抛 ApiError（204 空 body → {} 正常返回）
  return apiJson(`/api/orgs/${enc(org)}/datasets/${enc(id)}`, { method: "DELETE" });
}
function listDimensions(org) { return apiJson(`/api/orgs/${enc(org)}/dimensions`); }

// m3-2 ui-be 对账：POST /api/orgs/{org}/dimensions 真契约 {key, label,
// required?, enabled?}（m3-1 #13 实装——label=显示名；调用方 access.js
// dimCreate 以表单「名称」作 label）。
function createDimension(org, body) {
  return apiJson(`/api/orgs/${enc(org)}/dimensions`, { method: "POST", body: JSON.stringify(body) });
}

// be-1 端点已实装（m3-1 #20 D-①）：GET /api/orgs/{org}/documents
// ?dataset=&limit=&offset= → {documents:[…], total}。
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

/* ---------- 成员（m2-6 A3 写三方法 + m3-1 #13 GET members——ui-be 真源化） ---------- */

// GET members（org_admin 门控）：{members:[{user_id,username,role,expires_at}]}——
// 成员名单/身份菜单/成员行 role·到期 的真源（m3-2 ui-be：替换 export-CSV 单源）。
function listMembers(org) { return apiJson(`/api/orgs/${enc(org)}/members`); }

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

/* ---------- 组织管理（ui-2——POST /api/orgs 与 PATCH /api/orgs/{org} 均已实装） ---------- */

function createOrg(body) {
  return apiJson("/api/orgs", { method: "POST", body: JSON.stringify(body) });
}
// m3-2 ui-be 对账：PATCH /api/orgs/{org}（#14 停用/恢复——m3-1 实装）。跨组织
// 行操作按路径对齐 X-Org-Id（D18 路径/头一致性——不恒发 cfg.org 头）。
function setOrgStatus(org, status) {
  return apiJson(`/api/orgs/${enc(org)}`, {
    method: "PATCH",
    headers: { "X-Org-Id": org },
    body: JSON.stringify({ status }),
  });
}

/* ---------- 可见性解释（m3-1 #20 D-② 实装——m3-2 ui-be 接真端点） ---------- */

// GET explain：user_id 缺省=自解释；给他人解释须 org_admin（403 如实）。
function explainDocument(org, docId, userId) {
  const q = userId ? `?user_id=${enc(userId)}` : "";
  return apiJson(`/api/orgs/${enc(org)}/documents/${enc(docId)}/explain${q}`);
}

/* ---------- 时间显示（沿原型：UTC 字符串切 MM-DD HH:mm） ---------- */
function short(ts) { return ts ? String(ts).slice(5, 16) : "—"; }
