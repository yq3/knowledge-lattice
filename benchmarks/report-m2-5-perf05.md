# m2-5 TC-PERF-05 语义 P99 基准报告（R2 修订版——真实边图数据）

> **R2/P2-1 修正**：R1 版的 `rels`（310 条关系）构造后**从未传入
> run_sync**——get_entity 在零边图上空展开，「高扇出/全项达标」证据失效。
> 本版为关系真实入图（`records = recs + rels` 混合序列）后的数据；
> 图形态断言（nodes/edges/truncated）随脚本固化（回归守卫）。
>
> 执行（2026-11-01 R1 / 2026-11-02 R2 重跑，Apple M4，sqlite 本地库）：
> ```bash
> uv run python benchmarks/perf_m2_5.py
> ```
> 工件：`data/bench-results/m2-5-perf05.json`（100 样本 nearest-rank）。
> 样本形态：**万级词典**（10,312 实体：concept 10,000 + 别名 25,624 条
> AC keys）+ **高扇出图**（表 `ods.big` has_column 出向 300 列〔白名单
> ("has_column","table","column")〕+ 模板 `TPL_X` 被 10 场景 uses
> 〔("uses","scenario","template")——src=scenario dst=template〕；关系
> 310 条真实入图，build_stats relations=310）；sync 1.2s + build 5.9s。

## 达标判定（NFR-11 / TC-PERF-05——**P99 为稳态口径**：模糊面懒构建
首调单列〔R2 边界②裁定——docs 批注记归 supervised-coding〕）

| 指标 | 口径 | R1（零边图·作废） | **R2（真实边图）** | 判定 |
|---|---|---|---|---|
| annotate 整体（命中态） | < 20ms | 0.063ms | **0.054ms** | ✅（词典识别与图无关——数字持平佐证） |
| annotate 整体（零命中态） | < 20ms | 0.029ms | 0.029ms | ✅ |
| annotate AC 层（命中态） | < 5ms | 0.010ms | **0.011ms** | ✅ |
| annotate AC 层（零命中态） | < 5ms | 0.004ms | — | ✅ |
| get_entity depth=2（**表扇出 300 列 @fanout_limit=200**） | < 50ms | ~~0.041ms（空展开）~~ | **16.301ms** | ✅（真实边图：nodes=200 / edges=200 / **truncated=True**） |
| get_entity depth=2（**模板被 10 场景 uses**〔expand=["uses<"] 入向〕） | < 50ms | ~~0.034ms（空展开）~~ | **0.574ms** | ✅（nodes=10 / edges=10 / truncated=False） |
| AC 自动机 (org, dict_rev) 懒加载不重复构建 | 同 rev 同实例 | true | `is` 断言 **true** | ✅ |

**全项达标（真实边图）**——表扇出档 P99 16.3ms 为真实展开成本（截断后
200 边 BFS + 物化），仍余量 3×；模板入向 10 场景 0.57ms。

## 图形态断言（R2 固化——零边图回归守卫）

```
table_fanout: nodes=200, edges=200, truncated=True   （300 列 @200 截断）
tpl_fanout:   nodes=10,  edges=10,  truncated=False  （uses< 入向 10 场景）
build_stats:  relations=310, orphan_nodes=10000（万级 concept 词典实体
             无关系——孤立词典为词典面口径，高扇出子图在 table/template 侧）
```

## G-24④ 修复的量化佐证（m2-5 交付项）+ 并发时序收口（R2/P3-6）

| 档 | 修复前形态 | 实测 |
|---|---|---|
| Annotator 构造（AC-only 路径） | 无条件 build_fuzzy_terms——万级词典 ~3.75s pypinyin 固定开销 | **零**（懒构建） |
| fuzzy=True 首调 | 构造期已付 | 3742.4ms（一次摊销——**稳态口径外单列**） |
| fuzzy=True 稳态 | 每片段 dict() 全量复制 | **P99 0.303ms**（索引直读） |
| 并发首建（8 线程 Barrier） | 无锁重复构建 + 中间态可见 | **构建恰 1 次** + 哨兵语义零破坏（R2/P3-6 Lock + 赋值序——`tests/test_sem_g24_hardening.py::test_annotator_fuzzy_lazy_build_thread_safe`） |

## G-24③⑤ 交付说明（代码面）

- **③** search_entities vec 档：`query_embed_timeout_s` 有界等待 + 共享
  embed 熔断器（开路跳过）+ `search.degraded` 降级审计
  （scope=search_entities）；REST/MCP 端点接线；用例 ×3（超时/开路/正常
  零审计+**record_success 复位断言**〔R2/P3-11b〕）双后端；
- **⑤** vec top-k 参数化：`annotate(vec_top=…)` 消费
  `settings.semantic_fuzzy_vec_top`；R2/P3-11a 用例改 monkeypatch 捕获
  `annotate` 实参（vec_top=1 与缺省 3 双向断言——恒真风险根除）。

## 结论

TC-PERF-05 **全绿（真实边图数据）**；G-24③④⑤ 三项收口 + R2 并发时序
加固；known-gaps G-24 分项 ③④⑤ 回写材料（docs 批）。
