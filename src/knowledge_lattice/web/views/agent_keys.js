/* views/agent_keys.js —— D26 / issue #34 阶段 3：Agent 长期凭据管理页（VIEWS.agent_keys）。
 * - local 形态专属（后端 router 仅 auth_mode=local 注册；sso 形态导航项不出现）：
 *   本组织 agent key 列表（含已撤销）+ 代 active 成员签发 + 软撤销；
 * - 权限门：sysadmin 或当前组织 org_admin（sysadmin 无本组织成员关系也可管理）；
 * - 明文 key 只在 POST 响应出现一次（库内只存 sha256 + 前缀）——state.agentKeys.lastKey
 *   只驻内存、渲染一次，刷新/切组织即消失；复制走 clipboard、失败 prompt 兜底；
 * - 成员选择器数据源 = GET /api/orgs/{org}/members（org_admin 门控）；sysadmin 无成员
 *   关系时该请求 403 → 退化为手动 user_id 输入（不阻塞 key 列表）；
 * - 错误码先 agentKeys.err.*，其余回落 authErrorText（401/403 不再重复 toast——
 *   api.js 已统一处理）。动态值一律 esc；t() 返回值视为受信 HTML 片段。 */
"use strict";

/* ---------- 权限/表单助手 ---------- */

function canAgentKeysPage() {
  return AUTH.mode === "local" && connected() && !!AUTH.user &&
    (!!AUTH.user.is_system_admin || isAdmin());
}

function freshAgentKeyForm() {
  return { user_id: "", label: "" };
}

/* D26 API 错误码 → agentKeys.err.*；其余（网络/会话/通用）回落 authErrorText。 */
function agentKeysErrorText(e) {
  const code = ((e && e.body) || {}).code || "";
  const byCode = {
    org_admin_required: "agentKeys.err.org_admin_required",
    org_disabled: "agentKeys.err.org_disabled",
    org_not_found: "agentKeys.err.org_not_found",
    user_not_found: "agentKeys.err.user_not_found",
    user_not_active: "agentKeys.err.user_not_active",
    member_not_found: "agentKeys.err.member_not_found",
    agent_key_not_found: "agentKeys.err.agent_key_not_found",
    invalid_label: "agentKeys.err.invalid_label",
    agent_key_conflict: "agentKeys.err.agent_key_conflict",
  };
  if (code && byCode[code]) return t(byCode[code]);
  return authErrorText(e);
}

function agentKeysToastErr(e) {
  if (e && (e.status === 401 || e.status === 403)) return;
  toast(esc(agentKeysErrorText(e)));
}

/* ---------- 装载（key 列表与成员列表并行、互不阻塞） ---------- */

async function refreshAgentKeys(ep) {
  if (!cfg.org) return;
  try {
    const body = await listAgentKeys(cfg.org);
    if (ep !== state.epoch) return;
    state.agentKeys.list = (body && body.keys) || [];
    state.agentKeys.err = null;
  } catch (e) {
    if (ep !== state.epoch) return;
    state.agentKeys.err = agentKeysErrorText(e);
  }
}

async function refreshAgentKeyMembers(ep) {
  if (!cfg.org) return;
  try {
    const body = await listMembers(cfg.org);
    if (ep !== state.epoch) return;
    state.agentKeys.members = (body && body.members) || [];
    state.agentKeys.membersErr = null;
  } catch (e) {
    if (ep !== state.epoch) return;
    state.agentKeys.members = null;
    state.agentKeys.membersErr = agentKeysErrorText(e); // 403（sysadmin 无成员关系）等 → 手动输入回落
  }
}

async function onEnterAgentKeys() {
  if (!canAgentKeysPage() || !cfg.org) return;
  const ep = state.epoch;
  state.agentKeys.err = null;
  state.agentKeys.membersErr = null;
  /* 重新进入页面 = 上一次的一次性明文卡不再展示（只驻内存、创建后仅当场可复制）。 */
  state.agentKeys.lastKey = null;
  await Promise.all([refreshAgentKeys(ep), refreshAgentKeyMembers(ep)]);
}

/* ---------- 片段 ---------- */

function agentKeysHeaderHTML(withActions = true) {
  const ak = state.agentKeys;
  return `<header class="head">
    <h1>${esc(t("agentKeys.title"))}</h1>
    <p class="lede">${t("agentKeys.lede")}</p>
    ${withActions ? `<div class="head-act">
      <button class="btn ghost sm" data-act="agentKeysRetry"${ak.busy ? " disabled" : ""}>${esc(t("agentKeys.refresh"))}</button>
      <button class="btn seal-btn sm" data-act="agentKeysCreateToggle"${ak.busy ? " disabled" : ""}>${esc(ak.createOpen ? t("common.collapse") : t("agentKeys.form.new"))}</button>
    </div>` : ""}
  </header>`;
}

