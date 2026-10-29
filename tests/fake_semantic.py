"""语义层同步测试替身（M2-S1——沿 tests/fake_providers.py 惯例）。

- FakeSourceAdapter：协议级 SourceAdapter 替身——全量快照记录可变列表
  （fetch(org) 返回当前列表拷贝；记录 fetch 调用供 per-org 解析断言）；
- FakeTransport：HTTP 适配器的传输层替身——按 endpoint 前缀回放罐头响应并
  记录请求（TC-SYNC-01 per-org 端点解析断言数据源）；
- tpl_snapshot / md_canned：template_center / metadata 两源的标准罐头快照
  （语义 fixture 见 TEST-CASES §四口径段：TPL_VAT_INPUT·TAX_AMT 等）。
"""

from __future__ import annotations

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord


class FakeSourceAdapter:
    """全量快照假适配器：fetch(org) 吐当前快照（可变——测试中途改写模拟源端变化）。"""

    def __init__(self, name: str, records: list) -> None:
        self.name = name
        self.records = list(records)
        self.fetch_calls: list[str] = []

    def fetch(self, org: str):
        self.fetch_calls.append(org)
        return list(self.records)


def tpl_entity(key: str, name: str | None = None, **kw) -> EntityRecord:
    return EntityRecord(type="template", key=key, name=name or f"模板{key}", **kw)


def tpl_snapshot(
    n: int = 10,
    *,
    prefix: str = "TPL",
    with_fields: bool = True,
    with_dims: bool = False,
    dims_filled: int | None = None,
) -> list:
    """template_center 标准快照：n 个模板（+各一字段 + has_field 关系）。

    with_dims：全部携带 dims；dims_filled=k：仅前 k 个携带（骤降造数）。
    """
    out: list[EntityRecord | RelationRecord] = []
    for i in range(n):
        key = f"{prefix}_{i}"
        kw: dict = {}
        if with_dims or (dims_filled is not None and i < dims_filled):
            kw["dims"] = {"region": "CN"}
        out.append(tpl_entity(key, **kw))
        if with_fields:
            fkey = f"{key}.F1"
            out.append(
                EntityRecord(
                    type="template_field", key=fkey, name=f"字段{key}",
                    parent_key=f"template:{key}",
                )
            )
            out.append(
                RelationRecord(
                    src=("template", key), rel_type="has_field",
                    dst=("template_field", fkey),
                )
            )
    return out


class FakeTransport:
    """传输层替身：endpoint → (path, params) → 响应 dict；记录全部请求 URL。"""

    def __init__(self, routes: dict[str, dict]) -> None:
        # routes: {endpoint: {(method, path): response}}——method 缺省 GET
        self._routes = routes
        self.requests: list[str] = []

    def __call__(self, endpoint: str, path: str, params: dict | None = None) -> dict:
        url = endpoint.rstrip("/") + path
        self.requests.append(url + (f"?cursor={params['cursor']}" if params and params.get("cursor") else ""))
        table = self._routes.get(endpoint)
        if table is None:
            raise LookupError(f"no fake route for endpoint {endpoint!r}")
        for (method, p), resp in table.items():
            if p == path and (method == "GET"):
                return resp
        raise LookupError(f"no fake route for {url!r}")


def tc_canned(page_items: list[dict], pages: int = 1) -> dict:
    """template_center 罐头路由：分页 items（默认单页）。"""
    return {("GET", "/templates"): {"items": page_items, "next_cursor": None}}


def md_canned(tables: dict[str, dict]) -> dict[str, dict]:
    """metadata 罐头路由：table_key → {name, columns:[...]}。"""
    return {
        ("GET", f"/tables/{k}"): v for k, v in tables.items()
    }
