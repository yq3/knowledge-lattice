"""YAML 覆盖层仓库装载与 CI 校验规则集（design §5.8 YAML 规范 / 合并规则表
L905-952——m2s-3）。

仓库布局（§5.8）：`_schema/*.schema.json` + `concepts/` + `templates/` +
`report_items/` + `scenarios/` + `l0.yaml`；本段最小实现另接受
`dim_value_map.yaml`（TC-SYNC-06 值域显式映射表——design §4 无专表 DDL，
任务书授权最小实现+登记，演进缝触发时再议专表）。

- `load_corpus`：装载为结构化 Corpus；rev = 全仓内容哈希前 12 hex（YAML
  commit 的本地形态——git checkout 场景内容等价即可比，无需 .git）；
- `validate_corpus`：合并规则表中 CI 责任列 + TC-YAML-04 校验全集——
  返回 Issue 列表（error=拦截 / warning=提示），CI 与构建报告共用本规则集；
- L0 预算：`estimate_tokens`（CJK 计字 + 拉丁计词）× `semantic_l0_token_budget`
  （默认 1500——§5.8 YAML 规范 l0 行）。

owner 必填口径：§10「每条 YAML 必填 owner」按**全部条目**（纯人工+覆盖层）
执行——design §5.8 覆盖层样例未带 owner 属样例缺项，以规则文本为准（注记）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from knowledge_lattice.core.semantic.constants import (
    PURE_YAML_ENTITY_TYPES,
    SEM_ENTITY_TYPES,
    SEM_REL_TYPE_NAMES,
    YAML_DIR_TYPE_DOMAINS,
    rel_type_allowed,
)
from knowledge_lattice.core.semantic.norm import normalize_alias

logger = logging.getLogger(__name__)

__all__ = [
    "AliasSpec", "FieldOverlay", "ExtraRelation", "YamlEntry", "Corpus", "Issue",
    "load_corpus", "validate_corpus", "estimate_tokens", "COMMON_ALIAS_WORDS",
]

# 常用词黑名单（≥2 字——1 字由短词规则拦截；§5.8 合并规则表「常用词」行的
# 最小集，命中未标 context/fuzzy_only 即拦；领域实词〔如「税额」——design §5.8
# 样例别名〕不进黑名单，由歧义消歧面兜）
COMMON_ALIAS_WORDS = frozenset({
    "一个", "什么", "怎么", "这个", "那个", "我们", "他们", "没有", "可以",
    "如果", "但是", "情况", "问题", "发票", "模板", "报表",
})

_MIN_ALIAS_LEN = 2


@dataclass(frozen=True)
class Issue:
    """CI/构建报告问题条目（severity=error 拦截 / warning 提示）。"""

    severity: str        # "error" | "warning"
    file: str            # 仓库相对路径（定位到文件）
    message: str

    def __str__(self) -> str:  # CI 脚本直出
        return f"[{self.severity.upper()}] {self.file}: {self.message}"


@dataclass(frozen=True)
class AliasSpec:
    """别名声明：裸字符串（exact）或 {value, match_mode} 形态。"""

    value: str
    match_mode: str = "exact"   # exact | fuzzy_only | context


@dataclass(frozen=True)
class FieldOverlay:
    """覆盖层内嵌字段（template_field 等子实体的 curated 载体）。"""

    id: str
    aliases: tuple[AliasSpec, ...] = ()
    abbr: tuple[str, ...] = ()
    definition: str | None = None


@dataclass(frozen=True)
class ExtraRelation:
    """人工补充关系（源系统缺失——§5.8 extra_relations）。"""

    rel: str
    src: str
    dst: str
    note: str | None = None


@dataclass
class YamlEntry:
    """一条 YAML 条目（纯人工实体或覆盖层）。"""

    id: str
    type: str
    key: str
    file: str
    pure: bool                      # concepts/ 目录（纯人工实体）
    name: str | None = None
    aliases: tuple[AliasSpec, ...] = ()
    abbr: tuple[str, ...] = ()
    definition: str | None = None
    why: str | None = None
    caliber: str | None = None
    examples: tuple[str, ...] = ()
    samples: tuple[str, ...] = ()
    disambiguation: tuple[dict, ...] = ()
    refers_to: tuple[str, ...] = ()
    related_to: tuple[str, ...] = ()
    l0: bool = False
    sensitivity: str | None = None
    owner: str | None = None
    fields: tuple[FieldOverlay, ...] = ()
    extra_relations: tuple[ExtraRelation, ...] = ()
    raw: dict = field(default_factory=dict)   # 原始映射（JSON Schema 条目级校验面——R2/边界1）

    def abbr_specs(self) -> tuple[AliasSpec, ...]:
        """缩写列表 → AliasSpec（缩写天然短，不参与短词拦截——见 validate）。"""
        return tuple(AliasSpec(value=a) for a in self.abbr)

    def curated_payload(self) -> dict:
        """curated_json 载荷（非空字段——YAML 合并写入 sem_entities.curated_json）。

        R2/边界 4：`l0` 与 `owner` 入载荷——design §5.8 三种内容分工表把「L0
        标记」列入人工内容面；owner 为构建报告（§10「无人维护与孤立条目」）
        与 m2s-4 L0 导出的数据源。l0 仅在 True 时落键（缺省=非 L0）。"""
        out: dict = {}
        for k in ("definition", "why", "caliber"):
            v = getattr(self, k)
            if v:
                out[k] = v
        for k in ("examples", "samples"):
            v = getattr(self, k)
            if v:
                out[k] = list(v)
        if self.disambiguation:
            out["disambiguation"] = list(self.disambiguation)
        if self.l0:
            out["l0"] = True
        if self.owner:
            out["owner"] = self.owner
        return out


@dataclass
class Corpus:
    """整仓装载产物。"""

    root: Path
    entries: list[YamlEntry] = field(default_factory=list)
    l0_extra: tuple[dict, ...] = ()                       # l0.yaml {id, text}
    dim_value_map: dict[str, dict[str, str]] = field(default_factory=dict)
    rev: str = ""


def _alias_specs(raw) -> tuple[AliasSpec, ...]:
    if not raw:
        return ()
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append(AliasSpec(value=item))
        elif isinstance(item, dict) and item.get("value"):
            out.append(AliasSpec(
                value=str(item["value"]),
                match_mode=str(item.get("match_mode", "exact")),
            ))
    return tuple(out)


def _parse_entry(raw: dict, file: str, pure: bool) -> YamlEntry:
    eid = str(raw.get("id", ""))
    etype, _, key = eid.partition(":")
    return YamlEntry(
        id=eid, type=etype, key=key, file=file, pure=pure, raw=raw,
        name=(str(raw["name"]) if raw.get("name") else None),
        aliases=_alias_specs(raw.get("aliases")),
        abbr=tuple(str(a) for a in raw.get("abbr") or ()),
        definition=(str(raw["definition"]).strip() if raw.get("definition") else None),
        why=(str(raw["why"]).strip() if raw.get("why") else None),
        caliber=(str(raw["caliber"]).strip() if raw.get("caliber") else None),
        examples=tuple(str(x) for x in raw.get("examples") or ()),
        samples=tuple(str(x) for x in raw.get("samples") or ()),
        disambiguation=tuple(dict(d) for d in raw.get("disambiguation") or ()),
        refers_to=tuple(str(r) for r in raw.get("refers_to") or ()),
        related_to=tuple(str(r) for r in raw.get("related_to") or ()),
        l0=bool(raw.get("l0", False)),
        sensitivity=(str(raw["sensitivity"]) if raw.get("sensitivity") else None),
        owner=(str(raw["owner"]) if raw.get("owner") else None),
        fields=tuple(
            FieldOverlay(
                id=str(f.get("id", "")),
                aliases=_alias_specs(f.get("aliases")),
                abbr=tuple(str(a) for a in f.get("abbr") or ()),
                definition=(str(f["definition"]).strip() if f.get("definition") else None),
            )
            for f in raw.get("fields") or ()
        ),
        extra_relations=tuple(
            ExtraRelation(
                rel=str(x.get("rel", "")), src=str(x.get("from", "")),
                dst=str(x.get("to", "")),
                note=(str(x["note"]) if x.get("note") else None),
            )
            for x in raw.get("extra_relations") or ()
        ),
    )


def _content_rev(root: Path) -> str:
    """全仓内容哈希（排序遍历，sha256 前 12 hex——与 dict_rev 同展示形态）。
    跳过点目录（`.git`/`.github` 等——P3-7/R2：checkout 元数据变动不得扰动 rev）。"""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue  # 点目录（VCS/编辑器元数据）非语料内容
        digest.update(str(rel).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def load_corpus(root: Path | str) -> Corpus:
    """装载 YAML 仓（结构错误直接抛 ValueError——装载面 fail-fast；CI 规则面
    由 validate_corpus 承担）。"""
    import yaml

    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"yaml repo not found: {root!s}")

    corpus = Corpus(root=root, rev=_content_rev(root))
    for dirname in sorted(YAML_DIR_TYPE_DOMAINS):
        dir_ = root / dirname
        if not dir_.is_dir():
            continue
        for f in sorted(dir_.glob("*.yaml")):
            docs = yaml.safe_load(f.read_text(encoding="utf-8"))
            if docs is None:
                continue
            if not isinstance(docs, list):
                raise ValueError(f"{f}（YAML 顶层须为条目列表）")
            rel = f.relative_to(root).as_posix()
            for raw in docs:
                if not isinstance(raw, dict):
                    raise ValueError(f"{rel}: 条目须为映射")
                corpus.entries.append(
                    _parse_entry(raw, rel, pure=dirname == "concepts"))

    l0_file = root / "l0.yaml"
    if l0_file.is_file():
        doc = yaml.safe_load(l0_file.read_text(encoding="utf-8")) or {}
        entries = doc.get("entries", doc) if isinstance(doc, dict) else doc
        corpus.l0_extra = tuple(
            {"id": str(e.get("id", "")), "text": str(e.get("text", ""))}
            for e in entries or () if isinstance(e, dict)
        )

    map_file = root / "dim_value_map.yaml"
    if map_file.is_file():
        doc = yaml.safe_load(map_file.read_text(encoding="utf-8")) or {}
        for m in doc.get("mappings") or ():
            dim = str(m.get("dim", ""))
            if dim and isinstance(m.get("values"), dict):
                corpus.dim_value_map.setdefault(
                    dim, {str(k): str(v) for k, v in m["values"].items()})
    return corpus


def estimate_tokens(text: str) -> int:
    """L0 token 估算（CJK 计字 + 其余按空白分词——§5.8 l0 预算的保守估计）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    non_cjk = "".join(ch for ch in text if not ("\u4e00" <= ch <= "\u9fff"))
    words = len([w for w in non_cjk.split() if w])
    return cjk + words


