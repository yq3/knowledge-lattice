"""TC-ING-05 mojibake 质量门三档【单测｜M1——纯函数 + sqlite 摄取链】。

- 正常字符比 > 0.55 → 正常通过；0.40~0.55 → 告警（重试——TXT 编码候选已穷尽，
  按最优候选继续 + 审计事件）；< 0.40 → 失败（任务 failed、pending 版本删块 T8）。
"""

from __future__ import annotations

import pytest

from knowledge_lattice.core.docs.quality import (
    MojibakeQualityError,
    mojibake_tier,
    normal_char_ratio,
)

ORG = "org:tax"

# 造数字符：€（U+20AC）在 gb18030 下 0x80 单字节映射——「可解码但不正常」；
# U+FFFD 置换符为另一异常形态（两者均不在正常区间）。
ABN = "€"


def test_ing_05a_tier_boundaries() -> None:
    """三档边界：>0.55 pass / [0.40, 0.55) warn / <0.40 fail。"""
    assert mojibake_tier("正常中文内容占比充足的一段时间内没有异常字符" * 3)[0] == "pass"
    # 精确边界：40% 与 55%
    warn_text = "正" * 4 + ABN * 6  # 40% 正常 → warn 下边界
    tier, ratio = mojibake_tier(warn_text)
    assert tier == "warn" and abs(ratio - 0.4) < 1e-9
    mid = "正" * 5 + ABN * 5  # 50%
    assert mojibake_tier(mid)[0] == "warn"
    just_pass = "正" * 56 + ABN * 44  # 56% → pass 上边界
    assert mojibake_tier(just_pass)[0] == "pass"
    just_fail = "正" * 39 + ABN * 61  # 39% → fail
    tier, ratio = mojibake_tier(just_fail)
    assert tier == "fail" and ratio < 0.40
    # 空白不计分母；空文本 → 满比
    assert normal_char_ratio("") == 1.0
    assert normal_char_ratio("  \n\t ") == 1.0


def test_ing_05b_fail_tier_rejects_ingest(ingest_env) -> None:
    """失败档：解析产物主要为异常字符 → MojibakeQualityError → 任务 failed、
    pending 失败删块（T8——失败不留检索残留）。"""
    env = ingest_env
    payload = (ABN * 160).encode("gb18030")  # 解码成功但 0% 正常
    from fake_providers import FakeEmbedder

    svc = env["make_service"](FakeEmbedder(dim=2560))
    doc_id, task_id = svc.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="乱码样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=payload, mime_type="text/plain", filename="mojibake.txt",
    )
    with pytest.raises(MojibakeQualityError, match="mojibake"):
        svc.run_task(task_id)

    task = env["backend"].get_task(task_id)
    assert task["status"] == "failed" and "mojibake" in task["error"]
    doc = env["backend"].get_document(doc_id)
    assert doc["pending_status"] == "failed", "首次上传失败留在 pending 态（未切换）"
    assert env["conn"].execute(
        "SELECT count(*) FROM chunks WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0] == 0, "失败版本不留块（T8）"


def test_ing_05c_warn_tier_continues_with_audit(ingest_env) -> None:
    """告警档：编码候选穷尽后按最优候选继续摄取 + quality.mojibake_warn 审计。"""
    from fake_providers import FakeEmbedder

    env = ingest_env
    # 50% 正常 / 50% €：utf-8 解码失败（€ 的 gb18030 字节非 UTF-8），gb18030
    # 解码成功 → 最优候选 50% → warn 档继续
    text = "正常条款内容占五成" * 5 + ABN * 45
    svc = env["make_service"](FakeEmbedder(dim=2560))
    doc_id, task_id = svc.create_document(
        org_id=ORG, dataset_id="ds:vat_lib", title="半乱码样例",
        dims={"region": ["CN"]}, owner_user_id="u_full",
        file_bytes=text.encode("gb18030"), mime_type="text/plain",
        filename="half.txt",
    )
    svc.run_task(task_id)  # warn 不 raise

    assert env["backend"].get_task(task_id)["status"] == "done"
    assert env["backend"].get_document(doc_id)["active_status"] == "searchable_full"
    warned = env["conn"].execute(
        "SELECT count(*) FROM audit_outbox WHERE event_type = 'quality.mojibake_warn'"
    ).fetchone()[0]
    assert warned >= 1, "告警档应落 quality.mojibake_warn 审计事件"
