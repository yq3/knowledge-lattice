"""metadata 适配器：table / column 轻量节点 + has_column——**只拉被引用到的**
（design §5.8：`backed_by` / `maps_to` 引用面 + YAML 显式列出的（m2s-3），
不做全量镜像——TC-SYNC-02/FR-S1）。

引用面 refs 从**本次同步快照的 RelationRecord** 推导（derive_refs——见
adapters/__init__.py；冷启动接力：template_center 首轮的端点冲突在 table /
column 落库后自动消解）。列详情（类型/样例/分区/血缘）**不落库**——
describe_table 实时透传（§5.8 三种内容分工表；T-S11 归 m2s-2）。

端点契约：GET {endpoint}/tables/{key} → `{name, columns: [{name, type?, comment?}]}`。
column key = "{table_key}.{column_name}"、parent_key="table:{table_key}"。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

from . import SourceConfig


class MetadataAdapter:
    """元数据系统适配器（引用面驱动——只拉被引用的表及其列）。"""

    name = "metadata"

    def __init__(
        self,
        config: SourceConfig,
        *,
        refs: Iterable[tuple[str, str]] = (),
        transport: Callable[[str, str, dict | None], dict] | None = None,
    ) -> None:
        from . import _default_transport

        self._config = config
        self._refs = {tuple(r) for r in refs}
        self._transport = transport or _default_transport(config)

    def fetch(self, org: str) -> Iterator[EntityRecord | RelationRecord]:
        for table_key in sorted(self._referenced_tables()):
            detail = self._transport(
                self._config.endpoint, f"/tables/{table_key}", None
            )
            yield from self._expand_table(table_key, detail)

    # ---- 内部 ----

    def _referenced_tables(self) -> set[str]:
        """引用表集合：table 引用 + column 引用的父表（column key 内嵌表键）。"""
        tables: set[str] = set()
        for etype, key in self._refs:
            if etype == "table":
                tables.add(key)
            elif etype == "column":
                tables.add(key.rsplit(".", 1)[0])
        return tables

    @staticmethod
    def _expand_table(table_key: str, detail: dict) -> Iterator[EntityRecord | RelationRecord]:
        yield EntityRecord(
            type="table", key=table_key,
            name=str(detail.get("name") or table_key),
            attrs={"code": table_key},
        )
        for col in detail.get("columns") or ():
            ckey = f"{table_key}.{col['name']}"
            attrs = {"name": str(col["name"])}
            if col.get("type"):
                attrs["type"] = str(col["type"])
            yield EntityRecord(
                type="column", key=ckey,
                name=str(col.get("comment") or col["name"]),
                parent_key=f"table:{table_key}", attrs=attrs,
            )
            yield RelationRecord(
                src=("table", table_key), rel_type="has_column",
                dst=("column", ckey),
            )