function agentKeysNoAccessHTML() {
  return `<div id="agent-keys" class="agent-keys-view">
    ${agentKeysHeaderHTML(false)}
    <div class="empty"><h3>${esc(t("agentKeys.noAccess"))}</h3><p>${t("agentKeys.noAccessHint")}</p></div>
  </div>`;
}

function agentKeysNoOrgHTML() {
  return `<div id="agent-keys" class="agent-keys-view">
    ${agentKeysHeaderHTML(false)}
    <div class="empty"><h3>${esc(t("agentKeys.noOrg"))}</h3><p>${t("agentKeys.noOrgHint")}</p></div>
  </div>`;
}

function agentKeysSectionErrorHTML(err) {
  return `<div class="empty" style="margin:0"><h3>${esc(err)}</h3>
    <div style="margin-top:12px"><button class="btn ghost sm" data-act="agentKeysRetry">${esc(t("common.retry"))}</button></div></div>`;
}

/* 一次性明文卡：lastKey 只在内存（刷新/切组织即消失；服务端只存摘要与展示前缀）。 */
function agentKeyCardHTML(last) {
  return `<div class="note moss ak-keycard">
    <div class="ak-keycard-head"><b>${esc(t("agentKeys.key.title"))}</b>
      <span class="pill ok">${esc(t("agentKeys.key.badge"))}</span></div>
    <div class="ak-keycard-meta">
      <span>${esc(t("agentKeys.key.label"))}</span><b>${esc(last.label || "—")}</b>
      <span>${esc(t("agentKeys.key.member"))}</span><b>${esc(last.user_username || "—")}</b>
    </div>
    <div class="ak-keycard-line">
      <input class="inp" readonly value="${esc(last.key)}" aria-label="${esc(t("agentKeys.key.aria"))}">
      <button class="btn sm" data-act="agentKeysCopy">${esc(t("agentKeys.key.copy"))}</button>
    </div>
    <div class="tiny muted ak-keycard-once">${t("agentKeys.key.once")}</div>
    <div class="ak-config">
      <div class="ak-config-title">${esc(t("agentKeys.key.config"))}</div>
      <div class="ak-config-row"><span>${esc(t("agentKeys.key.endpoint"))}</span><code>${esc(location.origin)}/mcp</code></div>
      <div class="ak-config-row"><span>${esc(t("agentKeys.key.header"))}</span><code>Authorization: Bearer ${esc(last.key)}</code></div>
      <div class="ak-config-row"><span>${esc(t("agentKeys.key.org"))}</span><code>${esc(cfg.org || "—")}</code></div>
      <div class="ak-config-act">
        <button class="btn ghost sm" data-act="agentKeysCopyConfig">${esc(t("agentKeys.key.copyConfig"))}</button>
        <span class="tiny muted">${t("agentKeys.key.configHint")}</span>
      </div>
    </div>
  </div>`;
}

function agentKeyStatusPill(x) {
  const revoked = !!x.revoked_at;
  return `<span class="pill ${revoked ? "bad" : "ok"} ak-status">${esc(t(revoked ? "agentKeys.status.revoked" : "agentKeys.status.active"))}</span>
    ${revoked ? `<div class="t-sub">${tsHTML(x.revoked_at, "mono tiny")}</div>` : ""}`;
}

/* 创建人展示：成员名单可得时映射 username（sysadmin 无成员关系时回落 user_id）。 */
function agentKeyActorHTML(uid) {
  const id = uid || "";
  const m = (state.agentKeys.members || []).find((x) => x.user_id === id);
  const name = (m && m.username) || id || "—";
  const sub = name !== id && id ? `<div class="t-sub mono">${esc(id)}</div>` : "";
  return `<div class="tiny">${esc(name)}</div>${sub}`;
}

function agentKeyRowHTML(x) {
  const revoked = !!x.revoked_at;
  const username = x.user_username || x.user_id || "—";
  const userSub = x.user_username && x.user_id ? `<div class="t-sub mono">${esc(x.user_id)}</div>` : "";
  return `<tr>
    <td><div class="t-title">${esc(x.label || "—")}</div></td>
    <td><div>${esc(username)}</div>${userSub}</td>
    <td><code class="mono ak-prefix">${esc((x.prefix || "") + "…")}</code></td>
    <td>${agentKeyActorHTML(x.created_by)}</td>
    <td class="tiny">${tsHTML(x.created_at, "mono tiny")}</td>
    <td class="tiny">${x.last_used_at
      ? tsHTML(x.last_used_at, "mono tiny")
      : `<span class="muted">${esc(t("agentKeys.neverUsed"))}</span>`}</td>
    <td>${agentKeyStatusPill(x)}</td>
    <td>${revoked
      ? `<span class="tiny muted">—</span>`
      : `<button class="btn ghost sm" data-act="agentKeysRevoke" data-id="${esc(x.id)}" style="color:var(--danger)">${esc(t("agentKeys.action.revoke"))}</button>`}</td>
  </tr>`;
}

