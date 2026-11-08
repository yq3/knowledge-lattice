/* views/access.js —— 权限（ui-2 升级为原型 v0.6 全保真四子标签）：
 * - 授权格（默认）：export CSV = local 授权真相源（行=成员 username，列=维度取值）；
 *   点格 = 该成员全量 local 行 PUT 替换（expires 沿库内、新授权 null）；
 *   B① 行级到期编辑保留在成员行「详细」抽屉（ui-1 chips 编辑器 + CSV 迁入）。
 *   API 无维度 source 字段——不标 sync 只读格（export=local 口径，诚实差异）。
 * - 成员子标签：真端点（POST/PATCH/DELETE members——m2-6 A3）；名单源 = export
 *   用户名（无 GET members，m3-1 #13）；T23 约束（过期行 409 三步恢复 / 唯一
 *   管理员自锁 / 级联清授权）由服务端守卫如实回显。
 * - 维度子标签：ui-1 既有治理（停用/恢复/新增取值/退役/新建维度†）。
 * - 可见性矩阵：占位空态（待 be-① 文档列表 + be-② explain——前端不演算 ACL，B5）。 */
"use strict";

/* ---------- 授权数据装载（export CSV = local 真相源） ---------- */

async function loadGrantsTable() {
  const ep = state.epoch; // P1-5：组织/身份切换后旧响应不写入新视图
  state.loading.grants = true;
  try {
    const text = await exportGrants(cfg.org);
    if (ep !== state.epoch) return;
    const lines = text.trim().split(/\r?\n/);
    state.g.rows = lines.length > 1
      ? lines.slice(1).filter((l) => l.trim()).map((l) => {
          // 引号形态 CSV 单行解析（值含逗号不错位）——parseCsvLine 见 app.js
          const cols = parseCsvLine(l);
          return { username: cols[0], dimKey: cols[1], value: cols[2], expiresAt: cols[3] || "" };
        })
      : [];
    state.g.error = null; // 装载成功清错误态（P2-3）
    state.usernames = [...new Set([...state.g.rows.map((r) => r.username), ...knownMembers()])].sort();
    if (state.g.detail && !state.usernames.includes(state.g.detail)) state.g.detail = null;
    if (state.g.detail) seedGrantEditor(state.g.detail);
  } catch (e) {
    if (ep !== state.epoch) return;
    state.g.rows = [];
    state.g.error = String((e && e.message) || e); // P2-3：失败显错误态（非「暂无授权行」空态）
  } finally {
    if (ep === state.epoch) state.loading.grants = false;
  }
}

/* 授权格成员集（export 用户名 ∪ 会话成员注册表，升序——P1-3）与格态判定（display-only 到期比较） */
function latticeMembers() {
  return [...new Set([...state.g.rows.map((r) => r.username), ...knownMembers()])].sort();
}
function grantRowsOf(username) {
  return state.g.rows.filter((r) => r.username === username);
}
function nowUtcStr() {
  return new Date().toISOString().slice(0, 19).replace("T", " ");
}

/* 既有 expires 映射 + ui-1 chips 编辑器种子（B①——抽屉内逐行 expires） */
function seedGrantEditor(member, preserve = false) {
  state.g.member = member;
  const mine = grantRowsOf(member);
  state.g.existing = {};
  mine.forEach((r) => { state.g.existing[`${r.dimKey}=${r.value}`] = r.expiresAt; });
  if (!preserve) {
    state.g.picked = { ...state.g.existing };
    state.g.expires = { ...state.g.existing }; // 行内初始值=库内值（未编辑即沿用——B①）
  }
}

/* ---------- 授权格子标签：格矩阵（原型 .lattice-wrap/.lattice/.cellbtn） ---------- */

function grantsHTML() {
  const g = state.g;
  if (state.loading.grants && !g.rows.length) return loadingHTML("access");
  if (!isAdmin()) return `<div class="note amber">${t("access.grants.needAdmin")}</div>`;
  if (g.error) return `<div class="empty" style="margin:0"><h3>${esc(t("access.grants.loadErr", { err: esc(g.error) }))}</h3>
    <div style="margin-top:16px"><button class="btn ghost sm" data-act="grantsRetry">${esc(t("common.retry"))}</button></div></div>`; // P2-3：失败≠空态
  if (!g.rows.length) return `<div class="empty" style="margin:0"><h3>${esc(t("access.grants.empty.title"))}</h3><p>${t("access.grants.empty.body")}</p></div>`;
  const members = latticeMembers();
  const now = nowUtcStr();
  const dims = state.dims.filter((d) => d.status !== "retired");
  const valOf = (dim, value) => (dim.values || []).find((v) => v.value === value);
  return `
  <div class="lattice-wrap"><table class="lattice">
    <thead>
      <tr><th></th>${dims.map((d) => `<th class="dg" colspan="${(d.values || []).length}">${esc(d.name)}${d.required ? `<span class="req">*</span>` : ""}</th>`).join("")}</tr>
      <tr><th style="text-align:left;padding-left:14px">${esc(t("access.grants.memberCol"))}</th>${dims.map((d) => (d.values || []).map((v, i) => `<th class="vh ${i === 0 ? "dg" : ""}">${esc(v.label)}<span class="ck">${esc(v.value)}</span></th>`).join("")).join("")}</tr>
    </thead>
    <tbody>${members.map((u) => {
      const mine = grantRowsOf(u);
      const memberHasExp = mine.some((r) => r.expiresAt);
      return `<tr><th><b style="font-weight:600">${esc(u)}</b>
          ${memberHasExp ? `<span class="tiny muted"> · ${esc(t("access.grants.hasExpires"))}</span>` : ""}
          <button class="link tiny" data-act="latDetail" data-u="${esc(u)}" title="${esc(t("access.grants.detailTip"))}">${g.detail === u ? esc(t("common.collapse")) : esc(t("access.grants.detail"))}</button></th>
        ${dims.map((d) => (d.values || []).map((v, i) => {
          const row = mine.find((r) => r.dimKey === d.key && r.value === v.value);
          const on = !!row;
          const expired = on && row.expiresAt && row.expiresAt <= now;
          const title = `${u} · ${d.name}=${v.label}` + (row && row.expiresAt ? ` · ${expired ? t("access.grants.grantExpiredAt") : t("access.expires.existing")}: ${row.expiresAt}` : "");
          return `<td class="${i === 0 ? "dg" : ""}"><button class="cellbtn ${on ? "on" : ""}" ${expired ? `style="opacity:.4;outline:1px dashed var(--danger);outline-offset:1px"` : ""}
            data-act="latCell" data-u="${esc(u)}" data-k="${esc(d.key)}" data-v="${esc(v.value)}" data-dim="${esc(d.id)}"
            title="${esc(title)}" aria-label="${esc(title)}" aria-pressed="${on}" ${g.saving ? "disabled" : ""}></button></td>`;
        }).join("")).join("")}
      </tr>${g.detail === u ? `<tr><td colspan="${dims.reduce((a, d) => a + (d.values || []).length, 0) + 1}" style="border-bottom:0;padding:0">${grantDetailHTML(u)}</td></tr>` : ""}`;
    }).join("")}</tbody>
  </table></div>
  <div class="legend">
    <span class="lg"><span class="cellbtn on"></span>${esc(t("access.grants.legend.on"))}</span>
    <span class="lg"><span class="cellbtn"></span>${esc(t("access.grants.legend.off"))}</span>
    <span class="lg"><span class="cellbtn on" style="opacity:.4;outline:1px dashed var(--danger);outline-offset:1px"></span>${esc(t("access.grants.legend.expired"))}</span>
    <span class="lg">${t("access.grants.legend.note")}</span>
  </div>
  <div class="note" style="margin-top:16px;max-width:88ch">
    ${t("access.grants.footNote")}
  </div>
  ${state.dims.some((d) => d.status === "retired") ? `<div class="tiny muted" style="margin-top:8px">${t("access.grants.retiredNote", { dims: state.dims.filter((d) => d.status === "retired").map((d) => esc(d.name)).join(t("common.sep")) })}</div>` : ""}`;
}

