"""m3-1 D 组（issue #20 be-①②——契约冻结评论 issuecomment-6649900631，逐条
对照实装；双后端 REST 端到端参数化）。

D-① GET /api/orgs/{org}/documents（文档列表）：
- 参数：dataset?（单库过滤）· limit?（默认 50，1..200）· offset?（默认 0）；
- 响应：{documents: [{doc_id, title, dataset, dims, active_version,
  active_status, active_error, pending_version, pending_status, chunk_count,
  quality_open, updated_at, visible}], total}；
- 语义：org_admin=本组织全量（visible 按行回填——调用者本人 ACL 视角）；
  member=服务端 ACL 过滤后仅可见行（visible 恒 true）；行集不含 tombstone、
  含 pending 处理中文档；dims 与检索路同源（document_dimensions——D22）；
  排序 updated_at DESC。

D-② GET /api/orgs/{org}/documents/{doc_id}/explain?user_id?（可见性解释）：
- 权限：user_id 缺省=解释自己（可见/不可见均可）；给他人解释须 org_admin
  （否则 403）；文档不在本组织 404；
- 行序：membership（第 0 步——过期即 deny 收口）→ 逐 active 维度（按 key 序）：
  文档有值→与有效授权求交（交集 allow / 无交集 deny / 授权已过期 detail
  注明等效无授权）；文档空值→skip 放行；retired 维度不出现；
- 语义红线：**只解释不裁定**——结论与 ACL 编译产物同口径（矩阵用户×文档
  全组合断言 explain.visible == visible_doc_ids(compile_acl) 判定）。
"""

from __future__ import annotations

import pytest

from conftest import ORG
from helpers import dim_id_for

pytestmark = pytest.mark.usefixtures("rest_env")


def _hdr(env, uid: str) -> dict:
    return {"Authorization": f"Bearer {env['tokens'][uid]}"}


# 矩阵 5 文档的可视性预期（u_cn region=[CN]、无 tax_type 授权）：
#   d_cn(region=CN,tax_type=VAT) ✗——tax_type=VAT 带值与空授权无交集；
#   d_multi(region=[CN,OS],tax_type 无值) ✓（region 交集 CN + 空值放行）；
#   d_empty_region(全无值) ✓（空值放行）；d_cit(tax_type=CIT) ✗；d_os ✗


def _docs(resp) -> dict[str, dict]:
    return {d["doc_id"]: d for d in resp["documents"]}


# ============ D-①：文档列表 ============