def _alias_blocked(spec: AliasSpec) -> str | None:
    """短词/常用词且未标 context/fuzzy_only → 拦截原因（合并规则表两行）。"""
    norm = normalize_alias(spec.value)
    if not norm:
        return "empty alias"
    if len(norm) < _MIN_ALIAS_LEN and spec.match_mode not in ("context", "fuzzy_only"):
        return f"short alias {spec.value!r} (<{_MIN_ALIAS_LEN} chars) needs context/fuzzy_only"
    if norm in COMMON_ALIAS_WORDS and spec.match_mode not in ("context", "fuzzy_only"):
        return f"common word alias {spec.value!r} needs context/fuzzy_only"
    return None


def _ref_type(ref: str) -> str:
    return ref.partition(":")[0]


_VALID_MATCH_MODES = ("exact", "fuzzy_only", "context")
_ENTRY_SCHEMA_NAME = "entry.schema.json"


def _schema_self_check(schema: dict) -> str | None:
    """schema 一次性自校验（R3/N6）：jsonschema 在场走 `validator_for`
    .check_schema；缺席时走 `_minimal_schema_self_check`（与条目校验同一
    回退口径——语义非法 schema 在零依赖环境同样被拦，门禁不静默削弱）。
    返回问题描述（None=合法）。"""
    try:
        import jsonschema
    except ImportError:
        return _minimal_schema_self_check(schema)
    try:
        jsonschema.validators.validator_for(schema).check_schema(schema)
        return None
    except jsonschema.exceptions.SchemaError as exc:
        return str(exc)


