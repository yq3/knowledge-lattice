"""Agent 长寿命凭据域（D26 / issue #34 阶段 2A——`local` 形态 agent key 认证核心）。

设计口径（issue #34 决策提案 D26；库底座＝迁移 0013 + ``AgentKeyBackend``〔阶段 1〕）：

- **形态**：``lka_`` + ``secrets.token_urlsafe(32)``（32 字节随机源）；库内只存
  sha256 摘要 ``token_hash`` 与展示前缀 ``prefix``（明文仅在创建响应返回一次）；
- **归属**：key 绑定 ``(org_id, user_id)``——认证产出的 ``AuthContext.org_claim``
  即 key 绑定组织（org 路径端点由 api 层 ``org_scoped`` 做绑定守卫）；
  ``AuthContext.act`` 取 key ``label``（agent 标识——查询审计可区分不同 agent）；
  ``via="agent_key"``；
- **local-only**：仅 ``settings.auth_mode=="local"`` 可用（sso 形态长期凭据仍走
  D18 委托 token——本项不改变 sso 行为）；失败一律 401，且 **不 fallback** 到
  dev JWT/静态 token（``authenticate`` 顶部按前缀分流，D26）；
- **生命周期**：永不过期（``expires_at`` 恒 NULL、字段预留）；``revoked_at`` 非空
  ＝软撤销即时生效；判定都在本模块（store 读口不隐藏撤销行）；
- **last_used_at 节流**：≥60s 窗口才回写（domain 先判行内 ``last_used_at``，
  窗口内**不触库**；窗口外调 ``touch_agent_key_last_used``，其 WHERE 为并发
  兜底）；回写失败只记 warning，**绝不阻断认证**（认证可用性优先——NFR-8）。

失败消息与既有 ``AuthError`` 同语义（401）：未知 key 统一 ``invalid agent key``
不泄露是否存在；``revoked`` / ``expired`` / 用户停用等细分消息供运行侧排障。
key 明文、摘要均不进日志/错误消息。

分层：本模块只依赖 domain/config/store 协议（§3——不写方言 SQL）；与
``domain/auth.py`` 的循环导入经 ``authenticate`` 内局部 import 化解。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time

from knowledge_lattice.config import Settings
from knowledge_lattice.domain.auth import AuthContext, AuthError
from knowledge_lattice.store.taskclock import TS_FMT, utc_now_ts

logger = logging.getLogger(__name__)

# key 明文前缀（`authenticate` 以此识别 agent key 专道——不 fallback 开发形态）
AGENT_KEY_PREFIX = "lka_"
# 展示前缀长度（明文前 12 字符——`lka_` + 8 字符；列表页/审计展示用）
AGENT_KEY_PREFIX_LEN = 12
# last_used_at 回写窗口（秒——窗口内认证不重复写，降低热路径写放大）
LAST_USED_THROTTLE_S = 60.0


def hash_agent_key(token: str) -> str:
    """agent key 明文 → sha256 hex（库内 ``token_hash`` 存储与查询形态）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_agent_key() -> tuple[str, str, str]:
    """生成新 agent key → ``(plaintext, prefix, token_hash)``。

    - plaintext = ``lka_`` + ``secrets.token_urlsafe(32)``（32 字节随机源）；
    - prefix = plaintext 前 12 字符（展示用，不含完整凭据）；
    - token_hash = sha256 hex（入库形态；明文永不落库）。

    明文只应由调用方在创建响应返回一次（库/日志/审计均不得出现）。
    """
    plaintext = AGENT_KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, plaintext[:AGENT_KEY_PREFIX_LEN], hash_agent_key(plaintext)


def _touch_last_used(backend, row: dict) -> None:
    """节流回写 ``last_used_at``（≥60s 窗口）；失败只告警、绝不阻断认证。

    now/cutoff 用**一次** ``time.time()`` 派生（同一时钟快照——避免两次取样
    跨秒导致窗口边界抖动），库格式字符串（``taskclock.TS_FMT`` 单一常量源）。

    **domain 侧先判窗口**（认证行刚读到，``last_used_at >= cutoff`` 即窗口内）：
    窗口内直接返回、不触库——store 的 ``WHERE ... < cutoff`` 只保证「值不变」，
    UPDATE/commit 仍会每请求执行（SQLite 单写者；MCP 检索热路径每 query 一次
    写），与「≥60s 才写」的节流目标不符。窗口外才调 store（store 侧 WHERE 仍
    保留为并发/直调场景的幂等兜底）。
    """
    epoch = time.time()
    now = time.strftime(TS_FMT, time.gmtime(epoch))
    cutoff = time.strftime(TS_FMT, time.gmtime(epoch - LAST_USED_THROTTLE_S))
    last_used = row.get("last_used_at")
    if last_used is not None and last_used >= cutoff:
        return  # 窗口内：不触库（避免热路径写放大）
    try:
        backend.touch_agent_key_last_used(row["id"], now=now, cutoff=cutoff)
    except Exception:  # noqa: BLE001 —— 回写是旁路观测面，失败不得阻断认证
        logger.warning(
            "agent key last_used_at 回写失败（认证不阻断）：key_id=%s",
            row["id"], exc_info=True,
        )


def authenticate_agent_key(backend, settings: Settings, token: str) -> AuthContext:
    """agent key 明文 → ``AuthContext``（via='agent_key'）；失败一律 401。

    判定序（fail-closed）：
    ① 非 local 形态 → 401（agent key 仅 local 可用——sso 走 D18 委托 token）；
    ② ``hash_agent_key`` 后 ``get_agent_key_by_hash`` 精确取行——无行统一
       ``invalid agent key``（不泄露是否存在）；
    ③ ``revoked_at`` 非空 → 401 revoked（软撤销即时生效）；
    ④ ``expires_at`` 非空且 <= now（库格式字符串比较）→ 401 expired；
    ⑤ 用户：``get_user_auth`` 不存在 / ``disabled_at`` 非空 / ``status !=
       "active"`` → 401（key 不绕过用户状态）；
    ⑥ 成功：``user_id``/``org_claim=key.org_id``/``act=key.label``/系统管理员
       标记取用户行；``last_used_at`` 节流回写（失败不阻断）。

    成员关系/组织停用/ACL 每请求照常校验（由 api/mcp 层承载——key 不绕过 ACL）。
    """
    if settings.auth_mode != "local":
        raise AuthError("agent key 仅 local 形态可用（LATTICE_AUTH_MODE=local）")
    row = backend.get_agent_key_by_hash(hash_agent_key(token))
    if row is None:
        # 未知/格式不符统一文案——不泄露 key 是否存在（枚举防护）
        raise AuthError("invalid agent key")
    if row["revoked_at"] is not None:
        raise AuthError("agent key revoked")
    expires_at = row["expires_at"]
    if expires_at is not None and expires_at <= utc_now_ts():
        raise AuthError("agent key expired")
    user = backend.get_user_auth(row["user_id"])
    if user is None:
        raise AuthError(f"unknown user: {row['user_id']}")
    if user["disabled_at"] is not None:
        raise AuthError(f"user disabled: {row['user_id']}")
    if user["status"] != "active":
        raise AuthError(f"user not active: {row['user_id']}")
    context = AuthContext(
        user_id=row["user_id"],
        org_claim=row["org_id"],
        via="agent_key",
        is_system_admin=bool(user["is_system_admin"]),
        act=row["label"],
    )
    _touch_last_used(backend, row)
    return context
