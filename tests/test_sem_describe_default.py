"""P1-1（R1 Committer）：describe_table **默认透传通道**永久用例——不经
ADAPTER_FACTORIES["metadata"] 工厂覆盖（R1 三用例全走 fake 工厂=mock 自证）。

覆盖面（fake 只替换传输层 `_default_transport`——默认 fetcher 真实路径
resolve_source_config → MetadataAdapter.describe_table → 3s 钳制 → 缓存）：

- ① fake transport 成功透传（含客户端 close 收口断言——_default_transport
  每次 fetcher 新建 httpx.Client 的泄漏修复）；
- ② 传输超时 → 降级轻量节点 + degraded=true（T-S11③）；
- ③ **metadata 未配置 → 降级**（P1-1②：构造异常不得绕过降级裸出——
  部署未配源时 describe_table 仍可用本地轻量节点回答）；
- ④ 5min 缓存命中（transport 仅一次请求——T-S11④）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fake_semantic import FakeSourceAdapter
from helpers import seed_org

ORG = "org:tax"

NOW = "2026-10-30 12:00:00"

MD_ENDPOINT = "http://md/api"

MD_CANNED = {
    "ods.t1": {
        "name": "进项表",
        "columns": [
            {"name": "tax_amt", "type": "DECIMAL", "comment": "税额"},
            {"name": "inv_no", "type": "TEXT"},
        ],
    },
}


class ClosableFakeTransport:
    """传输替身 + close 记录（P1-1④ 客户端生命周期收口断言数据源）。"""

    def __init__(self, routes: dict, *, explode: bool = False) -> None:
        self._routes = routes
        self.requests: list[str] = []
        self.close_calls = 0
        self._explode = explode

    def __call__(self, endpoint: str, path: str, params: dict | None = None) -> dict:
        url = endpoint.rstrip("/") + path
        self.requests.append(url)
        if self._explode:
            raise TimeoutError("metadata timeout (simulated >3s)")
        resp = self._routes.get((endpoint, path))
        if resp is None:
            raise LookupError(f"no fake route for {url!r}")
        return resp

    def close(self) -> None:
        self.close_calls += 1


def _snapshot() -> list:
    from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

    return [
        EntityRecord(type="table", key="ods.t1", name="进项表"),
        EntityRecord(type="column", key="ods.t1.tax_amt", name="税额",
                     parent_key="table:ods.t1"),
        EntityRecord(type="column", key="ods.t1.inv_no", name="发票号",
                     parent_key="table:ods.t1"),
        RelationRecord(src=("table", "ods.t1"), rel_type="has_column",
                       dst=("column", "ods.t1.tax_amt")),
        RelationRecord(src=("table", "ods.t1"), rel_type="has_column",
                       dst=("column", "ods.t1.inv_no")),
    ]


@pytest.fixture()
def describe_env(backend, tmp_path, monkeypatch):
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic import adapters as sem_adapters
    from knowledge_lattice.core.semantic.lookup import clear_describe_cache
    from knowledge_lattice.core.semantic.sync import run_sync

    seed_org(backend, ORG)
    settings = Settings(
        environment="test", data_dir=tmp_path,
        semantic_sources_json=json.dumps({ORG: {"metadata": {"endpoint": MD_ENDPOINT}}}),
    )
    env = SimpleNamespace(db=backend, backend=backend.make_backend(),
                          settings=settings, transport=None)
    run_sync(env.backend, ORG, FakeSourceAdapter("metadata", _snapshot()),
             settings=settings, snapshot=_snapshot(), now=NOW)

    clear_describe_cache()  # 模块级缓存测试隔离
    transport = ClosableFakeTransport(
        {(MD_ENDPOINT, "/tables/ods.t1"): MD_CANNED["ods.t1"]})
    monkeypatch.setattr(sem_adapters, "_default_transport", lambda cfg: transport)
    env.transport = transport
    yield env
    clear_describe_cache()


def _describe(env, table: str = "ods.t1"):
    from knowledge_lattice.core.semantic.lookup import describe_table

    return describe_table(env.backend, env.settings, ORG, table)


# ---- ① 默认通道成功透传（MetadataAdapter.describe_table 真实方法） ----


def test_p1_1_default_channel_pass_through(describe_env) -> None:
    """未注册 metadata 工厂 → 默认 fetcher：resolve_source_config →
    MetadataAdapter.describe_table → 透传列详情 + 客户端 close。"""
    payload = _describe(describe_env)
    assert payload["degraded"] is False
    assert payload["table"] == "ods.t1"
    assert payload["name"] == "进项表"
    cols = {c["name"]: c for c in payload["columns"]}
    assert cols["tax_amt"]["type"] == "DECIMAL" and cols["tax_amt"]["comment"] == "税额"
    assert describe_env.transport.requests == [f"{MD_ENDPOINT}/tables/ods.t1"]
    # P1-1④：默认通道按次关闭底层客户端（不泄漏——每 5min/表一次的长期路径）
    assert describe_env.transport.close_calls == 1


# ---- ② 传输超时 → 降级 ----


def test_p1_1_default_channel_timeout_degraded(describe_env, monkeypatch) -> None:
    from knowledge_lattice.core.semantic import adapters as sem_adapters
    from knowledge_lattice.core.semantic.lookup import clear_describe_cache

    clear_describe_cache()
    exploding = ClosableFakeTransport({}, explode=True)
    monkeypatch.setattr(sem_adapters, "_default_transport", lambda cfg: exploding)
    payload = _describe(describe_env)
    assert payload["degraded"] is True
    assert payload["table"] == "ods.t1"
    assert {c["name"] for c in payload["columns"]} == {"tax_amt", "inv_no"}
    assert exploding.close_calls == 1  # 异常路径同样收口客户端


# ---- ③ metadata 未配置 → 降级（构造异常不得绕过 T-S11③） ----


def test_p1_1_unconfigured_metadata_degrades(describe_env, tmp_path) -> None:
    """per-org 无 metadata 源配置 → 不抛内部错误、降级轻量节点（T-S11③：
    「元数据系统不可用」涵盖未配置——与 sync fail-fast 400 口径区分，查询面
    只读降级不阻断）。"""
    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.semantic.lookup import clear_describe_cache, describe_table

    clear_describe_cache()
    bare = Settings(environment="test", data_dir=tmp_path)  # 无 LATTICE_SEM_SOURCES_JSON
    payload = describe_table(describe_env.backend, bare, ORG, "ods.t1")
    assert payload["degraded"] is True
    assert {c["name"] for c in payload["columns"]} == {"tax_amt", "inv_no"}


# ---- ④ 缓存命中（transport 单次请求） ----


def test_p1_1_default_channel_cache(describe_env) -> None:
    _describe(describe_env)
    payload = _describe(describe_env)  # TTL 内二次调用
    assert payload["degraded"] is False
    assert len(describe_env.transport.requests) == 1  # 命中缓存零重复请求
    assert describe_env.transport.close_calls == 1    # 缓存路径不再碰传输层