def test_d1_admin_full_rowset_with_visible(rest_env) -> None:
    """org_admin 面：本组织全量行集（5 文档全出）+ visible 按行回填（admin_tax
    无维度授权——全部带值文档不可见、空值文档可见）+ total + 契约字段全集。"""
    client, env = rest_env["client"], rest_env
    r = client.get(f"/api/orgs/{ORG}/documents", headers=_hdr(env, "admin_tax"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    docs = _docs(body)
    assert set(docs) == {"d_cn", "d_multi", "d_empty_region", "d_cit", "d_os"}
    row = docs["d_cn"]
    assert {
        "doc_id", "title", "dataset", "dims", "active_version", "active_status",
        "active_error", "pending_version", "pending_status", "chunk_count",
        "quality_open", "updated_at", "visible",
    } <= set(row), row
    assert row["dataset"] == "ds:vat_lib"  # 单文档 GET 同构（dataset id）
    assert row["active_version"] == 1 and row["chunk_count"] >= 1
    # dims 聚合与检索路同源（document_dimensions——D22）
    assert row["dims"] == {"region": ["CN"], "tax_type": ["VAT"]}
    assert docs["d_multi"]["dims"] == {"region": ["CN", "OS"]}
    assert docs["d_empty_region"]["dims"] == {}
    # admin_tax 无维度授权：带值文档 visible=False、空值文档 True
    assert docs["d_cn"]["visible"] is False
    assert docs["d_empty_region"]["visible"] is True
    assert docs["d_cit"]["visible"] is False  # tax_type=CIT 非空值无交集


def test_d1b_admin_visible_matches_own_acl(rest_env) -> None:
    """admin 面 visible 回填口径 = 调用者本人 ACL 编译产物（admin_full 持
    region=[CN,OS]+tax_type=[VAT]——d_cit 因 tax_type=CIT 无交集不可见，
    其余四篇可见）。"""
    client, env = rest_env["client"], rest_env
    r = client.get(f"/api/orgs/{ORG}/documents", headers=_hdr(env, "admin_full"))
    docs = _docs(r.json())
    visible_by_id = {d: docs[d]["visible"] for d in docs}
    assert visible_by_id == {
        "d_cn": True, "d_multi": True, "d_empty_region": True,
        "d_os": True, "d_cit": False,
    }, visible_by_id


def test_d2_member_acl_filtered_rowset(rest_env) -> None:
    """member 面：服务端 ACL 过滤后仅可见行（visible 恒 true）——u_cn 见
    d_multi/d_empty_region（region 交集 CN + 空值放行），不见 d_cn/d_cit
    （tax_type 带值与空授权无交集）与 d_os；total=过滤后计数。"""
    client, env = rest_env["client"], rest_env
    r = client.get(f"/api/orgs/{ORG}/documents", headers=_hdr(env, "u_cn"))
    assert r.status_code == 200, r.text
    body = r.json()
    docs = _docs(body)
    assert set(docs) == {"d_multi", "d_empty_region"}
    assert body["total"] == 2
    assert all(d["visible"] is True for d in docs.values())


def test_d3_pagination_and_dataset_filter(rest_env) -> None:
    """limit/offset 分页 + dataset 单库过滤 + 排序 updated_at DESC + limit
    边界 422（0/201 越界）。"""
    client, env = rest_env["client"], rest_env
    # 追加 4 篇文档（共 9）+ 显式 updated_at 造数（双方言 NULL 排序差异规避）
    from helpers import seed_searchable_doc

    doc_order = ["d_cn", "d_multi", "d_empty_region", "d_cit", "d_os"]
    for i in range(4):
        seed_searchable_doc(env["db"], f"d_page{i}", dims={"region": ["CN"]})
        doc_order.append(f"d_page{i}")
    for i, doc in enumerate(doc_order):
        env["db"].execute(
            "UPDATE documents SET updated_at = ? WHERE id = ?",
            (f"2026-01-{i + 1:02d} 00:00:00", doc),
        )
    env["db"].commit()

    admin = _hdr(env, "admin_tax")
    r1 = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                    params={"limit": 3})
    body1 = r1.json()
    assert len(body1["documents"]) == 3 and body1["total"] == 9
    r2 = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                    params={"limit": 3, "offset": 3})
    body2 = r2.json()
    ids1 = [d["doc_id"] for d in body1["documents"]]
    ids2 = [d["doc_id"] for d in body2["documents"]]
    assert not set(ids1) & set(ids2), "分页不得重叠"
    assert len(ids2) == 3
    r3 = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                    params={"limit": 3, "offset": 6})
    assert len(r3.json()["documents"]) == 3  # 9 篇恰三页
    r4 = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                    params={"offset": 9})
    assert r4.json()["documents"] == []

    # 排序：updated_at DESC（全量页逐行非升序断言）
    rall = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                      params={"limit": 200})
    stamps = [d["updated_at"] for d in rall.json()["documents"]]
    assert stamps == sorted(stamps, reverse=True), stamps

    # dataset 过滤
    from helpers import seed_dataset

    seed_dataset(env["db"], ORG, "ds:other")
    seed_searchable_doc(env["db"], "d_other", dataset_id="ds:other",
                        dims={})
    env["db"].commit()
    rf = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                    params={"dataset": "ds:other"})
    fdocs = _docs(rf.json())
    assert set(fdocs) == {"d_other"} and rf.json()["total"] == 1

    # limit 边界 422
    assert client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                      params={"limit": 0}).status_code == 422
    assert client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                      params={"limit": 201}).status_code == 422
    # 不存在 dataset 过滤 → 空集（200——过滤器非存在性断言）
    rnone = client.get(f"/api/orgs/{ORG}/documents", headers=admin,
                       params={"dataset": "ds:none"})
    assert rnone.status_code == 200 and rnone.json()["total"] == 0


