# TC-UI 双语 + 原型对照走查清单（ui-3——交用户/监督方手动执行；coder 提供步骤，不执行）

> 依据：TEST-CASES §二 TC-UI-01~05（v1.9.14 随 ui-3 重写，FR-8 界面国际化 + 原型 v0.6 对照）+ issue #20 E 项。
> 走查对象：`src/knowledge_lattice/web/`（新 UI：应用框架 + 文档/检索/权限/运维/语义/组织六视图；
> i18n.js / api.js / app.js / views/\*.js 经典脚本按序引入）。**本组为手动走查用例，不进 CI**
> （tests/test_e2e_07_shell.py 机制断言自动跑；本清单为浏览器人工执行）。
> **旧清单作废声明**：m1-5 批次（report-m1-5-tc-ui-walkthrough.md，含 m2-5 B① 4/4）基于旧薄壳
> 形态，走查状态一律作废——M1+M2 里程碑达成宣告的唯一待勾项按本清单新形态重新执行。

## 走查环境指引

```bash
# ① 造数（/tmp/ui2_seed.py 已含语义面/成员面；如需重跑）：
python3 /tmp/ui2_seed.py            # → /tmp/ui2-data/lattice.db（不入仓）

# ② 服务（独立终端；测完 Ctrl-C 杀净，防孤儿进程持有已删 DB fd）：
cd knowledge-lattice
LATTICE_DATA_DIR=/tmp/ui2-data LATTICE_ENV=dev \
  uv run uvicorn 'knowledge_lattice.app:create_app' --factory --port 8960

# ③ token 双模式（浏览器「连接设置」弹层两模式各验一次）：
#    模式 A · dev 重签：基 token 填静态 token（dev-static-root0=sysadmin /
#    dev-static-boss=org_admin / dev-static-staff=member），组织 org:tax，重签连接；
#    模式 B · 直接粘贴：POST /api/dev/token 现铸已签 token（参考 /tmp/ui1_tokens.txt 生成方式）：
curl -s -X POST localhost:8960/api/dev/token \
  -H 'Authorization: Bearer dev-static-boss' -H 'Content-Type: application/json' \
  -d '{"user_id": "boss_admin", "org": "org:tax"}'
#    （换 staff_wang / temp_li 同法；组织切换 org:fin 验跨组织隔离）
```

浏览器打开 `http://localhost:8960/`；右上「连接设置」按上述两模式连接。
建议走查身份：`boss_admin`（org_admin，全功能）与 `staff_wang`（member，只读降级面）；
越权对照可用 `staff_wang`（region=[CN]）。

---

## TC-UI-01 语言切换与持久化【M0a 机制就位，ui-1 起新壳复验】

| # | 步骤 | 预期 |
|---|---|---|
| 1 | DevTools → Application → Local Storage → 删除 `lattice.lang` → 刷新页面 | 默认**中文**；`<html lang="zh-CN">`（Elements 首行）；`<title>`＝「Knowledge Lattice 控制台」 |
| 2 | 点**顶栏「中 \| EN」**的 **EN**（新位置：品牌区右侧工具带，MCP 弹层旁） | 全页 UI 文案**即时**切英文（顶栏/侧栏/当前视图，无刷新）；`<html lang="en">`；`<title>`＝"Knowledge Lattice Console" |
| 3 | 保持 EN 态，逐一切换六个视图（文档/检索/权限/运维/语义/组织） | 每个视图均为英文渲染（缓存数据复用仅文案换），无闪中文、无空白 |
| 4 | 再点 **中** 切回 | 全页即时切回中文；`<html lang="zh-CN">` 与 `<title>` 同步 |
| 5 | EN 态下刷新页面（F5）、关闭浏览器完全重开 | 语言选择保持（localStorage `lattice.lang="en"` 持久化） |

## TC-UI-02 双语完整性——无混语言 UI 文案【ui-3 六视图全量】

EN 态逐项走查（zh 态反向抽查同项）：