_MINIMAL_SCHEMA_TYPES = frozenset({
    "object", "array", "string", "integer", "number", "boolean", "null",
})


def _minimal_schema_self_check(schema: object, path: str = "$") -> str | None:
    """回退路径最小 schema 合法性检查（R3/N6 + B2⑦/m2s-4——与 jsonschema 路径
    对称，且不再误拦合法形态）：type 接受单值或**数组**（如 ["string","null"]）、
    **布尔子 schema**（true/false——允许/拒绝任何值）合法、items 接受对象（单
    schema）或**数组**（tuple 形态）；required/enum/properties 形状校验保留；
    未知关键字忽略（方言子集口径）。畸形输入 except 兜底返回可定位信息
    （不崩溃——fail-closed 方向不变，零依赖 only）。"""
    try:
        return _minimal_schema_self_check_impl(schema, path)
    except Exception as exc:  # noqa: BLE001 —— B2⑦：畸形 schema 兜底不崩溃
        return f"{path}: schema 自校验异常（{type(exc).__name__}: {exc}）"


def _minimal_schema_self_check_impl(schema: object, path: str) -> str | None:
    if schema is True or schema is False:
        return None                      # 布尔子 schema（合法 JSON Schema 形态）
    if not isinstance(schema, dict):
        return f"{path}: schema 须为对象"
    stype = schema.get("type")
    if stype is not None:
        types = stype if isinstance(stype, list) else [stype]
        if not types or not all(
            isinstance(t, str) and t in _MINIMAL_SCHEMA_TYPES for t in types
        ):
            return (f"{path}: 未知 type {stype!r}"
                    f"（合法：{sorted(_MINIMAL_SCHEMA_TYPES)}）")
    if "required" in schema and not (
        isinstance(schema["required"], list)
        and all(isinstance(r, str) for r in schema["required"])
    ):
        return f"{path}: required 须为字符串数组"
    if "enum" in schema and not isinstance(schema["enum"], list):
        return f"{path}: enum 须为数组"
    if "properties" in schema and not isinstance(schema["properties"], dict):
        return f"{path}: properties 须为对象"
    if "items" in schema:
        items = schema["items"]
        if not isinstance(items, (dict, list)) and items not in (True, False):
            return f"{path}: items 须为对象或数组（tuple 形态）"
    for key, sub in (schema.get("properties") or {}).items():
        problem = _minimal_schema_self_check(sub, f"{path}.{key}")
        if problem:
            return problem
    items = schema.get("items")
    if isinstance(items, dict):
        return _minimal_schema_self_check(items, f"{path}.items")
    if isinstance(items, list):
        for k, sub in enumerate(items):
            problem = _minimal_schema_self_check(sub, f"{path}.items[{k}]")
            if problem:
                return problem
    return None


