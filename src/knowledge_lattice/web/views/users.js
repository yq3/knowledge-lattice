/* views/users.js —— D25 local 用户/邀请管理页（m4-3b，VIEWS.users）：
 * - sysadmin（AUTH.user.is_system_admin）：全局账号表（停用/恢复、重置密码链接、
 *   授撤 sysadmin）+ 建号表单（可同事务入组织并给 member/org_admin）；
 * - org_admin（isAdmin()，当前组织）：本组织邀请表（pending 可撤销）+ 邀请表单；
 * - 邀请/重置链接明文只出现在创建响应里（服务端只存 sha256）——state.users.lastInvite
 *   只驻内存、渲染一次，刷新即消失；链接统一 #invite=<token>（api.js inviteLink）。
 * 请求全部走 api.js 领域函数（apiJson：401 会话失效/403 统一 toast）；错误码经
 * usersErrorText（先 users.err.*，其余回落 authErrorText）。sso 形态不渲染本视图
 * （nav 项亦不出现——零回归）。动态值一律 esc；t() 返回值视为受信 HTML 片段。 */
"use strict";

/* ---------- 权限/状态助手 ---------- */

function sysadminUser() {
  return AUTH.mode === "local" && !!AUTH.user && !!AUTH.user.is_system_admin;
}
function canUsersPage() {
  return AUTH.mode === "local" && !!AUTH.user && (!!AUTH.user.is_system_admin || isAdmin());
}

function freshUserForm() {
  return { username: "", display_name: "", email: "", is_system_admin: false, org_id: "", role: "member" };
}
function freshInviteForm() {
  return { username: "", role: "member", display_name: "", email: "" };
}

/* m4-3b 新增错误码 → users.err.*；其余（用户名/邮箱冲突、邀请失效、弱密码等）
 * 回落 m4-3a 的 authErrorText（已覆盖大部分契约错误码）。 */
function usersErrorText(e) {
  const code = ((e && e.body) || {}).code || "";
  const byCode = {
    last_sysadmin: "users.err.last_sysadmin",
    member_exists: "users.err.member_exists",
    user_not_found: "users.err.user_not_found",
    user_disabled: "users.err.user_disabled",
    sysadmin_required: "users.err.sysadmin_required",
    org_admin_required: "users.err.org_admin_required",
    invalid_role: "users.err.invalid_role",
    org_not_found: "users.err.org_not_found",
  };
  if (code && byCode[code]) return t(byCode[code]);
  return authErrorText(e);
}

/* 动作失败 toast（401/403 已由 api.js 统一处理——不重复） */
function usersToastErr(e) {
  if (e && (e.status === 401 || e.status === 403)) return;
  toast(esc(usersErrorText(e)));
}

/* ---------- 装载（两面互不阻塞：各自 catch，失败只记 err） ---------- */

async function refreshUserList(ep) {
  try {
    const body = await listUsers();
    if (ep !== state.epoch) return;
    state.users.list = (body && body.users) || [];
  } catch (e) {
    if (ep !== state.epoch) return;
    state.users.err = usersErrorText(e);
  }
}

async function refreshInvites(ep) {
  if (!cfg.org) return;
  try {
    const body = await listInvitations(cfg.org);
    if (ep !== state.epoch) return;
    state.users.invites = (body && body.invitations) || [];
  } catch (e) {
    if (ep !== state.epoch) return;
    state.users.err = usersErrorText(e);
  }
}

/* 刷新当前身份可见的两面（sysadmin 用户表 / org_admin 邀请表）——并行、各自兜底。 */
async function refreshUsers(ep = state.epoch) {
  const jobs = [];
  if (sysadminUser()) jobs.push(refreshUserList(ep));
  if (isAdmin() && cfg.org) jobs.push(refreshInvites(ep));
  await Promise.all(jobs);
}

async function onEnterUsers() {
  if (!connected() || AUTH.mode !== "local" || !canUsersPage()) return;
  state.users.err = null;
  await refreshUsers(state.epoch);
}

/* ---------- 片段 ---------- */

function usersNoAccessHTML() {
  return `<div id="users" class="users-view">
    <header class="head"><h1>${esc(t("users.title"))}</h1><p class="lede">${t("users.lede")}</p></header>
    <div class="empty"><h3>${esc(t("users.noAccess"))}</h3><p>${t("users.noAccessHint")}</p></div>
  </div>`;
}

