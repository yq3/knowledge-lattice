/* views/mcp.js —— MCP 接入指南页（VIEWS.mcp）。
 * 定位：把 docs/MCP-INTEGRATION.md 的**用户面**搬进控制台——用户不必进代码仓。
 * 与文档的分工：本页 = 在自己环境里把 agent 连起来所需的最短闭环（端点/凭据/
 * 客户端片段/工具清单/上传三步/排错/安全）；文档 = 仓内长尾（MCP Inspector、
 * sso 委托细节、源码与用例指针）。代码片段/命令/JSON 不做翻译——中英共用一份
 * （MCP_SNIPPETS），i18n 只覆盖说明文字。
 * 形态分支（D25/D26）：local = Agent Key 路径（签发在「Agent 密钥」页）；
 * sso = D18 委托 token 路径（agent key 在 sso 形态 404/401，不能照搬）。
 * 工具清单为静态表，但 tests/test_mcp_guide_page.py 断言其与 mcp/server.py 的
 * @mcp.tool 注册集合相等——加/删工具未同步本页即测试红。
 * 动态值（端点/组织）取运行时真实值：location.origin + /mcp、cfg.org。 */
"use strict";

/* 工具清单（与 mcp/server.py 注册名一一对应——顺序即 docs/MCP-INTEGRATION.md §5）。
 * [工具名, i18n 用途键, 主要参数（技术串，不译）] */
const MCP_TOOLS = [
  ["search", "mcpPage.tool.search", "query, top_k=8, datasets?, doc_filter?, entities?"],
  ["fetch", "mcpPage.tool.fetch", "chunk_id, window=2"],
  ["upload", "mcpPage.tool.upload", "upload_id, dataset, dimensions, doc_id?, title?"],
  ["list_documents", "mcpPage.tool.list_documents", "datasets?, active_status?, limit=50"],
  ["annotate", "mcpPage.tool.annotate", "text, context_entities?, prefer_types?, fuzzy=false"],
  ["get_entity", "mcpPage.tool.get_entity", "id?, key?, expand?, depth=1, fanout_limit=50"],
  ["search_entities", "mcpPage.tool.search_entities", "q, types?, top_k=10"],
  ["describe_table", "mcpPage.tool.describe_table", "table, columns?"],
];

function mcpIsLocal() { return AUTH.mode === "local"; }
function mcpEndpoint() { return location.origin + "/mcp"; }

/* 代码片段单一来源（中英共用；key 见 data-k）。占位 key 用 lka_xxxxxxxx...，
 * sso 形态用 <delegated-token>——提示用户替换，绝不写真实 key。 */
function mcpSnippets() {
  const ep = mcpEndpoint();
  const ent = {
    claudeCode: [
      "claude mcp add --transport http knowledge-lattice \\",
      `  ${ep} \\`,
      '  --header "Authorization: Bearer lka_xxxxxxxx..."',
      "",
      "# 查看 / 删除",
      "claude mcp list",
      "claude mcp remove knowledge-lattice",
    ].join("\n"),
    desktop: JSON.stringify({
      mcpServers: {
        "knowledge-lattice": {
          type: "http",
          url: ep,
          headers: { Authorization: "Bearer lka_xxxxxxxx..." },
        },
      },
    }, null, 2),
    python: [
      "from fastmcp import Client",
      "from fastmcp.client.transports import StreamableHttpTransport",
      "",
      `URL = "${ep}"`,
      'KEY = "lka_xxxxxxxx..."  # 从环境变量或密钥管理读取',
      "",
      "async def main() -> None:",
      "    transport = StreamableHttpTransport(",
      "        url=URL, headers={\"Authorization\": f\"Bearer {KEY}\"})",
      "    async with Client(transport) as client:",
      "        tools = await client.list_tools()",
      "        print([t.name for t in tools])",
      "        await client.call_tool(",
      '            "search", {"query": "增值税留抵退税", "top_k": 5})',
    ].join("\n"),
    bridge: JSON.stringify({
      mcpServers: {
        "knowledge-lattice": {
          command: "npx",
          args: ["-y", "mcp-remote", ep, "--header", "Authorization: Bearer lka_xxxxxxxx..."],
        },
      },
    }, null, 2),
    sso: JSON.stringify({
      mcpServers: {
        "knowledge-lattice": {
          type: "http",
          url: ep,
          headers: { Authorization: "Bearer <delegated-token>" },
        },
      },
    }, null, 2),
    upload: [
      "# ① 声明并拿 upload_id（同一把 agent key）",
      `curl -s -X POST ${location.origin}/api/uploads \\`,
      '  -H "Authorization: Bearer lka_xxxxxxxx..." \\',
      "  -H 'content-type: application/json' \\",
      `  -d '{"filename":"vat.html","size":1234,"sha256":"<64位小写hex>","content_type":"text/html"}'`,
      "",
      "# ② PUT 字节到返回的 upload_url（同一把 key）",
      `curl -s -X PUT ${location.origin}/api/uploads/<upload_id> \\`,
      '  -H "Authorization: Bearer lka_xxxxxxxx..." \\',
      "  --data-binary @vat.html",
      "",
      "# ③ MCP tool: upload(upload_id=..., dataset=..., dimensions={...}, title=...)",
    ].join("\n"),
  };
  return ent;
}

