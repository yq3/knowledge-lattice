"""m2-5 A1/A2：跨组织隔离矩阵（TC-OPS-09 / T15 / TC-AZ-04——M2.6 验收句
「跨组织隔离全绿」）+ REST-PG 残项补齐（M1 B-1①/P3-18 顺延口径）。

**双后端 REST 面参数化**：M1 越权矩阵 REST/MCP/shell 面跑 sqlite 臂
（app_env 硬绑）、REST-PG 留 M2——本文件经 create_app(backend=注入)
（m2-6 B⑧ 基建）把 REST 面矩阵跑在 pg 臂上（同一测试代码双后端——
P3-18 残项的补齐载体）。

扫描面覆盖 **M2 新增端点全集**（m2-6 R3 P1-1 教训——全库化/org-scoped
消费面行集边界须独立多组织验证）：管理面 §6.2 全端点 + members 增改删 +
values CRUD + coverage/stats + 语义端点 sync/builds/sync-runs/entities/
describe/l0/report/annotate + reindex/reembed 投递 + 凭证/检索面。
第三组织 org:ops 独立造数（org:tax / org:gl 之外的行集边界对照）。
"""

from __future__ import annotations

import json

import pytest

from conftest import ORG, ORG_GL
from helpers import (
    FUTURE_TS,
    PAST_TS,
    dim_id_for,
    val_id_for,
)

ORG_OPS = "org:ops"   # 第三组织（行集边界独立对照——m2-6 P1-1 教训）
NOW_SEM = "2026-11-01 09:00:00"

# ============ fixture：matrix 造数 + 第三组织 + 语义三组织 + REST 壳 ============


@pytest.fixture()
def az_env(matrix, tmp_path):
    """标准矩阵（12 用户 5 文档双组织）+ org:ops 第三组织（admin/维度/文档/
    语义实体）+ 语义三组织 ready 构建 + create_app(backend=) REST 壳。

    静态 token：u_gl / sysadmin / u_full / admin_tax / admin_ops。
    """
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.annotator import clear_annotator_cache
    from knowledge_lattice.core.semantic.build import run_build
    from knowledge_lattice.core.semantic.records import EntityRecord
    from knowledge_lattice.core.semantic.sync import run_sync
    from knowledge_lattice.domain.auth import hash_token
    from fake_providers import FakeEmbedder
    from fake_semantic import FakeSourceAdapter
    from helpers import (
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_membership,
        seed_org,
        seed_searchable_doc,
        seed_user,
    )

    backend = matrix
    # ---- org:ops 第三组织（独立 dataset/维度/文档——行集边界对照） ----
    seed_org(backend, ORG_OPS, "运营组织")
    seed_dataset(backend, ORG_OPS, "ds:ops_lib")
    seed_dimension(backend, ORG_OPS, "region")
    seed_dim_value(backend, dim_id_for(ORG_OPS, "region"), "CN")
    seed_user(backend, "admin_ops")
    seed_membership(backend, "admin_ops", ORG_OPS, role="org_admin")
    seed_searchable_doc(backend, "d_ops_cn", org_id=ORG_OPS,
                        dataset_id="ds:ops_lib", owner_user_id="admin_ops",
                        dims={"region": ["CN"]}, content_seg="运营手册 留抵")

    # ---- 语义三组织（org:tax / org:gl / org:ops 同名 key 实体——隔离对照） ----
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=8,
                        embed_model="fake-embed")
    real = backend.make_backend()
    for org, key_suffix in ((ORG, "tax"), (ORG_GL, "gl"), (ORG_OPS, "ops")):
        recs = [
            EntityRecord(type="concept", key=f"vat.input_credit_{key_suffix}",
                         name=f"进项税额抵扣-{key_suffix}",
                         aliases=(f"进项抵扣-{key_suffix}",)),
            EntityRecord(type="concept", key=f"vat.retained_{key_suffix}",
                         name=f"留抵税额-{key_suffix}"),
        ]
        run_sync(real, org, FakeSourceAdapter("tc", recs), settings=settings,
                 snapshot=list(recs), now=NOW_SEM)
    clear_annotator_cache()
    for org in (ORG, ORG_GL, ORG_OPS):
        assert run_build(real, org, settings=settings,
                         embedder=FakeEmbedder(dim=8, model_name="fake-embed")
                         )["status"] == "ready"
    clear_annotator_cache()

    # ---- REST 壳（pg 臂注入 backend=create_app(backend=) 基建；sqlite 臂走
    #      默认工厂 ThreadLocalBackend——同一 db 文件〔tmp/lattice.db〕，
    #      TestClient portal 线程下 conftest 直连连接不可跨线程复用） ----
    if backend.name == "pg":
        app = create_app(
            Settings(environment="test", data_dir=tmp_path, embed_dim=2560,
                     probe_interval_s=0, worker_mode="inline"),
            embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
            run_startup_probe=False, backend=backend.make_backend(),
        )
    else:
        app = create_app(
            Settings(environment="test", data_dir=tmp_path, embed_dim=2560,
                     probe_interval_s=0, worker_mode="inline"),
            embedder=FakeEmbedder(dim=2560), gate=EmbeddingGate(),
            run_startup_probe=False,
        )

    # 静态 token（u_gl/sysadmin/u_full/admin_tax/admin_ops）
    tokens = {
        "u_gl": "dev-static-u-gl",
        "sysadmin": "dev-static-sysadmin",
        "u_full": "dev-static-u-full",
        "admin_tax": "dev-static-admin-tax",
        "admin_ops": "dev-static-admin-ops",
    }
    for uid, token in tokens.items():
        backend.execute(
            "UPDATE users SET token_hash = ? WHERE id = ?",
            (hash_token(token), uid),
        )
    backend.commit()

    with TestClient(app) as client:
        yield {
            "client": client, "db": backend, "backend": real,
            "tokens": tokens, "settings": settings,
        }
    clear_annotator_cache()