/* B① 详细抽屉：ui-1 chips 编辑器（逐行 expires）+ CSV 导入导出迁入 */
function grantDetailHTML(member) {
  const g = state.g;
  return `<div class="upload" style="margin:12px 0;border-radius:var(--r-lg)">
    <div style="grid-column:1/-1;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
      <b style="font-size:15px">${esc(t("access.grants.detailTitle", { user: member }))}</b>
      <span class="tiny muted">${t("access.grants.detailNote")}</span></div>
    <div class="u-row"><label>${esc(t("access.expires.prefill"))}</label>
      <div style="display:flex;gap:8px;align-items:center">
        <input class="inp" data-in="gPrefill" style="width:220px" placeholder="${esc(t("access.expires.ph"))}" value="${esc(g.prefill)}">
        <span class="tiny muted">${esc(t("access.expires.prefillNote"))}</span></div></div>
    ${state.dims.filter((d) => d.status !== "retired").map((dim) => `<div style="grid-column:1/-1">
      <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
        <b>${esc(dim.name)}</b><span class="tiny muted mono">${esc(dim.key)}</span>
        ${dim.required ? `<span class="tag">${esc(t("common.required"))}</span>` : ""}</div>
      <div class="chips" style="margin-top:8px">${(dim.values || []).map((v) => {
        const key = `${dim.key}=${v.value}`;
        const on = key in g.picked;
        const existing = g.existing[key];
        return `<span style="display:inline-flex;gap:6px;align-items:center">
          <button class="vchip ${on ? "on" : ""}" data-act="gCell" data-k="${esc(key)}" title="${existing ? esc(t("access.expires.existing")) + ": " + esc(existing) : ""}">${esc(v.label)}<span class="vx">${esc(v.value)}</span></button>
          ${on ? `<input class="chip-exp" data-in="gExp" data-id="${esc(key)}" placeholder="${esc(t("access.expires.rowPh"))}" value="${esc(g.expires[key] || "")}" title="${esc(t("access.expires.rowTitle"))}">` : ""}
        </span>`;
      }).join("")}</div>
    </div>`).join("")}
    <div class="u-foot">
      <button class="btn seal-btn" data-act="gSave">${esc(t("access.save"))}</button>
      <span class="tiny muted">${esc(t("access.save.note"))}</span>
      <span style="flex:1"></span>
      <button class="btn ghost sm" data-act="gExport">${esc(t("access.export"))}</button>
    </div>
    <div class="lane-h" style="grid-column:1/-1;margin-top:4px"><h3>${esc(t("access.csv.title"))}</h3><span class="tiny muted">${t("access.csv.hint")}</span></div>
    <textarea class="csv-box" data-in="gCsv" placeholder="username,dim_key,value,expires_at" style="grid-column:1/-1">${esc(g.csv)}</textarea>
    <div class="inline-act" style="grid-column:1/-1">
      <button class="btn sm" data-act="gCsvDry">${esc(t("access.csv.dryrun"))}</button>
      <button class="btn seal-btn sm" data-act="gCsvApply">${esc(t("access.csv.apply"))}</button>
      <span class="tiny muted">${esc(g.diffMsg || "")}</span>
    </div>
    ${g.diff ? `<pre class="diff-box" style="grid-column:1/-1">${esc(JSON.stringify(g.diff, null, 2))}</pre>` : ""}
  </div>`;
}

/* ---------- 成员子标签（真端点——m2-6 A3） ---------- */

