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
updatedAt: null          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-001: 任务标题

## 任务原文
（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

## 需求确认
- [ ] 用户已确认（确认后 status=implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入本任务，见 README §4.6）

## 遗留事项（跨任务移交）
- [ ] 无
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（改动…，自测：…）
- R1: tester …（用例通过情况）
- R1: committer …（意见摘要）

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）
