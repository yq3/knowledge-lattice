/* views/login.js —— D25 local 认证三屏（m4-3a，VIEWS.auth）：
 * - setup：零用户首启（首 sysadmin + 可选首组织 + LATTICE_INIT_PASSWORD 门禁）；
 * - login：username + password（登录限流/锁定错误由 authErrorText 映射）；
 * - accept：邀请/重置 token 接受（先匿名 lookup 展示账号/组织/角色/用途，再设密码）。
 * 归属与状态机在 app.js（AUTH / boot / bootLocal / applySession / handleAuthExpired）；
 * 本文件只做视图 + 动作 + INPUTS——所有请求走 api.js 的 apiPublic（不带 Authorization/
 * X-Org-Id、不触发连接设置）。sso 形态不注册 screen，本视图永不渲染（零回归）。
 * t() 返回值视为受信 HTML 片段；动态值（表单/邀请信息）一律 esc()。 */
"use strict";

/* ---------- 片段 ---------- */

function authBrandHTML() {
  return `<div class="auth-brand">
    <div class="brand-seal" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M6 6h12M6 12h12M6 18h12M6 6v12M12 6v12M18 6v12" stroke="#fff" stroke-opacity=".45" stroke-width="1.6" stroke-linecap="round"/><circle cx="6" cy="6" r="2.2" fill="#fff"/><circle cx="18" cy="12" r="2.2" fill="#fff"/><circle cx="12" cy="18" r="2.2" fill="#fff"/><path d="M6 6 18 12 12 18" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
    <span class="brand-name">Knowledge Lattice</span><span class="brand-sub">${esc(t("auth.brandSub"))}</span>
  </div>`;
}

function authFrame({ title, lede, body, note }) {
  return `<div class="auth-shell"><div class="auth-card">
    ${authBrandHTML()}
    <h1 class="auth-title">${esc(title)}</h1>
    ${lede ? `<p class="auth-lede">${lede}</p>` : ""}
    ${AUTH.error ? `<div class="auth-err" role="alert">${esc(AUTH.error)}</div>` : ""}
    ${body}
    ${note ? `<div class="auth-note">${note}</div>` : ""}
  </div></div>`;
}

/* 表单行（label + input；data-in 写 AUTH.form，render 重渲染保留输入并恢复焦点） */
function authRow({ id, key, label, type = "text", value = "", ph = "", autocomplete = "off", required = false }) {
  return `<label class="af-row" for="${id}"><span>${esc(label)}${required ? '<span class="req">*</span>' : ""}</span>
    <input class="inp" id="${id}" data-in="${key}" type="${type}" autocomplete="${autocomplete}" value="${esc(value)}" placeholder="${esc(ph)}"${required ? " required" : ""}></label>`;
}

function authSubmitHTML(kind, busy, idleText, busyText) {
  return `<button class="btn seal-btn auth-submit" type="submit" form="authForm-${kind}"${busy ? " disabled" : ""}>${esc(busy ? busyText : idleText)}</button>`;
}

/* ---------- setup 屏 ---------- */

function authSetupHTML() {
  const f = AUTH.form;
  const busy = AUTH.busy;
  const body = `<form class="auth-form" id="authForm-setup" data-auth="setup">
    ${authRow({ id: "authUsername", key: "authUsername", label: t("auth.setup.username"), value: f.username, ph: t("auth.setup.usernamePh"), autocomplete: "username", required: true })}
    ${authRow({ id: "authPassword", key: "authPassword", label: t("auth.setup.password"), type: "password", value: f.password, ph: t("auth.setup.passwordPh"), autocomplete: "new-password", required: true })}
    <p class="af-hint">${esc(t("auth.policy.password", { n: PASSWORD_MIN_LEN_HINT }))}</p>
    ${authRow({ id: "authConfirm", key: "authConfirm", label: t("auth.setup.confirm"), type: "password", value: f.confirm, ph: t("auth.setup.confirmPh"), autocomplete: "new-password", required: true })}
    ${authRow({ id: "authDisplayName", key: "authDisplayName", label: t("auth.setup.displayName"), value: f.display_name, ph: t("auth.setup.displayNamePh"), autocomplete: "nickname" })}
    <div class="af-sec">${esc(t("auth.setup.orgSection"))}</div>
    <p class="af-hint">${t("auth.setup.orgNote")}</p>
    ${authRow({ id: "authOrgId", key: "authOrgId", label: t("auth.setup.orgId"), value: f.org_id, ph: t("auth.setup.orgIdPh"), autocomplete: "off" })}
    ${authRow({ id: "authOrgName", key: "authOrgName", label: t("auth.setup.orgName"), value: f.org_name, ph: t("auth.setup.orgNamePh"), autocomplete: "off" })}
    ${authRow({ id: "authInitPassword", key: "authInitPassword", label: t("auth.setup.initPassword"), type: "password", value: f.init_password, ph: t("auth.setup.initPasswordPh"), autocomplete: "off" })}
    <p class="af-hint">${t("auth.setup.initPasswordNote")}</p>
    ${authSubmitHTML("setup", busy, t("auth.setup.submit"), t("auth.setup.busy"))}
  </form>`;
  return authFrame({
    title: t("auth.setup.title"),
    lede: t("auth.setup.lede"),
    body,
    note: t("auth.setup.note"),
  });
}