function membersHTML() {
  if (state.loading.grants && !state.g.rows.length) return loadingHTML("access");
  if (!isAdmin()) return `<div class="note amber">${t("access.grants.needAdmin")}</div>`;
  if (state.g.error) return `<div class="empty" style="margin:0"><h3>${esc(t("access.grants.loadErr", { err: esc(state.g.error) }))}</h3>
    <div style="margin-top:16px"><button class="btn ghost sm" data-act="grantsRetry">${esc(t("common.retry"))}</button></div></div>`;
  const m = state.mem;
  const roster = latticeMembers();
  const now = nowUtcStr();
  return `
  <div style="margin-bottom:12px"><button class="btn ghost sm" data-act="memAddToggle">${m.addOpen ? esc(t("common.collapse")) : esc(t("access.mem.add"))}</button></div>
  ${m.addOpen ? memAddHTML() : ""}
  <table class="ledger">
    <thead><tr><th>${esc(t("access.mem.col.member"))}</th><th>${esc(t("access.mem.col.role"))}</th><th>${esc(t("access.mem.col.membership"))}</th><th class="num">${esc(t("access.mem.col.grants"))}</th><th></th></tr></thead>
    <tbody>${roster.length ? roster.map((u) => {
      const mine = grantRowsOf(u);
      const expRows = mine.filter((r) => r.expiresAt && r.expiresAt <= now).length;
      const known = knownUser(u); // P1-4：会话已知 role/expiresAt（无则不默认代填）
      const row = `<tr>
        <td>${avatar(u)} <b class="t-title">${esc(u)}</b></td>
        <td>${m.roleSel === u
          ? `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
              <select class="sel" data-in="memRoleSel" style="height:26px;width:130px">
                ${m.roleVal ? "" : `<option value="" selected disabled hidden>${esc(t("access.mem.rolePick"))}</option>`}
                <option value="member" ${m.roleVal === "member" ? "selected" : ""}>member</option>
                <option value="org_admin" ${m.roleVal === "org_admin" ? "selected" : ""}>org_admin</option>
              </select>
              <span class="tiny muted">${m.roleVal ? esc(t("access.mem.roleConfirm", { role: esc(m.roleVal) })) : esc(t("access.mem.roleUnknown"))}</span>
              <button class="btn sm" data-act="memRoleOk" data-u="${esc(u)}" ${m.roleVal ? "" : "disabled"}>${esc(t("common.save"))}</button>
              <button class="btn ghost sm" data-act="memRoleCancel">${esc(t("common.cancel"))}</button></div>`
          : `<span class="pill ${known && known.role === "org_admin" ? "ok" : ""}">${esc(known && known.role ? known.role : "—")}</span>
             <button class="btn ghost sm" data-act="memRoleAsk" data-u="${esc(u)}" title="PATCH /members/${esc(u)}">${esc(t("access.mem.changeRole"))}</button>`}</td>
        <td>${m.expAsk === u
          ? `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
              <select class="sel" data-in="memExpMode" style="height:26px;width:110px">
                <option value="set" ${m.expMode !== "perm" ? "selected" : ""}>${esc(t("access.mem.expMode.set"))}</option>
                <option value="perm" ${m.expMode === "perm" ? "selected" : ""}>${esc(t("access.mem.expMode.perm"))}</option>
              </select>
              ${m.expMode === "perm"
                ? `<span class="tiny muted">${esc(t("access.mem.expConfirm", { v: "null" }))}</span>`
                : `<input class="inp" data-in="memExpVal" placeholder="${esc(t("access.mem.expEditPh"))}" value="${esc(m.expVal)}" style="height:26px;width:200px">
                   <span class="tiny muted">${m.expVal.trim() ? esc(t("access.mem.expConfirm", { v: esc(m.expVal.trim()) })) : ""}</span>`}
              <button class="btn sm" data-act="memExpOk" data-u="${esc(u)}" ${m.expMode === "set" && !m.expVal.trim() ? "disabled" : ""}>${esc(t("common.save"))}</button>
              <button class="btn ghost sm" data-act="memExpCancel">${esc(t("common.cancel"))}</button>
            </div>`
          : `<span class="tiny muted">${known && known.expiresAt ? tsHTML(known.expiresAt, "mono tiny") : "—"}</span>
             <button class="link tiny" data-act="memExpAsk" data-u="${esc(u)}" title="PATCH /members/${esc(u)} · ${esc(t("access.mem.expTip"))}">${esc(t("access.mem.changeExp"))}</button>`}</td>
        <td class="num">${mine.length}${expRows ? ` <span class="tag amber" title="${esc(t("access.mem.expGrantsTip"))}">${expRows} ${esc(t("access.mem.expGrants"))}</span>` : ""}</td>
        <td>${m.ask === u ? "" : `<button class="btn ghost sm" data-act="memAsk" data-u="${esc(u)}" style="color:var(--danger)">${esc(t("access.mem.remove"))}…</button>`}</td></tr>`;
      if (m.ask !== u) return row;
      return row + `<tr><td colspan="5" style="border-bottom:0"><div class="confirm">
        <b>${t("access.mem.removeAsk", { user: esc(u) })}</b> ${t("access.mem.removeBody")}
        <div class="cf-act"><button class="btn danger-btn sm" data-act="memDelOk" data-u="${esc(u)}">${esc(t("common.confirm"))}</button>
        <button class="btn ghost sm" data-act="memCancel">${esc(t("common.cancel"))}</button>
        <span class="tiny muted" style="align-self:center"><code>DELETE /api/orgs/${esc(cfg.org)}/members/${esc(u)}</code></span></div></div></td></tr>`;
    }).join("") : `<tr><td colspan="5" class="tiny muted" style="padding:20px 16px">${esc(t("access.mem.empty"))}</td></tr>`}</tbody>
  </table>
  <div class="note" style="margin-top:16px;max-width:92ch">${t("access.mem.footNote")}</div>`;
}

function memAddHTML() {
  const d = state.mem.form;
  return `<div class="upload" style="margin-bottom:16px">
    <div style="grid-column:1/-1"><b style="font-size:15px">${esc(t("access.mem.add"))}</b>
      <span class="tiny muted">—— ${t("access.mem.addNote")}</span></div>
    <div class="u-row"><label>user_id<span class="req">*</span></label>
      <input class="inp" data-in="memNewUid" placeholder="${esc(t("access.mem.uidPh"))}" value="${esc(d.uid)}" style="font-family:var(--mono)"></div>
    <div class="u-row"><label>${esc(t("access.mem.role"))}</label>
      <select class="sel" data-in="memNewRole">
        <option value="member" ${d.role === "member" ? "selected" : ""}>member · ${esc(t("role.member"))}</option>
        <option value="org_admin" ${d.role === "org_admin" ? "selected" : ""}>org_admin · ${esc(t("role.org_admin"))}</option>
      </select></div>
    <div class="u-row"><label>${esc(t("access.mem.expires"))}<span class="tiny muted"> ${esc(t("common.optional"))}</span></label>
      <input class="inp" data-in="memNewExp" placeholder="${esc(t("access.mem.expPh"))}" value="${esc(d.expires)}"></div>
    <div class="u-foot">
      <button class="btn seal-btn" data-act="memCreate" ${d.uid.trim() ? "" : "disabled"}>${esc(t("common.add"))}</button>
      <button class="btn ghost" data-act="memAddToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny muted">${t("access.mem.addFoot")}</span>
    </div></div>`;
}

/* ---------- 可见性矩阵（m3-1 be-①② 实装——m3-2 ui-be 实装：org_admin 逐格
 *           GET explain?user_id=X 取数；前端不演算 ACL〔B5〕，只平铺服务端结论） ---------- */

