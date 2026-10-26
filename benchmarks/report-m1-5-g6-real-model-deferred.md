# B-3① 真实嵌入模型重测——受阻申报与接入方案（G-6 校准路径①）

> 任务：M1-5 B-3①（用户 2026-10-26 拍板：先接真实嵌入模型重测双后端基线——
> TokenBag 代理对跨语言 query 系统性低估，q19/q20/q21 类缺口需真实模型泛化验证）。
> **本段受阻未执行**——申报受阻点与可执行方案，供后续段/M2 直接采用。

## 受阻点（实测核实，2026-10-26）

| 探测 | 结果 |
|---|---|
| 公司网关（现网 qwen3-embedding-4b） | 开发机不可达（内网环境外） |
| 本地 ollama（config 缺省 `127.0.0.1:11434/v1`） | 未安装（`ollama not found`；端口无监听） |
| 本地 sentence-transformers/推理框架 | 未安装（引入 torch 栈 ~GB 级依赖，违背实验段轻量口径） |
| 网络可达面 | pypi/hf-mirror 可达（docling 权重先例）；ollama.com 未经测 |

**结论**：无「零新增重依赖」的可运行真实模型路径——申报受阻而非静默跳过。

## 候选模型选型（本地可部署，按优先序）

| 模型 | 维度 | 形态 | 适用性 | 备注 |
|---|---|---|---|---|
| **qwen3-embedding-0.6b** | 1024（MRL 至 2560） | ollama / GGUF | **首选**——与现网 4b 同族同分词器系，泛化特性最接近；CPU 可跑（0.6B 量级，~1.2GB） | 模型卡声明 MRL 可变维度——可顺带补 G-8① 真实 MRL 截断验证 |
| bge-m3 | 1024 | ollama / sentence-transformers | 多语（zh/en 强）——跨语言 query 缺口验证的业界基线 | 与 qwen 系非同族，作对照 |
| gte-multilingual? | 768 | 同上 | 备选 | 维度与现网 2560 差距大 |
| 现网 qwen3-embedding-4b | 2560 | 公司网关 | **终局口径**——重测须以生产网关为准 | 开发机 CPU 跑 4B 不现实（分钟级/条） |

建议路径：先 ollama + qwen3-embedding-0.6b 出**方向性结论**（跨语言泛化是否
显著优于 token 袋代理），终值以公司网关 4b 重测落笔。

## 接入点（零产品改动）

现有 provider 接口即接入面（D12）：

```bash
# 1) 起 ollama 并拉模型（内网经镜像/离线导入按 RUNBOOK）
ollama serve & ollama pull qwen3-embedding:0.6b   # 或 GGUF 离线导入
# 2) 环境变量指向本地端点（LATTICE_EMBED_* 已支持，config.get_settings）
export LATTICE_EMBED_API_BASE=http://127.0.0.1:11434/v1
export LATTICE_EMBED_MODEL=qwen3-embedding
export LATTICE_EMBED_DIM=1024        # ollama 返回维度（需先探测核对）
# 3) 双后端重测（eval 基线脚本现成）
cd knowledge-lattice
uv run python scripts/eval_baseline.py --backend sqlite
LATTICE_PG_DSN=… uv run python scripts/eval_baseline.py --backend pg
```

注：`scripts/eval_baseline.py` 当前硬编码 TokenBagEmbedder（基线口径注明「真实
模型随 M1-5 接入」）——接入时改为按 `LATTICE_EMBED_API_BASE` 是否指向真实端点
择型（OpenAICompatEmbedder vs TokenBag），~10 行改动，属下一段首项。

## 重测步骤与预期判据

1. **冒烟**：3 哨兵经 provider 嵌入（`FingerprintProbe` 顺路建档）——维度核对
   （=LATTICE_EMBED_DIM，TC-EMB-01 路径）；
2. **双后端基线**：`eval_baseline.py` 双臂各一份（同黄金集同配方）；
3. **判据**（供 supervised-coding 参考）：
   - 主判据：双后端 r@10 偏差是否仍 >2pp（G-6 收窄②钩子）——真实模型下
     AND/OR 语义差的**绝对面**预计收窄（语义近邻补足 token 不齐），但**方向**
     （sqlite OR ≥ pg AND）预计保持；
   - 跨语言面：q19/q20/q21（en/mix）TokenBag 低估是否消失（r@10 → ≥0.5~1.0）；
   - 联动：真实模型到位后同轮补 G-8① 真实 MRL 截断（0.6b 原生 1024 vs 其
     MRL 高维输出的前 1024 截断——模型卡支持）与 G-8② 网关版本抖动采样。
