"""m2s-6 G-21 未闭 P3 顺手项收口（B 项核销面——任务书）。

- `/semantic/l0` 无 build 返回空片段（TC-SEM-06 注句——G-21 挂账「构建
  产物语义」锁定用例）；
- annotate 端点异常面完整（G-21 P3-16：仅捕 ValueError → 其他实现异常裸
  500——m2s-6 补统一 500 + 日志，与 describe_table 兜底同款）；
- fuzzy/实体路 REST 参数面（/api/search entities/auto_entities——A1 api 层）。
"""

from __future__ import annotations


def test_g21_l0_empty_without_build(app_env) -> None:
    """/semantic/l0 无 build → dict_rev=None + 空片段（构建产物语义——
    TC-SEM-06 注句；未构建不服务识别的先构建操作序）。"""
    client = app_env["client"]
    token = app_env["jwt"]("u_full", org="org:tax")
    r = client.get("/api/orgs/org:tax/semantic/l0",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["dict_rev"] is None
    assert body["fragments"] == []
    assert body["token_estimate"] == 0


def test_g21_annotate_internal_error_500(app_env, monkeypatch) -> None:
    """annotate 实现异常（非 ValueError）→ 统一 500 + 不外泄栈帧
    （G-21 P3-16 收口——describe_table 同款兜底）。"""
    import knowledge_lattice.core.semantic.annotator as ann_mod

    def _boom(*a, **kw):
        raise RuntimeError("injected internal failure")

    monkeypatch.setattr(ann_mod, "annotate_text", _boom)
    client = app_env["client"]
    token = app_env["jwt"]("u_full", org="org:tax")
    r = client.post("/api/orgs/org:tax/semantic/annotate",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"text": "进项税额抵扣"})
    assert r.status_code == 500
    assert "RuntimeError" in r.json()["detail"]
    assert "Traceback" not in r.json()["detail"]


def test_api_search_entity_params_validation(app_env) -> None:
    """/api/search 实体参数面：entities >20 → 400；auto_entities 空识别
    （无构建词典）→ 正常检索不启用实体路（增益路失败不阻断）。"""
    client = app_env["client"]
    token = app_env["jwt"]("u_full", org="org:tax")
    r = client.post("/api/search",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"query": "进项抵扣", "entities": list(range(1, 22))})
    assert r.status_code == 400
    assert "entities" in r.json()["detail"]
    # 无构建 + auto_entities=True：识别零命中 → 正常返回（不 500）
    r2 = client.post("/api/search",
                     headers={"Authorization": f"Bearer {token}"},
                     json={"query": "进项抵扣", "auto_entities": True})
    assert r2.status_code == 200
    assert "results" in r2.json()