function usersScopeHTML() {
  const org = cfg.org ? (orgName(cfg.org) || cfg.org) : "";
  if (sysadminUser() && isAdmin() && org) return t("users.scope.both", { org: esc(org) });
  if (sysadminUser()) return t("users.scope.sysadmin");
  return t("users.scope.org", { org: esc(org) });
}

function sectionErrorHTML(err) {
  return `<div class="empty" style="margin:0"><h3>${esc(err)}</h3>
    <div style="margin-top:12px"><button class="btn ghost sm" data-act="usersRetry">${esc(t("common.retry"))}</button></div></div>`;
}

/* 邀请链接卡：创建后只显示一次（lastInvite 在内存；刷新/切组织即消失）。 */
function inviteCardHTML(inv) {
  const link = inviteLink(inv.token);
  const reset = inv.kind === "reset";
  return `<div class="note moss invite-card">
    <div class="invite-head"><b>${esc(t("users.link.title"))}</b>
      <span class="pill ${reset ? "idle" : "ok"}">${esc(reset ? t("users.link.purpose.reset") : t("users.link.purpose.invite"))}</span></div>
    <div class="invite-meta"><span>${esc(t("users.link.username"))}</span><b class="mono">${esc(inv.username || "—")}</b></div>
    <div class="invite-link">
      <input class="inp" readonly value="${esc(link)}" aria-label="${esc(t("users.link.url"))}">
      <button class="btn sm" data-act="invCopy" data-token="${esc(inv.token)}">${esc(t("users.link.copy"))}</button>
    </div>
    <div class="invite-token">${esc(t("users.link.token"))}: ${esc(inv.token)}</div>
    <div class="tiny muted" style="margin-top:6px">${t("users.link.once")}</div>
  </div>`;
}

function userStatusPill(u) {
  if (u.disabled_at) return `<span class="pill bad users-status">${esc(t("users.status.disabled"))}</span>`;
  if (u.status === "invited") return `<span class="pill idle users-status">${esc(t("users.status.invited"))}</span>`;
  return `<span class="pill ok users-status">${esc(t("users.status.active"))}</span>`;
}

function inviteStatusPill(status) {
  const cls = { pending: "run", consumed: "ok", revoked: "bad", expired: "idle" }[status] || "idle";
  const key = "users.status." + (status || "expired");
  const text = t(key);
  return `<span class="pill ${cls} users-status">${esc(text === key ? (status || "—") : text)}</span>`;
}

function userRowHTML(u) {
  const self = AUTH.user && AUTH.user.id === u.id;
  const disabled = !!u.disabled_at;
  return `<tr>
    <td><div class="t-title mono">${esc(u.username)}</div>${self ? `<div class="t-sub">${esc(t("users.self"))}</div>` : ""}</td>
    <td>${esc(u.display_name || "—")}</td>
    <td class="tiny">${esc(u.email || "—")}</td>
    <td>${userStatusPill(u)}</td>
    <td>${u.is_system_admin
      ? `<span class="pill ok">${esc(t("common.yes"))}</span>`
      : `<span class="pill idle">${esc(t("common.no"))}</span>`}</td>
    <td class="tiny">${u.last_login_at ? tsHTML(u.last_login_at, "mono tiny") : `<span class="muted">—</span>`}</td>
    <td><div class="users-rowact">
      <button class="btn ghost sm" data-act="usersToggle" data-id="${esc(u.id)}"${disabled ? "" : ' style="color:var(--danger)"'}>${esc(disabled ? t("users.action.enable") : t("users.action.disable"))}</button>
      <button class="btn ghost sm" data-act="usersReset" data-id="${esc(u.id)}"${disabled ? " disabled" : ""}>${esc(t("users.action.reset"))}</button>
      <button class="btn ghost sm" data-act="usersSysadmin" data-id="${esc(u.id)}">${esc(u.is_system_admin ? t("users.action.revokeAdmin") : t("users.action.grantAdmin"))}</button>
    </div></td>
  </tr>`;
}

