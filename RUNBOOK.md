# knowledge-lattice 运维 Runbook（M0b-3 起）

> 代码仓内的运维手册（docs/ 属设计冻结区——本文件为运行侧活文档）。
> 依据：`benchmarks/report-m0b-2.md`（三项拍板实验报告）、`docs/design.md` §5.3、
> schema v1.1 迁移（`store/<dialect>/migrations/docs/0002_schema_v1_1.sql`）。
> 章节：§1 运行侧（重嵌入蓝绿 / §1.x 供应商切换 / §1.y 组织停用 / §1.z 查询审计 /
> §1.aa 评测依赖 / §1.ab 内置账号 / §1.ac Agent 密钥 / §1.ad 控制台时区）· §2 审计分区 · §3 迁移 · §4 备份恢复。

## 1. 运行侧操作（重嵌入蓝绿为主；§1.x 起为专题）

> 形态依据报告 §3.5（v1.1 分表建议表）+ §3.3（蓝绿四相位实测）；执行体自 m2-6 起
> 接管（见下方「m2-6 执行体接管后的操作口径」）——相位序列用于核查与手工兜底。核心物理前提：
> `chunk_vectors(rid, embed_model, embedding)` **PK(rid, embed_model)**——同 rid
> 多标签并存可插（仅 PK(rid) 的新标签写入即 IntegrityError，bench2
> `probe_pk_rid_conflict` 双后端实测；门禁内等价探针见
> `tests/test_v11_schema.py::test_pk_rid_only_conflict_probe`）。

相位序列（每相位 SQL 仅为示意，标签 `model:dim` 形态——D12）：

1. **新标签写入（并存期开始）**：以新标签 `new:2560` 走摄取同款路径
   （`mark_embedding_batch(doc, ver, "new:2560")` → 嵌入 → `write_embeddings`）——
   INSERT `chunk_vectors`，旧标签行零触碰、持续服务（功能零降级）。
   - 存量文档批量：sysadmin 经 `POST /api/orgs/{org}/documents/{doc_id}/reindex?embed_model=new:dim`
     投递（见下「m2-6 执行体接管」）；逐文档重摄取只用于排障。
2. **覆盖率观测**（分子/分母口径闭合——都限定在用块）：
   ```sql
   -- 分子：新标签已回写的在用块数
   SELECT count(*) FROM chunk_vectors cv
   JOIN chunks c ON c.rid = cv.rid
   WHERE cv.embed_model = 'new:2560'
     AND c.tombstone = 0
     AND c.version = (SELECT d.active_version FROM documents d WHERE d.id = c.doc_id);
   -- 分母：在用块总数（同一限定口径）
   SELECT count(*) FROM chunks c
   WHERE c.tombstone = 0
     AND c.version = (SELECT d.active_version FROM documents d WHERE d.id = c.doc_id);
   ```
   两值相等即覆盖率 100%（**不要**用裸 `SELECT embed_model, count(DISTINCT rid)
   FROM chunk_vectors GROUP BY embed_model` 对比——分母含 tombstone/旧版本块，
   会把覆盖率低估、误判未到 100%；重嵌入任务按 pending 维度认领，不含旧版本块）。
   - 共存窗口读代价（知情申报，报告 §3.3）：sqlite 零放大；pg 精确扫描需过双倍行页
     （P50 +6% / P95 +18% 量级，跑间波动带 -3%~+52%）。
3. **原子切 current_model**：配置标签翻转（`LATTICE_EMBED_MODEL` / config）——
   零 SQL（§5.8 dict_rev 同款模式）；inline 形态瞬时生效，subprocess 形态下
   主进程（API/检索）需重启才生效（见下「m2-6 执行体接管」）；向量路谓词
   `cv.embed_model = :current_model` 只命中新标签（TC-EMB-02）。
4. **旧标签延后清理（低峰）**：`DELETE FROM chunk_vectors WHERE embed_model = 'old:2560'`
   ——窗口自主；实测（5 万块档）：sqlite 清理 WAL 仅 ~4.3MB；pg DELETE 记满量死元组
   （~552MB WAL 量级）。
5. **空间回收（仅 pg 需要）**：`VACUUM chunk_vectors`——**plain VACUUM 不归还 OS**
   （空页在文件前段、页内复用消化；实测高水位 1257.8MB 不降）。需归还 OS 时
   `VACUUM FULL`（锁表）或 pg_repack；存储不紧则跳过（后续写入复用空页）。

回退：切换点前后任一时刻可把 config 标签翻回 `old:2560`（旧标签行仍在）——
蓝绿双向可退（生效窗口同上：inline 瞬时 / subprocess 重启主进程）。若已执行
相位 4 清理则不可退（重嵌入重来）。

