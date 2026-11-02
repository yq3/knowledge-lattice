"""report_center 适配器：report / report_item 实体 + has_item / child_of /
derived_from 关系（design §5.8 适配器表——每天；m2s-3 接入）。

HTTP 客户端形态（同 template_center 先例）：

- GET {endpoint}/reports?cursor= → `{"items": [...], "next_cursor": str|null}`；
- item：`{code, name, aliases?: [str], dims?: {...},
  items: [{code, name, parent?: 项编码, derived_from?: ["type:key", ...]}]}`。

产出：report 实体 + report_item 实体（key="{报表编码}.{项编码}"、parent_key=
报表或父项——§4 设计说明⑤ parent_id 冗余、真相以关系为准）+ has_item（报表→
项）/ child_of（项→父项，源端有父才产）/ derived_from（项→template_field/
column，源端有才产）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

from . import SourceConfig


class ReportCenterAdapter:
    """报表中心快照适配器（只读、幂等、全量）。"""

    name = "report_center"

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
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else None
            page = self._transport(self._config.endpoint, "/reports", params)
            for item in page.get("items", []):
                yield from self._expand(item)
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def close(self) -> None:
        closer = getattr(self._transport, "close", None)
        if callable(closer):
            closer()

    @staticmethod
    def _expand(item: dict) -> Iterator[EntityRecord | RelationRecord]:
        code = str(item["code"])
        yield EntityRecord(
            type="report", key=code, name=str(item.get("name") or code),
            attrs={"code": code},
            aliases=tuple(item.get("aliases") or ()),
            dims=item.get("dims") or None,
        )
        for sub in item.get("items") or ():
            ikey = f"{code}.{sub['code']}"
            parent_code = sub.get("parent")
            parent_key = f"report_item:{code}.{parent_code}" if parent_code \
                else f"report:{code}"
            yield EntityRecord(
                type="report_item", key=ikey,
                name=str(sub.get("name") or ikey),
                parent_key=parent_key, attrs={"code": str(sub["code"])},
            )
            if parent_code:
                yield RelationRecord(
                    src=("report_item", ikey), rel_type="child_of",
                    dst=("report_item", f"{code}.{parent_code}"),
                )
            else:
                yield RelationRecord(
                    src=("report", code), rel_type="has_item",
                    dst=("report_item", ikey),
                )
            for ref in sub.get("derived_from") or ():
                rtype, _, rkey = str(ref).partition(":")
                yield RelationRecord(
                    src=("report_item", ikey), rel_type="derived_from",
                    dst=(rtype, rkey),
                )
