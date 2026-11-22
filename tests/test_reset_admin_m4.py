"""M4 m4-4 break-glass CLI（`scripts/reset_admin.py`）——subprocess 级用例。

覆盖（sqlite 真文件 + 独立 `LATTICE_DATA_DIR`；走真实进程入口，不 mock）：

- 用户不存在且未 `--create` → 退出码 2 + 提示，库内零新建；
- `--create --password-stdin` → active + sysadmin + `created_by=break-glass`，
  scrypt hash 可 ``verify_password``；stdout/审计不含 hash/明文；
- 已有用户 `--promote`：`token_version` 递增、sysadmin=true、`disabled_at` 清空，
  旧口令失效、新口令可校验，审计事件同事务落 outbox；
- `--generate`：24 字符随机口令**只出现一次**且可 `verify_password`；
- 弱口令（建号与重置两路）→ 退出码 2，用户未创建/原密码未变；
- 无口令来源且非 TTY → 退出码 2 并提示 `--password-stdin`；
- `--data-dir` 覆盖 `LATTICE_DATA_DIR`。

口径：只断言 CLI 对外行为与库内结果；不导入 CLI 内部函数（防实现耦合）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from knowledge_lattice.domain.accounts import verify_password

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "reset_admin.py"
PASSWORD = "break-glass-pass-123"
NEW_PASSWORD = "new-break-glass-pass-456"
SHORT_PASSWORD = "short"


def _run(
    data_dir: Path,
    *args: str,
    stdin: str | None = None,
    env_data_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """以子进程跑 CLI（清空全部 LATTICE_* 环境，避免门禁 PG/密码长度等串味）。"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("LATTICE_")}
    env["LATTICE_DATA_DIR"] = str(env_data_dir or data_dir)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        # 恒用管道 stdin：即使 pytest 在交互终端运行，子进程也不是 TTY——
        # 否则「无口令来源 → getpass」用例会挂起等待输入。
        input="" if stdin is None else stdin,
        text=True,
        capture_output=True,
        timeout=120,
    )


def _user(data_dir: Path, username: str) -> dict | None:
    db = data_dir / "lattice.db"
    if not db.exists():
        # 前置校验失败（弱口令/非 TTY）发生在建库之前——库不存在即用户不存在
        return None
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else dict(row)


def _audit_events(data_dir: Path) -> list[dict]:
    conn = sqlite3.connect(data_dir / "lattice.db")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT event_type, payload_json FROM audit_outbox ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _generate_password(stdout: str) -> str:
    """从 `--generate` 输出解析明文（「只显示一次」提示的下一行）。"""
    lines = stdout.splitlines()
    marker = next(
        (i for i, line in enumerate(lines) if "只显示一次" in line), None
    )
    assert marker is not None, f"缺少「只显示一次」提示：{stdout!r}"
    assert marker + 1 < len(lines), f"提示后无密码行：{stdout!r}"
    return lines[marker + 1].strip()


def _assert_no_secret_in_output(result: subprocess.CompletedProcess[str]) -> None:
    combined = result.stdout + result.stderr
    assert "scrypt$" not in combined, "hash 不得出现在 CLI 输出"
    assert PASSWORD not in combined
    assert NEW_PASSWORD not in combined


# ============ 1. 用户不存在 + 未 --create ============


