"""实验 3（TC-AUTH-04 附注 / design §5.5 M0b 实测项 / §8 M0b.3）：langchain-mcp-adapters
按用户切换委托 token 的客户端形态实测——真实 FastMCP server（M0a-3 search 工具
+ 开发 JWT）经真实 HTTP（uvicorn 线程）驱动。

版本耦合发现（2026-10-24 实测，报告 §实验3）：
- 本项目 env 内 langchain-mcp-adapters（PyPI 全部版本 ≤0.3.2）import 即失败——
  其依赖 mcp 1.x 的 `mcp.shared.context.RequestContext`，而 fastmcp 4.1.3 精确
  钉死 mcp==2.3.0（fastmcp-slim==4.1.3），同进程共存不可能；
- 故客户端跑在 uv 独立钉版 env（`--with langchain-mcp-adapters==0.3.1 --with 'mcp<2'`
  ——解析得 mcp 1.30.0），服务端留在项目 env（fastmcp 4.1.3 / mcp 2.3.0）——
  顺带实证 mcp 1.x 客户端 ⇄ mcp 2.x/FastMCP4 服务端的线级协议兼容性；
- 该依赖因此不进 pyproject（§7 最小引入——引入即坏的组合不留仓）。

编排（本文件，项目 env）：
1. data/bench/mcp3 临时数据目录 → create_app（test 环境、fake embedder、无探针）；
2. 生产摄取路径种 3 文档（可被 BM25 命中）+ u_probe/u0..u9 十一用户（同授权）；
3. uvicorn 线程起真实 HTTP（127.0.0.1 随机端口，MCP 挂 /mcp）；
4. 签发开发 JWT（长 TTL 常规组；短 TTL 由 driver 侧现场铸造——dev secret 为
   仓库公开常量、仅 test 环境，config.json 传入）；
5. spawn driver 子进程（bench3_client_driver.py，独立 env）跑实验矩阵，
   stdout JSON lines 回收 → 表格 + data/bench-results/bench3.json。

复跑：LATTICE_PG_DSN 不需要（实验 3 纯 sqlite）；uv run python benchmarks/bench3_mcp_client.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn

from bench_common import BENCH_ORG, BENCH_DATASET, RESULTS_DIR, save_result

QUERY = "增值税 申报"


class _FakeEmbedder:
    """实验 3 不走嵌入路（BM25 单路）——占位 fake（create_app 注入）。"""

    def embed(self, texts):  # pragma: no cover - 不会被调用
        return [[0.0] for _ in texts]

    @property
    def model_label(self) -> str:  # pragma: no cover - 不会被调用
        return "fake:1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _seed(db_path: Path, settings) -> None:
    """生产摄取路径造数：org/双维度/11 用户/3 文档×3 块（可 BM25 命中）。"""
    from knowledge_lattice.store.sqlite import connect
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    conn = connect(db_path)
    backend = SqliteBackend(conn)
    e = backend._conn.execute  # noqa: SLF001 - bench 造数（同形 SQL 已在 backend 内公开）
    e("INSERT INTO orgs(id, name) VALUES(?, ?)", (BENCH_ORG, "mcp bench"))
    e("INSERT INTO datasets(id, org_id, name) VALUES(?, ?, ?)", (BENCH_DATASET, BENCH_ORG, "mcp 库"))
    for key, values in (("region", ("CN", "OS")), ("tax_type", ("VAT", "CIT"))):
        dim_id = f"dim:{BENCH_ORG}:{key}"
        e("INSERT INTO dimensions(id, org_id, key, name) VALUES(?, ?, ?, ?)", (dim_id, BENCH_ORG, key, key))
        for v in values:
            e(
                "INSERT INTO dimension_values(id, dimension_id, value, label) VALUES(?, ?, ?, ?)",
                (f"val:{dim_id}:{v}", dim_id, v, v),
            )
    users = ["u_probe"] + [f"u{i:02d}" for i in range(10)]
    for uid in users:
        e("INSERT INTO users(id, username) VALUES(?, ?)", (uid, uid))
        e("INSERT INTO user_org_memberships(user_id, org_id, role) VALUES(?, ?, 'member')", (uid, BENCH_ORG))
        for key, v in (("region", "CN"), ("tax_type", "VAT")):
            e(
                "INSERT INTO user_dimension_grants(user_id, dimension_id, value_id, source)"
                " VALUES(?, ?, ?, 'local')",
                (uid, f"dim:{BENCH_ORG}:{key}", f"val:dim:{BENCH_ORG}:{key}:{v}"),
            )
    conn.commit()
    for i in range(3):
        doc_id = f"doc:mcp:{i}"
        backend.create_document(
            doc_id=doc_id, org_id=BENCH_ORG, dataset_id=BENCH_DATASET,
            title=f"MCP 实验文档 {i}", source_uri=f"user:u_probe",
            content_hash=f"sha256:mcp{i}", mime_type="text/plain", parser="docling",
            owner_user_id="u_probe", raw_object_key=f"objects/mcp{i}",
            pending_dims_json=json.dumps({"region": ["CN"], "tax_type": ["VAT"]}),
        )
        backend.insert(
            doc_id, 1,
            [
                {
                    "id": f"chk:mcp:{i}:{j}",
                    "seq": j,
                    "content": f"文档 {i} 第 {j} 段 增值税 申报 指南 留抵退税",
                    "title_seg": f"MCP 实验文档 {i}",
                    "content_seg": f"文档 {i} 第 {j} 段 增值税 申报 指南 留抵退税",
                    "token_count": 10,
                    "dims_json": json.dumps({"region": ["CN"], "tax_type": ["VAT"]}),
                }
                for j in range(1, 4)
            ],
        )
    conn.close()


def main() -> None:
    from knowledge_lattice.config import Settings
    from knowledge_lattice.domain.auth import issue_dev_jwt
    from knowledge_lattice.app import create_app

    data_dir = Path(__file__).resolve().parent.parent / "data" / "bench" / "mcp3"
    import shutil

    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    settings = Settings(environment="test", data_dir=data_dir, probe_interval_s=0, mcp_timeout_s=30)
    app = create_app(settings, embedder=_FakeEmbedder(), run_startup_probe=False)
    _seed(settings.db_path, settings)

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn 未能在 15s 内启动"
    url = f"http://127.0.0.1:{port}/mcp"

    tokens = {
        "u_probe": issue_dev_jwt(settings, user_id="u_probe", org=BENCH_ORG),
        **{
            f"u{i:02d}": issue_dev_jwt(settings, user_id=f"u{i:02d}", org=BENCH_ORG)
            for i in range(10)
        },
    }
    cfg = {
        "url": url,
        "query": QUERY,
        "org": BENCH_ORG,
        "users": tokens,
        "probe_user": "u_probe",
        "hold_users": [f"u{i:02d}" for i in range(10)],
        "dev_jwt_secret": settings.dev_jwt_secret,  # 仓库公开 dev 常量（test 环境——driver 现场铸短 TTL）
    }
    cfg_path = data_dir.parent / "mcp3_driver_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    driver = Path(__file__).resolve().parent / "bench3_client_driver.py"
    cmd = [
        "uv", "run", "--no-project", "--quiet",
        "--with", "langchain-mcp-adapters==0.3.1",
        "--with", "mcp<2",
        "--with", "pyjwt>=2.15",
        "python", str(driver), "--config", str(cfg_path),
    ]
    print(f"服务端就绪：{url}（fastmcp 服务端 env：mcp 2.3.0 / fastmcp 4.1.3）")
    print(f"driver 子进程：{' '.join(cmd[:8])} …", flush=True)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    driver_s = time.perf_counter() - t0
    print(f"driver 退出码 {proc.returncode}，总耗时 {driver_s:.1f}s")

    events: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if proc.returncode != 0 or not events:
        print("== driver stderr ==")
        print(proc.stderr[-4000:])
        sys.exit(1)

    print("\n## 实验 3（TC-AUTH-04 附注）原始指标\n")
    for ev in events:
        if "value_ms" in ev:
            print(f"- [{ev['phase']}] {ev['metric']}: {ev['value_ms']:.2f} ms{(' ' + ev.get('detail','')) if ev.get('detail') else ''}")
        else:
            print(f"- [{ev['phase']}] {ev['metric']}: {ev.get('value')}{(' — ' + ev.get('detail','')) if ev.get('detail') else ''}")

    profile = {
        "server_stack": "fastmcp 4.1.3 / mcp 2.3.0（项目 env）",
        "client_stack": "langchain-mcp-adapters 0.3.1 / mcp 1.30.0（uv 独立 env）",
        "transport": "streamable_http",
        "url": url,
        "driver_wall_s": round(driver_s, 1),
    }
    print("\n## 栈口径")
    for k, v in profile.items():
        print(f"- {k}: {v}")

    server.should_exit = True
    thread.join(timeout=10)
    save_result("bench3", {"profile": profile, "events": events})
    print(f"\n结果工件：{RESULTS_DIR / 'bench3.json'}")


if __name__ == "__main__":
    main()
