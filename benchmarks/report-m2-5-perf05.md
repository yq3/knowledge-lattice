# m2-5 TC-PERF-05 语义 P99 基准报告（A8——m2s-6 移交性能兜底轮）

> 执行（2026-11-01，Apple M4，sqlite 本地库）：
> ```bash
> uv run python benchmarks/perf_m2_5.py
> ```
> 工件：`data/bench-results/m2-5-perf05.json`（100 样本 nearest-rank）。
> 样本形态：**万级词典**（10,000 concept + 10,312 实体总量：别名 5,000）+
> **高扇出图**（一表 300 列 has_column / 一模板被 10 场景关联——语义 fixture
> 口径的放大形态）；sync 1.2s + build 5.9s。

## 达标判定（NFR-11 / TC-PERF-05）

| 指标 | 口径 | 实测 P99 | 判定 |
|---|---|---|---|
| annotate 整体（命中态） | < 20ms | **0.063ms** | ✅（余量 317×） |
| annotate 整体（零命中态） | < 20ms | **0.048ms** | ✅ |
| annotate AC 层（命中态） | < 5ms | **0.010ms** | ✅（余量 500×） |
| annotate AC 层（零命中态） | < 5ms | **0.004ms** | ✅ |
| get_entity depth=2（表扇出 300 列） | < 50ms | **0.041ms** | ✅ |
| get_entity depth=2（模板扇出 10 场景） | < 50ms | **0.034ms** | ✅ |
| AC 自动机 (org, dict_rev) 懒加载不重复构建 | 同 rev 同实例 | `is` 断言 **true** | ✅ |

**全项达标**（微秒级实测 vs 毫秒级阈值——万级词典下 AC 扫描天然 O(文本长度)、
与词典规模无关；高扇出展开走 store BFS 有 fanout_limit 上界）。

## G-24④ 修复的量化佐证（m2-5 交付项）

| 档 | 修复前形态 | 修复后实测 |
|---|---|---|
| Annotator 构造（AC-only 路径） | 无条件 build_fuzzy_terms——万级词典 **~3.75s** pypinyin 固定开销 | **零**（懒构建——`fuzzy=True` 首调才支付） |
| fuzzy=True 首调 | 构造期已付（首请求即慢） | 3752ms（一次摊销） |
| fuzzy=True 稳态 | 每片段 dict() 全量复制（万级索引 × 片段数） | **P99 0.307ms**（索引直读） |

万级词典下 G-24④ 的修复把 **AC-only 主路径**（annotate/search 缺省形态、
auto_entities 识别路）从「每次构建/重启首个请求 3.75s」恢复为微秒级——
TC-PERF-05 整体 P99 的达标以本修复为前提（修复前 annotate 首调 3.7s +
>20ms，达标不可言）。

## G-24③⑤ 交付说明（代码面，随本报告一并核验）

- **③** search_entities vec 档：`query_embed_timeout_s` 有界等待（500ms 档——
  非 30s）+ 共享 embed 熔断器（开路跳过不发调用）+ `search.degraded` 降级
  审计（scope=search_entities——§5.2 同源口径）；REST/MCP 端点已接线传
  `service.breakers`；用例 ×3（超时/开路/正常零审计）双后端；
- **⑤** vec top-k 参数化：`annotate(vec_top=…)` 消费
  `settings.semantic_fuzzy_vec_top`（`LATTICE_SEM_FUZZY_VEC_TOP` 端到端）；
  硬编码 3 根除；用例 ×2。

## 结论

TC-PERF-05 **全绿**——无需 M1-5 式「不达标如实申报」；G-24③④⑤ 三项 P3 残留
全部收口（known-gaps G-24 分项 ③④⑤ 回写材料——docs 批）。