def _hdr(env, uid: str) -> dict:
    return {"Authorization": f"Bearer {env['tokens'][uid]}"}


# ============ TC-OPS-09：u_gl 对 org:tax 全端点扫描（全部拒绝或空集） ============

# 扫描面 = api/ 路由全集的管理面+语义+文档/任务面（R2/P2-3 补 values POST
# 与 yaml webhook）。**未扫项及原因**（共享守卫/独立身份防线——Tester P2①
# 论证 + Committer 裁定保留注记）：POST /orgs/{org}/documents（multipart
# 上传——org_scoped+上传时点维度写权限校验，与已扫 documents 面同一
# org_scoped 守卫）、PATCH/GET /api/quality-flags（resolve_request_org
# 成员校验 403 与 /api/search 同款守卫）、PUT /api/uploads/{id}（凭证
# sub+org+服务身份三要素绑定独立防线——T11 专项覆盖）。
# 资源 id 用 org:tax 真实 id（d_cn 等）与假 id 混合：权限校验先行
#（403 在存在性检查前——不泄露存在性）。
_SCAN_TEMPLATE = "/api/orgs/{org}"
SCAN_ENDPOINTS: list[tuple[str, str, dict | None, int]] = [
    # ---- 管理面（§6.2） ----
    ("get", "/dimensions", None, 403),
    ("get", "/datasets", None, 403),
    ("delete", "/datasets/ds:vat_lib", None, 403),
    ("patch", "/dimensions/999/values/999", {"status": "disabled"}, 403),
    ("post", "/dimensions/999/retire", None, 403),
    # values CRUD 的 POST（m2-6 A4——任务书 A1 点名项，R2/P2-3 补扫）
    ("post", "/dimensions/999/values", {"value": "X", "label": "x"}, 403),
    ("put", "/members/u_full/grants", {"grants": []}, 403),
    ("get", "/grants/export", None, 403),
    ("post", "/grants/import", "username,dim_key,value\n", 403),
    ("post", "/documents/d_cn/reindex", None, 403),
    ("get", "/embedding-coverage", None, 403),
    ("get", "/audit", None, 403),
    ("get", "/stats", None, 403),
    ("post", "/members", {"user_id": "u_full", "role": "member"}, 403),
    ("patch", "/members/u_full", {"role": "member"}, 403),
    ("delete", "/members/u_full", None, 403),
    # ---- 文档/任务/质量 ----
    ("get", "/documents/d_cn", None, 403),
    ("patch", "/documents/d_cn/dimensions", {"dims": {}}, 403),
    ("delete", "/documents/d_cn", None, 403),
    ("get", "/documents/d_cn/quality", None, 403),
    ("get", "/tasks", None, 403),
    ("get", "/tasks/task:x", None, 403),
    ("post", "/tasks/task:x/cancel", None, 403),
    # ---- 语义端点（sync/builds/sync-runs/entities/describe/l0/report/
    #      annotate + yaml webhook〔R2/P2-3 补——无签名 401 先行于一切
    #      业务语义，服务身份入口非成员端点〕） ----
    ("post", "/semantic/sync/tc", None, 403),
    ("get", "/semantic/sync-runs", None, 403),
    ("post", "/semantic/builds", None, 403),
    ("get", "/semantic/builds", None, 403),
    ("get", "/semantic/builds/999", None, 403),
    ("get", "/semantic/builds/999/report", None, 403),
    ("post", "/semantic/annotate", {"text": "进项抵扣"}, 403),
    ("get", "/semantic/l0", None, 403),
    ("get", "/semantic/entities?q=%E8%BF%9B%E9%A1%B9", None, 403),
    ("get", "/semantic/entities/1", None, 403),
    ("get", "/semantic/tables/ods.v/describe", None, 403),
    ("post", "/semantic/yaml/webhook", {}, 401),
]