function usersCreateFormHTML() {
  const f = state.users.form;
  const orgs = state.orgs || [];
  const busy = state.users.busy;
  return `<div class="users-form">
    <label class="uf-field"><span>${esc(t("users.form.username"))}<span class="req">*</span></span>
      <input class="inp" data-in="uCreateUsername" value="${esc(f.username)}" placeholder="${esc(t("users.form.usernamePh"))}" autocomplete="off"></label>
    <label class="uf-field"><span>${esc(t("users.form.display"))}</span>
      <input class="inp" data-in="uCreateDisplay" value="${esc(f.display_name)}" placeholder="${esc(t("users.form.displayPh"))}" autocomplete="off"></label>
    <label class="uf-field"><span>${esc(t("users.form.email"))}</span>
      <input class="inp" data-in="uCreateEmail" type="email" value="${esc(f.email)}" placeholder="${esc(t("users.form.emailPh"))}" autocomplete="off"></label>
    <label class="uf-field"><span>${esc(t("users.form.org"))}</span>
      <select class="sel" data-in="uCreateOrg">
        <option value="">${esc(t("users.form.orgNone"))}</option>
        ${orgs.map((o) => `<option value="${esc(o.org_id)}"${o.org_id === f.org_id ? " selected" : ""}>${esc(o.name || o.org_id)}${o.status === "disabled" ? " · " + esc(t("users.status.disabled")) : ""}</option>`).join("")}
      </select></label>
    <label class="uf-field"><span>${esc(t("users.form.role"))}</span>
      <select class="sel" data-in="uCreateRole"${f.org_id ? "" : " disabled"}>
        <option value="member"${f.role !== "org_admin" ? " selected" : ""}>${esc(t("role.member"))}</option>
        <option value="org_admin"${f.role === "org_admin" ? " selected" : ""}>${esc(t("role.org_admin"))}</option>
      </select></label>
    <label class="uf-field uf-check"><input type="checkbox" data-in="uCreateAdmin"${f.is_system_admin ? " checked" : ""}> <span>${esc(t("users.form.sysadmin"))}</span></label>
    <div class="uf-actions">
      <button class="btn seal-btn sm" data-act="usersCreate"${busy ? " disabled" : ""}>${esc(busy ? t("users.form.busy") : t("users.form.submit"))}</button>
      <button class="btn ghost sm" data-act="usersCreateToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny muted">${t("users.form.hint")}</span>
    </div>
  </div>`;
}

function usersSectionHTML() {
  const u = state.users;
  const rows = u.list || [];
  let body;
  if (u.list == null) {
    body = u.err ? sectionErrorHTML(u.err) : loadingHTML("users");
  } else {
    body = `<table class="ledger">
      <thead><tr>
        <th>${esc(t("users.col.username"))}</th><th>${esc(t("users.col.display"))}</th>
        <th>${esc(t("users.col.email"))}</th><th>${esc(t("users.col.status"))}</th>
        <th>${esc(t("users.col.sysadmin"))}</th><th>${esc(t("users.col.lastLogin"))}</th>
        <th>${esc(t("users.col.actions"))}</th>
      </tr></thead>
      <tbody>${rows.length ? rows.map(userRowHTML).join("") : `<tr><td colspan="7" class="tiny muted" style="padding:20px 16px">${esc(t("users.empty"))}</td></tr>`}</tbody>
    </table>`;
  }
  return `<div class="sec-title">${esc(t("users.usersTitle"))}
      ${u.list == null ? "" : `<small>${esc(t("users.usersCount", { n: rows.length }))}</small>`}
      <span style="flex:1"></span>
      <button class="btn seal-btn sm" data-act="usersCreateToggle">${esc(u.createOpen ? t("common.collapse") : t("users.form.new"))}</button>
    </div>
    ${u.createOpen ? usersCreateFormHTML() : ""}
    ${body}`;
}

