"""B 组维度 ACL 写链【单测｜M1-2】（design §8 M1.3——多值/写权限/PATCH 校验）。

- 上传/PATCH 值限授权内（TC-AZ-01①~④：新值越权 / 旧值越权 / org_admin 代标
  成功+审计 / 管理权与写权限分离）；
- PATCH pending 期间 409（P0-2.1）；
- 多值维度包含语义 + TC-E2E-04 复跑（PATCH 直接写 document_dimensions、
  检索输出 dims 经 store 聚合回填、维度变更即时生效不回退）；
- 统一空值模板不破坏（无维度行=不受限——PATCH 清值后放行）；
- 维度停用/改可选不影响既有过滤（D5/T4——CTE 快照口径）；
- dot-key 维度 key 写路径拒绝（m0b-1 P3-5 遗留清偿）；
- 操作权限矩阵：普通 member 非 owner 403 / 跨组织 404。
"""

from __future__ import annotations

import pytest

from helpers import NOW_TS, seed_doc_dims, seed_searchable_doc

from test_ver_01_version_chain import HTML_V1, HTML_V2, ORG, _upload

# ============ TC-AZ-01①：上传越权值拒绝（backend 参数化形态） ============


def test_upload_out_of_grants_rejected(ver_env) -> None:
    """u_cn（region=[CN]）上传 region=[OS] → UploadPermissionError（P0-2.1：
    写权限校验在 upload 即做——e2e_01 已有 app 形态，此处双后端单测形态）。"""
    from knowledge_lattice.core.docs.ingest import UploadPermissionError

    with pytest.raises(UploadPermissionError):
        _upload(ver_env, dims={"region": ["OS"]}, owner="u_cn")
    assert ver_env["db"].execute("SELECT count(*) FROM documents").fetchone()[0] == 5, (
        "越权上传不留文档行（matrix 基线 5 篇）"
    )


def test_upload_dotkey_rejected(ver_env) -> None:
    """dot-key 维度 key 写路径拒绝（m0b-1 P3-5——上传侧）：key 含 '.' 一律 400，
    即便库里存在同名 dot-key 维度（造数直插——设计上不允许经写路径进入）。"""
    from knowledge_lattice.core.docs.ingest import UploadValidationError

    with pytest.raises(UploadValidationError, match="dot-key"):
        _upload(ver_env, dims={"re.gion": ["CN"]})


# ============ TC-AZ-01②③④：PATCH 取值限操作者授权内 ============


@pytest.fixture()
def own_doc(ver_env):
    """d_cn_own：owner=u_cn、region=[CN]、tax_type 无值（#40 P1-R2 造数口径——
    自有文档防先撞操作权限 403；tax_type 置空防结果集全维度校验混淆）。"""
    seed_searchable_doc(
        ver_env["db"], "d_cn_own", dims={"region": ["CN"]}, owner_user_id="u_cn"
    )
    return ver_env


def _patch_dims(env, doc_id: str, dims: dict, actor: str):
    """PATCH 业务体（core 层直调——REST 映射见 test_ver_02 的 app 形态）。"""
    env["service"].patch_document_dims(
        org_id=ORG, doc_id=doc_id, dims=dims, actor_user_id=actor
    )


def test_patch_new_value_out_of_grants(own_doc) -> None:
    """TC-AZ-01②前半：u_cn PATCH 自己的 d_cn_own region [CN]→[OS]——新值越权 403。"""
    from knowledge_lattice.core.docs.ingest import UploadPermissionError

    env = own_doc
    with pytest.raises(UploadPermissionError, match="new value"):
        _patch_dims(env, "d_cn_own", {"region": ["OS"]}, actor="u_cn")
    # 维度行不变（拒绝零副作用）
    assert env["backend"].get_document_dims("d_cn_own") == {"region": ["CN"]}