def test_tc_ops09_u_gl_scan_org_tax_all_denied(az_env) -> None:
    """TC-OPS-09 主面：u_gl（仅 org:gl）对 org:tax 的端点扫描——管理面
    §6.2 + 语义端点 + 文档/任务面共 34 条 org 路径 403 + webhook 1 条 401
    （R2 口径——无签名 fail-closed 先行；成员关系校验
    先行——org_id 第一条件；绝不返回他组织资源内容/行集）。**覆盖口径**
    （R2/P2-3）：非实现全集——未扫 6 条及共享守卫论证见 SCAN_ENDPOINTS
    注释与 benchmarks/report-m2-5-matrix.md。"""
    client = az_env["client"]
    headers = _hdr(az_env, "u_gl")
    for method, tail, body, expected in SCAN_ENDPOINTS:
        path = f"{_SCAN_TEMPLATE.format(org=ORG)}{tail}"
        kwargs: dict = {}
        if isinstance(body, dict):
            kwargs["json"] = body
        elif isinstance(body, str):
            kwargs["content"] = body
        r = getattr(client, method)(path, headers=headers, **kwargs)
        assert r.status_code == expected, (
            f"u_gl → {method.upper()} {path}：期望 {expected}，实际"
            f" {r.status_code}（{r.text[:120]}）——跨组织端点不得放行")


def test_tc_ops09_u_gl_search_and_uploads_denied(az_env) -> None:
    """TC-OPS-09 无 org 路径端点：/api/search 与 /api/uploads 对 u_gl 以
    X-Org-Id=org:tax 解析 → 成员校验 403（resolve_org 统一规则——无隐式
    默认；检索面绝不空集放行）。"""
    client = az_env["client"]
    headers = {**_hdr(az_env, "u_gl"), "X-Org-Id": ORG}
    r = client.post("/api/search", headers=headers, json={"query": "增值税"})
    assert r.status_code == 403, f"跨组织检索须 403（got {r.status_code}）"
    r2 = client.post(
        "/api/uploads", headers=headers,
        json={"filename": "a.txt", "size": 3, "sha256": "x" * 64,
              "content_type": "text/plain"},
    )
    assert r2.status_code == 403