def test_d4_pending_doc_and_quality_open(rest_env) -> None:
    """行集含 pending 处理中文档（双态字段与单文档 GET 同构）+ quality_open
    计数（open 态 flags）。"""
    client, env = rest_env["client"], rest_env
    from helpers import seed_document

    seed_document(env["db"], "d_pend", org_id=ORG, dataset_id="ds:vat_lib",
                  owner_user_id="u_owner", title="处理中文档")
    env["db"].execute(
        "UPDATE documents SET pending_version = 1, pending_status = 'parsing'"
        " WHERE id = ?", ("d_pend",),
    )
    # d_cn 造 2 条 open + 1 条 resolved quality flags（chunk 用真实行——FK）
    for i, state in enumerate(("open", "open", "resolved")):
        env["db"].execute(
            "INSERT INTO quality_flags(id, chunk_id, doc_id, reason, state)"
            " VALUES(?, ?, ?, ?, ?)",
            (f"qf:{i}", "chk:d_cn:v1:1", "d_cn", "vector_crowding", state),
        )
    env["db"].commit()

    admin = _hdr(env, "admin_tax")
    r = client.get(f"/api/orgs/{ORG}/documents", headers=admin)
    docs = _docs(r.json())
    assert "d_pend" in docs, "pending 处理中文档须在行集"
    pend = docs["d_pend"]
    assert pend["active_version"] == 0 and pend["active_status"] is None
    assert pend["pending_version"] == 1 and pend["pending_status"] == "parsing"
    assert pend["chunk_count"] == 0  # 无在用块
    assert docs["d_cn"]["quality_open"] == 2  # 仅 open 态计数
    # member 面（u_cn 对 d_cn 不可见——tax_type 带值与空授权无交集；行集
    # 不含不可见行=数量不泄露，quality_open 不外泄）
    r2 = client.get(f"/api/orgs/{ORG}/documents", headers=_hdr(env, "u_cn"))
    assert "d_cn" not in _docs(r2.json())


# ============ D-②：可见性解释 ============


