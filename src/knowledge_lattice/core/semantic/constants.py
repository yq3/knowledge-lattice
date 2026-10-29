"""语义层常量：实体类型 / 关系类型白名单（design §5.8 L834-847 白名单表逐行）。

**三处一致**（TC-SYNC-09）：本常量 + `sem_rel_types` 迁移种子 +
`trg_sem_rel_check` 触发器——新增关系类型 = schema 变更走迁移（三方同步改）。
"""

from __future__ import annotations

# 实体类型九值（design §4 sem_entities.type CHECK 同源）
SEM_ENTITY_TYPES = frozenset({
    "concept", "system", "scenario", "template", "template_field",
    "report", "report_item", "table", "column",
})

# 任意型端点通配（§5.8 refers_to：concept / system → 任意实体——种子与触发器
# 以 '*' 表达，触发器对 '*' 放行）
DST_TYPE_ANY = "*"

# 关系类型白名单（rel_type, src_type, dst_type)——§5.8 白名单表十二行（十种
# rel_type：derived_from 两端点行、refers_to concept/system 两行）
SEM_REL_TYPES: tuple[tuple[str, str, str], ...] = (
    ("uses", "scenario", "template"),
    ("has_field", "template", "template_field"),
    ("backed_by", "template", "table"),
    ("maps_to", "template_field", "column"),
    ("has_item", "report", "report_item"),
    ("child_of", "report_item", "report_item"),
    ("derived_from", "report_item", "template_field"),
    ("derived_from", "report_item", "column"),
    ("has_column", "table", "column"),
    ("refers_to", "concept", DST_TYPE_ANY),
    ("refers_to", "system", DST_TYPE_ANY),
    ("related_to", "concept", "concept"),
)

# 十种关系类型名（计数校验用）
SEM_REL_TYPE_NAMES = frozenset(r for r, _, _ in SEM_REL_TYPES)


def rel_type_allowed(rel_type: str, src_type: str, dst_type: str) -> bool:
    """白名单判定（与 trg_sem_rel_check 同款语义——'*' 任意型放行）。

    同步编排的关系预校验用（冲突记因不写入——TC-SYNC-04）；触发器为库内
    最后防线（T-S5）。
    """
    return any(
        rel == rel_type and st == src_type and (dt == DST_TYPE_ANY or dt == dst_type)
        for rel, st, dt in SEM_REL_TYPES
    )


# 引用关系类型：metadata 适配器的引用面来源（backed_by→table / maps_to→column）
REFERENCE_REL_TYPES = ("backed_by", "maps_to")

# 本段适配器名集合（scenario_config / report_center / yaml 归后续段）
SYNC_ADAPTERS = ("template_center", "metadata")