def test_tc_ops09_semantic_entities_isolated_rest(az_env) -> None:
    """TC-OPS-09 语义隔离对照（T-S7 面，REST entities/l0 端点载体——R2
    名实修正：非 MCP 工具面）：u_gl 持 org:gl 上下文检索语义实体——只见
    org:gl 实体，org:tax/org:ops 实体零出现（同名 key 实体按组织隔离）。"""
    client = az_env["client"]
    headers = {**_hdr(az_env, "u_gl"), "X-Org-Id": ORG_GL}
    r = client.get(f"/api/orgs/{ORG_GL}/semantic/entities",
                   headers=headers, params={"q": "进项抵扣"})
    assert r.status_code == 200, r.text
    names = [e["name"] for e in r.json()["entities"]]
    assert names, "org:gl 自有实体应可检索（隔离对照的非空面）"
    assert all("gl" in n for n in names), f"org:gl 面不得出现他组织实体（{names}）"
    # l0 导出同口径（org:gl 只含本组织片段——curated l0 属 YAML 层造数，
    # fake 源无 curated 时片段为空合法；断言他组织 key 零出现）
    r2 = client.get(f"/api/orgs/{ORG_GL}/semantic/l0", headers=headers)
    assert r2.status_code == 200
    frag_keys = [f["entity_key"] for f in r2.json().get("fragments", [])]
    assert all("_tax" not in k and "_ops" not in k for k in frag_keys), \
        f"org:gl l0 不得含他组织实体（{frag_keys}）"


# ============ T15：他组织资源 id 逐端点（404 存在性敏感 / 403 明确越权） ============


def test_t15_cross_org_resource_ids_404_in_own_org(az_env) -> None:
    """T15：u_gl 以**自己组织**（org:gl）路径调 org:tax 的资源 id——
    dimension id / value id / document id：404（存在性敏感——org:gl 内无此
    id，资源内容零泄露；绝不返回他组织资源）。

    R2/P2-4：dimension/value id 断言改用**真实路由**（design §6.2 无 GET
    单维度/GET 单取值端点——该历史缺口按裁定①a 登记 backlog 不实装；R1 版
    用不存在的 GET values 路由，404 实为 MCP mount 兜底——伪绿）：PATCH
    values/{val}（admin.py 真实路径）/ POST retire（无 confirm 只做 impact
    查询、无副作用）/ POST values（create_dimension_value 真实路径）。
    """
    tax_dim = dim_id_for(ORG, "region")
    tax_val = val_id_for(ORG, "region", "CN")
    client = az_env["client"]
    headers = _hdr(az_env, "u_gl")   # u_gl 是 org:gl org_admin——操作权限过

    cases = [
        ("patch", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}/values/{tax_val}",
         {"status": "disabled"}),
        ("post", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}/retire", None),
        ("post", f"/api/orgs/{ORG_GL}/dimensions/{tax_dim}/values",
         {"value": "NEW", "label": "新值"}),
        ("get", f"/api/orgs/{ORG_GL}/documents/d_cn", None),
        ("delete", f"/api/orgs/{ORG_GL}/documents/d_cn", None),
        ("post", f"/api/orgs/{ORG_GL}/documents/d_cn/reindex", None),
    ]
    for method, path, body in cases:
        kwargs = {"json": body} if body is not None else {}
        r = getattr(client, method)(path, headers=headers, **kwargs)
        assert r.status_code == 404, (
            f"{method.upper()} {path}：org:tax 资源 id 在 org:gl 须 404"
            f"（got {r.status_code}——{r.text[:100]}）")

    # grants 端点（**T15 延伸面**——非 T15 的 403/404 二分规则内；R1
    # Committer 裁定：org:gl 路径 + org:tax 用户 = m2-3 既有「目标用户在
    # 本组织无有效成员关系 → 400 防孤儿授权」语义，非跨组织资源口径；
    # 400 不含他组织资源内容，实质约束满足）
    r = client.put(f"/api/orgs/{ORG_GL}/members/u_full/grants",
                   headers=headers, json={"grants": []})
    assert r.status_code == 400, "他组织用户 grants 端点固定 400（防孤儿授权）"


def test_t15_cross_org_path_denied_fixed(az_env) -> None:
    """T15 固定面：u_gl 直取 org:tax 路径端点（明确越权）→ 403（成员校验
    先行、按端点稳定——SCAF 面在 TC-OPS-09 已全扫描，此处锁 404/403 的
    端点固定口径：org 路径=403、资源 id 在他组织=404）。"""
    client = az_env["client"]
    tax_dim = dim_id_for(ORG, "region")
    tax_val = val_id_for(ORG, "region", "CN")
    r = client.patch(f"/api/orgs/{ORG}/dimensions/{tax_dim}/values/{tax_val}",
                     headers=_hdr(az_env, "u_gl"), json={"status": "disabled"})
    assert r.status_code == 403


# ============ TC-AZ-04：系统管理员仅管理权 + 临时授权完整构造 ============


