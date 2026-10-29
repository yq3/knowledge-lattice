"""template_center 适配器：template / template_field 实体 + has_field /
backed_by / maps_to 关系（design §5.8 适配器表——每天 + 手动触发）。

HTTP 客户端形态（真实源系统不可达——传输层可注入，测试替身验收沿 fake_providers
惯例；端点契约为本段定义的最小快照面）：

- GET {endpoint}/templates?cursor= → `{"items": [...], "next_cursor": str|null}`
  （可翻页拼全量——#37 前置条件①②：全量快照、只读、服务身份）；
- item：`{code, name, aliases?: [str], table?: "db.table", dims?: {...},
  fields: [{code, name, column?: "db.table.col"}]}`。

产出：template 实体（code=业务键）+ 每字段 template_field 实体
（key="{模板编码}.{字段编码}"、parent_key="template:{编码}"）+ has_field /
backed_by / maps_to 关系。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

from . import SourceConfig


class TemplateCenterAdapter:
    """模板中心快照适配器（只读、幂等、全量）。"""

    name = "template_center"

    def __init__(
        self,
        config: SourceConfig,
        *,
        transport: Callable[[str, str, dict | None], dict] | None = None,
    ) -> None:
        from . import _default_transport

        self._config = config
        self._transport = transport or _default_transport(config)

    def fetch(self, org: str) -> Iterator[EntityRecord | RelationRecord]:
        yield from self._templates()

    # ---- 内部：分页拼全量 ----

    def _templates(self) -> Iterator[EntityRecord | RelationRecord]:
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else None
            page = self._transport(self._config.endpoint, "/templates", params)
            for item in page.get("items", []):
                yield from self._expand(item)
            cursor = page.get("next_cursor")
            if not cursor:
                return

    @staticmethod
    def _expand(item: dict) -> Iterator[EntityRecord | RelationRecord]:
        code = str(item["code"])
        dims = item.get("dims") or None
        yield EntityRecord(
            type="template", key=code, name=str(item.get("name") or code),
            attrs={"code": code},
            aliases=tuple(item.get("aliases") or ()),
            dims=dims,
        )
        for field in item.get("fields") or ():
            fkey = f"{code}.{field['code']}"
            yield EntityRecord(
                type="template_field", key=fkey,
                name=str(field.get("name") or fkey),
                parent_key=f"template:{code}",
                attrs={"code": str(field["code"])},
            )
            yield RelationRecord(
                src=("template", code), rel_type="has_field",
                dst=("template_field", fkey),
            )
            column = field.get("column")
            if column:
                yield RelationRecord(
                    src=("template_field", fkey), rel_type="maps_to",
                    dst=("column", str(column)),
                )
        table = item.get("table")
        if table:
            yield RelationRecord(
                src=("template", code), rel_type="backed_by",
                dst=("table", str(table)),
            )
