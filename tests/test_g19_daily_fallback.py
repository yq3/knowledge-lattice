"""G-19 五源每日兜底调度收口（m2s-3 移交 B1——design §5.8「每天一次兜底」半句）：

- maintenance 注册表挂载 `semantic_daily_sync`：五源各一次/日兜底 sync 任务投递；
- 幂等/去重：pending 任务在队不再重复投递；窗口内成功 run（webhook/手动触发
  产物）24h 内不重复兜底（与 webhook 去重——同一 sem_sync_runs 真相源）；
- 窗口口径：semantic_night_window 配置后仅窗口内投递（本段起对兜底调度生效）；
- interval<=0 = 关闭；未配置源静默跳过（不误报）。
"""

from __future__ import annotations

import json

import pytest

from helpers import seed_org

ORG = "org:tax"
NOW = "2026-10-31 09:00:00"      # 09:00 UTC——缺省无窗口配置时可用

SOURCES_JSON = json.dumps({
    ORG: {
        "template_center": {"endpoint": "http://tc"},
        "metadata": {"endpoint": "http://md"},
        "scenario_config": {"endpoint": "http://sc"},
        "report_center": {"endpoint": "http://rc"},
        "yaml": {"endpoint": "/tmp/never"},
    },
})


@pytest.fixture()
def genv(backend, tmp_path):
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(environment="test", data_dir=tmp_path,
                        semantic_sources_json=SOURCES_JSON,
                        semantic_eval_golden_path="")
    return SimpleNamespace(db=backend, backend=backend.make_backend(),
                           settings=settings)


def _body(env, now=NOW):
    from knowledge_lattice.worker.maintenance import MAINTENANCE_BODIES

    assert "semantic_daily_sync" in MAINTENANCE_BODIES   # 注册表挂载（G-19）
    return MAINTENANCE_BODIES["semantic_daily_sync"](
        env.backend, None, env.settings, now)


def _pending_sync_tasks(env):
    rows = env.db.execute(
        "SELECT payload FROM tasks WHERE type = 'semantic_sync'"
        " AND status = 'pending'").fetchall()
    return sorted(json.loads(r[0])["adapter"] for r in rows)


def _mark_succeeded_run(env, adapter: str, finished_at: str) -> None:
    """造一次近期成功 run（webhook/手动触发的兜底去重真相源）。"""
    run_id = env.backend.sem_start_run(env.org if hasattr(env, "org") else ORG,
                                       adapter, now=finished_at)
    env.backend.sem_finish_run(
        ORG, run_id, status="succeeded", stats_json="{}", now=finished_at)


# ---- 基础：五源各一次/日投递 ----


def test_daily_fallback_enqueues_all_five_sources(genv) -> None:
    stats = _body(genv)
    assert stats["enqueued"] == 5
    assert _pending_sync_tasks(genv) == [
        "metadata", "report_center", "scenario_config", "template_center",
        "yaml",
    ]


def test_pending_tasks_not_duplicated(genv) -> None:
    """幂等：任务在队（pending 未消化）不重复投递。"""
    assert _body(genv)["enqueued"] == 5
    assert _body(genv)["enqueued"] == 0          # 二次 tick 零新增
    assert len(_pending_sync_tasks(genv)) == 5


def test_recent_success_skipped_webhook_dedup(genv) -> None:
    """与 webhook 去重：24h 内已有成功 run（webhook/手动产物）的源不兜底。"""
    _mark_succeeded_run(genv, "template_center", "2026-10-31 08:00:00")
    stats = _body(genv)
    assert stats["enqueued"] == 4
    tasks = _pending_sync_tasks(genv)
    assert "template_center" not in tasks and "yaml" in tasks


def test_stale_success_still_enqueued(genv) -> None:
    """超 24h 的成功 run 不拦截兜底（每天一次语义）。"""
    _mark_succeeded_run(genv, "template_center", "2026-10-29 08:00:00")
    assert _body(genv)["enqueued"] == 5


def test_failed_run_does_not_block_fallback(genv) -> None:
    """失败 run 不算兜底去重锚（源故障每日重试是兜底的存在意义）。"""
    run_id = genv.backend.sem_start_run(ORG, "yaml", now="2026-10-31 08:30:00")
    genv.backend.sem_finish_run(
        ORG, run_id, status="failed", stats_json="{}", error="boom",
        now="2026-10-31 08:31:00")
    stats = _body(genv)
    assert "yaml" in _pending_sync_tasks(genv)


# ---- 窗口口径 / 开关 / 配置面 ----


def test_night_window_outside_skips(genv) -> None:
    """窗口外不投递（错峰窗口——semantic_night_window 起效于兜底调度）。"""
    import dataclasses
    genv.settings = dataclasses.replace(
        genv.settings, semantic_night_window="01:00-05:00")
    stats = _body(genv, now="2026-10-31 09:00:00")     # 09:00 在窗外
    assert stats["enqueued"] == 0
    assert stats.get("window") == "01:00-05:00"
    assert _pending_sync_tasks(genv) == []


def test_night_window_inside_enqueues(genv) -> None:
    import dataclasses
    genv.settings = dataclasses.replace(
        genv.settings, semantic_night_window="01:00-05:00")
    stats = _body(genv, now="2026-10-31 02:00:00")     # 02:00 在窗内
    assert stats["enqueued"] == 5


def test_interval_disabled(genv) -> None:
    import dataclasses
    genv.settings = dataclasses.replace(
        genv.settings, semantic_daily_sync_interval_s=0)
    assert _body(genv) == "disabled"


def test_unconfigured_source_skipped(backend, tmp_path) -> None:
    """未配置的源静默跳过（无 endpoint 不投递——不误报）。"""
    from types import SimpleNamespace

    from knowledge_lattice.config import Settings

    seed_org(backend, ORG)
    settings = Settings(
        environment="test", data_dir=tmp_path,
        semantic_sources_json=json.dumps(
            {ORG: {"yaml": {"endpoint": "/tmp/never"}}}),
        semantic_eval_golden_path="")
    env = SimpleNamespace(db=backend, backend=backend.make_backend(),
                          settings=settings)
    assert _body(env)["enqueued"] == 1
    assert _pending_sync_tasks(env) == ["yaml"]


def test_run_maintenance_carries_daily_sync(genv) -> None:
    """run_maintenance 全链：body 进注册表随 maintenance 周期执行、stats 留痕。"""
    from knowledge_lattice.core.docs.credentials import CredentialService
    from knowledge_lattice.worker.maintenance import run_maintenance

    creds = CredentialService(genv.backend, genv.settings,
                              genv.settings.data_dir / "objects")
    task_id = genv.backend.create_task(None, task_type="maintenance")
    stats = run_maintenance(genv.backend, creds, genv.settings, task_id)
    assert "semantic_daily_sync" in stats
    assert stats["semantic_daily_sync"]["enqueued"] == 5
