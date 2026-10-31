"""scenario_config 适配器：scenario 实体 + uses 关系（design §5.8 适配器表——
每天 + 手动触发；m2s-3 接入）。

HTTP 客户端形态（同 template_center 先例——端点契约为本段定义的最小快照面）：

- GET {endpoint}/scenarios?cursor= → `{"items": [...], "next_cursor": str|null}`
  （可翻页拼全量——#37 前置条件①②：全量快照、只读、服务身份）；
- item：`{code, name, aliases?: [str], dims?: {...}, templates: [模板编码, ...]}`。

产出：scenario 实体（code=业务键）+ uses → template 关系（模板端点缺失走既有
冲突路径——TC-SYNC-04 面；scenario_config 是独立删边大户——关系级 missing
由既有流程接管，G-15）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord

from . import SourceConfig


class ScenarioConfigAdapter:
    """场景配置中心快照适配器（只读、幂等、全量）。"""

    name = "scenario_config"

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
            page = self._transport(self._config.endpoint, "/scenarios", params)
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
            type="scenario", key=code, name=str(item.get("name") or code),
            attrs={"code": code},
            aliases=tuple(item.get("aliases") or ()),
            dims=item.get("dims") or None,
        )
        for tpl in item.get("templates") or ():
            yield RelationRecord(
                src=("scenario", code), rel_type="uses",
                dst=("template", str(tpl)),
            )