function agentKeyFormHTML() {
  const ak = state.agentKeys;
  const f = ak.form;
  const busy = ak.busy;
  const members = ak.members;
  const manual = !!ak.membersErr || (members != null && members.length === 0);
  let memberField;
  if (manual) {
    const hint = ak.membersErr
      ? `${t("agentKeys.form.manualHint")} <span class="mono">${esc(ak.membersErr)}</span>`
      : t("agentKeys.form.manualEmpty");
    memberField = `<div class="ak-field">
      <label for="akUserId">${esc(t("agentKeys.form.member"))}<span class="req">*</span></label>
      <input class="inp" id="akUserId" data-in="akUserId" value="${esc(f.user_id)}" placeholder="${esc(t("agentKeys.form.memberPh"))}" autocomplete="off">
      <span class="tiny muted">${hint}</span></div>`;
  } else if (members == null) {
    memberField = `<div class="ak-field">
      <label for="akMember">${esc(t("agentKeys.form.member"))}<span class="req">*</span></label>
      <select class="sel" id="akMember" disabled><option>${esc(t("agentKeys.form.membersLoading"))}</option></select></div>`;
  } else {
    memberField = `<div class="ak-field">
      <label for="akMember">${esc(t("agentKeys.form.member"))}<span class="req">*</span></label>
      <select class="sel" id="akMember" data-in="akMember">
        <option value="">${esc(t("agentKeys.form.memberPick"))}</option>
        ${members.map((m) => `<option value="${esc(m.user_id)}"${m.user_id === f.user_id ? " selected" : ""}>${esc(m.username || m.user_id)}</option>`).join("")}
      </select></div>`;
  }
  return `<div class="ak-form">
    ${memberField}
    <div class="ak-field">
      <label for="akLabel">${esc(t("agentKeys.form.label"))}<span class="req">*</span></label>
      <input class="inp" id="akLabel" data-in="akLabel" value="${esc(f.label)}" maxlength="64" placeholder="${esc(t("agentKeys.form.labelPh"))}" autocomplete="off"></div>
    <div class="ak-actions">
      <button class="btn seal-btn sm" data-act="agentKeysCreate"${busy ? " disabled" : ""}>${esc(busy ? t("agentKeys.form.busy") : t("agentKeys.form.submit"))}</button>
      <button class="btn ghost sm" data-act="agentKeysCreateToggle"${busy ? " disabled" : ""}>${esc(t("common.cancel"))}</button>
      <span class="tiny muted">${t("agentKeys.form.hint")}</span>
    </div>
  </div>`;
}

function agentKeysSectionHTML() {
  const ak = state.agentKeys;
  const rows = ak.list || [];
  let body;
  if (ak.list == null) {
    body = ak.err ? agentKeysSectionErrorHTML(ak.err) : loadingHTML("agent_keys");
  } else {
    body = `<table class="ledger">
      <thead><tr>
        <th>${esc(t("agentKeys.col.label"))}</th><th>${esc(t("agentKeys.col.member"))}</th>
        <th>${esc(t("agentKeys.col.prefix"))}</th><th>${esc(t("agentKeys.col.creator"))}</th>
        <th>${esc(t("agentKeys.col.created"))}</th><th>${esc(t("agentKeys.col.lastUsed"))}</th>
        <th>${esc(t("agentKeys.col.status"))}</th><th>${esc(t("agentKeys.col.actions"))}</th>
      </tr></thead>
      <tbody>${rows.length ? rows.map(agentKeyRowHTML).join("") : `<tr><td colspan="8" class="tiny muted" style="padding:20px 16px">${esc(t("agentKeys.empty"))}</td></tr>`}</tbody>
    </table>`;
  }
  return `<div class="sec-title">${esc(t("agentKeys.listTitle"))}
      ${ak.list == null ? "" : `<small>${esc(t("agentKeys.count", { n: rows.length }))}</small>`}
    </div>
    ${body}`;
}

/* ---------- 视图 ---------- */

function viewAgentKeys() {
  if (!canAgentKeysPage()) return agentKeysNoAccessHTML();
  if (!cfg.org) return agentKeysNoOrgHTML();
  const ak = state.agentKeys;
  return `<div id="agent-keys" class="agent-keys-view">
    ${agentKeysHeaderHTML()}
    <div class="note ak-note">${t("agentKeys.note")}</div>
    ${ak.err && ak.list != null
      ? `<div class="note seal" style="margin:0 0 16px">${esc(ak.err)} <button class="btn ghost sm" data-act="agentKeysRetry" style="margin-left:8px">${esc(t("common.retry"))}</button></div>`
      : ""}
    ${ak.lastKey ? agentKeyCardHTML(ak.lastKey) : ""}
    ${ak.createOpen ? agentKeyFormHTML() : ""}
    ${agentKeysSectionHTML()}
  </div>`;
}

