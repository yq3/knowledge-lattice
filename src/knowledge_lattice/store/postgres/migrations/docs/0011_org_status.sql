-- 0011 orgs.status (PG)（m3-1 issue #14——组织停用载体；与 sqlite 同号等价，
-- D24 双方言各一份）。
ALTER TABLE orgs ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
  CHECK (status IN ('active','disabled'));