def test_patch_old_value_out_of_grants(own_doc) -> None:
    """TC-AZ-01②后半：u_cn PATCH [CN,OS]→[CN]——旧值 OS 不在其授权 → 403
    （新旧取值均须在操作者授权内——防操作自己看不见的状态）。"""
    from knowledge_lattice.core.docs.ingest import UploadPermissionError

    env = own_doc
    seed_doc_dims(env["db"], "d_cn_own", {"region": ["OS"]})  # 造数扩为 [CN,OS]
    with pytest.raises(UploadPermissionError, match="current value"):
        _patch_dims(env, "d_cn_own", {"region": ["CN"]}, actor="u_cn")
    assert env["backend"].get_document_dims("d_cn_own") == {
        "region": ["CN", "OS"]
    }, "拒绝零副作用"


def test_patch_by_admin_full_delegates_with_audit(own_doc) -> None:
    """TC-AZ-01③：admin_full（org_admin，region=[CN,OS]）代标 region=[OS]——
    成功且管理动作进审计（outbox）；检索即时生效（D6）。"""
    env = own_doc
    matrix, backend = env["db"], env["backend"]
    _patch_dims(env, "d_cn_own", {"region": ["OS"]}, actor="admin_full")

    assert backend.get_document_dims("d_cn_own") == {"region": ["OS"]}
    # 检索输出 dims 经 store 聚合回填（TC-E2E-04 复跑——PATCH 直接写
    # document_dimensions、检索即时反映、不重嵌）
    plan = matrix.compile_acl("u_os", ORG, now=NOW_TS)
    hits = backend.recall_fts(["common"], plan, top_k=50)
    by_doc = {h["doc_id"]: h["dims"] for h in hits}
    assert by_doc.get("d_cn_own") == {"region": ["OS"]}, "PATCH 后 dims 即时回填"
    # 审计：document.dims_change 事件已入 outbox（业务写与审计同事务纪律——M2 月库搬运）
    rows = matrix.execute(
        "SELECT event_type, payload_json FROM audit_outbox WHERE event_type = 'document.dims_change'"
    ).fetchall()
    assert rows and "d_cn_own" in rows[-1][1] and "admin_full" in rows[-1][1]


def test_patch_by_admin_tax_no_grant_rejected(own_doc) -> None:
    """TC-AZ-01④：admin_tax（org_admin、无维度授权）PATCH——操作权限放行但取值
    越权仍拒（管理权与写权限分离——与 TC-AZ-03 呼应）。"""
    from knowledge_lattice.core.docs.ingest import UploadPermissionError

    env = own_doc
    with pytest.raises(UploadPermissionError, match="new value"):
        _patch_dims(env, "d_cn_own", {"region": ["OS"]}, actor="admin_tax")


def test_patch_operation_permission_and_not_found(own_doc) -> None:
    """操作权限矩阵：普通 member 非 owner（u_full PATCH d_cn_own）→ 403；
    跨组织/不存在 → 404。"""
    from knowledge_lattice.core.docs.ingest import (
        UploadNotFoundError,
        UploadPermissionError,
    )

    env = own_doc
    with pytest.raises(UploadPermissionError):
        _patch_dims(env, "d_cn_own", {"region": ["CN"]}, actor="u_full")
    with pytest.raises(UploadNotFoundError):
        _patch_dims(env, "doc:none", {"region": ["CN"]}, actor="admin_full")


def test_patch_pending_409(ver_env) -> None:
    """PATCH 文档维度 pending 期间 409（P0-2.1——切换事务会以 pending_dims_json
    覆盖 document_dimensions，PATCH 与其竞态一律拒绝）。"""
    from knowledge_lattice.core.docs.ingest import UploadConflictError

    env = ver_env
    doc_id, task1 = _upload(env, dims={"region": ["CN"], "tax_type": ["VAT"]})
    env["service"].run_task(task1)
    from test_ver_01_version_chain import _overwrite_v2_to_lexical

    _overwrite_v2_to_lexical(env, doc_id, dims={"region": ["CN"]})

    with pytest.raises(UploadConflictError):
        env["service"].patch_document_dims(
            org_id=ORG, doc_id=doc_id, dims={"region": ["OS"]}, actor_user_id="u_full"
        )