def test_tc_az04_sysadmin_cross_org_denied_then_manage_only(az_env) -> None:
    """TC-AZ-04①：sysadmin 跨组织检索/语义读拒绝（无成员关系——系统管理员
    **仅管理权**无数据可见权）；管理面 GET /api/orgs 照常（管理权独立）。"""
    client = az_env["client"]
    headers = {**_hdr(az_env, "sysadmin"), "X-Org-Id": ORG}
    r = client.post("/api/search", headers=headers, json={"query": "增值税"})
    assert r.status_code == 403, "sysadmin 无 membership：跨组织检索须 403"
    r2 = client.get(f"/api/orgs/{ORG}/semantic/entities",
                    headers=headers, params={"q": "进项"})
    assert r2.status_code == 403, "sysadmin 语义读同口径 403"
    # 管理权独立：组织列表（sysadmin=全部）
    r3 = client.get("/api/orgs", headers=_hdr(az_env, "sysadmin"))
    assert r3.status_code == 200
    ids = sorted(o["org_id"] for o in r3.json()["orgs"])
    assert ORG in ids and ORG_GL in ids and ORG_OPS in ids


def test_tc_az04_temp_grant_full_construction(az_env) -> None:
    """TC-AZ-04③④：临时授权**完整构造**——admin_tax 给 u_temp 挂 org:tax
    临时成员（expires_at 短期）+ region=[CN]+tax_type=[VAT] **双维度**授权
    （d_cn 双维度均有值——缺一仍不可见）：
    ③ 生效期内检索 d_cn 可见、成员关系与授权行均带 expires_at、审计留痕
    （members/grants 两事件）；④ 造数过期后（成员关系到期）即刻不可见
    （权限计算过滤过期、不等清理——与 T1 同构）。"""
    from helpers import seed_user

    db = az_env["db"]
    client = az_env["client"]
    admin = _hdr(az_env, "admin_tax")

    seed_user(db, "u_temp")
    db.commit()

    # ③-1 挂临时成员（expires_at=未来短期）
    r = client.post(
        f"/api/orgs/{ORG}/members", headers=admin,
        json={"user_id": "u_temp", "role": "member", "expires_at": FUTURE_TS},
    )
    assert r.status_code == 201, r.text
    # ③-2 双维度授权（region=CN + tax_type=VAT——d_cn 双维度有值）
    r = client.put(
        f"/api/orgs/{ORG}/members/u_temp/grants", headers=admin,
        json={"grants": [
            {"dim_key": "region", "value": "CN", "expires_at": FUTURE_TS},
            {"dim_key": "tax_type", "value": "VAT", "expires_at": FUTURE_TS},
        ]},
    )
    assert r.status_code == 200, r.text

    # ③-3 生效期内可见 d_cn（双维度齐备）
    from knowledge_lattice.domain.auth import hash_token

    db.execute("UPDATE users SET token_hash = ? WHERE id = ?",
               (hash_token("dev-static-u-temp"), "u_temp"))
    db.commit()
    temp = {"Authorization": "Bearer dev-static-u-temp", "X-Org-Id": ORG}
    r = client.post("/api/search", headers=temp,
                    json={"query": "common sample"})
    assert r.status_code == 200, r.text
    doc_ids = {hit["doc_id"] for hit in r.json()["results"]}
    assert "d_cn" in doc_ids, f"临时授权生效期内 d_cn 应可见（got {doc_ids}）"

    # ③-4 审计留痕（members/grants 两类事件均在——按插入序；pg 侧无序次列，
    #      断言事件存在即可）
    order = "rowid" if db.name == "sqlite" else "created_at"
    events = [
        e[0] for e in db.execute(
            f"SELECT event_type FROM audit_outbox ORDER BY {order}"
        ).fetchall()
    ]
    assert any("grant" in e for e in events) and any(
        "member" in e for e in events), f"审计留痕（{events[-8:]}）"

    # ④ 造数过期（成员关系到期——直写过期时间戳）→ 即刻不可见
    try:
        db.execute(
            "UPDATE user_org_memberships SET expires_at = ? WHERE user_id = ?"
            " AND org_id = ?", (PAST_TS, "u_temp", ORG),
        )
        db.commit()
    except Exception:  # noqa: BLE001 —— pg 触发器路径经服务层（见下）
        pass
    r2 = client.post("/api/search", headers=temp, json={"query": "common sample"})
    assert r2.status_code == 403, (
        f"成员关系过期即拒（不等清理）——got {r2.status_code}")


