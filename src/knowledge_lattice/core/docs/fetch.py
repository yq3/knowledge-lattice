"""MCP fetch 业务逻辑（design §6.1 fetch——M1-2 落）。

按 chunk_id 取前后相邻内容窗口（先搜后读）；**旧版本块返回替代提示**（§6.1
replaced_by 对象——不承诺块级映射、不返回旧内容、不报"不存在"，agent 引用不
失效为幻觉误判——FR-1/P0-2.5）。

可见性口径（块可 fetch ⇔ 文档可见 + version=active_version + tombstone=0）：
- 在用块：编译调用者 ACL（§5.1 编译器）→ 块在可见集 → 返回窗口；
- 非在用块（tombstone / pending 版本）：**文档**可见（visible_docs CTE）→ 返回
  `replaced_by: {doc_id, active_version}`；文档不可见 → 404 语义（与检索零命中
  一致——不泄漏存在性，T21 面）。

分层纪律：读路径全经 StorageBackend（get_chunk / fetch_window /
visible_chunk_ids / visible_doc_ids）；编译经 core/docs/acl。
"""

from __future__ import annotations

from knowledge_lattice.core.docs.acl import compile_acl

__all__ = ["FetchNotFoundError", "fetch_chunks"]


class FetchNotFoundError(Exception):
    """chunk 不存在或文档对调用者不可见（404 语义——不泄漏存在性）。"""


def fetch_chunks(
    backend,
    *,
    user_id: str,
    org_id: str,
    chunk_id: str,
    window: int = 2,
    now: str | None = None,
) -> dict:
    """fetch 工具业务体（§6.1 契约）。

    返回 {"chunks": [{chunk_id, seq, content, page_no}], "replaced_by": None |
    {doc_id, active_version}}；chunk 不存在 / 文档不可见 → FetchNotFoundError。
    """
    plan = compile_acl(backend, user_id, org_id, now=now)  # AclDeniedError 由调用方转 403
    chunk = backend.get_chunk(chunk_id)
    if chunk is None:
        raise FetchNotFoundError(f"chunk not found: {chunk_id!r}")
    doc = backend.get_document(chunk["doc_id"])
    if doc is None or doc["org_id"] != org_id:
        raise FetchNotFoundError(f"chunk not found: {chunk_id!r}")

    is_active = chunk["version"] == doc["active_version"] and chunk["tombstone"] == 0
    if is_active:
        if chunk["rid"] in backend.visible_chunk_ids(plan, [chunk["rid"]]):
            rows = backend.fetch_window(
                chunk["doc_id"],
                chunk["version"],
                chunk["seq"] - window,
                chunk["seq"] + window,
            )
            return {"chunks": rows, "replaced_by": None}
        # 文档维度不可见 → 404 语义（与检索零命中一致——不区分"不可见"与"不存在"）
        raise FetchNotFoundError(f"chunk not found: {chunk_id!r}")

    # 非在用块（tombstone / pending 版本）：文档可见 → 替代提示（不返回旧内容、
    # 不报不存在——FR-1）；文档不可见 → 404（T21：撤销授权后不泄漏 active_version）
    if chunk["doc_id"] in backend.visible_doc_ids(plan, [chunk["doc_id"]]):
        return {
            "chunks": [],
            "replaced_by": {"doc_id": doc["id"], "active_version": doc["active_version"]},
        }
    raise FetchNotFoundError(f"chunk not found: {chunk_id!r}")
