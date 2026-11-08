-- 0011 orgs.status（m3-1 issue #14——组织停用载体，design P1-1「组织不可删
-- 只能停用」的实现载体）：active/disabled，默认 active（既有行回填 active）。
-- 停用语义（fail-closed）由 API 层承载：停用组织所有 /api/orgs/{org}/... 端点
-- 403、MCP 会话 403、webhook 拒绝；进行中任务让跑完、新任务投递拒绝；
-- 恢复 = PATCH status=active（幂等）；审计 org.disabled/org.enabled 同事务。
ALTER TABLE orgs ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
  CHECK (status IN ('active','disabled'));
