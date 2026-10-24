"""实验 3 客户端驱动（在 uv 独立钉版 env 运行：langchain-mcp-adapters 0.3.1 + mcp==1.30.0）。

由 bench3_mcp_client.py spawn；勿直接在项目 env 运行（真实入口
`langchain_mcp_adapters.client` import 即 ImportError——其依赖 mcp 1.x 的
RequestContext，与 fastmcp-slim 4.1.3 范围钉的 mcp 2.x（lock 解析值 2.3.0）
互斥，见编排文件头注与报告 §4.1）。

三种客户端形态实测（形态定义与代码示意见报告 §实验3）：
- 形态 A（每用户会话一个 client）：client.session() 建立并持有会话（headers 构造时
  注入该用户 token）——热调用复用连接；
- 形态 A'（langchain tool 默认路径）：adapters 0.3.1 的 get_tools() 返回的 tool
  每次 ainvoke **新建一次会话**（handshake + list_tools + call）——不持连接的默认形态；
- 形态 B（共享中继/每请求注入头）：每次调用新建 session、headers 按调用方 token
  现场构造——无用户态连接留存，token 每请求可换。

计时口径（P3-8）：每相位 n=15、无显式预热（首几次调用即数据点——会话建立/调用
本身轻量，冷热差异在 events 中可见）；P50=中位、P95=nearest-rank ceil 口径
（_p95——与 bench_common.sample_timings 一致）。

输出：stdout 每行一个 JSON 事件（编排器回收）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import resource
import sys
import time

import jwt as pyjwt


def emit(phase: str, metric: str, **kw) -> None:
    print(json.dumps({"phase": phase, "metric": metric, **kw}, ensure_ascii=False), flush=True)


def make_client(token: str, url: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    return MultiServerMCPClient(
        {
            "lattice": {
                "transport": "streamable_http",
                "url": url,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )


def mint(url_secret: str, user: str, org: str, ttl_s: float) -> str:
    now = time.time()
    return pyjwt.encode(
        {"sub": user, "iat": now, "exp": now + ttl_s, "org": org},
        url_secret,
        algorithm="HS256",
    )


def _p95(xs: list[float]) -> float:
    """nearest-rank P95：ceil(0.95·n)-1 下标（与 bench_common.sample_timings 同口径——P3-8）。"""
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]


def fd_count() -> int:
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:  # pragma: no cover - 非 macOS/Linux
        return -1


def rss_kb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


async def main_async(cfg: dict) -> None:
    from importlib.metadata import version

    url: str = cfg["url"]
    query: str = cfg["query"]
    org: str = cfg["org"]
    tokens: dict = cfg["users"]
    probe_user: str = cfg["probe_user"]
    hold_users: list = cfg["hold_users"]
    secret: str = cfg["dev_jwt_secret"]

    emit(
        "env", "client_versions",
        detail=f"mcp {version('mcp')} / langchain-mcp-adapters {version('langchain-mcp-adapters')}"
        + f" / langchain-core {version('langchain-core')}",
    )

    # ---- 协议兼容性探针：mcp 1.x client ⇄ fastmcp4(mcp 2.x) server 初始化 ----
    client0 = make_client(tokens[probe_user], url)
    t0 = time.perf_counter()
    async with client0.session("lattice", auto_initialize=False) as s:
        init = await s.initialize()
        establish_ms = (time.perf_counter() - t0) * 1000
        emit(
            "compat", "initialize",
            value=f"protocol={init.protocolVersion} server={init.serverInfo.name}"
            f" v{init.serverInfo.version}",
            detail=f"会话建立(含 initialize) {establish_ms:.1f} ms",
        )
        t0 = time.perf_counter()
        tools = await s.list_tools()
        emit("compat", "list_tools", value=[t.name for t in tools.tools],
             detail=f"{(time.perf_counter()-t0)*1000:.1f} ms")

    # ---- 形态 A：会话建立成本（每用户会话一个 client 的单位成本） ----
    xs = []
    for _ in range(15):
        c = make_client(tokens[probe_user], url)
        t0 = time.perf_counter()
        async with c.session("lattice") as s:
            xs.append((time.perf_counter() - t0) * 1000)
    xs.sort()
    emit("形态A", "会话建立(enter+initialize) p50", value_ms=xs[len(xs) // 2])
    emit("形态A", "会话建立(enter+initialize) p95", value_ms=_p95(xs))

    # ---- 形态 A：持有会话热调用（连接复用；n=40——热调用便宜，提样本使 P95
    # 脱离"=max"区，P3-7 口径） ----
    c = make_client(tokens[probe_user], url)
    async with c.session("lattice") as s:
        xs = []
        for i in range(40):
            t0 = time.perf_counter()
            res = await asyncio.wait_for(
                s.call_tool("search", {"query": query, "top_k": 5}), timeout=15
            )
            xs.append((time.perf_counter() - t0) * 1000)
            if i == 0:
                n_hits = sum(
                    1 for item in (res.content or []) if getattr(item, "type", "") == "text"
                )
                emit("形态A", "首调内容校验", value=f"text块 {n_hits}，isError={res.isError}")
        xs.sort()
        emit("形态A", "持有会话热调用 p50", value_ms=xs[len(xs) // 2])
        emit("形态A", "持有会话热调用 p95", value_ms=_p95(xs))

    # ---- 形态 A'：langchain tool 默认路径（每次 ainvoke 新建会话） ----
    c2 = make_client(tokens[probe_user], url)
    tools = await c2.get_tools()
    tool = next(t for t in tools if t.name == "search")
    xs = []
    for _ in range(15):
        t0 = time.perf_counter()
        out = await asyncio.wait_for(tool.ainvoke({"query": query, "top_k": 5}), timeout=15)
        xs.append((time.perf_counter() - t0) * 1000)
    xs.sort()
    emit("形态A'", "tool.ainvoke(每调用新建会话) p50", value_ms=xs[len(xs) // 2])
    emit("形态A'", "tool.ainvoke(每调用新建会话) p95", value_ms=_p95(xs))
    emit("形态A'", "返回形态", value=f"langchain tool 输出类型 {type(out).__name__}")

    # ---- 形态 B：每请求注入头（共享中继——每次调用按调用方 token 新建会话） ----
    xs = []
    for i in range(15):
        tok = tokens[hold_users[i % len(hold_users)]]
        cb = make_client(tok, url)
        t0 = time.perf_counter()
        async with cb.session("lattice") as s:
            await asyncio.wait_for(
                s.call_tool("search", {"query": query, "top_k": 5}), timeout=15
            )
        xs.append((time.perf_counter() - t0) * 1000)
    xs.sort()
    emit("形态B", "每请求建会话+调用 p50", value_ms=xs[len(xs) // 2])
    emit("形态B", "每请求建会话+调用 p95", value_ms=_p95(xs))

    # ---- 形态 A 规模化：10 用户会话并持（连接/FD/内存足迹） ----
    from contextlib import AsyncExitStack

    fds0, rss0 = fd_count(), rss_kb()
    stack = AsyncExitStack()
    t0 = time.perf_counter()
    sessions = []
    for u in hold_users:
        cu = make_client(tokens[u], url)
        sessions.append(await stack.enter_async_context(cu.session("lattice")))
    hold_ms = (time.perf_counter() - t0) * 1000
    ok = 0
    for s in sessions:
        res = await asyncio.wait_for(s.call_tool("search", {"query": query, "top_k": 3}), timeout=15)
        ok += 0 if res.isError else 1
    fds1, rss1 = fd_count(), rss_kb()
    emit("形态A", "10 用户会话并持建立", value_ms=hold_ms)
    emit("形态A", "10 会话 FD 增量", value=f"{fds1 - fds0}（{fds0}→{fds1}）")
    emit(
        "形态A", "10 会话峰值内存增量",
        value=f"{rss1 - rss0}（ru_maxrss——macOS 计字节 / Linux 计 KB，≈{(rss1-rss0)/10/1024:.0f} KB/会话@macOS）",
    )
    emit("形态A", "10 会话逐个调用成功", value=f"{ok}/10")
    await stack.aclose()

    # ---- token 过期刷新行为 ----
    # 形态 A：会话头在传输层构造时固定——过期后调用失败，须重建会话
    short = mint(secret, probe_user, org, ttl_s=2.0)
    ca = make_client(short, url)
    async with ca.session("lattice") as s:
        res = await s.call_tool("search", {"query": query, "top_k": 3})
        emit("过期", "形态A 过期前调用", value=f"isError={res.isError}")
        await asyncio.sleep(3.2)
        try:
            res = await asyncio.wait_for(s.call_tool("search", {"query": query, "top_k": 3}), timeout=15)
            emit("过期", "形态A 过期后调用(同会话)", value=f"isError={res.isError}（会话存活、工具层 401）")
        except Exception as exc:  # noqa: BLE001 - 行为记录
            emit("过期", "形态A 过期后调用(同会话)", value=f"异常 {type(exc).__name__}: {str(exc)[:120]}")
    # 同 client 重建会话（新 token）→ 恢复
    ca2 = make_client(tokens[probe_user], url)
    async with ca2.session("lattice") as s:
        res = await asyncio.wait_for(s.call_tool("search", {"query": query, "top_k": 3}), timeout=15)
        emit("过期", "形态A 重建会话(新token)恢复", value=f"isError={res.isError}")

    # 形态 B：每请求注入头——过期 token 当次失败，新 token 下一请求即恢复（无会话态）
    dead = mint(secret, probe_user, org, ttl_s=0.5)
    await asyncio.sleep(1.0)
    cb_dead = make_client(dead, url)
    try:
        async with cb_dead.session("lattice") as s:
            res = await asyncio.wait_for(s.call_tool("search", {"query": query, "top_k": 3}), timeout=15)
            emit("过期", "形态B 过期token调用", value=f"isError={res.isError}（工具层 401）")
    except Exception as exc:  # noqa: BLE001 - 行为记录
        emit("过期", "形态B 过期token调用", value=f"异常 {type(exc).__name__}: {str(exc)[:120]}")
    cb_fresh = make_client(tokens[probe_user], url)
    async with cb_fresh.session("lattice") as s:
        res = await asyncio.wait_for(s.call_tool("search", {"query": query, "top_k": 3}), timeout=15)
        emit("过期", "形态B 新token下一请求恢复", value=f"isError={res.isError}")


def main() -> None:
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    asyncio.run(main_async(cfg))


if __name__ == "__main__":
    main()