function mcpCopyBtn(k) {
  return `<button class="btn ghost sm" data-act="mcpCopy" data-k="${esc(k)}">${esc(t("mcpPage.copy"))}</button>`;
}

/* 代码面板：卡头皮（标题 + 复制）+ 代码体。.sql 既有代码块样式复用。 */
function mcpCodeBlock(k, titleKey) {
  const text = mcpSnippets()[k] || "";
  return `<div class="mcp-code">
    <div class="mcp-code-h"><span>${esc(t(titleKey))}</span>${mcpCopyBtn(k)}</div>
    <pre class="sql">${esc(text)}</pre>
  </div>`;
}

function mcpBullets(keys) {
  return `<ul class="mcp-bullets">${keys.map((k) => `<li>${t(k)}</li>`).join("")}</ul>`;
}

/* 分区卡：与运维页共用 .card + .lane-h（卡头带序号圆标，标题与正文以分隔线断开）。
 * 序号由渲染顺序生成（sso 形态没有「上传」，写死编号会出现跳号）。 */
function mcpSec(n, titleKey, bodyHTML, hint) {
  return `<section class="card mcp-sec">
    <div class="lane-h">
      <span class="mcp-n">${n}</span>
      <h3>${esc(t(titleKey))}</h3>
      ${hint ? `<span class="mcp-sec-hint">${esc(hint)}</span>` : ""}
    </div>
    ${bodyHTML}
  </section>`;
}

/* ---------- 分区片段 ---------- */

function mcpBasicsHTML() {
  const cred = mcpIsLocal() ? t("mcpPage.cred.local") : t("mcpPage.cred.sso");
  return `<dl class="mcp-kv">
    <div class="mcp-kv-row"><dt>${esc(t("mcpPage.endpoint"))}</dt>
      <dd><code>${esc(mcpEndpoint())}</code>${mcpCopyBtn("endpoint")}</dd></div>
    <div class="mcp-kv-row"><dt>${esc(t("mcpPage.cred"))}</dt><dd>${esc(cred)}</dd></div>
    <div class="mcp-kv-row"><dt>${esc(t("mcpPage.org"))}</dt><dd>${esc(cfg.org || "—")}</dd></div>
    <div class="mcp-kv-row"><dt>${esc(t("mcpPage.transport"))}</dt><dd>Streamable HTTP</dd></div>
  </dl>
  <p class="mcp-hint">${t("mcpPage.transportHint")}</p>`;
}

/* local：Agent Key 签发路径（admin 可直达签发页；member 给申请口径）。 */
function mcpKeyHTML() {
  const admin = !!(AUTH.user && (AUTH.user.is_system_admin || isAdmin()));
  const cta = admin
    ? `<button class="btn seal-btn sm" data-act="view" data-v="agent_keys">${esc(t("mcpPage.key.go"))}</button>`
    : `<span class="mcp-hint">${esc(t("mcpPage.key.member"))}</span>`;
  return `<ol class="mcp-steps">
      <li>${t("mcpPage.key.step1")}</li>
      <li>${t("mcpPage.key.step2")}</li>
      <li>${t("mcpPage.key.step3")}</li>
    </ol>
    <div class="mcp-row">${cta}</div>
    <div class="note amber">${t("mcpPage.key.warn")}</div>`;
}

/* sso：D18 委托/可信凭据（无 agent key）。 */
function mcpSsoHTML() {
  return `${mcpBullets(["mcpPage.sso.b1", "mcpPage.sso.b2", "mcpPage.sso.b3"])}
    <div class="note amber">${t("mcpPage.sso.warn")}</div>`;
}

function mcpOrgHTML() {
  return mcpBullets(["mcpPage.org.b1", "mcpPage.org.b2", "mcpPage.org.b3", "mcpPage.org.b4", "mcpPage.org.b5"]);
}

function mcpClientsHTML() {
  if (!mcpIsLocal()) {
    return `<p class="mcp-hint">${t("mcpPage.clients.ssoHint")}</p>
      ${mcpCodeBlock("sso", "mcpPage.client.sso")}`;
  }
  /* 竖排一段一种配置：命令行（CLI）→ 代码（Python）→ JSON 配置文件（Desktop，
   * 其余 JSON 客户端同构改用此片段）→ stdio 桥接兜底。不做双列混排（用户
   * 2026-11-22：子卡片保持竖排，不要混着排列）。 */
  return `<p class="mcp-hint">${t("mcpPage.clients.hint")}</p>
    <div class="mcp-clients">
      ${mcpCodeBlock("claudeCode", "mcpPage.client.claudeCode")}
      ${mcpCodeBlock("python", "mcpPage.client.python")}
      ${mcpCodeBlock("desktop", "mcpPage.client.desktop")}
      ${mcpCodeBlock("bridge", "mcpPage.client.bridge")}
    </div>`;
}