/* ---------- 动作 ---------- */

Object.assign(actions, {
  async agentKeysRetry() {
    const ak = state.agentKeys;
    if (ak.busy) return false;
    ak.busy = true;
    ak.err = null;
    ak.lastKey = null; // 刷新后明文不可再查看（一次性）
    render();
    await onEnterAgentKeys();
    ak.busy = false;
    render();
    return false;
  },

  agentKeysCreateToggle() {
    const ak = state.agentKeys;
    if (ak.busy) return false;
    ak.createOpen = !ak.createOpen;
    ak.form = freshAgentKeyForm();
    ak.err = null;
  },

  async agentKeysCreate() {
    const ak = state.agentKeys;
    if (!canAgentKeysPage() || !cfg.org || ak.busy) return false;
    const f = ak.form;
    const userId = String(f.user_id || "").trim();
    const label = String(f.label || "").trim();
    if (!userId) { toast(esc(t("agentKeys.form.needMember"))); return false; }
    if (!label) { toast(esc(t("agentKeys.form.needLabel"))); return false; }
    if (label.length > 64) { toast(esc(t("agentKeys.form.labelTooLong"))); return false; }
    const ep = state.epoch;
    ak.busy = true;
    ak.err = null;
    render();
    let res;
    try {
      res = await createAgentKey(cfg.org, { user_id: userId, label });
    } catch (e) {
      if (ep !== state.epoch) return false;
      ak.busy = false;
      ak.err = agentKeysErrorText(e);
      agentKeysToastErr(e);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    ak.busy = false;
    const plaintext = (res && res.key) || "";
    if (!plaintext) {
      ak.err = t("auth.err.generic");
      render();
      return false;
    }
    ak.lastKey = {
      key: plaintext,
      label: (res && res.label) || label,
      user_username: (res && res.user_username) || userId,
    };
    ak.createOpen = false;
    ak.form = freshAgentKeyForm();
    toast(t("agentKeys.toast.created", {
      label: esc(ak.lastKey.label), username: esc(ak.lastKey.user_username),
    }));
    render(); // 明文卡先行——一次性 key 不因列表刷新延迟而晚出现/丢失
    await refreshAgentKeys(ep);
    if (ep !== state.epoch) return false;
    render();
    return false;
  },

  async agentKeysRevoke(el) {
    const id = el.dataset.id;
    const ak = state.agentKeys;
    if (!cfg.org || ak.busy) return false;
    const row = (ak.list || []).find((x) => x.id === id);
    if (!row) return false;
    const username = row.user_username || row.user_id || "—";
    const label = row.label || "—";
    if (!window.confirm(t("agentKeys.confirm.revoke", { label, username }))) return false;
    const ep = state.epoch;
    ak.busy = true;
    render();
    try {
      await revokeAgentKey(cfg.org, id);
    } catch (e) {
      if (ep !== state.epoch) return false;
      ak.busy = false;
      if (e && e.status === 404) toast(esc(t("agentKeys.toast.revokeGone")));
      else agentKeysToastErr(e);
      await refreshAgentKeys(ep);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    ak.busy = false;
    toast(t("agentKeys.toast.revoked", { label: esc(label), username: esc(username) }));
    await refreshAgentKeys(ep);
    render();
    return false;
  },

  async agentKeysCopy() {
    const last = state.agentKeys.lastKey;
    const key = last && last.key;
    if (!key) return false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(key);
        toast(esc(t("agentKeys.key.copied")));
        return false;
      }
    } catch (e) { /* 剪贴板不可用（非安全上下文等）→ prompt 兜底 */ }
    window.prompt(t("agentKeys.key.prompt"), key);
    return false;
  },

  async agentKeysCopyConfig() {
    const last = state.agentKeys.lastKey;
    if (!last || !last.key) return false;
    const text = [
      `MCP endpoint: ${location.origin}/mcp`,
      `Authorization: Bearer ${last.key}`,
      `X-Org-Id: (optional; key bound to ${cfg.org || "—"})`,
    ].join("\n");
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        toast(esc(t("agentKeys.key.copiedConfig")));
        return false;
      }
    } catch (e) { /* 剪贴板不可用（非安全上下文等）→ prompt 兜底 */ }
    window.prompt(t("agentKeys.key.configPrompt"), text);
    return false;
  },
});

Object.assign(INPUTS, {
  akMember: (v) => { state.agentKeys.form.user_id = v; },
  akUserId: (v) => { state.agentKeys.form.user_id = v; },
  akLabel: (v) => { state.agentKeys.form.label = v; },
});

VIEWS.agent_keys = { render: viewAgentKeys, onEnter: onEnterAgentKeys };