function invitationRowHTML(x) {
  const pending = x.status === "pending";
  const roleText = x.role === "org_admin" ? t("role.org_admin")
    : x.role === "member" ? t("role.member") : (x.role || "—");
  const purpose = x.purpose === "reset" ? t("users.link.purpose.reset") : t("users.link.purpose.invite");
  return `<tr>
    <td><div class="t-title mono">${esc(x.username || x.user_id)}</div>${pending ? `<div class="t-sub">${esc(t("users.inv.linkOnlyOnce"))}</div>` : ""}</td>
    <td>${x.role ? `<span class="pill ${x.role === "org_admin" ? "ok" : ""}">${esc(roleText)}</span>` : `<span class="tiny muted">—</span>`}</td>
    <td class="tiny">${esc(purpose)}</td>
    <td>${inviteStatusPill(x.status)}</td>
    <td class="tiny">${tsHTML(x.created_at, "mono tiny")}</td>
    <td class="tiny">${tsHTML(x.expires_at, "mono tiny")}</td>
    <td>${pending
      ? `<button class="btn ghost sm" data-act="invRevoke" data-id="${esc(x.id)}" data-username="${esc(x.username || x.user_id)}" style="color:var(--danger)">${esc(t("users.action.revoke"))}</button>`
      : `<span class="tiny muted">—</span>`}</td>
  </tr>`;
}

function invCreateFormHTML() {
  const f = state.users.invForm;
  const busy = state.users.busy;
  return `<div class="users-form">
    <label class="uf-field"><span>${esc(t("users.form.username"))}<span class="req">*</span></span>
      <input class="inp" data-in="uInvUsername" value="${esc(f.username)}" placeholder="${esc(t("users.form.usernamePh"))}" autocomplete="off"></label>
    <label class="uf-field"><span>${esc(t("users.form.display"))}</span>
      <input class="inp" data-in="uInvDisplay" value="${esc(f.display_name)}" placeholder="${esc(t("users.form.displayPh"))}" autocomplete="off"></label>
    <label class="uf-field"><span>${esc(t("users.form.email"))}</span>
      <input class="inp" data-in="uInvEmail" type="email" value="${esc(f.email)}" placeholder="${esc(t("users.form.emailPh"))}" autocomplete="off"></label>
    <label class="uf-field"><span>${esc(t("users.form.role"))}</span>
      <select class="sel" data-in="uInvRole">
        <option value="member"${f.role !== "org_admin" ? " selected" : ""}>${esc(t("role.member"))}</option>
        <option value="org_admin"${f.role === "org_admin" ? " selected" : ""}>${esc(t("role.org_admin"))}</option>
      </select></label>
    <div class="uf-actions">
      <button class="btn seal-btn sm" data-act="invCreate"${busy ? " disabled" : ""}>${esc(busy ? t("users.form.busy") : t("users.inv.submit"))}</button>
      <button class="btn ghost sm" data-act="invCreateToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny muted">${t("users.inv.formHint")}</span>
    </div>
  </div>`;
}

function invitationsSectionHTML() {
  const u = state.users;
  const rows = u.invites || [];
  let body;
  if (u.invites == null) {
    body = u.err ? sectionErrorHTML(u.err) : `<div class="loading">${esc(t("common.loading", { what: t("users.inv.title") }))}</div>`;
  } else {
    body = `<table class="ledger">
      <thead><tr>
        <th>${esc(t("users.inv.username"))}</th><th>${esc(t("users.inv.role"))}</th>
        <th>${esc(t("users.inv.purpose"))}</th><th>${esc(t("users.col.status"))}</th>
        <th>${esc(t("users.inv.col.created"))}</th><th>${esc(t("users.inv.expires"))}</th>
        <th>${esc(t("users.col.actions"))}</th>
      </tr></thead>
      <tbody>${rows.length ? rows.map(invitationRowHTML).join("") : `<tr><td colspan="7" class="tiny muted" style="padding:20px 16px">${esc(t("users.inv.empty"))}</td></tr>`}</tbody>
    </table>`;
  }
  return `<div class="sec-title">${esc(t("users.inv.title"))}
      ${u.invites == null ? "" : `<small>${esc(t("users.inv.count", { n: rows.length }))}</small>`}
      <span style="flex:1"></span>
      <button class="btn seal-btn sm" data-act="invCreateToggle">${esc(u.invOpen ? t("common.collapse") : t("users.inv.new"))}</button>
    </div>
    <p class="tiny muted" style="margin:0 0 12px">${t("users.inv.lede")}</p>
    ${u.invOpen ? invCreateFormHTML() : ""}
    ${body}`;
}

/* ---------- 视图 ---------- */