sqlite 侧 `chunks.embed_model` 为摄取状态标签：重嵌入批次结束、覆盖率 100% 后，
新批次标签即当前 config 标签（`mark_embedding_batch` 钉标签机制不变）；旧标签
残留行不影响检索（谓词在 `chunk_vectors` 侧）。

**m2-6 执行体接管后的操作口径（2026-11-01 交付注记）**：

- **投递**：`POST /api/orgs/{org}/documents/{doc_id}/reindex?embed_model=new:dim`——
  **sysadmin 专属**（owner/org_admin 403；N-1 用户裁定 2026-11-01：换模型为系统级
  配置项）；worker 全库扫描（**含所有组织**）→ 全库覆盖率 100% 门 → 进程内原子切
  标签 + 逐组织 quality 重算与 semantic_build 投递 → 旧标签清理。上方相位 1~5 的
  SQL 仅供核查，日常走任务执行体。
- **未收敛处置**：全库覆盖率 3 轮不收敛（并发持续摄取极端窗口）→ 任务 **failed 留
  人工**（fail-closed，不自动重试——known-gaps G-27）；错误信息含「切换与清理未
  发生」——核查并发摄取后人工重投。
- **subprocess 形态任务完成 ≠ 主进程已切换**：worker 子进程内切换只作用于子进程；
  主进程（API/检索）需改 env（LATTICE_EMBED_MODEL）重启——重启窗口内向量路暂空、
  BM25 可用。inline 形态（测试/最小部署）同进程共享对象图、切换即时生效。
- **回退窗口**：旧标签清理执行前可翻回旧标签（上方「回退」段）；**清理执行后不可
  退**（重嵌入重来）。
- **单文档 reindex**（不带 embed_model，owner/org_admin）：全量重切窗口内文档暂不可
  搜（固有代价）；存在 pending_version（**含失败上传**）时 API 409 拒绝——先处置
  覆盖上传（重传或清理 pending）后重投（N-2 用户裁定 2026-11-01 选 a 保守）。

### 1.x 嵌入/重排供应商切换（m2-5 起——仅改 env 零代码，D12 端点中立）

- **嵌入**：`LATTICE_EMBED_API_BASE/_KEY/_MODEL/_DIM`——OpenAI 兼容端点均可用；
  百炼示例 `https://dashscope.aliyuncs.com/compatible-mode/v1` + `text-embedding-v4`
  （dimensions **枚举** [64,128,256,512,768,1024,1536,2048,3072]，无 2560——改维
  需 reembed 蓝绿全库迁移，见 §1）。切换后按 §1 执行重嵌入。
- **重排**：`LATTICE_RERANKER ∈ {none, cohere, dashscope}`（未知档位启动即拒）+
  `LATTICE_RERANK_API_BASE/_KEY/_MODEL`。dashscope 档为百炼原生 text-rerank
  （gte-rerank-v2——`parameters.top_n` 生效；m2-5 实测联调，live 探测脚本
  `benchmarks/rerank_dashscope_live.py`）；cohere 档为公司网关 Cohere 风格 `/rerank`
  （部署期联调）。示例见 `.env.example` rerank 段。
- **评测 LLM（m3-4 起）**：`LATTICE_EVAL_LLM_API_BASE/_KEY/_MODEL`——黄金集合成候选
  生成与 m3-5 judge 校准的 OpenAI 兼容端点（`scripts/eval_synth_m34.py`，ragas
  `BaseRagasLLM` 直连；开发态沿 m2-5 百炼先例）。合成生成是一次性离线动作，生成物
  入 `eval/`、复跑不依赖端点；生成/联调动作**不进门禁**（门禁全离线确定性）。
- m2-5 实验复跑：`benchmarks/{bench8_g6_halfvec_50k,calib_m2_5,perf_m2_5}.py` +
  `bench5_slo_perf03.py --scales 50000 --backends pg`（全链 SLO）。

### 1.y 组织停用与恢复（m3-1 起）

- **停用**：`PATCH /api/orgs/{org}` body `{"status": "disabled"}`——**sysadmin 专属**
  （org_admin 不能停自己的组织）；幂等（同值重复 200、零新审计）；`org.disabled` 审计同事务。
- **影响面**：该组织全部 `/api/orgs/{org}/...` 端点 + MCP 会话 + webhook（验签后）+
  resolve_org 端点（`/api/search`、`/api/uploads` 等）一律 403（`org_disabled`）；
  **进行中任务让跑完**（worker 不查组织态）、新任务由入口拦截不投递；**系统维护链豁免**
  （日度兜底 sync / semantic_build / 对账 retag / 全库 reembed forced build 照常——
  保数据一致性，恢复后语义不破缺；用户裁定 2026-11-08）。成员关系与授权全保留
  （GET /api/orgs 停用组织仍列出、带 `status: disabled`）。