function mcpToolsHTML() {
  const rows = MCP_TOOLS.map(([name, descKey, params]) => `<div class="mcp-row-item">
      <code class="mcp-name">${esc(name)}</code>
      <span>${esc(t(descKey))}</span>
      <code class="mcp-args">${esc(params)}</code>
    </div>`).join("");
  return `<div class="mcp-rows mcp-tools">
      <div class="mcp-row-head">
        <span>${esc(t("mcpPage.tools.col.name"))}</span>
        <span>${esc(t("mcpPage.tools.col.purpose"))}</span>
        <span>${esc(t("mcpPage.tools.col.params"))}</span>
      </div>
      ${rows}
    </div>
    <p class="mcp-hint">${t("mcpPage.tools.note")}</p>`;
}

function mcpUploadHTML() {
  return `${mcpCodeBlock("upload", "mcpPage.upload.title")}
    ${mcpBullets(["mcpPage.upload.b1", "mcpPage.upload.b2"])}`;
}

/* 排错表：现象（技术串，不译）+ 处理（i18n）。 */
const MCP_TROUBLE = [
  ["401: missing Bearer token", "mcpPage.tr.b1"],
  ["401: invalid agent key", "mcpPage.tr.b2"],
  ["401: agent key revoked", "mcpPage.tr.b3"],
  ["401: agent key 仅 local 形态可用", "mcpPage.tr.b4"],
  ["400: org ... 不一致", "mcpPage.tr.b5"],
  ["403: org disabled", "mcpPage.tr.b6"],
  ["403: ... membership_denied", "mcpPage.tr.b7"],
  ["连接被拒 / 超时", "mcpPage.tr.b8"],
  ["工具 60s 超时", "mcpPage.tr.b9"],
  ["客户端没有 headers 选项", "mcpPage.tr.b10"],
];

function mcpTroubleHTML() {
  const rows = MCP_TROUBLE.map(([sym, fixKey]) => `<div class="mcp-row-item">
      <code class="mcp-sym">${esc(sym)}</code>
      <span>${esc(t(fixKey))}</span>
    </div>`).join("");
  return `<div class="mcp-rows mcp-trouble">
      <div class="mcp-row-head">
        <span>${esc(t("mcpPage.trouble.col.sym"))}</span>
        <span>${esc(t("mcpPage.trouble.col.fix"))}</span>
      </div>
      ${rows}
    </div>`;
}

function mcpSecurityHTML() {
  return mcpBullets(["mcpPage.sec.b1", "mcpPage.sec.b2", "mcpPage.sec.b3", "mcpPage.sec.b4"]);
}

/* ---------- 视图 ---------- */

function viewMcp() {
  const local = mcpIsLocal();
  let n = 0;
  const sec = (titleKey, bodyHTML, hint) => mcpSec(++n, titleKey, bodyHTML, hint);
  return `<div id="mcp-guide" class="mcp-guide">
    <header class="head">
      <h1>${esc(t("mcpPage.title"))}</h1>
      <p class="lede">${t(local ? "mcpPage.lede.local" : "mcpPage.lede.sso")}</p>
      <div class="head-act"><span class="tag ${local ? "moss" : ""}">${esc(t(local ? "mcpPage.mode.local" : "mcpPage.mode.sso"))}</span></div>
    </header>
    ${sec("mcpPage.sec.basics", mcpBasicsHTML())}
    ${local ? sec("mcpPage.sec.key", mcpKeyHTML()) : sec("mcpPage.sec.key", mcpSsoHTML())}
    ${sec("mcpPage.sec.org", mcpOrgHTML())}
    ${sec("mcpPage.sec.clients", mcpClientsHTML())}
    ${sec("mcpPage.sec.tools", mcpToolsHTML(), t("mcpPage.tools.count", { n: MCP_TOOLS.length }))}
    ${local ? sec("mcpPage.sec.upload", mcpUploadHTML(), t("mcpPage.upload.hint")) : ""}
    ${sec("mcpPage.sec.trouble", mcpTroubleHTML())}
    ${sec("mcpPage.sec.security", mcpSecurityHTML())}
    <div class="tiny muted mcp-foot">${t("mcpPage.foot")}</div>
  </div>`;
}

/* ---------- 动作 ---------- */

Object.assign(actions, {
  async mcpCopy(el) {
    const k = el.dataset.k;
    const text = k === "endpoint" ? mcpEndpoint() : (mcpSnippets()[k] || "");
    if (!text) return false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        toast(esc(t("mcpPage.copied")));
        return false;
      }
    } catch (e) { /* 剪贴板不可用（非安全上下文等）→ prompt 兜底 */ }
    window.prompt(t("mcpPage.copyPrompt"), text);
    return false;
  },
});

VIEWS.mcp = { render: viewMcp };
