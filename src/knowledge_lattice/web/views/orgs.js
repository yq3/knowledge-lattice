/* views/orgs.js —— 组织管理（ui-2 新增，nav 运维组「组织」项）：
 * - ledger：GET /api/orgs 结果（系统管理员=全部组织 {org_id,name,status}；
 *   普通用户=本人 membership {org_id,name,role,expires_at,status}——跨组织
 *   存在性不泄露 TC-AZ-02）+ 当前 token 可见性标注 + 状态徽标（m3-1 #14
 *   实装——m3-2 ui-be 撤降级接真列）。
 * - 建组织：POST /api/orgs {id,name,org_admin} 三必填（sysadmin 专属 403 /
 *   用户不存在 404 / 重复 409 如实回显）。
 * - 停用/恢复：PATCH /api/orgs/{org} {status}（#14 m3-1 实装——sysadmin
 *   专属/只停不删/审计同事务；跨组织行按路径对齐 X-Org-Id——api.js 承载）。 */
"use strict";

async function onEnterOrgs() {
  if (!connected()) return;
  const ep = state.epoch; // P1-5
  if (!state.orgView.list) {
    try {
      const body = await listOrgs();
      if (ep !== state.epoch) return;
      state.orgView.list = body.orgs || [];
      state.orgView.loadErr = null;
    } catch (e) {
      if (ep !== state.epoch) return;
      state.orgView.list = [];
      state.orgView.loadErr = String((e && e.message) || e); // P2-3：失败显错误态（非「无组织」空态）
    }
  }
}

function viewOrgs() {
  if (!connected()) return connGate();
  const v = state.orgView;
  // 首装无缓存（list 未取到且元数据也未带出组织）→ loading（防「无组织」空态误闪——ui-3）
  if (v.list == null && !state.orgs.length) return loadingHTML("orgs");
  if (v.loadErr && !(v.list || []).length) return `<div class="empty" style="margin:0"><h3>${esc(t("orgs.loadErr", { err: esc(v.loadErr) }))}</h3>
    <div style="margin-top:16px"><button class="btn ghost sm" data-act="orgsRetry">${esc(t("common.retry"))}</button></div></div>`; // P2-3
  const orgs = v.list != null ? v.list : state.orgs;
  return `
  <header class="head"><h1>${esc(t("orgs.title"))}</h1>
    <p class="lede">${t("orgs.lede")}</p>
    <div class="head-act"><button class="btn seal-btn" data-act="orgNewToggle">${v.newOpen ? esc(t("common.collapse")) : esc(t("orgs.new"))}</button></div>
  </header>
  <div class="note" style="margin:0 0 16px;max-width:92ch">${t("orgs.viewNote")}</div>
  ${v.newOpen ? orgNewHTML() : ""}
  <table class="ledger">
    <thead><tr><th>${esc(t("orgs.col.org"))}</th><th>${esc(t("orgs.col.visible"))}</th><th>${esc(t("orgs.col.role"))}</th><th>${esc(t("orgs.col.expires"))}</th><th></th></tr></thead>
    <tbody>${orgs.length ? orgs.map((x) => {
      const isCurrent = x.org_id === cfg.org;
      const disabled = x.status === "disabled";
      const row = `<tr class="${isCurrent ? "on" : ""} ${disabled ? "retired" : ""}">
        <td><div class="t-title">${esc(x.name)}</div><div class="t-sub mono">${esc(x.org_id)}</div></td>
        <td>${isCurrent ? `<span class="pill ok">${esc(t("orgs.current"))}</span>` : `<span class="tiny muted">${esc(t("orgs.listedOnly"))}</span>`}</td>
        <td>${x.role ? `<span class="pill ${x.role === "org_admin" ? "ok" : ""}">${esc(x.role)}</span>` : `<span class="tiny muted">—</span>`}</td>
        <td class="tiny">${x.expires_at ? tsHTML(x.expires_at, "mono tiny") : `<span class="tiny muted">${esc(t("orgs.permanent"))}</span>`}</td>
        <td><div style="display:flex;gap:6px;align-items:center">
          ${disabled
            ? `<span class="pill bad">${esc(t("orgs.statusDisabled"))}</span>
               <button class="btn ghost sm" data-act="orgEnable" data-id="${esc(x.org_id)}" data-name="${esc(x.name)}" title="${esc(t("orgs.enableTip"))}">${esc(t("orgs.enable"))}</button>`
            : `<span class="pill ok">${esc(t("orgs.statusActive"))}</span>
               <button class="btn ghost sm" data-act="orgDisableAsk" data-id="${esc(x.org_id)}" data-name="${esc(x.name)}" title="${esc(t("orgs.disableTip"))}" style="color:var(--danger)">${esc(t("orgs.disable"))}…</button>`}
        </div></td></tr>`;
      if (v.askOrg !== x.org_id) return row;
      return row + `<tr><td colspan="5" style="border-bottom:0"><div class="confirm">
        <b>${t("orgs.disableAsk", { name: esc(x.name) })}</b> ${t("orgs.disableBody")}
        <div class="cf-act"><button class="btn danger-btn sm" data-act="orgDisableOk" data-id="${esc(x.org_id)}" data-name="${esc(x.name)}">${esc(t("common.confirm"))}</button>
        <button class="btn ghost sm" data-act="orgDisableCancel">${esc(t("common.cancel"))}</button>
        <span class="tiny muted" style="align-self:center">${esc(t("orgs.disableCode"))}</span></div></div></td></tr>`;
    }).join("") : `<tr><td colspan="5" class="tiny muted" style="padding:20px 16px">${esc(t("orgs.empty"))}</td></tr>`}</tbody>
  </table>
  <div class="note" style="margin-top:16px;max-width:92ch">${t("orgs.foot")}</div>`;
}