- **恢复**：`PATCH /api/orgs/{org}` body `{"status": "active"}`（幂等；`org.enabled` 审计）——
  恢复后全部端点立即回通，无需额外动作。

### 1.z 查询级审计观测（m3-2 起）

- **形态**：`query_audit.py` 进程内异步队列——满 5s 或满批 200 条 flush 直写当月月库
  （`audit_events`，action=`search.query`/`search.annotate`/`search.get_entity`；哈希链自动入链）；
  热路径仅入队；关停（uvicorn lifespan stop）drain flush，正常关停零丢失，崩溃尾部窗口 ≤5s（FR-6 接受）。
- **日志观测**：`grep -E "query audit (queue overflow|flush failed|drop)"` ——溢出丢最旧/连续失败
  3 次丢批均有计数日志；**dropped/pending 已暴露于 /stats**（`query_audit{dropped,pending}` 键——m3-3 起，未装配/取数异常→null 不 500；G-28⑦ 销账）。
- **查询**：`GET /api/orgs/{org}/audit`（org_admin 全量含查询词与命中；sysadmin 仅元数据——
  detail_json 逐事件剥离）；ops 视图审计「查询道」泳道按 `search.` 前缀自动分流。
- **PG 接线前置（G-28③——机制+测试已随 m3-3 交付，生产接线点部署期落地）**：
  ①`QueryAuditQueue` 已收 `backend_factory`（ContextManager 工厂）+ `store/postgres/audit_factory.py`
  `audit_backend_factory` 惰性单连接（独立于请求连接——pg 臂 `pg_backend_pid()` 断言双连接）；
  生产 PG 形态落地时需在 **app lifespan 装配处注入工厂**并在关停处调 `factory.close()`
  （当前 app 恒 sqlite 无暴露——G-28③ 残余即此接线）；
  ②**惰性单连接择型依据（复现注记）**：每轮 flush 开新连接会触发连接工厂内审计分区滚动
  setup DDL 与并发写事务在 pg catalog 锁上交叉死锁（DeadlockDetected——m3-3 开发期实测收敛为
  惰性单连接+`_flush_lock` 串行复用）；
  ③PG 工厂连接损坏（PG 重启等）无自动重连路径——flush 失败走既有回队/3 次丢弃循环，
  进程重启自愈；接线时可评估 broken 检测重连；
  ④ensure_month_partition DDL 缓存与 last_row_hash 索引随部署期接线同批。
- **模糊索引 code versioning（m3-3 起）**：`FUZZY_CODE_REV`（core/semantic/fuzzy.py）入 dict_rev——
  pinyin/编辑距离/term 构造/规范化行为变更时**必须 bump**（否则健康索引 skipped 快速通过会保留
  陈旧产物）；bump 或首次升级后各组织 dict_rev 变化→semantic_build 全量重建一次（沿 yaml_rev
  先例属预期行为，构建任务错峰限速照常）。

### 1.aa 评测依赖组与部署同步口径（m3-4 起）

- **依赖分组**：`deepeval` 在主依赖（门禁默认可跑）；`ragas 0.2.15`+langchain 0.3 era 钉版在
  **eval 依赖组**（`[dependency-groups] eval`——默认环境零 ragas/langchain，D2 最小服务端依赖）。
  ragas 钉版系上游 `vertexai` import 断裂防御（known-gaps **G-29①**）。
- **部署/门禁环境同步用 `uv sync --frozen`**（精确同步，与 uv.lock 逐字一致）；**不要用累积
  `uv run --group eval` 的环境直接部署**——`uv run` 是 inexact sync，eval 组包会残留（声明面
  无问题，`uv sync` 即还原；Tester P3-3）。统一 lock 副作用：eval 组入 lock 后 docling 系共享
  依赖 transformers/huggingface-hub 随之锁入降级版本（G-29②——门禁双模式全绿证明兼容；
  **升级 docling 时必须回归全量门禁**）。
- **评测门禁（TC-EVAL-04）**：`tests/test_eval_gate_m34.py` 全离线确定性（零 LLM/零外网）；
  逐 query recall@10 exact 冻结表+聚合 0.05 余量双层；**有意配方变更会红——属预期，须显式重测
  并同步更新冻结表与 `eval/reports/m3-baseline-*.json`**（两处同源，防漂移）。
- **基线复跑**：`scripts/eval_baseline.py --backend {sqlite,pg}`（缺省 `--label m3`，
  产物 `eval/reports/m3-baseline-*`；**m1 历史档只读**——`--label m1` 需显式
  `--allow-m1-overwrite`，否则 exit 1）；黄金集合成生成
  `scripts/eval_synth_m34.py`（需 `LATTICE_EVAL_LLM_*` env，见 §1.x；`--offline` 确定性兜底）。
