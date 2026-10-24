"""共享 fixtures。

- `conn`：全新 lattice.db → 连接工厂 → 迁移到 schema v1（TC-SCAF 前置，M0a-1）。
- `matrix`：标准矩阵 fixture（TEST-CASES §三口径段——越权矩阵/编译器用例复用）：
  组织 `org:tax`（主）/ `org:gl`（隔离对照）；维度 `region`（required=1 active，
  CN/OS）+ `tax_type`（required=0 active，VAT/CIT）；用户 12 人（口径段清单）；
  文档 5 篇（org:tax / ds:vat_lib，未显式列出取值的 active 维度一律无值——#38 P1-1）。
  `channel` 维度由 T20/TC-ACL-04 用例内创建（建维度时库内已有存量文档——零回填前提）。
  时间一律造数：PAST_TS/NOW_TS/FUTURE_TS（UTC `YYYY-MM-DD HH:MM:SS`，与
  CURRENT_TIMESTAMP 同格式——v1.4 钉死）。
- **backend 参数化骨架（M0b-1，M0a-1 R1 边界拍板选项 A 的激活项）**：
  `backend`——sqlite 臂实跑（tmp lattice.db）+ pg 臂有 `LATTICE_PG_DSN` 实跑
  （每用例独立 schema `lattice_test_<hex>`：CREATE SCHEMA → SET search_path →
  迁移 → 用例 → DROP SCHEMA CASCADE），无 DSN `pytest.skip`（门禁脚本将 skip
  视为失败——scripts/test_gate.sh）；`matrix` 随 backend 参数化（同一测试代码
  双后端）；`sqlite_matrix` 保留旧 sqlite 直连形态（sqlite 渲染器文本回归等
  sqlite-only 用例）；`pg_db` 供 PG 专用断言（连接池/迁移框架/审计分区/六域种子）。

docling 模型环境（TC-ING-01 PDF 样例）：权重经 HF hub 下载；本机网络 huggingface.co
不可达——统一走 hf-mirror 镜像 + 禁用 xet 协议（镜像不支持）；权重已入本地缓存
（~/.cache/docling/models）则置 HF_HUB_OFFLINE 省去每次在线元数据检查的分钟级超时。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def _tune_hf_env() -> None:
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    # docling 权重留在 HF hub 缓存（artifacts_path 未设时）——已缓存则离线省去
    # 每次转换的在线元数据检查（直连超时分钟级）
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    docling_cache = Path.home() / ".cache" / "docling" / "models"
    cached = (hub.is_dir() and any(hub.glob("models--docling-project--*"))) or (
        docling_cache.is_dir() and any(docling_cache.iterdir())
    )
    if cached:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")


_tune_hf_env()

import sqlite3  # noqa: E402  (env 先于任何 docling/huggingface 导入)
import contextlib  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402

from dbwrap import PgDb, SqliteDb  # noqa: E402
from fake_providers import FakeEmbedder  # noqa: E402
from helpers import (  # noqa: E402
    PAST_TS,
    dim_id_for,
    seed_dataset,
    seed_dim_value,
    seed_dimension,
    seed_grant,
    seed_membership,
    seed_org,
    seed_searchable_doc,
    seed_user,
    val_id_for,
)

ORG = "org:tax"
ORG_GL = "org:gl"
DATASET = "ds:vat_lib"

PG_DSN_ENV = "LATTICE_PG_DSN"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "lattice.db"


@pytest.fixture()
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    from knowledge_lattice.store.sqlite import connect, migrate_db

    c = connect(db_path)
    migrate_db(c)
    yield c
    c.close()


# ============ backend 参数化骨架（M0b-1：sqlite 实跑 + pg 有 DSN 实跑 / 无 DSN skip） ============


@pytest.fixture(params=["sqlite", "pg"])
def backend(request, tmp_path: Path):
    """双后臂测试包装器（tests/dbwrap.py）——同一测试代码的方言分派面。"""
    if request.param == "sqlite":
        from knowledge_lattice.store.sqlite import connect, migrate_db

        c = connect(tmp_path / "lattice.db")
        migrate_db(c)
        db = SqliteDb(c)
        yield db
        c.close()
        return

    dsn = os.environ.get(PG_DSN_ENV)
    if not dsn:
        pytest.skip(
            f"{PG_DSN_ENV} 未设置——pg 臂跳过（docker start lattice-pg 后 "
            "export LATTICE_PG_DSN=postgresql://postgres:lattice@localhost:5432/lattice 重跑；"
            "本地门禁 scripts/test_gate.sh 将 skip 视为失败）"
        )
    with _pg_db(dsn) as db:
        yield db


@contextlib.contextmanager
def _pg_db(dsn: str):
    """pg 臂库的规范上下文：独立 schema 生命周期（CREATE → search_path → 工厂纪律
    （dumper/版本/pgvector 断言 + 审计分区滚动）→ 迁移 → yield → DROP CASCADE）。"""
    from knowledge_lattice.store.postgres import migrate_db, setup_connection

    schema = f"lattice_test_{uuid.uuid4().hex[:12]}"
    raw = psycopg.connect(dsn, autocommit=True)
    try:
        raw.execute(f'CREATE SCHEMA "{schema}"')
        raw.execute(f'SET search_path TO "{schema}", public')
        setup_connection(raw)
        migrate_db(raw)
        yield PgDb(raw, schema, dsn)
    finally:
        try:
            raw.execute("SET search_path TO public")
            raw.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except psycopg.Error:
            pass  # teardown 失败不得覆盖用例原始异常
        finally:
            raw.close()


@pytest.fixture()
def pg_db():
    """PG 专用断言用库（连接池 / 迁移框架 / 审计分区 / 六域种子——M0b-1 PG spike）。

    无 LATTICE_PG_DSN 时 skip——门禁脚本（scripts/test_gate.sh）将 skip 视为失败。
    """
    dsn = os.environ.get(PG_DSN_ENV)
    if not dsn:
        pytest.skip(
            f"{PG_DSN_ENV} 未设置——pg 臂跳过（docker start lattice-pg 后 "
            f"export {PG_DSN_ENV}=postgresql://postgres:lattice@localhost:5432/lattice 重跑）"
        )
    with _pg_db(dsn) as db:
        yield db


def _seed_standard_matrix(db) -> None:
    """标准矩阵造数（方言无关——db 为 tests/dbwrap.py 包装器或 sqlite 直连）。"""
    seed_org(db, ORG)
    seed_org(db, ORG_GL, "隔离组织")
    seed_dataset(db, ORG, DATASET)

    # 维度：region required=1 active（CN/OS）；tax_type required=0 active（VAT/CIT）
    seed_dimension(db, ORG, "region")
    seed_dim_value(db, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(db, dim_id_for(ORG, "region"), "OS")
    seed_dimension(db, ORG, "tax_type")
    db.execute(
        "UPDATE dimensions SET required = 0 WHERE org_id = ? AND key = ?", (ORG, "tax_type")
    )
    seed_dim_value(db, dim_id_for(ORG, "tax_type"), "VAT")
    seed_dim_value(db, dim_id_for(ORG, "tax_type"), "CIT")

    def grant(user_id: str, key: str, value: str, *, expires_at: str | None = None) -> None:
        seed_grant(
            db,
            user_id=user_id,
            dim_id=dim_id_for(ORG, key),
            val_id=val_id_for(ORG, key, value),
            expires_at=expires_at,
        )

    # 用户（§三口径段清单）
    for uid in (
        "u_full", "u_cn", "u_cn_vat", "u_os", "u_expired_grant", "u_expired_member",
        "u_owner", "admin_tax", "admin_full", "sysadmin", "u_gl", "u_multi",
    ):
        seed_user(db, uid)
    db.execute("UPDATE users SET is_system_admin = 1 WHERE id = ?", ("sysadmin",))

    # 成员关系（org:tax；u_expired_member 过期造数；sysadmin 无行——TC-ACL-05）
    for uid in (
        "u_full", "u_cn", "u_cn_vat", "u_os", "u_expired_grant", "u_owner", "u_multi",
    ):
        seed_membership(db, uid, ORG)
    seed_membership(db, "u_expired_member", ORG, expires_at=PAST_TS)
    seed_membership(db, "admin_tax", ORG, role="org_admin")
    seed_membership(db, "admin_full", ORG, role="org_admin")
    seed_membership(db, "u_gl", ORG_GL, role="org_admin")
    seed_membership(db, "u_multi", ORG_GL)

    # 授权（§三口径段清单；admin_tax 无维度授权）
    for value in ("CN", "OS"):
        grant("u_full", "region", value)
    grant("u_full", "tax_type", "VAT")
    grant("u_cn", "region", "CN")
    grant("u_cn_vat", "region", "CN")
    grant("u_cn_vat", "tax_type", "VAT")
    grant("u_os", "region", "OS")
    grant("u_expired_grant", "region", "CN", expires_at=PAST_TS)
    grant("u_expired_grant", "tax_type", "VAT")
    grant("u_expired_member", "region", "CN")
    grant("u_expired_member", "tax_type", "VAT")
    grant("u_owner", "region", "OS")
    grant("u_owner", "tax_type", "VAT")
    for value in ("CN", "OS"):
        grant("admin_full", "region", value)
    grant("admin_full", "tax_type", "VAT")

    # 文档（org:tax / ds:vat_lib；owner=u_owner；单 chunk v1 在用）
    seed_searchable_doc(db, "d_cn", dims={"region": ["CN"], "tax_type": ["VAT"]})
    seed_searchable_doc(db, "d_multi", dims={"region": ["CN", "OS"]})
    seed_searchable_doc(db, "d_empty_region")
    seed_searchable_doc(db, "d_cit", dims={"tax_type": ["CIT"]})
    seed_searchable_doc(db, "d_os", dims={"region": ["OS"]})


@pytest.fixture()
def matrix(backend):
    """标准矩阵（随 backend 参数化——同一测试代码双后端，M0b-1）。"""
    _seed_standard_matrix(backend)
    return backend


@pytest.fixture()
def sqlite_matrix(conn: sqlite3.Connection) -> sqlite3.Connection:
    """旧 sqlite 直连矩阵（sqlite 渲染器文本回归等 sqlite-only 用例——r2 安全回归）。"""
    _seed_standard_matrix(conn)
    return conn


# ============ M0a-3 摄取/检索链 fixtures ============


@pytest.fixture()
def ingest_env(tmp_path):
    """摄取链测试环境：全新库 + org:tax 造数（region/tax_type 维度 + u_full 授权）。

    返回 dict(backend=..., settings=..., gate=..., objects_dir=..., make_service=...)——
    make_service(embedder) 以可替换 Embedder 构造 IngestService（fake fixture 注入）。
    """
    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.ingest import IngestService
    from knowledge_lattice.store.sqlite import connect, migrate_db
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    db_path = tmp_path / "lattice.db"
    conn = connect(db_path)
    migrate_db(conn)
    seed_org(conn, ORG)
    seed_dataset(conn, ORG, DATASET)
    seed_dimension(conn, ORG, "region")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "OS")
    seed_dimension(conn, ORG, "tax_type")
    conn.execute(
        "UPDATE dimensions SET required = 0 WHERE org_id = ? AND key = 'tax_type'", (ORG,)
    )
    seed_dim_value(conn, dim_id_for(ORG, "tax_type"), "VAT")
    for uid in ("u_full", "u_cn"):
        seed_user(conn, uid)
        seed_membership(conn, uid, ORG)
    for value in ("CN", "OS"):
        seed_grant(
            conn, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
            val_id=val_id_for(ORG, "region", value),
        )

    backend = SqliteBackend(conn)
    settings = Settings(environment="test", data_dir=tmp_path, embed_dim=2560)
    gate = EmbeddingGate()
    objects_dir = tmp_path / "objects"

    def make_service(embedder) -> IngestService:
        return IngestService(backend, embedder, settings, gate, objects_dir)

    yield {
        "conn": conn,
        "backend": backend,
        "settings": settings,
        "gate": gate,
        "objects_dir": objects_dir,
        "make_service": make_service,
    }
    conn.close()


@pytest.fixture()
def app_env(tmp_path):
    """服务壳测试环境：create_app（fake Embedder 注入、跳过启动探针、无周期任务）+
    org:tax 造数（u_full/u_cn/sysadmin + 静态 token 引导 + region 维度授权）。

    返回 dict(app, client, conn, settings, gate, embedder, static=…, jwt(…))。
    """
    from fastapi.testclient import TestClient

    from knowledge_lattice.adapters.embedder import EmbeddingGate
    from knowledge_lattice.app import create_app
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import hash_token, issue_dev_jwt
    from knowledge_lattice.store.sqlite import connect

    settings = Settings(
        environment="test",
        data_dir=tmp_path,
        embed_dim=2560,
        probe_interval_s=0,
        mcp_timeout_s=60.0,
    )
    embedder = FakeEmbedder(dim=2560)
    gate = EmbeddingGate()
    app = create_app(settings, embedder=embedder, gate=gate, run_startup_probe=False)

    conn = connect(settings.db_path)
    seed_org(conn, ORG)
    seed_dataset(conn, ORG, DATASET)
    seed_dimension(conn, ORG, "region")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(conn, dim_id_for(ORG, "region"), "OS")
    for uid in ("u_full", "u_cn", "u_os", "sysadmin"):
        seed_user(conn, uid)
        seed_membership(conn, uid, ORG)
    conn.execute("UPDATE users SET is_system_admin = 1 WHERE id = 'sysadmin'")
    for value in ("CN", "OS"):
        seed_grant(
            conn, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
            val_id=val_id_for(ORG, "region", value),
        )
    seed_grant(
        conn, user_id="u_cn", dim_id=dim_id_for(ORG, "region"),
        val_id=val_id_for(ORG, "region", "CN"),
    )
    # 静态 token 引导（仅 dev/test——D18）
    static = {"u_full": "dev-static-u-full", "u_cn": "dev-static-u-cn", "sysadmin": "dev-static-sysadmin"}
    for uid, token in static.items():
        conn.execute("UPDATE users SET token_hash = ? WHERE id = ?", (hash_token(token), uid))
    conn.commit()

    with TestClient(app) as client:
        yield {
            "app": app,
            "client": client,
            "conn": conn,
            "settings": settings,
            "gate": gate,
            "embedder": embedder,
            "static": static,
            "jwt": lambda uid, org=None: issue_dev_jwt(settings, user_id=uid, org=org),
        }
    conn.close()