# ============ 三组织行集边界（m2-6 P1-1 教训——独立多组织验证） ============


def test_three_org_rowset_boundaries(az_env) -> None:
    """org-scoped 消费面行集边界三组织独立验证：coverage/stats/audit/
    dimensions/datasets/grants export——各组织 admin 只见本组织行集
    （org:ops 第三组织对照：org:tax 的 dataset/维度/文档零出现）。"""
    client = az_env["client"]

    # org:ops admin 视角
    ops = _hdr(az_env, "admin_ops")
    r = client.get(f"/api/orgs/{ORG_OPS}/embedding-coverage", headers=ops)
    assert r.status_code == 200, r.text
    cov = r.json()["coverage"]
    assert [c["dataset_id"] for c in cov] == ["ds:ops_lib"], \
        f"coverage 只列本组织 datasets（got {cov}）——m2-6 P1-1 同型面"

    r = client.get(f"/api/orgs/{ORG_OPS}/stats", headers=ops)
    assert r.status_code == 200
    assert "maintenance" in r.json()  # maintenance 计数面板键在位（值随任务族运行态）
    dims = [d["key"] for d in client.get(
        f"/api/orgs/{ORG_OPS}/dimensions", headers=ops).json()["dimensions"]]
    assert dims == ["region"], f"org:ops 只有自己的 region 维度（got {dims}）"
    dss = [d["id"] for d in client.get(
        f"/api/orgs/{ORG_OPS}/datasets", headers=ops).json()["datasets"]]
    assert dss == ["ds:ops_lib"]

    # 审计行集（R2/P3-11c 补断言）：org:ops admin 查本组织审计——事件
    # org_id 全为本组织（read_org_audit 的 org 第一谓词）
    r = client.get(f"/api/orgs/{ORG_OPS}/audit", headers=ops)
    assert r.status_code == 200
    events = r.json().get("events") or r.json().get("items") or []
    orgs_seen = {json.loads(e["payload_json"]).get("org_id")
                 for e in events if e.get("payload_json")}
    assert orgs_seen <= {ORG_OPS, None}, \
        f"org:ops 审计面不得出现他组织事件（org_id 集 {orgs_seen}）"

    # grants export 行集：org:ops 只含本组织授权（u_full 的 org:tax 授权不出现）
    export = client.get(f"/api/orgs/{ORG_OPS}/grants/export",
                        headers=ops).text
    assert "u_full" not in export, "org:ops grants 导出不得含 org:tax 用户授权"

    # org:tax admin 对照（互不出现对方资源）
    tax = _hdr(az_env, "admin_tax")
    cov_tax = client.get(f"/api/orgs/{ORG}/embedding-coverage",
                         headers=tax).json()["coverage"]
    assert all(c["dataset_id"] != "ds:ops_lib" for c in cov_tax)

    # 语义行集：org:ops 只回本组织实体
    r = client.get(f"/api/orgs/{ORG_OPS}/semantic/entities",
                   headers=ops, params={"q": "进项抵扣"})
    assert r.status_code == 200
    for e in r.json()["entities"]:
        assert "ops" in (e.get("name") or ""), \
            f"org:ops 语义面不得出现他组织实体（{e}）"


def test_gl_admin_cannot_touch_ops(az_env) -> None:
    """u_gl（org:gl org_admin）对 org:ops 第三组织同样全拒——隔离面在
    「任意非本组织」上成立（不止 tax/gl 双组织对照）。"""
    client = az_env["client"]
    headers = _hdr(az_env, "u_gl")
    for path in (f"/api/orgs/{ORG_OPS}/embedding-coverage",
                 f"/api/orgs/{ORG_OPS}/stats",
                 f"/api/orgs/{ORG_OPS}/semantic/entities?q=x",
                 f"/api/orgs/{ORG_OPS}/documents/d_ops_cn"):
        r = client.get(path, headers=headers)
        assert r.status_code == 403, f"{path} 须 403（got {r.status_code}）"