- **judge 校准三形态（m3-5 起，TC-EVAL-03）**：`scripts/eval_judge_m35.py`——`--materials`
  （生成 50 条双评材料+标注回流模板；**answersheet 已含人工标注〔label/rater 任一非空〕时默认
  拒写 rc=1**〔报错含标注行数〕，防静默清空人工标签——确认放弃标注加 `--force` 显式覆盖；
  标注前建议先备份到 `data/eval-judge/`）/`--run-judge`（真实联调——judge 端点沿百炼先例
  `LATTICE_EVAL_LLM_*` env，联调不进门禁）/`--calibrate`（一致率/Cohen's κ 校准报告）。
  **当前 chat 端点配额受阻**（403/429/404 全档）——复跑路径与受阻记录见
  `eval/reports/m3-5-blocked-claims.md`；人工标注回流后出数、A-6 阈值随后定数。
- **响应层指标（m3-5 起）**：`ragas_bridge.response_layer_rows`（harness 基线报告+黄金集→
  ragas 行）→ `rows_to_ragas_samples`（惰性，需 `--group eval`）→ `ragas evaluate`
  （faithfulness/answer_relevancy——真实 LLM judge 面不进门禁）。**应答来源口径**：复跑主来源
  =增强器应答、辅助=judge 材料构造应答（如实标注）。
- **在线锚点抽样（m3-5 起，TC-EVAL-05）**：`scripts/eval_anchor_m35.py --demo`（构造会话全链：
  真实检索配方+审计写月库+读回抽样，双后端出数——现库归档
  `eval/reports/m3-5-anchor-sampling-*`）/`--db`（生产月库抽样——**actor_prefix 现硬编码
  `agent:`，现网审计 actor 为裸 user_id，生产使用前须按部署 actor 形态配置**，见 G-30）。
- **MRL 截断复测（m3-5 起，G-8①）**：判据材料 `benchmarks/report-m3-5-g8-mrl-fullset.md`
  （512/256 两档全 0.00pp、分辨率 1.67pp——「截断开放为可选配置」经 env
  `LATTICE_EMBED_MODEL/DIM` 零代码）；复测工件在 `data/bench-results/`（**gitignored 不入库，
  需真实 API key+配额**——不可从仓库复现，m2-5 28q 旧档数字保留于
  `benchmarks/report-m2-5-g8-real-model.md`）。

### 1.ab 内置账号与邀请（m4 起，D25——实现完成 2026-11-20）

- **模式切换**：`LATTICE_AUTH_MODE=sso`（默认，现状 D16/D18）| `local`（内置账号 + 邀请制）。local 形态**必须**显式配 `LATTICE_SESSION_SECRET`（任何环境启动即校验：缺失 / <32 字节 / 仓库公开缺省值一律拒绝）；建议配 `LATTICE_INIT_PASSWORD` 作为首启门禁。`sso` 形态下本地登录端点 404，现有 SSO/JIT/委托/可信行为不变。
- **首次 setup（Web 流程）**：`export LATTICE_AUTH_MODE=local`、
  `export LATTICE_SESSION_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"`，
  按需 `export LATTICE_INIT_PASSWORD=...` → `uv run uvicorn "knowledge_lattice.app:create_app" --factory --port 8000`
  → 打开 <http://127.0.0.1:8000/>，boot 门进入 **Setup 屏**（空库）建首 `sysadmin`
  （可同事务建首组织并任 `org_admin`）；二次/并发 409。无浏览器时等价 REST：
  `curl -s -X POST http://127.0.0.1:8000/api/setup -H 'content-type: application/json' -d '{"username":"admin","password":"<新密码>","init_password":"<LATTICE_INIT_PASSWORD>"}'`
  （`GET /api/setup/status` 先确认 `setup_needed=true`）。`sso` 形态该端点 404。
- **建组织并任命首任管理员**：sysadmin 在「组织」页 `POST /api/orgs`（`id/name/org_admin` 三必填）。local 形态 `org_admin` 填**用户名**（兼容用户 ID）——目标用户须已接受邀请/处于 active（invited/disabled → 409；建组织只挂 membership，不建账号）；sso 形态仍按既有用户 ID。
- **邀请（链接线下交付）**：`org_admin` 在「用户与邀请」页建邀请（`username/email?/role`）
  → 页面**只显示一次**可复制链接（形如 `http://<host>/#invite=<token>`，token 在 fragment、
  不进访问日志）→ **线下交付**（72h、单次、可撤销/重发）；被邀请人打开链接设密码激活并自动登录。
  **链接含 token，勿贴公开渠道**；过期/撤销后在页面重发。无 SMTP——不会自动发邮件（G-31）。
