#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""break-glass 管理员重置（M4/m4-4——D25 账号面的逃生口）。

用途：local 形态下**忘记管理员口令 / 无可用 sysadmin**（例如唯一 sysadmin
密码丢失、账号被停用）时，从宿主机 shell 直接重置账号。这是 shell 级运维
通道（需数据目录访问权限），不是 Web/REST 能力——不替代正常的管理面重置。

用法（`uv run python scripts/reset_admin.py --help` 同源）::

    # 推荐：口令从标准输入读一行（不落 shell history / ps）
    printf '%s\\n' "$NEW_PASSWORD" | uv run python scripts/reset_admin.py \\
        --username alice --password-stdin

    # 自动化/无口令来源：生成 24 字符随机口令并只打印一次
    uv run python scripts/reset_admin.py --username alice --generate --create

    # 交互式（TTY）：getpass 两次输入确认
    uv run python scripts/reset_admin.py --username alice

    # 已有用户：授予 sysadmin 并启用（清 disabled_at）
    uv run python scripts/reset_admin.py --username alice --password-stdin --promote

    # 指定数据目录（缺省 LATTICE_DATA_DIR，再缺省 data/）
    uv run python scripts/reset_admin.py --username alice --generate \\
        --data-dir /srv/lattice/data

行为口径（`_m4-impl-contract.md` §7 / `_m4-plan.md` m4-4）：

- **纯 store 层**：`Settings` + `store.factory.build_backend`（与 app 同源——
  当前为 sqlite；工厂检测到 `LATTICE_PG_DSN` 时只告警并仍用 sqlite，见
  `store/factory.py`），只调用 ``AccountsBackend`` 的
  ``create_user``/``get_user_by_username``/``set_user_password``/
  ``update_user_flags``，**不写裸 SQL**；
- **默认不建号**：username 不存在 → 退出码 2，提示加 ``--create``；
- **默认不动 sysadmin 状态**：``--promote`` 才授予 sysadmin 并启用
  （``disabled_at`` 清空；``token_version`` 不回退——旧会话不复活）；
- **重置必设口令**（没有 ``--no-password``）：已有用户
  ``set_user_password(bump_token_version=True)``（``tv++`` 撤销全部旧会话）；
- 口令强度用 ``domain.accounts.validate_password``（``LATTICE_PASSWORD_MIN_LEN``，
  缺省 10，最小 8）；
- 审计走 store 的 ``audit=`` 同事务通道：已有用户 ``auth.password_reset``
  （+ ``--promote`` 时 store 按实际变化写 ``user.enabled``/
  ``user.sysadmin_changed``），新用户 ``user.created``——payload 只含
  user_id/username/actor，**密码明文/ hash 永不进审计、stdout、错误消息**；
- 退出码：成功 0；用户不存在未 ``--create`` / 口令不合规 / 参数互斥等
  用法错误 2；配置或数据库错误 1。

限制：当前 ``store.factory.build_backend`` 恒 sqlite（D24 双后端的 app/worker
统一装配；PG 后端接线属部署期）——即已切 PG 的部署本 CLI 暂不适用，需待
factory 接线后在 PG 上执行等价操作。
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from knowledge_lattice.config import get_settings  # noqa: E402
from knowledge_lattice.domain.accounts import (  # noqa: E402
    WeakPasswordError,
    hash_password,
    validate_password,
    validate_username,
)
from knowledge_lattice.domain.audit_events import (  # noqa: E402
    EVENT_AUTH_PASSWORD_RESET,
    EVENT_USER_CREATED,
    EVENT_USER_ENABLED,
    EVENT_USER_SYSADMIN_CHANGED,
)
from knowledge_lattice.store.factory import build_backend  # noqa: E402

ACTOR = "break-glass"
GENERATED_PASSWORD_LEN = 24  # secrets.token_urlsafe(18) 的字符数
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_RUNTIME = 1


class _UsageError(Exception):
    """参数/前置条件错误（退出码 2——不触碰数据库写路径）。"""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reset_admin.py",
        description=(
            "break-glass：重置 local 账号口令（可选建号/授 sysadmin）。"
            "密码明文绝不落审计或 hash 输出；推荐 --password-stdin。"
        ),
        epilog=(
            "退出码：0 成功 | 2 用户不存在（未 --create）/ 密码不合规 / 参数错误"
            " | 1 配置或数据库错误"
        ),
    )
    parser.add_argument("--username", required=True, help="登录名（精确匹配，不转小写）")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="数据目录（缺省 LATTICE_DATA_DIR，再缺省 data/）",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--password-stdin",
        action="store_true",
        help="从标准输入读一行作为新密码（推荐——不落 shell history）",
    )
    source.add_argument(
        "--generate",
        action="store_true",
        help="生成 24 字符随机密码并只打印一次（脚本/自动化用）",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="用户不存在时创建（active + sysadmin）；缺省则报错退出 2",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="授予 sysadmin 并启用（清 disabled_at）；缺省不动 sysadmin/停用状态",
    )
    return parser.parse_args(argv)