def test_patch_unknown_dim_or_value_rejected(own_doc) -> None:
    """PATCH 未知维度 key / 未知取值 / dot-key → 400（UploadValidationError）。"""
    from knowledge_lattice.core.docs.ingest import UploadValidationError

    env = own_doc
    for dims in ({"no_such_dim": ["CN"]}, {"region": ["NO_VALUE"]}, {"re.gion": ["CN"]}):
        with pytest.raises(UploadValidationError):
            _patch_dims(env, "d_cn_own", dims, actor="u_cn")


# ============ R2 B-1①：覆盖上传校验文档当前（旧）维度值 ∈ 操作者授权 ============


def test_r2_b1_overwrite_requires_current_dims_in_grants(own_doc) -> None:
    """B-1①（FR-4 严格口径，用户拍板 2026-10-25）：覆盖上传须校验文档**当前
    （旧）维度值** ∈ 操作者 grants——Committer 场景：u_cn 文档 region=[CN] →
    admin PATCH 成 [OS] → u_cn 覆盖上传（新值 [CN] 在其授权内）应 403 拒绝
    （防把文档拉回自己可见域而不曾看见现行状态）。首上传无旧值不涉及。"""
    from knowledge_lattice.core.docs.ingest import UploadPermissionError

    env = own_doc
    # 造数：admin_full 把 d_cn_own（owner=u_cn）PATCH 成 region=[OS]
    _patch_dims(env, "d_cn_own", {"region": ["OS"]}, actor="admin_full")
    assert env["backend"].get_document_dims("d_cn_own") == {"region": ["OS"]}

    # u_cn（region=[CN]）覆盖上传——新值 [CN] 在授权内、旧值 [OS] 不在 → 403
    doc = env["backend"].get_document("d_cn_own")
    content = (
        "<html><body><h1>覆盖上传内容</h1><p>伽马条款测试正文。</p></body></html>"
    ).encode("utf-8")
    with pytest.raises(UploadPermissionError, match="current value"):
        env["service"].create_document(
            org_id=ORG, dataset_id="ds:vat_lib", title="覆盖",
            dims={"region": ["CN"]}, owner_user_id=doc["owner_user_id"],
            file_bytes=content, mime_type="text/html", filename="g.html",
            doc_id="d_cn_own",
        )

    # 对照①：admin_full（region=[CN,OS]，旧值 [OS] 在授权内）覆盖上传放行
    _, task_ok = env["service"].create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="覆盖",
        dims={"region": ["CN"]}, owner_user_id="admin_full",
        file_bytes=content, mime_type="text/html", filename="g2.html",
        doc_id="d_cn_own",
    )
    doc = env["backend"].get_document("d_cn_own")
    assert doc["pending_version"] == 2 and doc["active_version"] == 1, "对照①放行（旧值在授权内）"
    env["service"].run_task(task_ok)

    # 对照②：旧值含部分越权（region=[CN,OS]、操作者仅 [CN]）同样拒绝——逐值校验
    from helpers import seed_doc_dims as _seed_dims

    _seed_dims(env["db"], "d_cn_own", {"region": ["OS"]})  # 切换后已是 [CN]→ 补回 [OS]
    with pytest.raises(UploadPermissionError, match="current value"):
        env["service"].create_document(
            org_id=ORG, dataset_id="ds:vat_lib", title="覆盖2",
            dims={"region": ["CN"]}, owner_user_id="u_cn",
            file_bytes=content, mime_type="text/html", filename="g3.html",
            doc_id="d_cn_own",
        )


