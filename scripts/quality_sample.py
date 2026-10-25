#!/usr/bin/env python
"""区分度误报抽查（M1.7 验收句的记录形态——机制面；阈值校准实验属 M1-5）。

用法：
  uv run python scripts/quality_sample.py --n 20 --seed m1
  LATTICE_PG_DSN=... uv run python scripts/quality_sample.py --backend pg

输出 open flags 确定性抽样清单（JSON——供人工复核）；复核结论经
PATCH /api/quality-flags/{id} 落 state（resolved=误报处置 / ignored=接受通用）
与 manual_tags 审计轨迹——记录即 quality_flags 行 + audit_outbox 事件。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="sqlite 库路径（缺省 data/lattice.db）")
    parser.add_argument("--org", default="org:tax")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", default="m1")
    args = parser.parse_args()

    from knowledge_lattice.config import Settings
    from knowledge_lattice.core.docs.quality import QualityService
    from knowledge_lattice.store.sqlite import connect
    from knowledge_lattice.store.sqlite.backend import SqliteBackend

    db_path = Path(args.db) if args.db else ROOT / "data" / "lattice.db"
    if not db_path.exists():
        print(f"库不存在：{db_path}", file=sys.stderr)
        return 1
    conn = connect(db_path)
    try:
        service = QualityService(SqliteBackend(conn), Settings())
        sample = service.sample_open_flags(args.org, n=args.n, seed=args.seed)
        print(json.dumps({"org": args.org, "seed": args.seed, "flags": sample},
                         ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
