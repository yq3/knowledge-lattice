# task-knowledge-lattice-ui-3 · i18n 终审 + 真实数据形态 + TC-UI 对照走查组重写（issue #20 收官段）

> 段位：M3-UI 第 4 段（收官）。ui-1/2 已交付六视图原型级实装；本段收口 issue E 项非功能要求 + TC-UI 走查组随新 UI 重写（原走查状态作废——issue 评论 2 连带注记口径）。
> 基线：门禁 1715+1 双后端双模式 0 skipped（13bffba 后工作区）。

## 硬约束

1. **文件白名单**：
   - `src/knowledge_lattice/web/**`
   - `docs/TEST-CASES.md`（**活文档**——仅 TC-UI 组重写 + TC-E2E-07 条目更新 + 版本行；版本行声明「非决策变更、冻结结论不动、用例数不变」）
   - `benchmarks/report-ui3-tc-ui-walkthrough.md`（**新增**——新 UI 手动走查清单，沿 report-m1-5-tc-ui-walkthrough.md 先例形态）
   - `tests/test_e2e_07_shell.py`（仅当机制断言需微调；第三用例一字不动）
   - 禁区：prototype/（只读）、docs/ 其余正文（requirements/design 冻结）、src/** 其余、tests/** 其余。零 commit / push / add。
2. 沿 ui-1/2 代码约定与设计系统（不新增设计语言；真实形态的样式复用既有类 + 必要小补充集中 style.css「ui-3 additions」节）。
3. i18n 全文案走 t()；分页/截断/时间等新形态文案同样入字典（zh/en 同步）。

## 工作项

### A. i18n 终审（FR-8 / TC-E2E-07 机制断言保活）

1. 键对账脚本全量跑：t() 引用 + data-i18n* vs zh/en 双字典——零缺键（ui-2 已 612=612，本段新增键后复跑）。
2. **硬编码文案扫描**：模板字符串/属性中的裸中文（排除：代码注释、业务数据字段渲染〔标题/实体名等来自 API 的值〕、API 路径与工具名/状态枚举〔TC-UI-02 排除项口径〕）——发现即修（入字典）。
3. EN 态全视图走查一遍：无混语言（含 toast/placeholder/title/空态/教学文案）。

### B. 真实数据形态系统化（issue E 项「原型未画，实装段定」的约定落档）

对六类形态做**全视图盘点 → 补漏 → 约定**（盘点表进交付报告；约定文案入走查清单）：

1. **空态**：docs（无库/空库/be-① 降级）、search（无结果/403）、access（无授权行/无维度/矩阵占位）、ops（无任务/无审计/maintenance null）、semantic（未接入/无权限/无结果/404 零泄露）、orgs（无组织）——已有大部分，统一「空态 = 说明 + 下一步动作」模式，补漏。
2. **加载态**：各视图 onEnter 异步首装必有 loading 指示（loadingHTML 复用）；二次刷新不闪空（缓存先行渲染再更新）——盘点补漏。
3. **错误态**：401（api.js 统一 → toast + 打开连接设置）/403（toast detail + 视图内降级面）/404（视图内空态）/网络异常——盘点各视图错误路径呈现一致。
4. **条数与分页**：审计 limit=50 → 表头/脚注标注「最近 50 条」+「加载更多」（limit 递增 50→100→200，api.js audit 已有 limit 参数）；sync-runs limit=50 同款；任务列表全量（无分页参数——注记）；docs be-① 未定不处理。
5. **长文截断**：实体名/brief/title/别名等列表位文本 CSS 截断（沿原型 text-overflow/字数截断惯例——.t-title/.crumbs 已有部分）；详情位全文。盘点补漏（如审计 detail_json 160 字符截断已有——title 加「展开全文」或保留截断约定）。
6. **UTC 时间显示**：统一约定——显示 `MM-DD HH:mm`（short()）+ hover title 完整 UTC 原文；时间列/pane 时间行标注 UTC（一处全局约定文案，如表头「更新(UTC)」或脚注）。盘点所有时间显示位统一。

### C. 功能小件（既有端点 + 既有 UI 模式，薄加法）

1. **质检抽查入口**（org_admin）：docs 视图工具栏「质检抽查」按钮 → 面板（sample flags 表：flag_id/doc_id/reason〔中文化〕/mean_sim/avg_idf）+ 行内补标（keywords/tags 输入 + 解决/忽略）→ `GET /api/quality-flags/sample` + `PATCH /api/quality-flags/{flag_id}`（api.js 已有 sampleQualityFlags/patchQualityFlag，挂载即可）。
2. **覆盖上传入口**：doc 详情 pane「上传新版本」按钮（owner/org_admin）→ 打开上传抽屉且锁定该 doc（提交时 FormData 带 doc_id——uploadMultipart 已支持 docId 参数）→ 202 → 轮询；pending 期间 409 如实；版本原子切换口径注记（到 searchable_full 才切换在用）。

### D. docs/TEST-CASES.md 回写（活文档、非决策变更）

1. **TC-UI 组重写**（§二 TC-UI 节）：
   - **TC-UI-01 语言切换与持久化**：机制步骤平移（顶栏「中 | EN」新位置），断言不变 + 全视图重渲染即时生效。
   - **TC-UI-02 双语完整性**：按新六视图 + 顶栏/连接弹层/toast/空态/占位重写步骤；排除项口径保留（状态枚举/API 路径/工具名/文档锚点/业务数据）。
   - **TC-UI-03 业务数据与行为不随语言变化**：新交互路径（检索 hit 卡对照 / 授权格点格 PUT 两语言各一次对照 export 一致）。
   - **TC-UI-04 服务端不感知语言**：新路径（检索 + 授权格 PUT 抓包对照）。
   - **新增 TC-UI-05 原型 1:1 对照走查**【手动｜ui-3】：逐视图（文档/检索/权限〔授权格/维度/成员/矩阵占位〕/运维/语义/组织/顶栏与侧栏）与 prototype v0.6 并排对照——同一设计系统类名、布局结构、交互口径；诚实差异清单（facet 无计数/成员 role 缺位/aliases 无徽标/矩阵占位等——以 ui-2 检查点落档清单为基线）为已知豁免项。
   - **B① 逐行过期编辑新路径注记**：原 4/4 走查基于旧薄壳形态作废；新路径 = 权限·授权格 → 成员「详细」抽屉内逐行 expires（预填/行内/保存全量替换）。步骤并入 TC-UI-03 或单列 TC-UI-06，二选一（实现时按清单篇幅定）。
   - 节首口径注记：**本组随 ui-3 重写为新 UI 原型对照走查口径；旧走查状态（含 m2-5 B① 4/4）作废**——M1+M2 里程碑达成宣告的唯一待勾项按新形态重新执行。
2. **TC-E2E-07 条目更新**：预期句改新壳口径（应用框架 + 六视图 + api.js 契约收口 + 前两用例 ui-1/2 随壳重写注记；第三用例 API 侧不变）。
3. **版本行**：v1.9.14（2026-11-04 随 ui-3 交付——非决策变更、冻结结论不动、CI 用例数不变：TC-UI 手动组重写不进门禁）。§六对照表如有 TC-UI 引用行同步注记。

### E. 走查清单（benchmarks/report-ui3-tc-ui-walkthrough.md 新增）

沿 report-m1-5-tc-ui-walkthrough.md 先例形态：TC-UI-01~05（+B① 新路径）逐用例步骤/预期/勾验栏；附录：六类真实数据形态约定（B 项盘点结论）+ 诚实差异豁免清单 + 走查环境指引（/tmp 造数 + uvicorn + token 双模式）。

### F. 门禁

- `uv run pytest -q` 全绿 0 skipped，用例数不增（TC-E2E-07 若仅机制断言微调则数量不变）。

## 端到端验证（子代理必做）

- 沿 /tmp/ui2_seed.py 环境（或增补：几份无 quality flag 的空态样例不必强求——空态用无 flag 文档验）；浏览器走查：B 项六类形态逐类触发（含「加载更多」翻页、长文截断 hover、UTC title、EN 态全视图）；C 两小件闭环（抽查补标 PATCH 生效 / 覆盖上传新版本号 + 原子切换注记 + pending 409 路径）；console 零 JS 错误。
- i18n 扫描脚本输出零缺键零硬编码（排除口径内）。

## 验收标准（自检后才算完成）

1. git 白名单外零触及、零 commit。
2. i18n：键对账零缺键 + 硬编码扫描零命中（排除口径内）+ EN 全视图无混语言。
3. 六类形态盘点表 + 补漏实现逐项过；两小件闭环实测。
4. TEST-CASES 回写：TC-UI 组新形态（01 平移/02-04 新路径/05 对照走查/B① 新路径注记/作废声明）、TC-E2E-07 更新、版本行非决策变更声明——**diff 不触碰正文冻结区**（仅活文档相关节）。
5. 走查清单文件就位（结构同先例）。
6. `uv run pytest -q` 全绿 0 skipped 用例数不增。

## 交付报告格式

文件清单与行数 / 六类形态盘点表（现状→补漏→约定）/ i18n 扫描结果 / TEST-CASES diff 摘要 / 自检 6 项勾验 / 遗留清单。

---

## 交付记录（2026-11-04，主会话验收后回填）

- **开发**：subagent（general-purpose）；**验收**：主会话独立复核。
- **交付物**：web/ 十文件收口（i18n 640=640 键 +28/修 1 重复键、tsHTML UTC 悬停、审计/同步历史「最近 N 条」+加载更多 50→100→200 阶梯、六类形态补漏〔空态下一步/二次刷新不闪空/假空表修正/CSS 截断〕、**质检抽查面板**〔sample+行内补标+换 seed 重抽〕、**覆盖上传**〔锁定横幅+doc_id+pending 409 专属 toast〕）+ docs/TEST-CASES.md 4 hunk（版本行 v1.9.14 非决策声明 / TC-E2E-07 新壳口径 / **TC-UI 组重写**〔01 平移·02-04 新路径·05 新增原型对照走查·B① 并入 03·旧状态作废声明含 m2-5 B① 4/4〕/ §六 M1 行注记）+ benchmarks/report-ui3-tc-ui-walkthrough.md（129 行，沿 m1-5 先例 + 六类形态约定附录 + 豁免清单）。
- **主会话独立验收**：
  - ✅ git 白名单（web/** + TEST-CASES 指定节 + benchmarks 新清单；api.js/test_e2e_07 零改动）；TEST-CASES diff **恰 4 hunk 全在活文档区**、版本行非决策声明在位。
  - ✅ **门禁独立复跑 GATE PASS**：1715+1 deselected、0 skipped、双后端双模式——用例数不增。
  - ✅ 浏览器实测（重建 /tmp/ui2-data 环境）：质检抽查面板（本种子无 flag → 空态如实；机制与 ui-3 子代理 DB 级复验一致）；**覆盖上传全链**（上传 v1 → 「↥ 上传新版本」→ 锁定横幅+库锁 → 传 v2 → pending v2 / 在用 v1 不动——原子切换语义可视）；审计「加载更多」脚注与 50 起点；UTC 悬停 title（`…UTC` 全文）；任务全量注记；console 零 JS 错误。
  - ✅ i18n 独立复跑：zh=en=640 零缺键。
- **遗留**：走查清单待用户人工执行回填（TC-UI-01~05——**M1+M2 里程碑达成宣告唯一待勾项按新形态执行**）；组织到期 (UTC) 悬停视觉位需带 expires 视角复验（机制同源已验）；be-①/m3-1/m3-2 contract-first 降级维持（后端轮次清偿）。
- **状态**：**done**——开发+主会话独立验收+用户视觉验收通过（TC-UI-05 对照走查，2026-11-04）→ M3-UI 四段收官。
