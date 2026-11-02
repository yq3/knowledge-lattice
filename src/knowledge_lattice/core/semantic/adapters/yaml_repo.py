"""yaml 仓库适配器（design §5.8 适配器表 `yaml` 行——m2s-3）。

- 产出：concept / system 纯人工实体（source='curated'——经 run_sync 的
  per-source upsert 面落库）+ refers_to / related_to 关系（source='curated'，
  端点解析/白名单走既有冲突路径）；覆盖层 curated 内容由 yaml_merge 的
  post_run 挂钧合并（本适配器只吐源端记录——勿另起炉灶）；
- 传输形态：本地 Git checkout 目录（`endpoint` = 仓库路径——Git 合并后
  webhook 拉起的同步读工作区；HTTP 远端为部署侧前置动作〔git pull〕，不在
  适配器职责内）；rev = 全仓内容哈希（yaml_corpus._content_rev）；
- 频率：Git 合并后 webhook 触发 + 每天一次兜底（§5.8 适配器表——兜底经既有
  POST sync/yaml 手动面/调度面投递）。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from knowledge_lattice.core.semantic.records import EntityRecord, RelationRecord
from knowledge_lattice.core.semantic.yaml_corpus import Corpus, load_corpus

from . import SourceConfig


class YamlRepoAdapter:
    """YAML 覆盖层仓库快照适配器（只读、幂等、全量 corpus）。"""

    name = "yaml"
    relation_source = "curated"   # 本源关系 source='curated'（§5.8 合并规则表）

    def __init__(self, config: SourceConfig, *, root: Path | None = None) -> None:
        self._config = config
        self._root = root if root is not None else Path(config.endpoint)
        self._corpus: Corpus | None = None

    def corpus(self) -> Corpus:
        """装载（实例内缓存——一次 run 内 rev/entries 一致性由缓存保证）。"""
        if self._corpus is None:
            self._corpus = load_corpus(self._root)
        return self._corpus

    @property
    def rev(self) -> str:
        return self.corpus().rev

    def fetch(self, org: str) -> Iterator[EntityRecord | RelationRecord]:
        corpus = self.corpus()
        for entry in corpus.entries:
            if not entry.pure:
                continue  # 覆盖层不是源端事实——curated 合并面（yaml_merge）
            yield EntityRecord(
                type=entry.type, key=entry.key,
                name=entry.name or entry.key,
                attrs={"owner": entry.owner} if entry.owner else {},
            )
            for ref in entry.refers_to:
                rtype, _, rkey = ref.partition(":")
                yield RelationRecord(
                    src=(entry.type, entry.key), rel_type="refers_to",
                    dst=(rtype, rkey),
                )
            for ref in entry.related_to:
                rtype, _, rkey = ref.partition(":")
                yield RelationRecord(
                    src=(entry.type, entry.key), rel_type="related_to",
                    dst=(rtype, rkey),
                )

    def close(self) -> None:  # 本地目录读取——无传输资源
        return None