def test_missing_user_without_create_exits_2(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = _run(
        data_dir, "--username", "nobody", "--password-stdin", stdin=PASSWORD + "\n"
    )
    assert result.returncode == 2, result.stderr
    assert "--create" in result.stderr
    assert "用户不存在" in result.stderr
    assert _user(data_dir, "nobody") is None


# ============ 2. --create --password-stdin ============


def test_create_active_sysadmin_with_stdin_password(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = _run(
        data_dir,
        "--username",
        "alice",
        "--create",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert result.returncode == 0, result.stderr

    row = _user(data_dir, "alice")
    assert row is not None
    assert row["status"] == "active"
    assert row["is_system_admin"] == 1
    assert row["disabled_at"] is None
    assert row["created_by"] == "break-glass"
    assert row["token_version"] == 0
    assert verify_password(PASSWORD, row["password_hash"])
    assert not verify_password("wrong-password", row["password_hash"])

    assert "created        : true" in result.stdout
    assert "is_system_admin: True" in result.stdout
    _assert_no_secret_in_output(result)

    events = _audit_events(data_dir)
    assert [e["event_type"] for e in events] == ["user.created"]
    payload = json.loads(events[0]["payload_json"])
    assert set(payload) == {"user_id", "username", "actor"}
    assert payload["actor"] == "break-glass"
    assert PASSWORD not in events[0]["payload_json"]
    assert "scrypt$" not in events[0]["payload_json"]


# ============ 3. 已有用户 --promote（tv++ / sysadmin / 清 disabled） ============


def test_promote_existing_user_resets_password_and_clears_disabled(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    created = _run(
        data_dir,
        "--username",
        "bob",
        "--create",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert created.returncode == 0, created.stderr

    # 造数：撤 sysadmin、停用、推进 tv（模拟历史账号状态）
    conn = sqlite3.connect(data_dir / "lattice.db")
    try:
        conn.execute(
            "UPDATE users SET is_system_admin = 0,"
            " disabled_at = '2020-01-01 00:00:00', token_version = 7"
            " WHERE username = 'bob'"
        )
        conn.commit()
    finally:
        conn.close()

    result = _run(
        data_dir,
        "--username",
        "bob",
        "--promote",
        "--password-stdin",
        stdin=NEW_PASSWORD + "\n",
    )
    assert result.returncode == 0, result.stderr

    row = _user(data_dir, "bob")
    assert row is not None
    assert row["is_system_admin"] == 1
    assert row["disabled_at"] is None
    assert row["token_version"] == 8  # 7 → set_user_password bump → 8
    assert verify_password(NEW_PASSWORD, row["password_hash"])
    assert not verify_password(PASSWORD, row["password_hash"])
    assert "created        : false" in result.stdout
    _assert_no_secret_in_output(result)

    events = {e["event_type"]: e for e in _audit_events(data_dir)}
    assert {"auth.password_reset", "user.enabled", "user.sysadmin_changed"} <= set(
        events
    )
    for event_type in (
        "auth.password_reset",
        "user.enabled",
        "user.sysadmin_changed",
    ):
        payload = json.loads(events[event_type]["payload_json"])
        assert set(payload) == {"user_id", "username", "actor"}
        assert payload["actor"] == "break-glass"
        assert NEW_PASSWORD not in events[event_type]["payload_json"]
        assert "scrypt$" not in events[event_type]["payload_json"]


# ============ 4. --generate 只打印一次 ============


def test_generate_prints_password_once_and_is_verifiable(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = _run(
        data_dir, "--username", "carol", "--create", "--generate"
    )
    assert result.returncode == 0, result.stderr

    password = _generate_password(result.stdout)
    assert len(password) == 24
    assert result.stdout.count(password) == 1, "生成的口令只能出现一次"
    assert "scrypt$" not in result.stdout

    row = _user(data_dir, "carol")
    assert row is not None
    assert verify_password(password, row["password_hash"])


# ============ 5. 弱口令（建号 / 重置两路） ============


def test_weak_password_create_rejected_without_user(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = _run(
        data_dir,
        "--username",
        "weakuser",
        "--create",
        "--password-stdin",
        stdin=SHORT_PASSWORD + "\n",
    )
    assert result.returncode == 2
    assert "密码" in result.stderr
    assert _user(data_dir, "weakuser") is None


def test_weak_password_reset_keeps_old_password(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    created = _run(
        data_dir,
        "--username",
        "dave",
        "--create",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert created.returncode == 0, created.stderr
    before = _user(data_dir, "dave")
    assert before is not None

    result = _run(
        data_dir,
        "--username",
        "dave",
        "--password-stdin",
        stdin=SHORT_PASSWORD + "\n",
    )
    assert result.returncode == 2
    after = _user(data_dir, "dave")
    assert after is not None
    assert after["token_version"] == before["token_version"]
    assert after["password_hash"] == before["password_hash"]
    assert verify_password(PASSWORD, after["password_hash"])


# ============ 6. 非 TTY 且未给口令来源 ============


def test_non_tty_without_source_hints_password_stdin(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = _run(data_dir, "--username", "erin", "--create")
    assert result.returncode == 2
    assert "--password-stdin" in result.stderr
    assert _user(data_dir, "erin") is None


# ============ 7. --data-dir 覆盖 LATTICE_DATA_DIR ============


def test_create_into_missing_nested_data_dir(tmp_path: Path) -> None:
    """目录不存在（多层）时 `--create` 自动建目录（与 create_app 同款）。"""
    data_dir = tmp_path / "nested" / "does-not-exist" / "data"
    assert not data_dir.exists()
    result = _run(
        data_dir,
        "--username",
        "grace",
        "--create",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert result.returncode == 0, result.stderr
    assert (data_dir / "lattice.db").exists()
    row = _user(data_dir, "grace")
    assert row is not None and row["status"] == "active"


def test_data_dir_flag_overrides_env(tmp_path: Path) -> None:
    env_dir = tmp_path / "env-data"
    flag_dir = tmp_path / "flag-data"
    result = _run(
        flag_dir,
        "--username",
        "frank",
        "--create",
        "--generate",
        "--data-dir",
        str(flag_dir),
        env_data_dir=env_dir,
    )
    assert result.returncode == 0, result.stderr
    assert (flag_dir / "lattice.db").exists()
    assert not (env_dir / "lattice.db").exists()
    assert _user(flag_dir, "frank") is not None