function visHTML() {
  if (!isAdmin()) {
    return `<div class="note amber">${t("access.grants.needAdmin")}</div>
    <div class="note" style="margin-top:12px;max-width:88ch">${t("access.vis.memberNote")}</div>`;
  }
  const v = state.vis;
  if (v.error) return `<div class="empty" style="margin:0"><h3>${esc(t("access.grants.loadErr", { err: esc(v.error) }))}</h3>
    <div style="margin-top:16px"><button class="btn ghost sm" data-act="visRetry">${esc(t("common.retry"))}</button></div></div>`;
  if (!v.rows) return loadingHTML("access");
  if (!(v.members || []).length || !(v.docs || []).length) {
    return `<div class="empty" style="margin:0"><h3>${esc(t("access.vis.empty.title"))}</h3><p>${t("access.vis.empty.body")}</p></div>`;
  }
  return `
  <div class="lane-h" style="margin-top:4px"><h3>${esc(t("access.vis.title"))}</h3>
    <span class="tiny muted">${t("access.vis.legend.note")}</span></div>
  <table class="lattice vis-lattice">
    <thead>
      <tr><th style="text-align:left;padding-left:14px">${esc(t("access.vis.col.member"))} \\ ${esc(t("access.vis.col.doc"))}</th>
        ${v.docs.map((d) => `<th class="vh dg"><span class="cut" style="max-width:130px;display:inline-block" title="${esc(d.doc_id)}">${esc(d.title || d.doc_id)}</span></th>`).join("")}
      </tr>
    </thead>
    <tbody>${v.members.map((u) => `<tr><th><b style="font-weight:600">${esc(u)}</b></th>
      ${v.docs.map((d) => {
        const cell = v.cells[`${u}|${d.doc_id}`];
        const cls = cell ? (cell.visible ? "ok" : "bad") : "";
        const mark = cell == null ? `<span class="tiny muted">·</span>`
          : cell.visible ? "✓" : "✗";
        return `<td><button class="cellbtn vis-cell ${cls}" data-act="visCell" data-u="${esc(u)}" data-id="${esc(d.doc_id)}"
          title="${esc(u)} · ${esc(d.doc_id)}" aria-label="${esc(u)} × ${esc(d.doc_id)}">${mark}</button></td>`;
      }).join("")}</tr>`).join("")}
    </tbody>
  </table>
  <div class="legend">
    <span class="lg"><span class="cellbtn on"></span>${esc(t("access.vis.legend.visible"))}</span>
    <span class="lg"><span class="cellbtn"></span>${esc(t("access.vis.legend.hidden"))}</span>
    <span class="lg">·</span>
    <span class="lg">${t("access.vis.legend.note")}</span>
  </div>
  ${state.vis.detail ? visDetailHTML(state.vis.detail) : ""}
  <div class="note" style="margin-top:16px;max-width:88ch">${t("access.vis.note")}</div>`;
}

/* 点格下钻：该 (member, doc) 的 explain 行集（逐维度结论——服务端解释） */
function visDetailHTML(detail) {
  return `<div class="pane" style="margin-top:16px;padding:14px 16px">
    <div class="lane-h"><h3>${esc(t("access.vis.detailTitle", { user: detail.user, doc: detail.doc }))}</h3>
      <button class="link tiny" data-act="visDetailClose">${esc(t("common.collapse"))}</button></div>
    ${(detail.rows || []).map((r) => `<div class="explain-row">
      <span>${VERDICT_PILL[r.verdict] || esc(r.verdict || "—")}</span>
      <b>${esc(r.kind === "membership" ? t("docs.vis.membership") : (r.label || r.key || r.kind))}</b>
      <span class="tiny muted">${esc(r.detail || "")}</span>
    </div>`).join("")}
    <div class="tiny" style="margin-top:6px">${detail.visible
      ? `<span class="pill ok">${esc(t("docs.vis.visible"))}</span>`
      : `<span class="pill bad">${esc(t("docs.vis.notVisible"))}</span>`}</div>
  </div>`;
}

/* 矩阵取数（org_admin）：members（GET members 真源）× documents（GET documents）
 * 逐格 GET explain?user_id——并发小批（4）推进，格点落位即渲染（不阻塞整表）。 */
async function loadVisMatrix() {
  const ep = state.epoch;
  state.vis = { rows: false, members: [], docs: [], cells: {}, error: null, detail: null };
  render();
  try {
    const [memBody, docBody] = await Promise.all([
      listMembers(cfg.org), listDocuments(cfg.org),
    ]);
    if (ep !== state.epoch) return;
    state.vis.members = (memBody.members || []).map((m) => m.user_id);
    state.vis.docs = (docBody.documents || []).filter((d) => d.doc_id);
    state.vis.rows = true;
    render();
    // 逐格取数（小批并发——org_admin 面；403/失败格保持 · 未取态）
    const jobs = [];
    for (const u of state.vis.members) {
      for (const d of state.vis.docs) jobs.push([u, d.doc_id]);
    }
    const CONC = 4;
    let idx = 0;
    async function worker() {
      while (idx < jobs.length) {
        const [u, docId] = jobs[idx++];
        try {
          const body = await explainDocument(cfg.org, docId, u);
          if (ep !== state.epoch) return;
          state.vis.cells[`${u}|${docId}`] = {
            visible: !!body.visible, rows: body.rows || [],
          };
        } catch (e) { /* 单格失败保持未取态——不阻断整表 */ }
      }
    }
    await Promise.all(Array.from({ length: CONC }, worker));
    if (ep !== state.epoch) return;
    render();
  } catch (e) {
    if (ep !== state.epoch) return;
    state.vis.error = String((e && e.message) || e);
    render();
  }
}

/* ---------- 维度子标签（ui-1 平移） ---------- */

async function loadGovernanceDims() {
  const ep = state.epoch; // P1-5
  state.loading.govDims = true;
  try {
    const body = await listDimensions(cfg.org);
    if (ep !== state.epoch) return;
    state.dims = body.dimensions || [];
  } finally {
    if (ep === state.epoch) state.loading.govDims = false;
  }
}