| # | 走查位置 | 预期 |
|---|---|---|
| 1 | 顶栏：品牌、组织 picker 菜单、API 参考、MCP 弹层（工具名列表）、语言切换、「以此身份查看」picker、连接设置弹层（模式 A/B 全部标签与 placeholder 与状态行） | EN，无裸中文 |
| 2 | 侧栏：三组导航（知识/管理/运维）与计数旁注、页脚连接状态卡 | EN |
| 3 | 文档视图：标题/lede、知识库 seg、列表表头（含「Updated (UTC)」）、空态卡、上传抽屉全部标签与提示、新建知识库表单、**质检抽查面板**（标题/表头/按钮/空态）、详情 pane（版本/维度/质检/删除确认）、**覆盖上传锁定横幅** | EN |
| 4 | 检索视图：qbar placeholder、知识库下拉、实体召回路开关、命中卡 meta、无结果空态、403 拒绝卡、右 pane notice/管线说明/当前连接 | EN |
| 5 | 权限视图：四子标签、只读降级横幅、授权格表头/图例/底注、详细抽屉（预填/行内到期/CSV 区）、成员表（角色/改过期/移除确认）、维度治理（停用/恢复/退役确认/新建维度）、可见性占位卡 | EN |
| 6 | 运维视图：任务表头与「Tasks return in full…」注记、覆盖率面板、stats、审计双泳道标题与空态、**「最近 N 条」脚注与「Load more」按钮** | EN |
| 7 | 语义视图：探针空态（未构建/403）、搜索与 facet、结果表、详情（定义/别名/关系/SVG 注记）、术语识别、同步与构建（五源表/运行历史/构建表/L0） | EN |
| 8 | 组织视图：列表、建组织表单、停用确认条 | EN |
| 9 | 全局：toast 文案（上传/保存/403 detail 回显）、按钮 title 悬停、时间悬停 title（`… UTC` 后缀原文） | EN |
| 10 | zh 态反向抽查以上各项 | 无裸英文（**排除项按口径原样保留**：状态枚举 `searchable_full` 等、API 路径与端点串、工具名、度量名 mean_sim/avg_idf、文档锚点 §5.1、业务数据不译、「中 \| EN」语言自称） |

## TC-UI-03 业务数据与行为不随语言变化【ui-3 新路径（含 B① 逐行过期编辑）】

| # | 步骤 | 预期 |
|---|---|---|
| 1 | zh 态输入同一 query（如「留抵 退税」）检索，记录**命中卡**（rank 序/snippet/标题·页·库/dims chips/score/matched_entities 计数） | 记录基准 |
| 2 | 切 EN 态，**同一 query** 再检索 | 命中集合、排序、score、dims 展示与步骤 1 **完全一致**；文档标题/维度取值标签保持数据本身语言（业务数据不译——FR-8） |
| 3 | 「权限·授权格」任取一格（如 `staff_wang` × region=CN）zh 态点一次（取消或加上），记录 toast 的 removed/inserted | PUT 全量替换语义生效，export 复验行集变化 |
| 4 | EN 态对**同一格**再点一次（还原），对照 toast 与重新导出 CSV | removed/inserted 与 CSV 终态两语言一致——语言不影响管理行为 |
| 5 | **B① 新路径**：`staff_wang` 行「详细」抽屉——zh 态改一行 expires（如 2030-06-30 00:00:00）保存；EN 态再改回（空=永久）保存 | 输入框预填=库内值、保存=一次 PUT 全量替换；两语言导出 CSV 终态一致 |
| 6 | 越权对照：`staff_wang`（region=[CN]）zh 态检索 | 结果不含 region=[OS] 文档（或 403 拒绝语义——按库内数据） |
| 7 | EN 态重复步骤 6 | 过滤/拒绝行为与步骤 6 一致——语言不影响权限行为 |

## TC-UI-04 服务端不感知语言【ui-3 新路径】

| # | 步骤 | 预期 |
|---|---|---|
| 1 | DevTools → Network；zh 态执行一次检索 | 抓取 `POST /api/search` 请求/响应报文存档 |
| 2 | 切 EN 态，同一 query 再检索，抓取同请求 | 两报文**逐字段等价**（除时间性字段）：请求体/头**无任何语言参数**（浏览器自动 `Accept-Language` 头不属于应用参数，如携带需人工确认服务端不消费） |
| 3 | zh / EN 各执行一次授权格点格（`PUT /api/orgs/{org}/members/{id}/grants`，点后还原） | 请求体（grants 全量数组）无语言差异；响应 removed/inserted 一致 |
| 4 | （可选）查审计事件（运维视图治理泳道） | 同一操作两语言下审计事件字段一致——服务端不感知语言 |

## TC-UI-05 原型 1:1 对照走查【ui-3 新增】

`prototype/index.html`（v0.6 mock）与服务端新 UI（/tmp 环境）**并排**逐视图对照：

