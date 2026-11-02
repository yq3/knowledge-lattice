-- 0008 semantic build 快照附表（sqlite）：G-21 方案 A（m2s-5）。
-- · sem_build_snapshots(build_id PK → sem_builds ON DELETE CASCADE, snapshot_json)
--   ——快照 = 构建时点 sem_active_snapshot 的最小 JSON（实体〔含 curated_json〕+
--   别名 + 关系〔消歧共现/L0 佐证必需面〕），与 ready 切换同一事务写入
--   （sem_switch_build_ready / sem_reactivate_build 的 snapshot_json 参数）；
-- · get_annotator / render_l0 按 current build id 取快照构建实例——冷缓存/
--   重启后服务 build 产物而非 live（G-21 反转）；无快照回退 live + 告警
--   （0008 之前存量 ready 行的兼容路径）；
-- · org_id 冗余列：对账/运维按 org 定位快照（sem_builds 本身可 join，
--   冗余换取不依赖 join 的清理/巡检路径）。

CREATE TABLE sem_build_snapshots (
  build_id      INTEGER PRIMARY KEY REFERENCES sem_builds(id) ON DELETE CASCADE,
  org_id        TEXT    NOT NULL,
  snapshot_json TEXT    NOT NULL CHECK (json_valid(snapshot_json)),
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_sem_bsnap_org ON sem_build_snapshots(org_id);