/* ---------- login 屏 ---------- */

function authLoginHTML() {
  const f = AUTH.form;
  const busy = AUTH.busy;
  const body = `<form class="auth-form" id="authForm-login" data-auth="login">
    ${authRow({ id: "authUsername", key: "authUsername", label: t("auth.login.username"), value: f.username, ph: t("auth.login.usernamePh"), autocomplete: "username", required: true })}
    ${authRow({ id: "authPassword", key: "authPassword", label: t("auth.login.password"), type: "password", value: f.password, ph: t("auth.login.passwordPh"), autocomplete: "current-password", required: true })}
    ${authSubmitHTML("login", busy, t("auth.login.submit"), t("auth.login.busy"))}
  </form>`;
  return authFrame({
    title: t("auth.login.title"),
    lede: t("auth.login.lede"),
    body,
    note: `<div>${t("auth.login.note")}</div>
      <div class="auth-note-sub">${t("auth.login.inviteHint")}</div>
      <div class="auth-note-sub">${esc(t("auth.policy.password", { n: PASSWORD_MIN_LEN_HINT }))}</div>`,
  });
}

/* ---------- accept 屏（邀请 / 重置） ---------- */

function authAcceptHTML() {
  const inv = AUTH.invite || {};
  if (inv.loading || !inv.info) {
    const body = inv.loading
      ? `<div class="loading">${esc(t("auth.invite.loading"))}</div>`
      : `<div class="auth-actions"><button class="btn ghost" data-act="authToLogin">${esc(t("auth.invite.back"))}</button></div>`;
    return authFrame({
      title: t("auth.invite.title"),
      lede: t("auth.invite.lede"),
      body,
      note: t("auth.invite.note"),
    });
  }
  const info = inv.info;
  const isReset = info.purpose === "reset";
  const f = AUTH.form;
  const busy = AUTH.busy;
  const roleText = info.role === "org_admin" ? t("role.org_admin")
    : info.role === "member" ? t("role.member") : (info.role || "");
  const meta = `<div class="auth-meta">
    <div><span>${esc(t("auth.invite.username"))}</span><b class="mono">${esc(info.username || "—")}</b></div>
    ${(info.org_name || info.org_id) ? `<div><span>${esc(t("auth.invite.org"))}</span><b>${esc(info.org_name || info.org_id)}</b>${info.org_id ? `<small class="mono">${esc(info.org_id)}</small>` : ""}</div>` : ""}
    ${roleText ? `<div><span>${esc(t("auth.invite.role"))}</span><b>${esc(roleText)}</b></div>` : ""}
    <div><span>${esc(t("auth.invite.purpose"))}</span><b class="pill ${isReset ? "idle" : "ok"}">${esc(isReset ? t("auth.invite.purpose.reset") : t("auth.invite.purpose.invite"))}</b></div>
    ${info.expires_at ? `<div><span>${esc(t("auth.invite.expires"))}</span><b class="mono">${esc(info.expires_at)}</b></div>` : ""}
  </div>`;
  const body = `<form class="auth-form" id="authForm-accept" data-auth="accept">
    ${meta}
    ${isReset ? "" : authRow({ id: "authDisplayName", key: "authDisplayName", label: t("auth.invite.displayName"), value: f.display_name, ph: t("auth.invite.displayNamePh"), autocomplete: "nickname" })}
    ${authRow({ id: "authPassword", key: "authPassword", label: t("auth.invite.password"), type: "password", value: f.password, ph: t("auth.invite.passwordPh"), autocomplete: "new-password", required: true })}
    <p class="af-hint">${esc(t("auth.policy.password", { n: PASSWORD_MIN_LEN_HINT }))}</p>
    ${authRow({ id: "authConfirm", key: "authConfirm", label: t("auth.invite.confirm"), type: "password", value: f.confirm, ph: t("auth.invite.confirmPh"), autocomplete: "new-password", required: true })}
    ${authSubmitHTML("accept", busy, isReset ? t("auth.invite.submitReset") : t("auth.invite.submit"), t("auth.invite.busy"))}
    <button class="btn ghost auth-back" type="button" data-act="authToLogin">${esc(t("auth.invite.back"))}</button>
  </form>`;
  return authFrame({
    title: isReset ? t("auth.invite.titleReset") : t("auth.invite.title"),
    lede: t("auth.invite.lede"),
    body,
    note: t("auth.invite.note"),
  });
}

