---
taskId: task-001
target: <目标项目目录>
supervisorSessionId: null
coderTaskId: null
testerTaskId: null
committerTaskId: null
status: spec_confirm
round: 1
maxRounds: 3
testVerdict: null
reviewVerdict: null
testedSha: null
reviewedSha: null
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: []
endReason: null
createdAt: null          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: null
---

# task-001: 任务标题

## 任务原文
（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

## 需求确认
- [ ] 用户已确认（确认后 status=implementing）

## 轮次记录
- R1: coder 完成（改动…，自测：…）
- R1: tester …（用例通过情况）
- R1: committer …（意见摘要）

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）