- **重置/停用**：sysadmin 生成一次性重置链接（`POST /api/users/{id}/reset`；停用用户先恢复）；
  接受后 `tv++` 使旧会话失效；停用即时 401（每请求查 `disabled_at`）；`org_admin` 不能重置他人密码。
- **break-glass CLI（`scripts/reset_admin.py`——须 shell + 数据目录访问权限）**：

  ```bash
  # ① 已有用户：从 stdin 读新密码（推荐——不落 shell history；stdout 不打印密码/hash）
  printf '%s\n' "$NEW_PASSWORD" | uv run python scripts/reset_admin.py --username alice --password-stdin

  # ② 已有用户：生成 24 字符随机密码（只打印一次，立即保存）
  uv run python scripts/reset_admin.py --username alice --generate

  # ③ 交互式（TTY）：getpass 两次；非 TTY 会报错并提示 --password-stdin
  uv run python scripts/reset_admin.py --username alice

  # ④ 用户不存在时创建（active + sysadmin）——不加 --create 则退出码 2 并提示
  uv run python scripts/reset_admin.py --username alice --create --password-stdin

  # ⑤ 已有用户：重置口令 + 授予 sysadmin + 启用（清 disabled_at；tv 不回退）
  uv run python scripts/reset_admin.py --username alice --password-stdin --promote

  # 可选 --data-dir（缺省 LATTICE_DATA_DIR，再缺省 data/）
  uv run python scripts/reset_admin.py --username alice --generate --data-dir /srv/lattice/data
  ```

  - 密码来源三选一：`--password-stdin`（推荐）、`--generate`、无参数交互式 `getpass`；
    **没有 `--no-password`**——重置必设密码。强度用 `LATTICE_PASSWORD_MIN_LEN`（默认 10、最小 8）。
  - 退出码：0 成功；2 用户不存在且未 `--create` / 密码不合规 / 参数错误；1 配置或数据库错误。
  - 审计（与写同事务）：已有用户 `auth.password_reset`；`--promote` 按实际变化补
    `user.enabled`/`user.sysadmin_changed`；新建 `user.created`。payload 只含
    user_id/username/actor——**密码/hash 不进审计、stdout、错误消息**。
  - **sqlite 限制**：CLI 走 `store.factory.build_backend`（当前与 app 一致=sqlite）；若环境
    设置了 `LATTICE_PG_DSN`，工厂只告警并仍用 sqlite——已切 PG 的部署暂不能用本 CLI，
    待 factory PG 接线后执行等价操作。`--data-dir` 目录不存在会自动创建。
- **会话/撤销**：本地 session 为 HS256 JWT（12h，localStorage Bearer）；改密/重置 `tv++`；
  登出仅清客户端 token；`LATTICE_SESSION_SECRET` 轮换=所有本地会话失效（需重新登录）。
- **MCP 边界**：本地会话（`via=local`）只用于 Web/REST，MCP 拒绝；local 形态的 agent
  供数走 **D26 agent key**（§1.ac——`via=agent_key`），**无需切 `sso` 形态**；`sso` 形态
  仍走 D18 委托/可信 token（hybrid 账号绑定仍非目标，G-33）。
- **审计**：`auth.login`/`auth.login_refused`/`auth.invite_*`/`user.*`/`instance.setup`；
  密码/token 不入审计；登录失败限流与写放大见 G-32。
- **门禁**（双后端双模式 0 skipped）：

  ```bash
  docker start lattice-pg
  export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice
  scripts/test_gate.sh        # 常规 + python -O；当前 2190+1（pg 臂 809；M4 基线 2090+1）
  # 本机 uv 缓存不可写时：UV_CACHE_DIR="$PWD/.uv-cache" scripts/test_gate.sh
  ```

  数字随批次变化，以 AGENTS §1 / 最近检查点为准。

### 1.ac Agent 密钥（D26，local 形态——issue #34）

> `LATTICE_AUTH_MODE=local` 专属：每 agent 长期凭据（**永不过期、软撤销即时生效**）。
> `sso` 形态管理端点 404、key 认证 401（sso 长期凭据仍走 D18 委托 token）。
> 管理面仅 `org_admin`/`sysadmin` 可见；**明文只显示一次**（库内只存 sha256+前缀）。
> **Agent 侧接入**（端点 `/mcp`、客户端配置、工具清单、上传三步、排错）见
> [docs/MCP-INTEGRATION.md](docs/MCP-INTEGRATION.md)；控制台「运维 → MCP 接入」是同一内容的实例化向导
> （端点取运行时 origin、客户端片段可复制）。