def _read_password(args: argparse.Namespace) -> tuple[str, bool]:
    """读取新密码 → ``(password, generated)``；错误抛 :class:`_UsageError`。"""
    if args.generate:
        return secrets.token_urlsafe(18), True
    if args.password_stdin:
        line = sys.stdin.readline()
        if not line:
            raise _UsageError("--password-stdin 未读到密码（标准输入为空/已关闭）")
        return line.rstrip("\r\n"), False
    if not sys.stdin.isatty():
        raise _UsageError(
            "非交互环境不能使用 getpass——请改用 --password-stdin"
            "（推荐）或 --generate"
        )
    first = getpass.getpass("新密码: ")
    second = getpass.getpass("再次输入新密码: ")
    if first != second:
        raise _UsageError("两次输入的密码不一致")
    return first, False


def _audit(event_type: str, *, user_id: str, username: str) -> tuple[str, str]:
    """审计载体（同事务写入 outbox）——payload 只含 id/username/actor。"""
    return event_type, json.dumps(
        {"user_id": user_id, "username": username, "actor": ACTOR},
        ensure_ascii=False,
    )


def _validate_password_or_usage(password: str, min_len: int) -> None:
    try:
        validate_password(password, min_len)
    except WeakPasswordError as exc:
        raise _UsageError(str(exc)) from exc


def _print_summary(user: dict, *, created: bool) -> None:
    print("用户状态：")
    print(f"  user id        : {user['id']}")
    print(f"  username       : {user['username']}")
    print(f"  status         : {user['status']}")
    print(f"  is_system_admin: {bool(user['is_system_admin'])}")
    print(f"  created        : {'true' if created else 'false'}")


def _run(args: argparse.Namespace) -> int:
    try:
        username = validate_username(args.username)
    except ValueError as exc:
        raise _UsageError(f"username 非法：{exc}") from exc

    password, generated = _read_password(args)

    settings = get_settings()
    if args.data_dir:
        from dataclasses import replace

        settings = replace(settings, data_dir=Path(args.data_dir))
    if settings.auth_mode != "local":
        # 不拒绝（break-glass 应在配置异常时仍可用），只提示：sso 形态下本地
        # 账号不参与登录，改密/建号不会产生可登录路径。
        print(
            "警告：当前 LATTICE_AUTH_MODE 不是 local——本地账号在 sso 形态下"
            "不参与登录（本操作仅改库）。",
            file=sys.stderr,
        )
    _validate_password_or_usage(password, settings.password_min_len)

    try:
        # 与 app.create_app 同款：数据目录不存在时先建（break-glass 常发生在
        # 首次部署/临时目录场景；sqlite connect 不会建父目录）。
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        backend = build_backend(settings)
        user = backend.get_user_by_username(username)
        if user is None:
            if not args.create:
                raise _UsageError(
                    f"用户不存在：{username!r}——如需创建请加 --create"
                    "（新用户为 active + sysadmin，并设置本次密码）"
                )
            user_id = f"u_{secrets.token_hex(12)}"
            created = True
            user = backend.create_user(
                user_id=user_id,
                username=username,
                display_name=None,
                email=None,
                password_hash=hash_password(password),
                status="active",
                is_system_admin=True,
                created_by=ACTOR,
                audit=_audit(
                    EVENT_USER_CREATED, user_id=user_id, username=username
                ),
            )
        else:
            created = False
            user = backend.set_user_password(
                user_id=user["id"],
                password_hash=hash_password(password),
                bump_token_version=True,
                audit=_audit(
                    EVENT_AUTH_PASSWORD_RESET,
                    user_id=user["id"],
                    username=user["username"],
                ),
            )

        if args.promote and not created:
            # 幂等：已是 active sysadmin 时 store 零写入零审计。
            # disabled=False + is_system_admin=True 只会「启用/授权」，不会触发
            # 末位 sysadmin 守卫（该守卫只拦撤权/停用）。两个候选事件由 store
            # 按**实际变化**择一/多写入（无变化则一个都不写）。
            user = backend.update_user_flags(
                user_id=user["id"],
                disabled=False,
                is_system_admin=True,
                actor=ACTOR,
                audits=[
                    _audit(
                        EVENT_USER_ENABLED,
                        user_id=user["id"],
                        username=user["username"],
                    ),
                    _audit(
                        EVENT_USER_SYSADMIN_CHANGED,
                        user_id=user["id"],
                        username=user["username"],
                    ),
                ],
            )
    except _UsageError:
        raise
    except KeyError as exc:
        # store 写路径在并发删除时抛 KeyError——按不存在处理（退出码 2）
        raise _UsageError(f"用户不存在（并发删除？）：{username!r}") from exc
    except Exception as exc:  # noqa: BLE001 - 顶层 CLI：配置/DB 错误统一 1
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_RUNTIME

    if generated:
        # 明文只出现这一次：不写日志/审计，提示立即保存。
        print("生成的密码（只显示一次，请立即保存；丢失需重新重置）：")
        print(password)
    _print_summary(user, created=created)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return _run(args)
    except _UsageError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - 顶层 CLI：配置/DB 错误统一 1
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
