/* i18n 机制（FR-8 / design §5.7）：静态字典 zh/en + t(key, params) + data-i18n。
 * - 无 i18n 框架、无构建链（薄壳纪律）；只译 UI 文案，业务数据不译；
 * - 头部「中 | EN」切换 + localStorage 持久化，默认中文（浏览器 locale 不作强制）；
 * - <html lang>（zh-CN / en）与 <title> 随切换同步（TC-UI-01）；
 * - 服务端不感知语言（请求不带语言参数——FR-8）。
 */
"use strict";

const I18N = {
  zh: {
    "app.title": "知识库薄壳",
    "app.subtitle": "上传 / 检索最小闭环 · API 契约先行",
    "nav.upload": "文档上传",
    "nav.search": "检索测试",
    "nav.hint": "M0a 页壳：两视图",
    "settings.title": "连接设置",
    "settings.token": "Bearer Token",
    "settings.token.ph": "开发 JWT（POST /api/dev/token 签发）",
    "settings.org": "组织 X-Org-Id",
    "settings.org.ph": "如 org:tax",
    "settings.save": "保存",
    "upload.title": "文档上传",
    "upload.lede": "multipart 直传：维度值须在你的授权内（M0a；agent 凭证三步随 M1）。",
    "upload.dataset": "知识库",
    "upload.dataset.none": "（先加载知识库）",
    "upload.file": "文件",
    "upload.dims": "文档维度",
    "upload.dims.hint": "必选维度至少选一值；不选 = 空值放行",
    "upload.submit": "上传",
    "upload.required": "必选",
    "upload.ok": "已入队",
    "upload.empty": "本组织还没有知识库。",
    "search.title": "检索测试",
    "search.lede": "BM25 单路（M0a）——与 MCP search 同一条管线、同一套维度过滤。",
    "search.q.ph": "问一个业务问题……",
    "search.go": "检索",
    "search.dataset": "知识库",
    "search.all": "全部可见",
    "search.results": "命中",
    "search.col.rank": "#",
    "search.col.chunk": "chunk_id",
    "search.col.doc": "文档",
    "search.col.page": "页/sheet",
    "search.col.score": "score",
    "search.col.dims": "维度",
    "search.col.source": "来源",
    "search.empty": "没有可见结果——换个说法，或检查 token / 组织。",
    "search.denied": "403：成员关系无效或无授权。",
    "status.title": "任务与文档状态",
    "status.doc": "文档",
    "status.task": "任务",
    "status.active": "在用",
    "status.pending": "处理中",
    "status.refresh": "刷新",
    "footer.note": "服务端不感知语言；语言仅为前端状态（localStorage）。",
  },
  en: {
    "app.title": "Knowledge Lattice Shell",
    "app.subtitle": "Minimal upload / search loop · API contract first",
    "nav.upload": "Upload",
    "nav.search": "Search Test",
    "nav.hint": "M0a shell: two views",
    "settings.title": "Connection",
    "settings.token": "Bearer Token",
    "settings.token.ph": "Dev JWT (issue via POST /api/dev/token)",
    "settings.org": "Org X-Org-Id",
    "settings.org.ph": "e.g. org:tax",
    "settings.save": "Save",
    "upload.title": "Upload Document",
    "upload.lede": "Multipart upload: dimension values must be within your grants (M0a; agent 3-step credentials in M1).",
    "upload.dataset": "Dataset",
    "upload.dataset.none": "(load datasets first)",
    "upload.file": "File",
    "upload.dims": "Document dimensions",
    "upload.dims.hint": "Required dimensions need at least one value; empty = pass-through for everyone",
    "upload.submit": "Upload",
    "upload.required": "required",
    "upload.ok": "queued",
    "upload.empty": "No datasets in this org yet.",
    "search.title": "Search Test",
    "search.lede": "BM25 single route (M0a) — same pipeline and dimension ACL as MCP search.",
    "search.q.ph": "Ask a business question…",
    "search.go": "Search",
    "search.dataset": "Dataset",
    "search.all": "All visible",
    "search.results": "hits",
    "search.col.rank": "#",
    "search.col.chunk": "chunk_id",
    "search.col.doc": "Document",
    "search.col.page": "Page/Sheet",
    "search.col.score": "score",
    "search.col.dims": "Dims",
    "search.col.source": "Source",
    "search.empty": "No visible results — rephrase, or check token / org.",
    "search.denied": "403: membership invalid or no grants.",
    "status.title": "Task & Document Status",
    "status.doc": "Document",
    "status.task": "Task",
    "status.active": "active",
    "status.pending": "pending",
    "status.refresh": "Refresh",
    "footer.note": "The server is language-agnostic; language is a client-side state (localStorage).",
  },
};

const LANG_KEY = "lattice.lang";
const TITLES = { zh: "知识库薄壳", en: "Knowledge Lattice Shell" };

/** t(key, params)：查字典 + {name} 占位符替换（缺键回退 zh、再回退 key 本身）。 */
function t(key, params) {
  const lang = currentLang();
  let s = (I18N[lang] && I18N[lang][key]) != null ? I18N[lang][key] : I18N.zh[key];
  if (s == null) s = key;
  if (params) {
    for (const [k, v] of Object.entries(params)) s = s.split("{" + k + "}").join(String(v));
  }
  return s;
}

function currentLang() {
  const saved = localStorage.getItem(LANG_KEY);
  return saved === "en" || saved === "zh" ? saved : "zh"; // 默认中文
}

/** setLang(lang)：即时全页生效 + <html lang>/<title> 同步 + localStorage 持久化。 */
function setLang(lang) {
  if (lang !== "zh" && lang !== "en") lang = "zh";
  localStorage.setItem(LANG_KEY, lang);
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.title = TITLES[lang];
  applyI18n();
  document.dispatchEvent(new CustomEvent("langchange", { detail: { lang } }));
}

/** applyI18n()：扫描 data-i18n / data-i18n-ph / data-i18n-title 并套文案。 */
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph")));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
  });
}