def test_r2_p3_2_patch_failed_pending_still_409(ver_env) -> None:
    """R2 P3-2：PATCH 对 pending_status='failed' 的从严 409 分支直测（口径①：
    PATCH 409 = pending 存在即拒——含 failed，防 pending_dims_json 覆盖竞态；
    与上传侧「failed 放行」形成对照）。"""
    from knowledge_lattice.core.docs.ingest import UploadConflictError

    env = ver_env
    doc_id, task1 = _upload(env)
    env["service"].run_task(task1)

    # 造 failed pending：覆盖上传 v2 在 embed 阶段失败
    env["embedder"].fail = True
    _, task2 = env["service"].create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="v2", dims={"region": ["CN"]},
        owner_user_id="u_full", file_bytes=HTML_V2, mime_type="text/html",
        filename="v2.html", doc_id=doc_id,
    )
    with pytest.raises(Exception):  # noqa: B017
        env["service"].run_task(task2)
    doc = env["backend"].get_document(doc_id)
    assert doc["pending_version"] == 2 and doc["pending_status"] == "failed", (
        "前置：failed pending 在列（上传侧对 failed 攧行——对照）"
    )

    # PATCH 仍 409（从严口径——pending_status='failed' 分支）
    with pytest.raises(UploadConflictError):
        env["service"].patch_document_dims(
            org_id=ORG, doc_id=doc_id, dims={"region": ["OS"]}, actor_user_id="u_full"
        )


def test_patch_multivalue_and_empty_semantics(own_doc) -> None:
    """多值维度 PATCH（u_full region=[CN,OS] 全授权）：[CN]→[CN,OS] 多值生效、
    包含语义正确；清空值 → 空值放行（统一空值模板不破坏——B3）。"""
    env = own_doc
    matrix, backend = env["db"], env["backend"]
    _patch_dims(env, "d_cn_own", {"region": ["CN", "OS"]}, actor="admin_full")
    assert backend.get_document_dims("d_cn_own") == {"region": ["CN", "OS"]}

    # 多值包含语义：u_os（region=[OS]）与 u_cn（region=[CN]）均可见（交集非空）；
    # admin_tax（region 零授权）不可见（有值需交集——T22 单条件）
    for user, expect_visible in (("u_os", True), ("u_cn", True), ("admin_tax", False)):
        plan = matrix.compile_acl(user, ORG, now=NOW_TS)
        hits = {h["doc_id"] for h in backend.recall_fts(["common"], plan, top_k=50)}
        assert ("d_cn_own" in hits) is expect_visible, user

    # 清空（空列表）→ 无维度行 = 空值放行（不受限——统一空值模板）
    _patch_dims(env, "d_cn_own", {"region": []}, actor="admin_full")
    assert backend.get_document_dims("d_cn_own") == {}
    plan = matrix.compile_acl("admin_tax", ORG, now=NOW_TS)
    hits = {h["doc_id"] for h in backend.recall_fts(["common"], plan, top_k=50)}
    assert "d_cn_own" in hits, "空值放行（B3：统一空值模板不破坏）"


def test_dimension_config_change_no_filter_effect(own_doc) -> None:
    """B4/D5：维度停用（enabled=0）/必选改可选（required 1→0）不影响既有过滤——
    PATCH 写链完成后翻转维度配置，同 Plan 重执行结果稳定（CTE 快照口径）、
    重新编译可见集亦不变（生命周期与过滤解耦）。"""
    env = own_doc
    matrix, backend = env["db"], env["backend"]

    def _visible(user: str) -> set[str]:
        plan = matrix.compile_acl(user, ORG, now=NOW_TS)
        return {h["doc_id"] for h in backend.recall_fts(["common"], plan, top_k=50)}

    baseline_cn = _visible("u_cn")
    assert "d_cn_own" in baseline_cn

    matrix.execute(
        "UPDATE dimensions SET required = 0, enabled = 0 WHERE org_id = ? AND key = 'region'",
        (ORG,),
    )
    assert _visible("u_cn") == baseline_cn, "维度配置变更不影响既有过滤（T4/B4）"
