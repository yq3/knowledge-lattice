# TC-UI 双语走查清单（M1-5——交用户/监督方手动执行；coder 提供步骤，不执行）

> 依据：TEST-CASES §二 TC-UI-01~04（v1.5，FR-8 界面国际化）+ design §5.7 薄壳。
> 走查对象：`src/knowledge_lattice/web/`（index.html + i18n.js + app.js——上传/检索两视图，
> M1 检索页已落地）。**本组为手动走查用例，不进 CI**（tests/test_ui_01_manual.py 为
> 常驻 manual 标记的占位——门禁 `-m "not manual"` 排除）。
>
> 走查前置（服务与身份）：
> ```bash
> cd knowledge-lattice
> LATTICE_ENV=dev uv run uvicorn knowledge_lattice.app:create_app --factory --port 8000
> # dev token（另一终端；替换 <token>）：
> curl -s -X POST localhost:8000/api/dev/token -H 'Authorization: Bearer <任意静态 token 或首签>' \
>   -H 'Content-Type: application/json' -d '{"user_id": "u_full", "org": "org:tax"}'
> ```
> 浏览器打开 `http://localhost:8000/`；页面右上「连接设置」填入上面签发的
> dev JWT 与组织 `org:tax` 后保存（localStorage 持久）。
>
> 建议语料：任一已入库文档（有检索结果即可）；越权对照用户可用 `u_cn`
> （region=[CN]）另签一枚 token。

---

## TC-UI-01 语言切换与持久化【M0a 机制就位，M1 随检索页复验】

| # | 步骤 | 预期 |
|---|---|---|
| 1 | 浏览器 DevTools → Application → Local Storage → 删除 `lattice.lang` → 刷新页面 | 默认**中文**；`<html lang="zh-CN">`（DevTools Elements 首行）；`<title>`＝「知识库薄壳」 |
| 2 | 点头部「中 \| EN」的 **EN** | 全页 UI 文案**即时**切英文（导航/标题/按钮/表头/页脚，无刷新）；`<html lang="en">`；`<title>`＝"Knowledge Lattice Shell" |
| 3 | 再点 **中** 切回 | 全页即时切回中文；`<html lang="zh-CN">` 与 `<title>` 同步 |
| 4 | EN 态下刷新页面（F5） | 仍为英文（localStorage `lattice.lang="en"` 持久化） |
| 5 | 关闭浏览器完全重开，再访问页面 | 语言选择保持（EN） |

## TC-UI-02 双语完整性——无混语言 UI 文案【M1 检索页起】

EN 态逐项走查（zh 态反向抽查同项）：

| # | 走查位置 | 预期 |
|---|---|---|
| 1 | 左侧导航两项（Upload / Search Test）与底部提示（M0a shell…） | EN 文案，无裸中文 |
| 2 | 「连接设置」卡片：标题、两个输入框 placeholder（Dev JWT…/e.g. org:tax）、保存按钮 | EN |
| 3 | 上传视图：标题、lede 说明、知识库/文件/文档维度标签、维度 chips 内「required」旁注与提示、上传按钮、空库提示（无库时） | EN |
| 4 | 检索视图：标题、lede、输入框 placeholder（Ask a business question…）、检索按钮、知识库下拉「All visible」、结果表七列表头（#/chunk_id/Document/Page-Sheet/score/Dims/Source） | EN |
| 5 | 空态卡片（No visible results — …）与「403」拒绝提示 | EN |
| 6 | 任务与文档状态区（上传后）：标题与 状态/active/pending/刷新 等标签 | EN |
| 7 | zh 态反向抽查以上各项 | 无裸英文（**排除项按口径原样保留**：状态枚举 `searchable_full` 等、API 路径、工具名、章节引用锚点、业务数据不译） |

## TC-UI-03 业务数据与行为不随语言变化【M1】

| # | 步骤 | 预期 |
|---|---|---|
| 1 | zh 态输入同一 query（如「增值税 申报」）检索，记录命中列表（chunk_id 序、score、dims 列、文档标题） | 记录基准 |
| 2 | 切 EN 态，**同一 query** 再检索 | 命中集合、排序、score、dims 展示与步骤 1 **完全一致**；文档标题/维度取值标签保持数据本身语言（业务数据不译——FR-8） |
| 3 | 越权对照：换 `u_cn` token（region=[CN]）+ X-Org-Id=org:tax，zh 态检索 | 结果中不含 region=[OS] 文档（或 403 拒绝语义——按库内数据） |
| 4 | EN 态重复步骤 3 | 拒绝/过滤行为与步骤 3 一致——语言不影响权限行为 |

## TC-UI-04 服务端不感知语言【M1】

| # | 步骤 | 预期 |
|---|---|---|
| 1 | DevTools → Network 面板；zh 态执行一次检索 | 抓取 `POST /api/search` 请求/响应报文存档 |
| 2 | 切 EN 态，同一 query 再检索，抓取同请求 | 两报文**逐字节等价**（除时间性字段）：请求体/头**无任何语言参数**（无 `lang`/`Accept-Language` 差异——注：浏览器自动附带的 `Accept-Language` 头不属于应用参数，如携带需人工确认服务端不消费） |
| 3 | zh/EN 各执行一次管理面操作（如上传或刷新状态） | 请求不带语言参数；响应错误码/字段不随语言变化 |
| 4 | （可选）查服务端日志/审计事件（audit_outbox） | 同一操作在两语言下产生的审计事件字段一致——服务端不感知语言 |

---

**走查记录归档**：逐条勾验结果（通过/不通过 + 截图/备注）回填本文件同目录
（建议 `report-m1-5-tc-ui-walkthrough-filled.md`）或交监督方归档；§六 M1 行
TC-UI 完成态由 supervised-coding 落笔。