function dimsHTML() {
  if (state.loading.govDims) return loadingHTML("access");
  if (!state.dims.length) return `
  <div class="empty" style="margin:0"><h3>${esc(t("access.dims.empty"))}</h3>
    <p>${t("access.dims.emptyBody")}</p>
    ${isAdmin() ? `<div style="margin-top:16px"><button class="btn ghost sm" data-act="dimNewToggle">${state.dimNewOpen ? esc(t("common.collapse")) : esc(t("access.dims.new"))}</button></div>` : ""}
  </div>
  ${state.dimNewOpen && isAdmin() ? dimNewHTML() : ""}`;
  const canEdit = isAdmin();
  return `
  ${canEdit ? `<div style="margin-bottom:12px"><button class="btn ghost sm" data-act="dimNewToggle">${state.dimNewOpen ? esc(t("common.collapse")) : esc(t("access.dims.new"))}</button></div>${state.dimNewOpen ? dimNewHTML() : ""}` : ""}
  ${state.govAsk ? govConfirmHTML() : ""}
  <table class="ledger dims-ledger">
    <thead><tr><th>${esc(t("access.dims.col.dim"))}</th><th>${esc(t("access.dims.col.required"))}</th><th>${esc(t("access.dims.col.values"))}</th><th></th></tr></thead>
    <tbody>${state.dims.map((dim) => `<tr class="${dim.status === "retired" ? "retired" : ""}">
      <td><div class="t-title">${esc(dim.name)}</div><div class="t-sub mono">${esc(dim.key)}</div></td>
      <td>${dim.required ? esc(t("common.yes")) : `<span class="muted">${esc(t("common.no"))}</span>`}<div class="tiny muted">${esc(t("access.dims.reqNote"))}</div></td>
      <td><div class="vals" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">
        ${(dim.values || []).map((v) => `<span style="display:inline-flex;gap:4px;align-items:center">
          <span class="chip d${dimIdx(dim.key)}" title="${esc(v.value)}">${esc(v.label)} <span class="ck">${esc(v.value)}</span></span>
          ${canEdit && dim.status !== "retired" ? `<button class="link tiny" data-act="valOff" data-dim="${esc(dim.id)}" data-id="${esc(v.id)}" data-v="${esc(v.value)}" title="${esc(t("access.dims.disable.hint"))}">${esc(t("access.dims.disable"))}</button>` : ""}
        </span>`).join("") || `<span class="tiny muted">—</span>`}
        ${(state.disabledVals || []).filter((x) => x.dimId === dim.id).map((x) => `<span style="display:inline-flex;gap:4px;align-items:center">
          <span class="chip v-off" title="${esc(x.value)} · ${esc(t("access.dims.disabledTip"))}">${esc(x.label || x.value)}</span>
          ${canEdit ? `<button class="link tiny" data-act="valOn" data-dim="${esc(dim.id)}" data-id="${esc(x.id)}" data-v="${esc(x.value)}" title="${esc(t("access.dims.enable.hint"))}">${esc(t("access.dims.enable"))}</button>` : ""}
        </span>`).join("")}
        ${canEdit && dim.status !== "retired" ? (state.valAsk === dim.id
          ? `<input class="inp" data-in="valKey" placeholder="value" style="height:26px;width:96px;font-family:var(--mono)" value="${esc(state.valNew.v)}"><input class="inp" data-in="valLabel" placeholder="${esc(t("access.dims.valLabelPh"))}" style="height:26px;width:96px" value="${esc(state.valNew.l)}"><button class="btn sm" data-act="valAdd" data-dim="${esc(dim.id)}" title="POST /dimensions/${esc(dim.id)}/values">${esc(t("common.add"))}</button>`
          : `<button class="vchip" data-act="valAsk" data-dim="${esc(dim.id)}" title="POST /dimensions/${esc(dim.id)}/values">＋ ${esc(t("access.dims.addValue"))}</button>`) : ""}
        ${dim.status === "retired" ? `<span class="tiny muted">${esc(t("access.dims.retiredVal"))}</span>` : ""}
      </div></td>
      <td>${dim.status === "active" && canEdit ? `<button class="btn ghost sm" data-act="dimRetire" data-dim="${esc(dim.id)}" data-key="${esc(dim.key)}">${esc(t("access.dims.retire"))}</button>` : dim.status === "retired" ? `<span class="pill idle">${esc(t("access.dims.retiredPill"))}</span>` : ""}</td>
    </tr>`).join("")}</tbody>
  </table>
  <div class="legend" style="margin-top:12px">
    <span class="lg">${t("access.dims.legend.req")}</span>
    <span class="lg">${t("access.dims.legend.filter")}</span>
    <span class="lg">${t("access.dims.legend.disable")}</span>
    <span class="lg">${t("access.dims.legend.restore")}</span>
  </div>`;
}

function dimNewHTML() {
  const d = state.dimNew;
  const ok = d.key.trim().length > 0 && d.name.trim().length > 0;
  return `<div class="upload" style="margin-bottom:16px">
    <div style="grid-column:1/-1"><b style="font-size:15px">${esc(t("access.dims.new"))}</b>
      <span class="tiny muted">—— ${t("access.dims.new.note")}</span></div>
    <div class="u-row"><label>key<span class="req">*</span></label>
      <input class="inp" data-in="dimKey" placeholder="region / biz_line" value="${esc(d.key)}" style="font-family:var(--mono)"></div>
    <div class="u-row"><label>${esc(t("access.dims.col.name"))}<span class="req">*</span></label>
      <input class="inp" data-in="dimName" placeholder="${esc(t("access.dims.namePh"))}" value="${esc(d.name)}"></div>
    <div class="u-row"><label>${esc(t("access.dims.col.required"))}</label>
      <label class="switch"><input type="checkbox" data-in="dimReq" ${d.required ? "checked" : ""}><span class="tiny muted">${esc(t("access.dims.reqNote"))}</span></label></div>
    <div class="u-foot">
      <button class="btn seal-btn" data-act="dimCreate" ${ok ? "" : "disabled"}>${esc(t("common.create"))}</button>
      <button class="btn ghost" data-act="dimNewToggle">${esc(t("common.cancel"))}</button>
      <span class="tiny ${ok ? "" : "muted"}">${ok ? esc(t("access.dims.new.ok")) : esc(t("access.dims.new.need"))}</span>
      <span style="flex:1"></span>
      <span class="tiny muted">${t("access.dims.new.foot")}</span>
    </div></div>`;
}