function orgNewHTML() {
  const d = state.orgView.form;
  const ok = d.id.trim() && d.name.trim() && d.admin.trim();
  return `<div class="upload" style="margin-bottom:16px">
    <div style="grid-column:1/-1"><b style="font-size:15px">${esc(t("orgs.new"))}</b>
      <span class="tiny muted">—— ${t("orgs.newNote")}</span></div>
    <div class="u-row"><label>org_id<span class="req">*</span></label>
      <input class="inp" data-in="orgNewId" placeholder="${esc(t("orgs.idPh"))}" value="${esc(d.id)}" style="font-family:var(--mono)"></div>
    <div class="u-row"><label>${esc(t("orgs.name"))}<span class="req">*</span></label>
      <input class="inp" data-in="orgNewName" placeholder="${esc(t("orgs.namePh"))}" value="${esc(d.name)}"></div>
    <div class="u-row"><label>org_admin<span class="req">*</span></label>
      <input class="inp" data-in="orgNewAdmin" placeholder="${esc(t("orgs.adminPh"))}" value="${esc(d.admin)}" style="font-family:var(--mono)"></div>
    <div class="u-foot">
      <button class="btn seal-btn" data-act="orgCreate" ${ok ? "" : "disabled"}>${esc(t("common.create"))}</button>
      <button class="btn ghost" data-act="orgNewToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny ${ok ? "" : "muted"}">${ok ? esc(t("orgs.newOk")) : esc(t("orgs.newNeed"))}</span>
      <span style="flex:1"></span>
      <span class="tiny muted">${t("orgs.newFoot")}</span>
    </div></div>`;
}

Object.assign(actions, {
  orgNewToggle() {
    const v = state.orgView;
    v.newOpen = !v.newOpen;
    v.form = { id: "", name: "", admin: "" };
    v.askOrg = null;
  },
  /* P2-3：组织列表装载失败后的显式重试 */
  async orgsRetry() {
    state.orgView.list = null;
    state.orgView.loadErr = null;
    render();
    await onEnterOrgs();
    render();
    return false;
  },
  async orgCreate() {
    const d = state.orgView.form;
    const id = d.id.trim(), name = d.name.trim(), admin = d.admin.trim();
    if (!id || !name || !admin) return false;
    let body;
    try {
      body = await createOrg({ id, name, org_admin: admin });
    } catch (e) {
      if (e.status === 403) toast(t("orgs.create403"));
      else if (e.status === 404) toast(t("orgs.create404", { user: esc(admin) }));
      else if (e.status === 409) toast(t("orgs.create409", { org: esc(id) }));
      else errToast(e);
      return false;
    }
    toast(t("orgs.created", { name: esc(body.name || name), admin: esc(body.org_admin || admin) }));
    state.orgView.newOpen = false;
    state.orgView.form = { id: "", name: "", admin: "" };
    state.orgView.list = null;
    await onEnterOrgs();
    await loadMeta().catch(() => { /* 已 toast */ });
    render();
    return false;
  },
  orgDisableAsk(el) { state.orgView.askOrg = el.dataset.id; },
  orgDisableCancel() { state.orgView.askOrg = null; },
  async orgEnable(el) {
    const org = el.dataset.id, name = el.dataset.name;
    let body;
    try {
      body = await setOrgStatus(org, "active");
    } catch (e) {
      if (e.status === 403) toast(t("orgs.disable403"));
      else errToast(e);
      return false;
    }
    toast(t("orgs.enabled", { name: esc(name), status: esc(body && body.status || "active") }));
    state.orgView.list = null;
    await onEnterOrgs();
    render();
    return false;
  },
  async orgDisableOk(el) {
    const org = el.dataset.id, name = el.dataset.name;
    state.orgView.askOrg = null;
    let body;
    try {
      body = await setOrgStatus(org, "disabled");
    } catch (e) {
      if (e.status === 403) toast(t("orgs.disable403"));
      else errToast(e);
      return false;
    }
    toast(t("orgs.disabled", { name: esc(name), status: esc(body && body.status || "disabled") }));
    state.orgView.list = null;
    await onEnterOrgs();
    render();
    return false;
  },
});

Object.assign(INPUTS, {
  orgNewId: (v) => { state.orgView.form.id = v; },
  orgNewName: (v) => { state.orgView.form.name = v; },
  orgNewAdmin: (v) => { state.orgView.form.admin = v; },
});

VIEWS.orgs = { render: viewOrgs, onEnter: onEnterOrgs };