| # | 对照视图 | 预期（一致面） |
|---|---|---|
| 1 | 骨架：顶栏（brand/picker/工具带/语言切换/连接）+ 侧栏（分组导航/页脚卡）+ 主区 | 同布局结构、同类名（.topbar/.rail/.nav-item…）、同视觉语言（品牌蓝/灰阶/圆角卡片） |
| 2 | 文档：seg 分段、ledger 列表、split 双栏、pane 详情、上传抽屉（.upload/.u-row/.u-foot） | 同结构与交互口径；真实数据形态（空态/加载/截断/UTC）按附录 A 约定 |
| 3 | 检索：qbar、qopts、.hits/.hit 卡（rank 徽标/snippet/meta 行/score bar） | 同结构；notice 面板与管线说明口径一致 |
| 4 | 权限：.lattice 授权格（.cellbtn 三态+过期虚线）、图例底注、成员 ledger、维度治理行、可见性占位 | 同结构；点格 PUT 语义底注一致 |
| 5 | 运维：任务 ledger、覆盖率漏斗 bars、审计 .lanes 双泳道（.ev 事件行） | 同结构 |
| 6 | 语义：类型 tiles 落地页、facet chips、结果表、对象图 SVG（.graph/.node/.edge）、术语识别（.ann-in/.annot mark 下划线+浮标）、同步与构建表 | 同结构与配色（类型色/关系色）；fanout 截断 +N 占位口径一致 |
| 7 | 组织：ledger、建组织表单、停用确认 | 同结构 |
| — | 全视图 | **诚实差异清单外差异即不通过**（豁免清单见附录 B，以 ui-2 检查点落档为基线） |

---

## 附录 A：六类真实数据形态约定（ui-3 B 项盘点结论——走查时按此口径验）

| 形态 | 约定 | 主要触发位 |
|---|---|---|
| 空态 | 「说明 + 下一步动作」卡片（.empty）；各视图已备：docs 无库/空库/be-① 降级横幅、search 无结果/403、access 无授权行/无维度（含新建入口）/矩阵占位、ops 无任务/无审计/maintenance null、semantic 未接入/403/无命中/404 零泄露、orgs 无组织 | docs 空库（ds:cit_lib）、staff_wang 检索无结果、org:fin 未建词典 |
| 加载态 | 各视图首装必有 loading 指示（.loading 复用）；**二次刷新不闪空**（缓存先行、原位更新）——ops 刷新保留旧表、semantic 同步子标签数据未到显示加载条、orgs 首装无缓存不闪「无组织」 | ops 反复点「刷新」；semantic 切「同步与构建」子标签 |
| 错误态 | 401 统一 toast + 自动打开连接设置（坏 token 即触发）；403 toast 服务端 detail + 视图内降级面（只读横幅/面板不可用注记）；404 视图内空态（语义详情 404 零泄露 / be-① 横幅）；网络异常 toast | 连接设置粘贴坏 token 后任一操作；staff_wang 开运维视图（覆盖率/stats/审计 403 面板） |
| 条数与分页 | 审计 = 「最近 N 条」脚注 + 「加载更多」（limit 50→100→200，上限 200 停）；语义同步运行历史同款；任务列表全量返回（无分页参数——表下注记如实）；docs be-① 未定不处理 | 运维审计脚注连点三次（50→100→200 后按钮消失）；semantic 运行历史同验 |
| 长文截断 | 列表位 CSS 截断（title/.t-sub/brief/别名等，hover title 看全文）；详情位全文；审计 detail_json 240 字符截断 + title 全文；任务 error 60 字符 + title | 造一份长标题文档看列表行；审计看长 detail 行 |
| UTC 时间 | 显示 `MM-DD HH:mm`（short()）+ **hover title 完整 UTC 原文**（`原文 UTC`）；时间列表头/pane 时间行标注 **(UTC)**（docs/ops/audit/sem runs/builds/orgs expires） | 任意时间位悬停；对照表头标注 |

## 附录 B：诚实差异豁免清单（原型 mock ≠ 真实契约——对照走查已知豁免）

1. 语义类型 facet **无计数**（真实无全图 counts 端点——原型计数为 mock）；
2. 授权格成员行 **role 不可得**（无 GET members 端点，m3-1 #13——名单源=export 用户名）；
3. 授权格**不标 sync 只读格**（API 无维度 source 字段——export=local 口径）；
4. **可见性矩阵占位**（待 be-① 文档列表 + be-② explain——前端不演算 ACL，B5）;
5. 实体别名**无 kind/mode 徽标**（include=aliases 只回别名文本）；
6. **组织停用/恢复 contract-first**（PATCH /api/orgs/{org} 待 m3-1 #14——404/405 降级 toast）；
7. 建知识库/建维度 contract-first（待 m3-1 #13）；docs 列表 be-① contract-first（404 降级横幅 + 会话缓存）；
8. 查询审计道空态注记（查询级审计待 m3-2 G-22）；
9. L0 片段联动走 entity_key 搜索直达（REST 路径只有 int entity_id）。

---

**走查记录归档**：逐条勾验结果（通过/不通过 + 截图/备注）回填本文件同目录
（建议 `report-ui3-tc-ui-walkthrough-filled.md`）或交监督方归档；§六 M1 行
TC-UI 完成态由 supervised-coding 落笔。