function viewUsers() {
  if (AUTH.mode !== "local" || !connected()) return usersNoAccessHTML();
  if (!canUsersPage()) return usersNoAccessHTML();
  const u = state.users;
  return `<div id="users" class="users-view">
    <header class="head">
      <h1>${esc(t("users.title"))}</h1>
      <p class="lede">${t("users.lede")}</p>
      <div class="head-act"><button class="btn ghost sm" data-act="usersRetry"${u.busy ? " disabled" : ""}>${esc(t("users.refresh"))}</button></div>
    </header>
    <div class="note users-note">${t("users.note")}</div>
    <div class="tiny muted users-scope">${usersScopeHTML()}</div>
    ${u.err && (u.list != null || u.invites != null)
      ? `<div class="note seal" style="margin:0 0 16px">${esc(u.err)} <button class="btn ghost sm" data-act="usersRetry" style="margin-left:8px">${esc(t("common.retry"))}</button></div>`
      : ""}
    ${u.lastInvite ? inviteCardHTML(u.lastInvite) : ""}
    ${sysadminUser() ? usersSectionHTML() : ""}
    ${isAdmin() && cfg.org ? invitationsSectionHTML() : ""}
  </div>`;
}

/* ---------- 动作 ---------- */

Object.assign(actions, {
  async usersRetry() {
    const u = state.users;
    if (u.busy) return false;
    u.busy = true;
    u.err = null;
    render();
    await onEnterUsers();
    u.busy = false;
    render();
    return false;
  },

  usersCreateToggle() {
    const u = state.users;
    u.createOpen = !u.createOpen;
    u.form = freshUserForm();
    u.err = null;
  },

  async usersCreate() {
    if (!sysadminUser() || state.users.busy) return false;
    const f = state.users.form;
    const username = String(f.username || "").trim();
    if (!username) { toast(esc(t("auth.err.required"))); return false; }
    const body = { username };
    const displayName = String(f.display_name || "").trim();
    const email = String(f.email || "").trim();
    if (displayName) body.display_name = displayName;
    if (email) body.email = email;
    if (f.is_system_admin) body.is_system_admin = true;
    const org = String(f.org_id || "").trim();
    if (org) {
      body.org_id = org;
      body.role = f.role === "org_admin" ? "org_admin" : "member";
    }
    const ep = state.epoch;
    state.users.busy = true;
    state.users.err = null;
    render();
    let res;
    try {
      res = await createUser(body);
    } catch (e) {
      if (ep !== state.epoch) return false;
      state.users.busy = false;
      state.users.err = usersErrorText(e);
      usersToastErr(e);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    state.users.busy = false;
    const inv = res && res.invitation;
    if (inv && inv.token) {
      state.users.lastInvite = {
        token: inv.token,
        username: (res.user && res.user.username) || username,
        kind: "invite",
      };
    }
    state.users.createOpen = false;
    state.users.form = freshUserForm();
    await refreshUsers(ep);
    toast(t("users.toast.created", { username: esc(username) }));
    render();
    return false;
  },

  async usersToggle(el) {
    const id = el.dataset.id;
    const u = (state.users.list || []).find((x) => x.id === id);
    if (!u) return false;
    const disabling = !u.disabled_at;
    if (disabling && !window.confirm(t("users.confirm.disable", { username: u.username }))) return false;
    const ep = state.epoch;
    let res;
    try {
      res = await patchUser(id, { disabled: disabling });
    } catch (e) {
      if (ep !== state.epoch) return false;
      usersToastErr(e);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    state.users.list = (state.users.list || []).map((x) => (x.id === id ? (res.user || x) : x));
    toast(t(disabling ? "users.toast.disabled" : "users.toast.enabled", { username: esc(u.username) }));
    render();
    return false;
  },

  async usersSysadmin(el) {
    const id = el.dataset.id;
    const u = (state.users.list || []).find((x) => x.id === id);
    if (!u) return false;
    const makeAdmin = !u.is_system_admin;
    const ep = state.epoch;
    let res;
    try {
      res = await patchUser(id, { is_system_admin: makeAdmin });
    } catch (e) {
      if (ep !== state.epoch) return false;
      usersToastErr(e);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    state.users.list = (state.users.list || []).map((x) => (x.id === id ? (res.user || x) : x));
    toast(t(makeAdmin ? "users.toast.sysadminOn" : "users.toast.sysadminOff", { username: esc(u.username) }));
    render();
    return false;
  },

  async usersReset(el) {
    const u = (state.users.list || []).find((x) => x.id === el.dataset.id);
    if (!u) return false;
    if (u.disabled_at) { toast(esc(t("users.err.user_disabled"))); return false; }
    const ep = state.epoch;
    let res;
    try {
      res = await resetUser(u.id);
    } catch (e) {
      if (ep !== state.epoch) return false;
      usersToastErr(e);
      return false;
    }
    if (ep !== state.epoch) return false;
    const inv = res && res.invitation;
    if (!inv || !inv.token) { toast(esc(t("auth.err.generic"))); return false; }
    state.users.lastInvite = { token: inv.token, username: u.username, kind: "reset" };
    toast(t("users.toast.reset", { username: esc(u.username) }));
    render();
    return false;
  },

  invCreateToggle() {
    const u = state.users;
    u.invOpen = !u.invOpen;
    u.invForm = freshInviteForm();
    u.err = null;
  },

  async invCreate() {
    if (!isAdmin() || !cfg.org || state.users.busy) return false;
    const f = state.users.invForm;
    const username = String(f.username || "").trim();
    if (!username) { toast(esc(t("auth.err.required"))); return false; }
    const role = f.role === "org_admin" ? "org_admin" : "member";
    const body = { username, role };
    const displayName = String(f.display_name || "").trim();
    const email = String(f.email || "").trim();
    if (displayName) body.display_name = displayName;
    if (email) body.email = email;
    const ep = state.epoch;
    state.users.busy = true;
    state.users.err = null;
    render();
    let res;
    try {
      res = await createInvitation(cfg.org, body);
    } catch (e) {
      if (ep !== state.epoch) return false;
      state.users.busy = false;
      state.users.err = usersErrorText(e);
      usersToastErr(e);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    state.users.busy = false;
    const inv = res && res.invitation;
    if (inv && inv.token) {
      state.users.lastInvite = { token: inv.token, username, kind: "invite" };
    }
    state.users.invOpen = false;
    state.users.invForm = freshInviteForm();
    await refreshUsers(ep);
    if (res && res.membership_added) {
      toast(t("users.inv.added", { username: esc(username) }));
    } else {
      toast(t("users.inv.created", { username: esc(username) }));
    }
    render();
    return false;
  },

  async invRevoke(el) {
    const inv = (state.users.invites || []).find((x) => x.id === el.dataset.id);
    if (!inv || !cfg.org) return false;
    const username = inv.username || inv.user_id || "";
    if (!window.confirm(t("users.inv.revokeConfirm", { username }))) return false;
    const ep = state.epoch;
    try {
      await revokeInvitation(cfg.org, inv.id);
    } catch (e) {
      if (ep !== state.epoch) return false;
      if (e && e.status === 404) toast(esc(t("users.inv.revokeGone")));
      else usersToastErr(e);
      await refreshInvites(ep);
      render();
      return false;
    }
    if (ep !== state.epoch) return false;
    toast(t("users.inv.revoked", { username: esc(username) }));
    await refreshInvites(ep);
    render();
    return false;
  },

  async invCopy(el) {
    const token = el.dataset.token || "";
    if (!token) return false;
    const link = inviteLink(token);
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(link);
        toast(esc(t("users.link.copied")));
        return false;
      }
    } catch (e) { /* 剪贴板不可用（非安全上下文等）→ prompt 兜底 */ }
    window.prompt(t("users.link.prompt"), link);
    return false;
  },
});

Object.assign(INPUTS, {
  uCreateUsername: (v) => { state.users.form.username = v; },
  uCreateDisplay: (v) => { state.users.form.display_name = v; },
  uCreateEmail: (v) => { state.users.form.email = v; },
  uCreateAdmin: (v) => { state.users.form.is_system_admin = !!v; },
  uCreateOrg: (v) => {
    state.users.form.org_id = v;
    if (!v) state.users.form.role = "member";
  },
  uCreateRole: (v) => { state.users.form.role = v === "org_admin" ? "org_admin" : "member"; },
  uInvUsername: (v) => { state.users.invForm.username = v; },
  uInvDisplay: (v) => { state.users.invForm.display_name = v; },
  uInvEmail: (v) => { state.users.invForm.email = v; },
  uInvRole: (v) => { state.users.invForm.role = v === "org_admin" ? "org_admin" : "member"; },
});

VIEWS.users = { render: viewUsers, onEnter: onEnterUsers };