def test_d5_explain_self_rows_and_order(rest_env) -> None:
    """explain 自解释：u_cn 对 d_multi（region 交集 + tax_type 空值）visible
    =true——行序 [membership, region, tax_type]（membership 第 0 步 + 维度
    按 key 序）；verdict 全 allow/skip、维度行带 key/label。对照：u_cn 对
    d_cn（tax_type=VAT 带值与空授权无交集）visible=false。"""
    client, env = rest_env["client"], rest_env
    r = client.get(
        f"/api/orgs/{ORG}/documents/d_multi/explain", headers=_hdr(env, "u_cn"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_id"] == "d_multi" and body["visible"] is True
    kinds = [(row["kind"], row.get("key")) for row in body["rows"]]
    assert kinds == [
        ("membership", None), ("dimension", "region"), ("dimension", "tax_type"),
    ], kinds
    for row in body["rows"]:
        assert {"kind", "label", "verdict", "detail"} <= set(row)
    dim_rows = [row for row in body["rows"] if row["kind"] == "dimension"]
    assert dim_rows[0]["label"] == "region"  # 矩阵造数 name=key

    # 对照：u_cn × d_cn——tax_type=VAT 带值与空授权无交集 → deny
    r1 = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_cn"))
    body1 = r1.json()
    assert body1["visible"] is False
    by_key = {row.get("key"): row for row in body1["rows"]}
    assert by_key["region"]["verdict"] == "allow"
    assert by_key["tax_type"]["verdict"] == "deny"


def test_d6_explain_deny_and_skip(rest_env) -> None:
    """deny/skip 行：u_cn 对 d_os（region 无交集 deny → visible=false）；
    对 d_empty_region（region 空值 skip 放行——visible=true）。"""
    client, env = rest_env["client"], rest_env
    r = client.get(
        f"/api/orgs/{ORG}/documents/d_os/explain", headers=_hdr(env, "u_cn"))
    body = r.json()
    assert body["visible"] is False
    region_row = next(row for row in body["rows"] if row.get("key") == "region")
    assert region_row["verdict"] == "deny"

    r2 = client.get(
        f"/api/orgs/{ORG}/documents/d_empty_region/explain",
        headers=_hdr(env, "u_cn"))
    body2 = r2.json()
    assert body2["visible"] is True
    region2 = next(row for row in body2["rows"] if row.get("key") == "region")
    assert region2["verdict"] == "skip", "文档空值维度 skip 放行"
    # d_cit：region skip + tax_type deny（CIT 与 u_cn 空授权无交集）
    r3 = client.get(
        f"/api/orgs/{ORG}/documents/d_cit/explain", headers=_hdr(env, "u_cn"))
    body3 = r3.json()
    assert body3["visible"] is False
    by_key = {row.get("key"): row for row in body3["rows"]}
    assert by_key["region"]["verdict"] == "skip"
    assert by_key["tax_type"]["verdict"] == "deny"


def test_d7_explain_expired_grant_detail(rest_env) -> None:
    """授权已过期 detail 注明等效无授权：u_expired_grant（region CN 授权过期 +
    tax_type VAT 有效）对 d_cn——region deny 且 detail 注明过期；
    tax_type allow；visible=false。"""
    client, env = rest_env["client"], rest_env
    r = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain",
        headers=_hdr(env, "u_expired_grant"))
    body = r.json()
    assert body["visible"] is False
    by_key = {row.get("key"): row for row in body["rows"]}
    assert by_key["region"]["verdict"] == "deny"
    assert "过期" in by_key["region"]["detail"], by_key["region"]
    assert by_key["tax_type"]["verdict"] == "allow"


def test_d8_explain_membership_expired_and_missing(rest_env) -> None:
    """membership 第 0 步：过期成员**自解释**在 org_scoped 即 403（与检索路
    compile_acl 同语义——第 0 步收口）；org_admin 给过期成员解释 → membership
    deny（过期行 detail 注明 expires_at）；给无成员关系用户（u_gl）解释 →
    membership deny（无行），维度行照常展开（不泄露他人授权面——仅交集
    verdict）。m3-2 边界①（用户裁定选 A）：membership deny 下维度行 detail
    改「成员关系无效，维度行仅供参考」——不得声称「有效授权 []」。"""
    client, env = rest_env["client"], rest_env
    # 过期成员自解释：org_scoped 成员校验 403（与检索路同口径）
    r = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain",
        headers=_hdr(env, "u_expired_member"))
    assert r.status_code == 403

    # org_admin 给过期成员解释：membership deny（过期行注明）
    r1 = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain",
        headers=_hdr(env, "admin_tax"),
        params={"user_id": "u_expired_member"},
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["visible"] is False
    m_row = body1["rows"][0]
    assert m_row["kind"] == "membership" and m_row["verdict"] == "deny"
    assert "过期" in m_row["detail"]
    # 边界①：membership deny 下带值维度行 = 参考口径（不声称「有效授权 []」）
    dim_rows = [row for row in body1["rows"] if row["kind"] == "dimension"]
    valued = [row for row in dim_rows if row["verdict"] == "deny"]
    assert valued, "带值维度行应保持展开（裁定 A——管理面对账信息）"
    for row in valued:
        assert "成员关系无效" in row["detail"] and "仅供参考" in row["detail"], row
        assert "有效授权" not in row["detail"], row

    # org_admin 给无成员关系用户（u_gl）解释
    r2 = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain",
        headers=_hdr(env, "admin_tax"), params={"user_id": "u_gl"})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["rows"][0]["verdict"] == "deny"  # 无成员关系
    assert body2["visible"] is False
    # 同口径：无成员关系的维度 deny 行也是参考文案
    for row in body2["rows"]:
        if row["kind"] == "dimension" and row["verdict"] == "deny":
            assert "成员关系无效" in row["detail"], row


def test_d9_explain_permission_boundaries(rest_env) -> None:
    """explain 权限：member 解释他人 → 403；org_admin 解释他人 → 200；
    member 自解释 200；文档不在本组织 → 404；跨组织调用 → 403。"""
    client, env = rest_env["client"], rest_env
    # member 解释他人 403
    assert client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_full"),
        params={"user_id": "u_cn"},
    ).status_code == 403
    # org_admin 解释他人 200
    assert client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "admin_tax"),
        params={"user_id": "u_cn"},
    ).status_code == 200
    # 自解释 200（显式 user_id=自己——member 亦可为本人解释）
    assert client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_full"),
        params={"user_id": "u_full"},
    ).status_code == 200
    # 文档不在本组织 404（org:tax 路径 + 他组织文档不存在）
    assert client.get(
        f"/api/orgs/{ORG}/documents/doc:none/explain",
        headers=_hdr(env, "u_full"),
    ).status_code == 404
    # 跨组织调用 403（u_gl 对 org:tax——org_scoped 承载）
    assert client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_gl"),
    ).status_code == 403