def _schema_errors(instance: dict, schema: dict) -> list[str]:
    """JSON Schema 校验（最小实现——R2/边界 1）：优先 `jsonschema` 库（可用
    时全量方言——R3/N6：按 `validator_for` 检出的校验器实例化，不硬编码
    Draft 版本，`$schema` 非 2020-12 的合法 schema 不误抛）；不可用时回退
    手写子集（type/required/properties/enum/items/additionalProperties——CI
    环境无第三方依赖也能跑）。schema 自身合法性由加载时 `_schema_self_check`
    一次性保证（本方法不重复 check_schema）。"""
    try:
        import jsonschema
    except ImportError:
        return _minimal_schema_errors(instance, schema)
    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda e: list(e.absolute_path),
    )
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '$'}: {e.message}"
        for e in errors
    ]


def _minimal_schema_errors(instance: dict, schema: dict, path: str = "$") -> list[str]:
    """手写最小子集（jsonschema 缺席时的回退——未知关键字忽略；B2⑦/m2s-4：
    布尔子 schema（true 放行/false 拒绝）、type 数组（any-of）、items 数组
    （tuple 按位）同口径；畸形 schema except 兜底不崩溃——fail-closed 方向）。"""
    try:
        if schema is True:
            return []
        if schema is False:
            return [f"{path}: schema false（任何值都不通过）"]
        if not isinstance(schema, dict):
            return [f"{path}: schema 非法形态（须对象/布尔）"]
        return _minimal_schema_errors_impl(instance, schema, path)
    except Exception as exc:  # noqa: BLE001 —— B2⑦：兜底（可定位不崩溃）
        return [f"{path}: 校验异常（{type(exc).__name__}: {exc}）"]