function govConfirmHTML() {
  const a = state.govAsk;
  const imp = a.impact || {};
  const impactText = a.type === "disable"
    ? `${t("access.dims.impact.docs")}: <b>${esc(imp.docs ?? "—")}</b> · ${t("access.dims.impact.grants")}: <b>${esc(imp.grants ?? "—")}</b> · ${t("access.dims.impact.users")}: <b>${esc(imp.users ?? "—")}</b> · ${t("access.dims.impact.locked")}: <b>${esc(imp.locked_docs ?? "—")}</b>`
    : `${t("access.dims.impact.docs")}: <b>${esc(imp.docs ?? "—")}</b> · ${t("access.dims.impact.grants")}: <b>${esc(imp.grants ?? "—")}</b> · ${t("access.dims.impact.values")}: <b>${esc(imp.values ?? "—")}</b>`;
  // R2 P0：value/key 为后端可控存储值（维度取值/键）——t() 纯插值不转义，参数必须 esc()
  const title = a.type === "disable"
    ? t("access.dims.disable.ask", { value: esc(a.value) })
    : t("access.dims.retire.ask", { key: esc(a.dimKey) });
  return `<div class="confirm"><b>${title}</b> ${a.type === "disable" ? t("access.dims.disable.body") : t("access.dims.retire.body")}
    <div>${impactText}</div>
    <div class="cf-act">
      <button class="btn danger-btn sm" data-act="govOk">${esc(t("common.confirm"))}</button>
      <button class="btn ghost sm" data-act="govCancel">${esc(t("common.cancel"))}</button>
      <span class="tiny muted" style="align-self:center">${a.type === "disable"
        ? `<code>PATCH /dimensions/${esc(a.dimId)}/values/${esc(a.valueId)}</code>`
        : `<code>POST /dimensions/${esc(a.dimId)}/retire?confirm=1</code>`}</span>
    </div></div>`;
}

/* ---------- 视图装配 ---------- */

function viewAccess() {
  if (!connected()) return connGate();
  const sub = state.sub.access;
  const tabs = [
    ["grants", t("access.tab.grants")],
    ["dims", t("access.tab.dims")],
    ["members", t("access.tab.members")],
    ["vis", t("access.tab.vis")],
  ];
  return `
  <header class="head"><h1>${esc(t("access.title"))}</h1>
    <p class="lede">${t("access.lede")}</p>
  </header>
  <nav class="sub-tabs">${tabs.map(([k, l]) => `<button class="sub-tab ${sub === k ? "on" : ""}" data-act="sub" data-s="access" data-v="${k}">${esc(l)}</button>`).join("")}</nav>
  ${!isAdmin() && sub !== "vis" ? `<div class="note amber" style="margin-bottom:16px">${t("access.readonly", { user: esc(lensUser()) })}</div>` : ""}
  ${sub === "grants" ? grantsHTML() : sub === "dims" ? dimsHTML() : sub === "members" ? membersHTML() : visHTML()}`;
}

async function onEnterAccess() {
  if (!connected()) return;
  const sub = state.sub.access;
  if ((sub === "grants" || sub === "members") && isAdmin() && !state.g.rows.length && !state.loading.grants) {
    await loadGrantsTable();
  }
  if (!state.dims.length && !state.loading.govDims) {
    await loadGovernanceDims().catch(() => { /* 已 toast */ });
  }
  // 成员行 role/到期真源补全（GET members——org_admin；失败静默退化会话注册表）
  if (sub === "members" && isAdmin()) await loadMembers();
  // 可见性矩阵懒装载（首次进入 vis 子标签）
  if (sub === "vis" && isAdmin() && state.vis.rows === null) await loadVisMatrix();
}

/* ---------- 动作与输入 ---------- */