- **签发（Web）**：local 登录 → 左侧导航 **「Agent 密钥」** → 选择本组织 active 成员
  （member/org_admin 均可）→ 填 label（agent 标识，1..64，进审计 `act`）→ 创建 →
  弹窗显示 `lka_...` 明文**一次**，立即复制——关闭后不可再查看。等价 REST：

  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/orgs/org:tax/agent-keys \
    -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d '{"user_id":"u_xxx","label":"agent-a"}'
  ```

  响应 `{key, id, org_id, user_id, user_username, label, prefix, created_by, created_at,
  last_used_at, revoked_at, revoked_by, expires_at}`；`expires_at` 恒 `null`（永不过期）。
- **使用**：明文配给 agent 客户端作 Bearer（`Authorization: Bearer lka_...`）；MCP/REST
  均可用（key 不绕过用户状态/成员关系/ACL）。REST 路径 org 必须等于 key 绑定组织
  （越界 403 `org_mismatch`，sysadmin 的 key 同样受限）；MCP `X-Org-Id` 与 key claim
  不一致 → 400。审计：查询级 `act`=label、`via=agent_key`、`entry=mcp|rest`
  （不同 agent 可区分；`agent_key.created`/`agent_key.revoked` 载荷无明文/摘要）。
- **撤销（泄露应急）**：管理页列表 → 对应 key「撤销」（软撤销，即时生效——下一次请求
  401 `agent key revoked`；行保留供对账，二次撤销幂等 204）。等价
  `DELETE /api/orgs/{org}/agent-keys/{key_id}`。**轮换 = 撤销旧 key + 新建 key**
  （无自动轮转，G-35）。`sysadmin` 可管理任意组织（含停用组织——撤销泄露 key 的应急
  路径）；`org_admin` 仅本组织、不能管停用组织（403 `org_disabled`）。
- **安全建议**：①key 视同口令——不贴群、不进日志、不写代码库；泄露立即撤销；
  ②按 agent 独立签发（不同 label），勿多 agent 共用（审计无法区分）；③定期轮换
  （无强制过期）；④key 继承绑定用户全部权限（**无 key 级 scope**，G-35）——为 agent
  建专门低权成员账号；⑤切 `LATTICE_AUTH_MODE=sso` 后 key 全部失效，改用 D18 委托 token。
- **已知缺口**：G-35（永不过期/无轮转/无细粒度 scope/失败认证不写审计/sysadmin
  跨组织管理——仅 local/POC，生产回 sso）。

### 1.ad 控制台时间显示与时区（2026-11-22 用户走查）

**一句话**：库内和接口一律 UTC，控制台按"显示时区"渲染；显示时区不对 → 改
`LATTICE_DISPLAY_TZ`，**不要动存储**。

- **存储口径（不改，也不许改）**：库内时间恒为 UTC `YYYY-MM-DD HH:MM:SS`
  （`store/taskclock.py` 的 `TS_FMT`；SQLite `CURRENT_TIMESTAMP` 与 PG 连接工厂
  `SET TIME ZONE 'UTC'` 同源）。审计月库分区（按 UTC 月份滚）、备份文件名
  （`-<UTC 时间戳>Z`）、凭证/成员 `expires_at` 契约都建立在这个前提上——把存储改成本地
  时间会同时改掉对账、跨时区部署与既有数据语义。
- **展示口径**：`GET /api/auth/config` 下发 `display_tz`，前端据此把 UTC 换算到该区
  再渲染（存储恒 UTC 的口径见 design §3「PG 连接纪律」；展示分工注记见 `tzdisplay.py`
  模块头）。`display_tz = null` 表示"用浏览器时区"。
- **配置**：`LATTICE_DISPLAY_TZ`（`config.py`，模板见 `.env.example`）

  | 取值 | 行为 |
  |---|---|
  | 留空（缺省） | 前端用**浏览器时区**——谁看谁的本地时间 |
  | `Asia/Shanghai` 等 IANA 名 | 固定该区，所有浏览器一致（**容器里部署推荐显式钉死**：容器默认往往是 UTC） |
  | `server` / `auto` | 探测服务器时区：`TZ` 环境变量 → `/etc/localtime` 符号链接 → `/etc/timezone` |

  非法 IANA 名 → WARNING（日志里可见）并回落到探测结果，不阻断启动（展示层
  fail-open：时区名写错不该让服务起不来）。
- **验证**：`curl -s localhost:8000/api/auth/config | jq .display_tz`；页面上悬停任一
  时间单元格，tooltip 形如 `2026-11-22 09:52:26 · Asia/Shanghai`（前为完整时间、后为
  生效时区）。时间列**表头不再标 `(UTC)`**——区名统一在 tooltip 里给。
- **输入面（到期时间）**：成员/授权 `expires_at` 输入框填的是**显示时区**的墙钟，提交
  前前端换算回 UTC 再落库；表格与 tooltip 显示的是显示时区。**CSV 导入导出保持 UTC**
  （交换格式，导出→导入原样往返，不做换算——CSV 区的提示里已写明）。
- **接 MCP / REST 的 agent 侧**：接口时间仍是 UTC（`expires_at` 序列化为 ISO 8601 Z），
  时区只影响控制台渲染。agent 按 UTC 解释即可。

## 2. 审计分区回溯（R2-P3-8——deploy 场景注记）

`ensure_month_partition`（`store/postgres/audit.py`）只滚**当月/调用时点月份**分区。
deploy 场景注意：

- **月中上线**的存量部署：上线前的历史月份分区未建——历史 `audit_events` 行不存在
  （新库无回溯需求）；若需要为**历史月份预建分区**（合规导出/对账），须显式按月调用：
  ```python
  from datetime import UTC, datetime
  from knowledge_lattice.store.postgres.audit import ensure_month_partition
  ensure_month_partition(conn, when=datetime(2026, 9, 1, tzinfo=UTC))  # 逐月回填
  ```
- 回填的每个分区都会显式落 `BEFORE TRUNCATE` 触发器（PG 16 父表 statement 触发器
  **不克隆分区**——分区必须逐个落，M0b-1 R2 P2-4 实测注记）：TRUNCATE 任何分区
  都会被拦（append-only 红线）。
- **不要**以 TRUNCATE + 重导的方式"修正"审计分区数据——append-only 触发器会拒绝
  （设计即如此；数据修正走追加补偿事件）。

## 3. 迁移注意事项（migrate）

- 双方言迁移框架：sqlite `user_version` / PG `schema_migrations`——版本只前进、
  幂等重放无副作用、失败整事务回滚（含 DDL）；乱序补入小编号迁移 fail-fast。
- **PG 并发启动**：`schema_migrations` 建表在 advisory lock 之外，并发 fresh 连接
  同跑的 CREATE TABLE IF NOT EXISTS 非原子——**真实竞态为 pg_type 唯一键冲突
  （UniqueViolation 23505，主形态）间或 DuplicateTable（42P07）**，由
  DuplicateTable/UniqueViolation 双捕获 + 复核在场分支兜底（M0b-3 P3-6，R2 收口）；
  迁移应用本身经事务级 advisory lock 序列化——双进程并发迁移一者应用、另一者
  锁内重读后干净跳过。
- **sqlite 迁移窗口**：`PRAGMA foreign_keys=OFF` + 事务末 `foreign_key_check`
  ——结束（含失败路径）恢复 `foreign_keys=ON`；**成功路径下恢复失败会记
  WARNING 日志**（`knowledge_lattice.store.sqlite.migrate` logger——连接已坏等
  场景，需人工核对连接态）。
- v1.1（0002）迁移内做了存量向量搬运（`INSERT..SELECT` chunks→chunk_vectors），
  空库/有库两形态均可跑；搬运幂等性由版本记录保证（已应用不重放）。
- **0004（tombstoned_at）升级注意（M2.1，2026-10-28）**：新增列回填取
  **迁移执行时点**为存量 `tombstone=1` 行的 90 天清理起点（保守窗口——存量
  tombstone 实际延后清理，无提前删除风险）；升级后首 90 天内清理量低于理论值
  属预期。新切换事务即时写入 `tombstoned_at` 不受影响。
- **0005（target_version）存量行为注记（M2.4 m2-2，2026-10-29）**：迁移前的
  存量任务行 `target_version=NULL`——取消（cancel）与崩溃耗尽清扫
  （fail_exhausted_tasks → fail_document_version）对 NULL 行**只落任务行
  failed、文档侧不触碰**（可能残留 `pending_status='parsing'` 文档——需人工
  核对或重传新版本）；执行侧 `run_task` 对 NULL 行回退 `_effective_version`
  （文档当前有效版本——M1 口径）。新任务（0005 后创建）恒写目标版本，无此窗口。
- **0007（语义 YAML/构建指针/FTS 表，m2s-3，2026-10-31）升级注意——sqlite·pg 双方言同适用**：
  迁移**不回填** `sem_search_texts`——既有 active 实体在下一次对应源 sync 前
  FTS 第三层（label 模糊）为空；升级后请触发一次各源 sync
  （`POST /semantic/sync/{adapter}`）完成回填；前两层（alias 精确/前缀）不受影响。

## 4. 备份恢复 Runbook（M2-2 起，D24 双后端各一份）

> 依据：design §2 NFR-10（RPO ≤24h / RTO ≤4h——POC 目标）、TC-OPS-05、
> `benchmarks/report-m2-2-ops05.md`（恢复演练实测）、known-gaps G-5/G-13/G-14。
> 自动化形态：maintenance 任务族 `backup_snapshot` 任务体（节流
> `LATTICE_BACKUP_INTERVAL_S` 默认 86400s = RPO 口径）。

> **审计月库读回行注记（m2-6/A5——m2-3 B5 移交收口，2026-11-01）**：
> `read_monthly_events` 读回行经重投影后 **row_hash 不自洽**（读回的语义列是
> 投影非真相源）——消费者**勿以读回行复算哈希链**；链验证一律走 `walk_chain`
> 路径（m2-3 B2 交付——canonical 十语义列重算，六边界 fail-closed）。

### 4.1 SQLite 后端（VACUUM INTO）

```bash
# 快照（主库 + objects + 审计月库 一并）——maintenance backup_snapshot 任务体周期执行
#   产物目录：data/backups/（固定路径，无独立配置项；G-5 快照目的地缺口维持登记）
#   产物清单（m2-3 B3 起）：lattice-<tag>.db（主库 VACUUM INTO）+ objects-<tag>.tar.gz
#     + audit-months-<tag>.tar.gz（tag = UTC 时间戳 + 6 位随机后缀，防同秒覆盖）
# 手动等价（脚本 benchmarks/dr_ops05_drill.py 演练同款路径；文件名为手工示意）
#   sqlite3 data/lattice.db "VACUUM INTO 'data/backups/lattice-manual.db'"
#   tar -czf data/backups/objects-manual.tar.gz -C data objects