def test_d10_explain_retired_dimension_absent(rest_env) -> None:
    """retired 维度不出现：d_cn 挂 region 值，退役 tax_type 后 explain 行集
    不含 tax_type（唯一放宽路径——过滤面同口径）。"""
    client, env = rest_env["client"], rest_env
    env["db"].execute(
        "UPDATE dimensions SET status = 'retired'"
        " WHERE org_id = ? AND key = 'tax_type'", (ORG,),
    )
    env["db"].commit()
    r = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_cn"))
    body = r.json()
    keys = [row.get("key") for row in body["rows"] if row["kind"] == "dimension"]
    assert keys == ["region"], keys
    assert body["visible"] is True  # tax_type 撤过滤后 u_cn 对 d_cn 可见


def test_d11_explain_matches_acl_compiled_verdict(rest_env) -> None:
    """**语义红线断言**（漂移即失败）：矩阵全部有效成员 × 5 文档组合——
    explain.visible 与 ACL 编译产物（compile_acl + visible_doc_ids）判定一致；
    过期/无成员用户 explain visible=false 且 compile_acl 拒绝（第 0 步收口）。"""
    client, env = rest_env["client"], rest_env
    backend = env["backend"]
    doc_ids = ["d_cn", "d_multi", "d_empty_region", "d_cit", "d_os"]
    viewers = {
        "u_full": "u_full", "u_cn": "u_cn", "u_cn_vat": "u_cn_vat",
        "u_os": "u_os", "u_expired_grant": "u_expired_grant",
        "u_owner": "u_owner", "admin_full": "admin_full",
        "admin_tax": "admin_tax", "u_multi": "u_multi",
    }
    from knowledge_lattice.core.docs.acl import compile_acl

    for uid in viewers:
        plan = compile_acl(backend, uid, ORG)
        visible = backend.visible_doc_ids(plan, doc_ids)
        # admin 代他人解释（admin_tax 视角全覆盖 member 面）
        for doc_id in doc_ids:
            r = client.get(
                f"/api/orgs/{ORG}/documents/{doc_id}/explain",
                headers=_hdr(env, "admin_tax"), params={"user_id": uid})
            assert r.status_code == 200, f"{uid}/{doc_id}: {r.text}"
            explained = r.json()["visible"]
            expected = doc_id in visible
            assert explained is expected, (
                f"explain 与编译产物漂移：{uid} × {doc_id}——explain={explained}"
                f" visible_doc_ids={sorted(visible)}（红线：只解释不裁定，"
                "结论必须同口径）"
            )
    # 过期/无成员：explain visible=False（membership deny 收口）
    for uid in ("u_expired_member", "u_gl"):
        for doc_id in doc_ids[:2]:
            r = client.get(
                f"/api/orgs/{ORG}/documents/{doc_id}/explain",
                headers=_hdr(env, "admin_tax"), params={"user_id": uid})
            assert r.json()["visible"] is False, f"{uid} 无有效成员关系"


def test_d12_explain_disabled_value_grant_tightened(rest_env) -> None:
    """停用取值=收紧（T3 联动）：u_cn 的 region=CN 授权在取值停用后——
    explain region 行 deny（有效授权不含停用值——与编译产物同口径）。"""
    client, env = rest_env["client"], rest_env
    val = f"val:{dim_id_for(ORG, 'region')}:CN"
    env["db"].execute(
        "UPDATE dimension_values SET status = 'disabled' WHERE id = ?", (val,)
    )
    env["db"].commit()
    r = client.get(
        f"/api/orgs/{ORG}/documents/d_cn/explain", headers=_hdr(env, "u_cn"))
    body = r.json()
    assert body["visible"] is False
    region_row = next(row for row in body["rows"] if row.get("key") == "region")
    assert region_row["verdict"] == "deny"
    # 同口径：编译产物同样不可见
    from knowledge_lattice.core.docs.acl import compile_acl

    plan = compile_acl(env["backend"], "u_cn", ORG)
    assert "d_cn" not in env["backend"].visible_doc_ids(plan, ["d_cn"])
