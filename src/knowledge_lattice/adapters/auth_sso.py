"""SSO 验签适配器（design §3 adapters/auth_sso.py——m2-4 A1/A2）。

**协议中立可插拔接口**（用户裁定 2026-11-01：当前外部环境开发、真实企业
IdP 信息不可得——待决-2〔企业 SSO 协议〕维持未决；适配器留口子，mock 实现
不侵入业务层，企业内基于开源版继续开发时替换真实 IdP 适配器即可）：

- `SsoTokenVerifier`：验签协议（token → `SsoClaims`；失败 raise
  `SsoVerificationError`——语义性拒绝〔aud/act 非法〕由 domain 层承载，
  适配器只管「IdP 是否签发过这个 token、claims 是什么」）；
- `MockIdpVerifier`：mock IdP（自签 JWT·HS256）——POC 交付形态（OIDC 优先
  口径下的占位实现；`issue_token` 供测试/本地构造，生产真实联调挂账
  m2-5/部署期）；
- `build_sso_verifier`：配置化注入工厂（`LATTICE_SSO_PROVIDER`：none=缺省
  dev 形态不注入 / mock-idp=mock 实现；真实协议适配器企业内在此登记）。

分层注（§3）：本模块是外置依赖适配层——不写方言 SQL、不做计权/JIT/审计
（domain/auth.py 承载）；mock 密钥经 `LATTICE_SSO_MOCK_SECRET` 配置（与
dev_jwt_secret 同款纪律——生产另配，默认值仅 dev/test）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import jwt as pyjwt

MOCK_IDP_ISSUER = "mock-idp"
MOCK_IDP_ALG = "HS256"
DEFAULT_TOKEN_TTL_S = 600.0  # SSO/委托 token 短 TTL（D18——比 dev JWT 12h 更紧）


class SsoVerificationError(Exception):
    """IdP 验签失败（签名不符/过期/非本 IdP 签发——domain 层据此落回或拒绝）。"""


@dataclass(frozen=True)
class SsoClaims:
    """验签通过后的标准化 claims（协议中立——适配器负责归一，domain 只见本形态）。

    - sub：全局用户 id（JIT 建档主键来源）；
    - aud：受众集合（字符串/数组归一——domain 校验本服务是否在受众内）；
    - org：组织 claim（单值——按组织签发，D18）；
    - act：委托 act claim **原样**（string | object——RFC 8693 §4.1 形态解析
      在 domain/auth.resolve_act_claim，适配器不预解析）；
    - username/display_name：OIDC 惯例 claim（preferred_username/name——JIT
      建档资料；缺失回退 sub/None）。
    """

    sub: str
    aud: tuple[str, ...]
    org: str | None = None
    act: object | None = None
    username: str | None = None
    display_name: str | None = None
    raw: dict = field(default_factory=dict)


@runtime_checkable
class SsoTokenVerifier(Protocol):
    """SSO/委托 token 验签协议（可插拔——真实 IdP 适配器同形替换）。"""

    name: str

    def verify(self, token: str) -> SsoClaims:
        """验签并归一 claims；失败（含过期）raise SsoVerificationError。"""
        ...


def _normalize_aud(aud: object) -> tuple[str, ...]:
    """aud claim 归一（string | list[str] → 元组；非法形态视为空——domain 拒）。"""
    if isinstance(aud, str):
        return (aud,)
    if isinstance(aud, list) and all(isinstance(a, str) for a in aud):
        return tuple(aud)
    return ()


class MockIdpVerifier:
    """mock IdP 验签器（自签 JWT·HS256）——POC 交付形态（待决-2）。

    签发端 `issue_token` 与验签端同体（测试/本地一体；真实形态签发在 IdP 侧、
    本系统只做验签方——Token Exchange 服务端代理不做，design「不做」边界）。
    """

    def __init__(self, *, secret: str, issuer: str = MOCK_IDP_ISSUER) -> None:
        self.name = "mock-idp"
        self._secret = secret
        self._issuer = issuer

    def issue_token(
        self,
        *,
        sub: str,
        aud: tuple[str, ...] | list[str] | str = ("knowledge-lattice",),
        org: str | None = None,
        act: object | None = None,
        username: str | None = None,
        display_name: str | None = None,
        ttl_s: float | None = None,
        extra: dict | None = None,
    ) -> str:
        """签发（测试/本地构造用）：sub/aud/org/act + OIDC 惯例资料 claim。"""
        now = time.time()
        payload: dict[str, object] = {
            "iss": self._issuer,
            "sub": sub,
            "aud": list(aud) if not isinstance(aud, str) else aud,
            "iat": now,
            "exp": now + (DEFAULT_TOKEN_TTL_S if ttl_s is None else ttl_s),
        }
        if org is not None:
            payload["org"] = org
        if act is not None:
            payload["act"] = act
        if username is not None:
            payload["preferred_username"] = username
        if display_name is not None:
            payload["name"] = display_name
        if extra:
            payload.update(extra)
        return pyjwt.encode(payload, self._secret, algorithm=MOCK_IDP_ALG)

    def verify(self, token: str) -> SsoClaims:
        """验签（签名/过期/受众形态失败 → SsoVerificationError）。"""
        try:
            claims = pyjwt.decode(
                token, self._secret, algorithms=[MOCK_IDP_ALG],
                options={"verify_aud": False},  # aud 校验语义（本服务受众）归 domain
            )
        except pyjwt.PyJWTError as exc:
            raise SsoVerificationError(str(exc)) from exc
        return SsoClaims(
            sub=claims.get("sub") or "",
            aud=_normalize_aud(claims.get("aud")),
            org=claims.get("org"),
            act=claims.get("act"),
            username=claims.get("preferred_username"),
            display_name=claims.get("name"),
            raw=claims,
        )


def build_sso_verifier(settings) -> SsoTokenVerifier | None:
    """配置化注入工厂（auth 装配分层——A5：缺省 dev 形态返回 None，现有
    门禁/测试零感知）。畸形 provider 名 fail-closed raise。"""
    provider = settings.sso_provider
    if provider == "none":
        return None
    if provider == "mock-idp":
        return MockIdpVerifier(secret=settings.sso_mock_secret)
    raise ValueError(
        f"unknown sso_provider {provider!r}（合法值：none | mock-idp——真实 IdP"
        " 适配器企业在 build_sso_verifier 登记，待决-2）"
    )