# 恢复（新环境）
#   1) 释放快照与 tar 至目标 data/ 目录
#   2) 启动服务（迁移框架自动对齐——user_version 只前进，快照已含则幂等跳过）
#   3) 抽查：检索一组关键词 + 越权矩阵子集（演练脚本内建）
```

- **审计月库 `audit_YYYYMM.db` 备份口径（G-13 关联；v2 随 m2-3 B3 更新）**：自动快照
  **已含月库**——sqlite 备份产物为 `audit-months-<tag>.tar.gz`（全部 `audit_*.db`
  + `-wal/-shm` + `*.seal.json` sidecar；月库 append-only 独立文件、tar 安全），
  恢复时解包回 data/ 后按 prev_hash 链遍历读路径自动纳管。pg 侧月库分区随
  pg_dump 全量覆盖。~~自动快照不含月库文件~~（m2-2 遗留 B3 已于 m2-3 收编）。
- 恢复产物上做**链验证须按 prev_hash 链遍历**，不要依赖 rowid 读序
  （G-13：rowid 跨 VACUUM 不保证保留）。

### 4.2 PostgreSQL 后端（pg_dump）

```bash
# 快照（自定义格式 -Fc；容器形态经 LATTICE_PG_DUMP_CMD 注入）
LATTICE_PG_DUMP_CMD="docker exec lattice-pg pg_dump"   # .env 注入示例
#   实现形态：pg_dump --format=custom --no-owner --no-privileges <DSN>（DSN 为位置参数）
#             经 stdout 流写 data/backups/lattice-<tag>.dump（-f 直写非实现路径）
#   objects 目录同 sqlite（tar.gz）

