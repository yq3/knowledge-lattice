#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP 接入冒烟（D26——用 agent key 验证 /mcp 连通与工具面）。

用途：agent 侧接入前的一键自检——连 Streamable HTTP 端点、列工具、调一次
``search``。只读，不打印/不落盘明文 key（从 ``LATTICE_MCP_KEY`` 或 ``--key``
读；推荐环境变量，避免 shell history）。

用法::

    export LATTICE_MCP_KEY="lka_xxxxxxxx..."
    uv run python scripts/mcp_smoke.py \
        --url http://127.0.0.1:8000/mcp --query "增值税留抵退税"

退出码：0 成功；2 参数缺失；1 连接/认证/工具调用失败。

接入细节（端点/客户端配置/组织规则/排错）见 ``docs/MCP-INTEGRATION.md``。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

DEFAULT_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_QUERY = "增值税留抵退税"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="用 agent key 冒烟 /mcp：列工具 + search（不打印 key）"
    )
    p.add_argument("--url", default=DEFAULT_URL,
                   help=f"MCP Streamable HTTP 端点（默认 {DEFAULT_URL}）")
    p.add_argument("--key", default=os.environ.get("LATTICE_MCP_KEY", ""),
                   help="agent key（lka_...）；缺省读 LATTICE_MCP_KEY（推荐）")
    p.add_argument("--query", default=DEFAULT_QUERY, help="search 查询词")
    p.add_argument("--top-k", type=int, default=3, help="search top_k（默认 3）")
    return p


async def _run(url: str, key: str, query: str, top_k: int) -> int:
    transport = StreamableHttpTransport(
        url=url,
        headers={"Authorization": f"Bearer {key}"},
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        print("tools:", ", ".join(t.name for t in tools))
        if "search" not in {t.name for t in tools}:
            print("ERROR: search 工具不在工具列表——端点/版本不匹配", file=sys.stderr)
            return 1
        try:
            result = await client.call_tool(
                "search", {"query": query, "top_k": top_k}
            )
        except ToolError as exc:
            # 认证/组织/权限错误以 tool error 文本返回（如 401: ...）
            print(f"tool error: {exc}", file=sys.stderr)
            return 1
        payload = json.loads(result.content[0].text)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.key:
        print(
            "ERROR: 缺少 agent key——export LATTICE_MCP_KEY=lka_... 或 --key",
            file=sys.stderr,
        )
        return 2
    try:
        return asyncio.run(_run(args.url, args.key, args.query, args.top_k))
    except Exception as exc:  # noqa: BLE001 —— 连接/传输/非 ToolError 统一报错
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