function downloadCsv(text) {
  const blob = new Blob([text], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `grants-${cfg.org}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

Object.assign(actions, {
  /* ----- 授权格：点格 = 全量替换该成员 local 行 ----- */
  async latCell(el) {
    const u = el.dataset.u, k = el.dataset.k, v = el.dataset.v;
    const mine = grantRowsOf(u);
    const hit = mine.find((r) => r.dimKey === k && r.value === v);
    // 目标集 = 现有 local 行集 ∪/− 被点格；expires 沿库内、新授权 null
    const grants = (hit
      ? mine.filter((r) => r !== hit)
      : mine.concat([{ dimKey: k, value: v, expiresAt: "" }]))
      .map((r) => ({ dim_key: r.dimKey, value: r.value, expires_at: r.expiresAt || null }));
    state.g.saving = u + "|" + k + "=" + v;
    render();
    try {
      const res = await putGrants(cfg.org, u, grants);
      const set = grants.filter((x) => x.dim_key === k).map((x) => x.value);
      toast(t("access.grants.put", {
        user: esc(u), dim: esc(k), set: esc(set.join(t("common.sep"))) || "∅",
        removed: res.removed, inserted: res.inserted,
      }));
    } catch (e) {
      errToast(e);
      state.g.saving = "";
      return false;
    }
    await loadGrantsTable();
    state.g.saving = "";
    render();
    const nb = document.querySelector(`[data-act="latCell"][data-u="${CSS.escape(u)}"][data-k="${CSS.escape(k)}"][data-v="${CSS.escape(v)}"]`);
    if (nb) nb.classList.add("pop");
    return false;
  },
  latDetail(el) {
    const u = el.dataset.u;
    if (state.g.detail === u) {
      state.g.detail = null;
    } else {
      state.g.detail = u;
      seedGrantEditor(u);
      state.g.diff = null; state.g.diffMsg = "";
    }
  },

  /* ----- 详细抽屉内 ui-1 chips 编辑器（B① 逐行 expires） ----- */
  gCell(el) {
    const key = el.dataset.k;
    if (key in state.g.picked) {
      delete state.g.picked[key];
      delete state.g.expires[key];
    } else {
      state.g.picked[key] = "";
      // 新选行预填：全局输入框值优先（显式意图），否则库内既有值
      state.g.expires[key] = state.g.prefill.trim() || state.g.existing[key] || "";
    }
  },
  async gSave() {
    const member = state.g.member;
    if (!member) return false;
    // B①：逐行独立 expires——每行取自身输入框值（初始值=库内值；空=永久）
    const grants = Object.keys(state.g.picked).map((k) => {
      // R2 P2-5：按首个 = 分割——取值本身可含 =（split("=") 会截断）
      const eq = k.indexOf("=");
      const dimKey = k.slice(0, eq), value = k.slice(eq + 1);
      const expires = state.g.expires[k] ?? state.g.existing[k] ?? "";
      return { dim_key: dimKey, value, expires_at: expires || null };
    });
    try {
      const res = await putGrants(cfg.org, member, grants);
      toast(t("access.saved", { removed: res.removed, inserted: res.inserted }));
    } catch (e) { errToast(e); return false; }
    await loadGrantsTable();
    if (state.g.detail) seedGrantEditor(state.g.detail);
    render();
    return false;
  },
  async gExport() {
    try {
      const text = await exportGrants(cfg.org);
      downloadCsv(text);
    } catch (e) { errToast(e); }
    return false;
  },
  async gCsvDry() { return importCsvRun(true); },
  async gCsvApply() { return importCsvRun(false); },

  /* ----- 成员三方法（真端点——服务端守卫如实回显） ----- */
  memAddToggle() {
    state.mem.addOpen = !state.mem.addOpen;
    state.mem.form = { uid: "", role: "member", expires: "" };
  },
  async memCreate() {
    const d = state.mem.form;
    const uid = d.uid.trim();
    if (!uid) return false;
    let body;
    try {
      body = await addMember(cfg.org, {
        user_id: uid, role: d.role, expires_at: d.expires.trim() || null,
      });
    } catch (e) {
      if (e.status === 404) toast(t("access.mem.add404", { user: esc(uid) }));
      else if (e.status === 409) toast(t("access.mem.add409", { user: esc(uid) }));
      else errToast(e);
      return false;
    }
    // P1-3：201 响应 {user_id, role, expires_at} 入会话注册表——零授权新成员立即可见
    // （expires_at 为 null=永久是合法值——仅 undefined 才回退表单值）
    setKnownUser(body.user_id || uid, {
      role: body.role !== undefined ? body.role : d.role,
      expiresAt: body.expires_at !== undefined ? body.expires_at : (d.expires.trim() || null),
    });
    toast(t("access.mem.added", { user: esc(body.user_id || uid), role: esc(body.role || d.role) }));
    state.mem.addOpen = false;
    state.mem.form = { uid: "", role: "member", expires: "" };
    state.usernames = [...new Set([...state.usernames, body.user_id || uid])].sort();
    await loadGrantsTable();
    render();
    return false;
  },
  memRoleAsk(el) {
    const u = el.dataset.u;
    state.mem.roleSel = u;
    // P1-4：会话已知 role 预选；未知则空选项 + 保存禁用——不默认代填 member
    const known = knownUser(u);
    state.mem.roleVal = known && known.role ? known.role : "";
    state.mem.ask = null;
  },
  memRoleCancel() { state.mem.roleSel = null; },
  async memRoleOk(el) {
    const u = el.dataset.u;
    const role = state.mem.roleVal;
    if (!role) return false; // 未知当前角色时必须显式选择（P1-4）
    let body;
    try {
      body = await patchMember(cfg.org, u, { role }); // 单字段发送（键缺失=不变不受影响）
    } catch (e) {
      if (e.status === 409) toast(t("access.mem.patch409", { user: esc(u) }));
      else if (e.status === 404) toast(t("access.mem.patch404", { user: esc(u) }));
      else errToast(e);
      return false;
    }
    // PATCH 回整行 {user_id, role, expires_at}——null=永久为合法值，仅 undefined 回退旧值
    const prevRole = knownUser(u) || {};
    setKnownUser(u, {
      role: body.role !== undefined ? body.role : (prevRole.role ?? role),
      expiresAt: body.expires_at !== undefined ? body.expires_at : (prevRole.expiresAt ?? null),
    });
    toast(t("access.mem.roleSet", { user: esc(u), role: esc(body.role || role) }));
    state.mem.roleSel = null;
    await loadGrantsTable();
    render();
    return false;
  },
  memExpAsk(el) {
    const u = el.dataset.u;
    state.mem.expAsk = u;
    // P1-4：显式二选一（设时点 / 改永久）——known 有值则预填；不再隐式空串=永久
    const known = knownUser(u);
    state.mem.expVal = known && known.expiresAt ? known.expiresAt : "";
    state.mem.expMode = "set";
    state.mem.ask = null;
  },
  memExpCancel() { state.mem.expAsk = null; },
  async memExpOk(el) {
    const u = el.dataset.u;
    const m = state.mem;
    let value;
    if (m.expMode === "perm") value = null;              // 显式改永久
    else { value = m.expVal.trim(); if (!value) return false; } // 设时点必须非空（禁用隐式空=永久）
    let body;
    try {
      body = await patchMember(cfg.org, u, { expires_at: value }); // 键显式出现（null=改永久）
    } catch (e) {
      if (e.status === 409) toast(t("access.mem.patch409", { user: esc(u) }));
      else if (e.status === 404) toast(t("access.mem.patch404", { user: esc(u) }));
      else errToast(e);
      return false;
    }
    const prevExp = knownUser(u) || {};
    setKnownUser(u, {
      role: body.role !== undefined ? body.role : (prevExp.role ?? null),
      expiresAt: body.expires_at !== undefined ? body.expires_at : null, // 本动作显式改 expires
    });
    toast(t("access.mem.expSet", { user: esc(u), v: esc(body.expires_at == null ? "null" : body.expires_at) }));
    state.mem.expAsk = null;
    render();
    return false;
  },
  memAsk(el) { state.mem.ask = el.dataset.u; state.mem.expAsk = null; state.mem.roleSel = null; },
  memCancel() { state.mem.ask = null; },
  async memDelOk(el) {
    const u = el.dataset.u;
    try {
      await deleteMember(cfg.org, u); // R2 P1-1：!ok 抛 ApiError（204 空 body 正常返回）
    } catch (e) {
      if (e.status === 409) toast(t("access.mem.del409", { user: esc(u) }));
      else if (e.status === 404) toast(t("access.mem.patch404", { user: esc(u) }));
      else errToast(e); // 403/500 等如实 toast（api.js 已 toast 403 detail）
      return false; // 失败不删行、不收起确认条
    }
    dropKnownUser(u); // P1-3：会话注册表移除
    toast(t("access.mem.deleted", { user: esc(u) }));
    state.mem.ask = null;
    if (state.g.detail === u) state.g.detail = null;
    await loadGrantsTable();
    render();
    return false;
  },
  /* P2-3：授权导出装载失败后的显式重试（grants/members 两子标签共用） */
  async grantsRetry() {
    await loadGrantsTable();
    render();
    return false;
  },

  /* ----- 可见性矩阵（m3-2 ui-be：org_admin 逐格取数） ----- */
  async visRetry() {
    await loadVisMatrix();
    return false;
  },
  visCell(el) {
    const u = el.dataset.u, docId = el.dataset.id;
    const cell = state.vis.cells[`${u}|${docId}`];
    if (!cell) {
      // 未取格（单格失败面）——点按单格重取
      explainDocument(cfg.org, docId, u).then((body) => {
        state.vis.cells[`${u}|${docId}`] = {
          visible: !!body.visible, rows: body.rows || [],
        };
        state.vis.detail = { user: u, doc: docId, rows: body.rows || [], visible: !!body.visible };
        render();
      }).catch((e) => errToast(e));
      return false;
    }
    state.vis.detail = { user: u, doc: docId, ...cell };
    render();
    return false;
  },
  visDetailClose() { state.vis.detail = null; },

  /* ----- 维度治理（ui-1 平移） ----- */
  dimNewToggle() { state.dimNewOpen = !state.dimNewOpen; },
  async dimCreate() {
    const d = state.dimNew;
    const key = d.key.trim(), label = d.name.trim();
    if (!key || !label) return false;
    let body;
    try {
      // m3-2 ui-be 对账：真契约 {key, label, required?}（m3-1 #13 实装——
      // label=显示名；表单「名称」作 label）
      body = await createDimension(cfg.org, { key, label, required: !!d.required });
    } catch (e) {
      if (e.status === 409) toast(esc(String(e.message || "")));
      else errToast(e);
      return false;
    }
    state.dimNewOpen = false;
    state.dimNew = { key: "", name: "", required: false };
    toast(t("access.dims.created", { key: esc(key) }));
    await loadGovernanceDims();
    render();
    return false;
  },
  valAsk(el) {
    const dim = el.dataset.dim;
    state.valAsk = state.valAsk === dim ? null : dim;
    state.valNew = { v: "", l: "" };
  },
  async valAdd(el) {
    const dimId = el.dataset.dim;
    const v = state.valNew.v.trim(), l = state.valNew.l.trim();
    if (!v) { toast(esc(t("access.dims.valNeed"))); return false; }
    try {
      await createValue(cfg.org, dimId, { value: v, label: l || null }); // retired 409 → api 统一语义
    } catch (e) {
      if (e.status === 409) toast(t("access.dims.val409", { v: esc(v) }));
      else errToast(e);
      return false;
    }
    state.valNew = { v: "", l: "" };
    toast(t("access.dims.valAdded", { v: esc(v) }));
    await loadGovernanceDims();
    render();
    return false;
  },
  async valOff(el) {
    const dimId = el.dataset.dim, valueId = el.dataset.id, value = el.dataset.v;
    let body;
    try {
      body = await patchValueStatus(cfg.org, dimId, valueId, { status: "disabled", dry_run: true });
    } catch (e) { errToast(e); return false; }
    state.govAsk = { type: "disable", dimId, valueId, value, impact: body.impact };
    render();
    return false;
  },
  async valOn(el) {
    const dimId = el.dataset.dim, valueId = el.dataset.id;
    try {
      await patchValueStatus(cfg.org, dimId, valueId, { status: "active" }); // D19 恢复路径
    } catch (e) { errToast(e); return false; }
    state.disabledVals = (state.disabledVals || []).filter((x) => x.id !== valueId);
    toast(t("access.dims.enabled"));
    await loadGovernanceDims();
    render();
    return false;
  },
  async dimRetire(el) {
    const dimId = el.dataset.dim, dimKey = el.dataset.key;
    let body;
    try {
      body = await retireDimension(cfg.org, dimId, false); // 无 confirm = 影响面预估
    } catch (e) { errToast(e); return false; }
    state.govAsk = { type: "retire", dimId, dimKey, impact: body.impact };
    render();
    return false;
  },
  govCancel() { state.govAsk = null; },
  async govOk() {
    const a = state.govAsk;
    if (!a) return false;
    state.govAsk = null;
    try {
      if (a.type === "disable") {
        await patchValueStatus(cfg.org, a.dimId, a.valueId, { status: "disabled" });
        const dim = state.dims.find((d) => d.id === a.dimId);
        const val = dim && (dim.values || []).find((v) => v.id === a.valueId);
        state.disabledVals = state.disabledVals || [];
        state.disabledVals.push({ dimId: a.dimId, id: a.valueId, value: a.value, label: val ? val.label : a.value });
        toast(t("access.dims.disabled", { v: esc(a.value) }));
      } else {
        await retireDimension(cfg.org, a.dimId, true);
        toast(t("access.dims.retired", { key: esc(a.dimKey) }));
      }
    } catch (e) { errToast(e); }
    await loadGovernanceDims();
    render();
    return false;
  },
});

async function importCsvRun(dryRun) {
  const text = state.g.csv.trim();
  if (!text) { toast(esc(t("access.csv.empty"))); return false; }
  let body;
  try {
    body = await importGrants(cfg.org, text, dryRun);
  } catch (e) { errToast(e); return false; }
  if (dryRun) {
    const d = body.diff;
    state.g.diff = d;
    state.g.diffMsg = t("access.csv.diffMsg", { a: d.added.length, r: d.removed.length, c: d.changed.length, j: (body.rejected || []).length });
  } else {
    state.g.diff = null;
    state.g.diffMsg = "";
    toast(t("access.csv.applied", { users: body.applied_users, rejected: (body.rejected || []).length }));
    await loadGrantsTable();
    if (state.g.detail) seedGrantEditor(state.g.detail);
  }
  render();
  return false;
}

Object.assign(INPUTS, {
  gPrefill: (v) => { state.g.prefill = v; },
  gExp: (v, el) => { state.g.expires[el.dataset.id] = v.trim(); return false; },
  gCsv: (v) => { state.g.csv = v; return false; },
  memNewUid: (v) => { state.mem.form.uid = v; },
  memNewRole: (v) => { state.mem.form.role = v; },
  memNewExp: (v) => { state.mem.form.expires = v; },
  /* P1-4：选择/输入即重渲染——确认行（role := X / expires_at := v）随动明示目标值 */
  memRoleSel: (v) => { state.mem.roleVal = v; },
  memExpVal: (v) => { state.mem.expVal = v; },
  memExpMode: (v) => { state.mem.expMode = v; },
  dimKey: (v) => { state.dimNew.key = v; },
  dimName: (v) => { state.dimNew.name = v; },
  dimReq: (v) => { state.dimNew.required = v; },
  valKey: (v) => { state.valNew.v = v; },
  valLabel: (v) => { state.valNew.l = v; },
});

VIEWS.access = { render: viewAccess, onEnter: onEnterAccess };

/* 子标签切换也走懒装载（onEnter 只覆盖整视图进入——首切「授权/成员/矩阵」时补载） */
const _subBase = actions.sub;
actions.sub = (el) => {
  _subBase(el);
  const s = el.dataset.s, v = el.dataset.v;
  if (s === "access" && (v === "grants" || v === "members")
      && isAdmin() && !state.g.rows.length && !state.loading.grants) {
    loadGrantsTable().then(() => render()).catch(() => { /* 已 toast */ });
  }
  if (s === "access" && v === "members" && isAdmin()) {
    loadMembers().then(() => render()).catch(() => {});
  }
  if (s === "access" && v === "vis" && isAdmin() && state.vis.rows === null) {
    loadVisMatrix().catch(() => { /* 错误态已在 loadVisMatrix 呈现 */ });
  }
};
