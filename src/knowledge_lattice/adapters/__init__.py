"""第三方依赖与外部服务封装（design §3 adapters/）。

M0a-1 已落：embedder.py（Embedder provider 接口——D12）、reranker.py（Reranker
接口 + none 实现）。
M0a-3 已落：tokenizer.py（jieba 预分词——content_seg/title_seg/查询侧切分）、
parser_docling.py（docling → 统一块结构）、embedder.py 扩展（OpenAI 兼容客户端 +
维度校验 + 指纹探针两档 + EmbeddingGate）。随 M1+ 再落：parser_mineru / llm /
auth_sso / grant_sync。
"""
