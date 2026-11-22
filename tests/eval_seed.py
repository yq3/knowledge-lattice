"""评测 clean 矩阵种子（单一来源——门禁评测环境与基线生成环境同源）。

m3-5 P3-8/P3-9 前提：deepeval 门禁的冻结表与 ``eval/reports/m3-baseline-*.json``
同源，要求**门禁测试环境 == 基线生成环境**（否则 in-corpus 名次面漂移——
m3-4 门禁沿用 conftest 标准矩阵〔含 5 篇语料外杂文档〕，recall@10 恰好一致
但 RR 被杂文档压缩名次，sqlite q11 实测 0.3333 ≠ 基线 0.25——m3-5 起 clean
 env 对齐，语料外命中面移除，「确定性系统冻结值即可复现值」严格成立）。

使用方：``tests/test_eval_gate_m34.py``（门禁）与 ``scripts/eval_baseline.py``
（基线生成）——**改本函数会同时影响两者**，重测须同步冻结表与基线 JSON。
"""

from __future__ import annotations

ORG = "org:tax"


def seed_clean_eval_matrix(db) -> None:
    """org:tax 评测 clean 矩阵（org/dims/users/grants——零语料文档）。

    与 conftest 标准矩阵的差异：不含 d_cn/d_multi 等 5 篇杂文档（评测语料
    73 docs 是唯一文档面）；u_full 带全维度授权（语料含 tax_type=VAT 文档
    ——FR-4 写校验面）。
    """
    from helpers import (
        dim_id_for,
        seed_dataset,
        seed_dim_value,
        seed_dimension,
        seed_grant,
        seed_membership,
        seed_org,
        seed_user,
        val_id_for,
    )

    seed_org(db, ORG)
    seed_dataset(db, ORG, "ds:vat_lib")
    seed_dataset(db, ORG, "ds:expense_lib")
    seed_dimension(db, ORG, "region")
    seed_dim_value(db, dim_id_for(ORG, "region"), "CN")
    seed_dim_value(db, dim_id_for(ORG, "region"), "OS")
    seed_dimension(db, ORG, "tax_type")
    db.execute(
        "UPDATE dimensions SET required = 0 WHERE org_id = ? AND key = 'tax_type'",
        (ORG,),
    )
    seed_dim_value(db, dim_id_for(ORG, "tax_type"), "VAT")
    seed_user(db, "u_full")
    seed_membership(db, "u_full", ORG)
    for value in ("CN", "OS"):
        seed_grant(
            db, user_id="u_full", dim_id=dim_id_for(ORG, "region"),
            val_id=val_id_for(ORG, "region", value),
        )
    seed_grant(  # 语料含 tax_type=VAT 文档——u_full 须有对应授权（FR-4 写校验）
        db, user_id="u_full", dim_id=dim_id_for(ORG, "tax_type"),
        val_id=val_id_for(ORG, "tax_type", "VAT"),
    )
    db.commit()