# 恢复（新库——需 pgvector 预装）
#   1) CREATE EXTENSION vector;                    -- 前置（镜像需含 pgvector 0.8.x）
#   2) pg_restore -d $NEW_DSN /backup/lattice-<tag>.dump
#   3) 启动服务（schema_migrations 框架幂等对齐）+ 检索/矩阵抽查
```

- 分区审计表与主库同库——dump 天然包含；`--no-privileges` 使封存分区的
  REVOKE 不随恢复迁移（sealed 触发器仍在，纵深少一层——恢复后如需收紧
  手动补 REVOKE）。
- **seq 列首次部署窗口（G-14）**：升级到 M2-2+ 版本后，**先单独跑一次连接
  工厂初始化（或任意单连接启动）再放开并发服务**——`audit_events` 分区的
  seq 列首次 ensure 触发全表 rewrite（ACCESS EXCLUSIVE，POC 量级亚秒级）。
- DSN 含密码经 argv 传递对 `ps` 可见（m2-2 遗留 P3-14，记录）——高安全
  环境可用 `.pgpass`/`PGPASSWORD` 环境变量方式部署。

### 4.3 备份失败可发现性

- 工具**缺失**（pg_dump 不在 PATH/容器）→ maintenance stats 记
  `backup_snapshot: "unavailable: …"` + WARNING 日志、任务 done（部署面
  显式状态）。
- 工具**在但失败**（DSN 错/磁盘满）→ 任务 **failed**（error 前缀
  `backup_snapshot`）——任务列表/日志可发现，`data/backups/` 快照产物异常
  应纳入例行巡检。