def _type_matches(instance, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(instance, dict)
    if type_name == "array":
        return isinstance(instance, list)
    if type_name == "string":
        return isinstance(instance, str)
    if type_name == "boolean":
        return isinstance(instance, bool)
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if type_name == "null":
        return instance is None
    return True


def _minimal_schema_errors_impl(instance, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if types and not any(_type_matches(instance, t) for t in types):
            errors.append(
                f"{path}: expected {'|'.join(map(str, types))}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']!r}")
    if isinstance(instance, dict):
        for req in schema.get("required", ()):
            if req not in instance:
                errors.append(f"{path}: {req!r} is a required property")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors.extend(
                    _minimal_schema_errors(value, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(
                    f"{path}.{key}: additional property not allowed")
    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):            # 单 schema：逐项
            for i, item in enumerate(instance):
                errors.extend(
                    _minimal_schema_errors(item, items, f"{path}[{i}]"))
        elif isinstance(items, list):          # tuple 形态：按位校验
            for i, (item, sub) in enumerate(zip(instance, items)):
                errors.extend(
                    _minimal_schema_errors(item, sub, f"{path}[{i}]"))
    return errors


def validate_corpus(corpus: Corpus, *, l0_budget: int = 1500) -> list[Issue]:
    """CI 校验全集（TC-YAML-04）——错误可定位到文件；warning 供构建报告。

    R2/边界 1：`_schema/entry.schema.json` 在场时按条目做 **JSON Schema 校验**
    （`_schema_errors`——jsonschema 库优先、手写子集回退）；手写结构规则保留为
    补充面（schema 未覆盖的语义约束仍由本函数承担）。"""
    issues: list[Issue] = []
    by_id = {e.id: e for e in corpus.entries}

    # _schema 自描述存在性（缺失为 warning——schema 文件集非功能前置）
    entry_schema: dict | None = None
    if not (corpus.root / "_schema").is_dir():
        issues.append(Issue("warning", "_schema/", "schema 自描述目录缺失（建议随仓维护）"))
    else:
        for f in sorted((corpus.root / "_schema").glob("*.json")):
            rel = f.relative_to(corpus.root).as_posix()
            try:
                parsed = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as exc:
                issues.append(Issue(
                    "error", rel, f"schema JSON 解析失败: {exc}"))
                continue
            if f.name != _ENTRY_SCHEMA_NAME:
                continue
            # R3/N6：entry.schema.json 加载时一次性自校验——语义非法 → 可定位
            # error + entry_schema 置 None（条目走手写补充面，不崩溃不静默）
            if not isinstance(parsed, dict):
                issues.append(Issue(
                    "error", rel, "entry.schema.json 须为 JSON 对象（schema 文件）"))
                continue
            problem = _schema_self_check(parsed)
            if problem is not None:
                issues.append(Issue("error", rel, f"schema 语义非法: {problem}"))
                continue
            entry_schema = parsed

    l0_tokens = 0
    # 别名冲突检测的聚合面：alias_norm → [(entity_id, has_disambiguation, marked)]
    alias_owners: dict[str, list[tuple[str, bool, bool]]] = {}
    # P3-8①/R2：全局 id 唯一（design 样例「全局唯一，CI 校验」——条目+内嵌字段）
    id_locations: dict[str, list[str]] = {}

    def _collect_alias(entity_id: str, spec: AliasSpec, file: str,
                       has_disamb: bool) -> None:
        norm = normalize_alias(spec.value)
        blocked = _alias_blocked(spec)
        if blocked:
            issues.append(Issue("error", file, f"alias blocked: {blocked}"))
        alias_owners.setdefault(norm, []).append(
            (entity_id, has_disamb, spec.match_mode == "context"))

    for entry in corpus.entries:
        # 边界 1/R2：JSON Schema 条目级校验（entry.schema.json 在场时）
        if entry_schema is not None and entry.raw:
            for err in _schema_errors(entry.raw, entry_schema):
                issues.append(Issue(
                    "error", entry.file, f"schema violation: {err}"))
        # P3-8②/R2：match_mode 枚举（非法值入库会撞 DB CHECK → run failed）
        for spec in (*entry.aliases,
                     *(s for f in entry.fields for s in f.aliases)):
            if spec.match_mode not in _VALID_MATCH_MODES:
                issues.append(Issue(
                    "error", entry.file,
                    f"match_mode 非法 {spec.match_mode!r}"
                    f"（合法：{list(_VALID_MATCH_MODES)}）——alias {spec.value!r}"))
        # P3-8①/R2：id 唯一性登记（条目 + 内嵌字段）
        id_locations.setdefault(entry.id, []).append(entry.file)
        for f in entry.fields:
            id_locations.setdefault(f.id, []).append(entry.file)
        # 结构面
        if not entry.type or not entry.key or entry.type not in SEM_ENTITY_TYPES:
            issues.append(Issue(
                "error", entry.file, f"malformed id {entry.id!r}（须 type:key 且 type 已知）"))
            continue
        domain = next(
            (d for d, types in YAML_DIR_TYPE_DOMAINS.items()
             if entry.file.startswith(f"{d}/") and entry.type in types), None)
        if domain is None:
            issues.append(Issue(
                "error", entry.file,
                f"条目类型 {entry.type} 与目录域不符（pure entry 仅允许 "
                "concept/system——concepts/ 目录；其余目录按域）"))
            continue
        if entry.pure and entry.type not in PURE_YAML_ENTITY_TYPES:
            issues.append(Issue(
                "error", entry.file,
                f"纯人工实体仅允许 concept/system（got {entry.type}）"))
        if not entry.owner:
            issues.append(Issue("error", entry.file, "owner 缺失（每条 YAML 必填 owner）"))
        if entry.pure and not entry.name:
            issues.append(Issue("error", entry.file, "纯人工实体 name 必填"))
        if entry.sensitivity is not None and entry.sensitivity not in ("normal", "restricted"):
            issues.append(Issue(
                "error", entry.file,
                f"sensitivity 非法 {entry.sensitivity!r}（normal|restricted）"))
        if len(entry.samples) > 3:
            issues.append(Issue(
                "error", entry.file,
                f"samples 超限（{len(entry.samples)} > 3——样本值 ≤3，v1.4/#42 P2）"))
        has_disamb = bool(entry.disambiguation)
        for spec in entry.aliases:
            _collect_alias(entry.id, spec, entry.file, has_disamb)
        for a in entry.abbr:
            norm = normalize_alias(a)
            alias_owners.setdefault(norm, []).append((entry.id, has_disamb, False))
        for f in entry.fields:
            for spec in f.aliases:
                _collect_alias(f.id, spec, entry.file, False)
        if entry.l0:
            l0_tokens += (estimate_tokens(entry.name or "")
                          + estimate_tokens(entry.definition or "")
                          + sum(estimate_tokens(a.value) for a in entry.aliases))

        # 引用面
        for ref in (*entry.refers_to, *entry.related_to):
            rtype = _ref_type(ref)
            if not rtype or ":" not in ref or rtype not in SEM_ENTITY_TYPES:
                issues.append(Issue("error", entry.file, f"malformed reference {ref!r}"))
            elif rtype in PURE_YAML_ENTITY_TYPES and ref not in by_id:
                issues.append(Issue(
                    "error", entry.file,
                    f"reference {ref!r} not in repo（concept/system 只能出自本仓）"))
            elif ref not in by_id:
                issues.append(Issue(
                    "warning", entry.file,
                    f"reference {ref!r} not in repo（可解析自同步实体——未同步仅警告）"))
        if entry.related_to:
            if entry.type != "concept":
                # P3-8③/R2：白名单 related_to 仅 concept→concept——src 非概念
                # 运行时必被拒，CI 前置拦截
                issues.append(Issue(
                    "error", entry.file,
                    f"related_to 声明方只允许 concept（got {entry.type}"
                    f" {entry.id!r}——白名单 concept→concept）"))
            for ref in entry.related_to:
                if _ref_type(ref) != "concept":
                    issues.append(Issue(
                        "error", entry.file,
                        f"related_to 端点只允许 concept（got {ref!r}）"))

    # extra_relations 白名单
    for entry in corpus.entries:
        for xr in entry.extra_relations:
            st, _, _ = xr.src.partition(":")
            dt, _, _ = xr.dst.partition(":")
            if xr.rel not in SEM_REL_TYPE_NAMES:
                issues.append(Issue(
                    "error", entry.file, f"extra_relations 未知 rel {xr.rel!r}"))
            elif not rel_type_allowed(xr.rel, st, dt):
                issues.append(Issue(
                    "error", entry.file,
                    f"extra_relations 端点类型不在 whitelist: {xr.rel} {xr.src}→{xr.dst}"))
            for ref in (xr.src, xr.dst):
                if _ref_type(ref) in PURE_YAML_ENTITY_TYPES and ref not in by_id:
                    issues.append(Issue(
                        "error", entry.file,
                        f"extra_relations 端点 {ref!r} not in repo"))

    # 别名冲突（同 norm 多实体）：至少一方 disambiguation 或别名标 context
    for norm, owners in alias_owners.items():
        ids = {o[0] for o in owners}
        if len(ids) > 1 and not any(o[1] or o[2] for o in owners):
            issues.append(Issue(
                "error", "/".join(sorted(e.file for e in corpus.entries
                                         if e.id in ids)),
                f"ambiguous alias {norm!r} → {sorted(ids)}：需至少一方 disambiguation"
                " 或别名标 match_mode: context"))

    # P3-2/R2 CI 查重：同一实体内重复 alias_norm（aliases/abbr 跨清单撞）→
    # error（合并侧仅保首条，重复面应在提交前消除）
    for entry in corpus.entries:
        seen: set[str] = set()
        for spec in (*entry.aliases, *entry.abbr_specs()):
            norm = normalize_alias(spec.value)
            if norm in seen:
                issues.append(Issue(
                    "error", entry.file,
                    f"duplicate alias {spec.value!r}（同条目内 alias_norm 重复——"
                    "UNIQUE(org,entity,alias_norm) 约束面）"))
            seen.add(norm)

    # P3-8①/R2：全局 id 唯一（design 样例「全局唯一，CI 校验」）
    for eid, files in sorted(id_locations.items()):
        if len(files) > 1:
            issues.append(Issue(
                "error", "/".join(sorted(set(files))),
                f"duplicate id {eid!r}（全局唯一——出现于 {len(files)} 处）"))

    # L0 预算
    l0_tokens += sum(estimate_tokens(str(e.get("text", ""))) for e in corpus.l0_extra)
    if l0_tokens > l0_budget:
        issues.append(Issue(
            "error", "l0.yaml",
            f"L0 总 token 超预算（{l0_tokens} > {l0_budget}）——CI 拦截"))

    return issues