function renderAuth() {
  if (AUTH.screen === "setup") return authSetupHTML();
  if (AUTH.screen === "accept") return authAcceptHTML();
  return authLoginHTML();
}

/* ---------- 动作 ---------- */

Object.assign(actions, {
  async authSetup() {
    if (AUTH.busy) return false;
    const f = AUTH.form;
    const username = String(f.username || "").trim();
    const password = String(f.password || "");
    const orgId = String(f.org_id || "").trim();
    const orgName = String(f.org_name || "").trim();
    if (!username || !password) { AUTH.error = t("auth.err.required"); render(); return false; }
    if (password !== String(f.confirm || "")) { AUTH.error = t("auth.err.password_mismatch"); render(); return false; }
    if (!!orgId !== !!orgName) { AUTH.error = t("auth.err.org_pair"); render(); return false; }
    AUTH.busy = true; AUTH.error = ""; render();
    let data;
    try {
      data = await setupInstance({
        username,
        password,
        display_name: String(f.display_name || "").trim() || undefined,
        org_id: orgId || undefined,
        org_name: orgName || undefined,
        init_password: String(f.init_password || "") || undefined,
      });
    } catch (e) {
      AUTH.error = authErrorText(e);
      AUTH.busy = false;
      f.password = ""; f.confirm = "";
      render();
      return false;
    }
    await applySession(data, "");
    return false;
  },

  async authLogin() {
    if (AUTH.busy) return false;
    const f = AUTH.form;
    const username = String(f.username || "").trim();
    const password = String(f.password || "");
    if (!username || !password) { AUTH.error = t("auth.err.required"); render(); return false; }
    AUTH.busy = true; AUTH.error = ""; render();
    let data;
    try {
      data = await authLogin(username, password);
    } catch (e) {
      AUTH.error = authErrorText(e);
      AUTH.busy = false;
      f.password = "";
      render();
      return false;
    }
    await applySession(data, "");
    return false;
  },

  async authAccept() {
    if (AUTH.busy) return false;
    const inv = AUTH.invite || {};
    if (!inv.token || !inv.info) return false;
    const f = AUTH.form;
    const password = String(f.password || "");
    if (!password) { AUTH.error = t("auth.err.required"); render(); return false; }
    if (password !== String(f.confirm || "")) { AUTH.error = t("auth.err.password_mismatch"); render(); return false; }
    const isReset = inv.info.purpose === "reset";
    AUTH.busy = true; AUTH.error = ""; render();
    let data;
    try {
      data = await acceptInvitation({
        token: inv.token,
        password,
        display_name: isReset ? undefined : (String(f.display_name || "").trim() || undefined),
      });
    } catch (e) {
      AUTH.error = authErrorText(e);
      AUTH.busy = false;
      f.password = ""; f.confirm = "";
      render();
      return false;
    }
    /* 接受成功即清 hash（token 不留在地址栏/历史；query 保留按任务口径） */
    try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { /* file:// 等 */ }
    await applySession(data, "");
    return false;
  },

  authToLogin() {
    showAuthScreen("login");
    return false;
  },
});

/* Enter 提交：统一走 form submit（type=submit 按钮 + 回车），避免输入动作重渲染时
 * 触发页面刷新。 */
document.addEventListener("submit", (ev) => {
  const form = ev.target && ev.target.closest ? ev.target.closest("form.auth-form") : null;
  if (!form) return;
  ev.preventDefault();
  const kind = form.dataset.auth;
  const act = kind === "setup" ? "authSetup" : kind === "accept" ? "authAccept" : "authLogin";
  const fn = actions[act];
  if (!fn) return;
  const out = fn();
  if (out && typeof out.then === "function") return;
});

Object.assign(INPUTS, {
  authUsername: (v) => { AUTH.form.username = v; },
  authPassword: (v) => { AUTH.form.password = v; },
  authConfirm: (v) => { AUTH.form.confirm = v; },
  authDisplayName: (v) => { AUTH.form.display_name = v; },
  authOrgId: (v) => { AUTH.form.org_id = v; },
  authOrgName: (v) => { AUTH.form.org_name = v; },
  authInitPassword: (v) => { AUTH.form.init_password = v; },
});

VIEWS.auth = { render: renderAuth };
