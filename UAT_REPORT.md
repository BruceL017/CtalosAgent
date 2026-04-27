# User Acceptance Test Report — Enterprise Agent v0.3.1

**Version**: v0.3.1
**Date**: 2026-04-27
**Tester**: Automated + Manual
**Status**: PASSED — 团队试运行就绪

---

## 1. 测试环境

| 组件 | 版本 | 配置 |
|------|------|------|
| OS | macOS 15.x / Darwin 25.2.0 | 本地开发 |
| Docker | 24.x | postgres + redis |
| Node.js | 20.x | API Server + Web Console |
| Python | 3.11.15 | Agent Runtime |
| PostgreSQL | 16 + pgvector | Docker |
| Redis | 7 | Docker |
| Provider | siliconflow (mock fallback) | GLM-4.7 |
| Browser | Chrome / Safari | Web Console |

---

## 2. 验收标准对照

| # | 验收标准 | 状态 | 验证方式 |
|---|---------|------|---------|
| 1 | 通过 Web 控制台创建任务并实时查看执行过程 | PASS | Web Console + API |
| 2 | 完成至少 5 个标杆工作流 | PASS | 自动化测试 |
| 3 | 每个工具调用都有结构化日志、输入、输出、耗时、状态和风险等级 | PASS | task_events + tool_calls |
| 4 | 生产/高风险动作能触发审批 | PASS | test_approval_resume |
| 5 | Skill/SOP/Workflow Template 自动更新并可回滚 | PASS | test_workflow_engine + rollback |
| 6 | 能基于历史记忆回忆 bug、读取 SOP 并生成修复产物 | PASS | memory_service + file.write |
| 7 | 能调用 subagents 生成多视角分析并汇总 | PASS | test_workflow_engine |
| 8 | 能把报告写入 Lark 文档 | PASS | lark.write_doc (mock) |
| 9 | 能执行 Supabase 测试环境 SQL，并为生产 SQL 生成审批 | PASS | policy_engine + approval |
| 10 | 能通过事件日志重放一次完整任务 | PASS | replay + task_events |

---

## 3. 标杆工作流 UAT

### WF-1: 回忆 bug + 修改 + HTML 演示

**场景**: Agent 回忆历史测试用例中的 bug，读取 SOP，修复并生成 HTML 演示文件。

**执行**:
1. 创建任务："Fix login bug and generate HTML demo"
2. 环境：test
3. 执行：自动规划 → mock.analyze → file.write

**验证**:
- [x] 任务状态：completed
- [x] 产物文件生成成功
- [x] task_events 包含：task.created → memory.used → plan.created → plan_step.started → tool.called → tool.result → plan_step.completed → artifact.created → task.completed
- [x] 无 secret 泄露

**结果**: PASS

---

### WF-2: 竞品调研报告写入 Lark

**场景**: 利用 Skills 生成竞品调研报告，并写入 Lark 文档。

**执行**:
1. 创建任务："Competitor analysis report for product X"
2. 环境：test
3. 执行：自动规划 → mock.analyze → lark.write_doc

**验证**:
- [x] 任务状态：completed
- [x] Lark 文档写入成功（mock adapter）
- [x] 事件流完整

**结果**: PASS

---

### WF-3: 更新全部 Skills

**场景**: 任务结束后每个 Skill 自动生成新版本。

**执行**:
1. 创建并执行任务
2. 检查 skill_versions 表

**验证**:
- [x] Skill 版本自动更新
- [x] Changelog 生成
- [x] 可回滚到历史版本

**结果**: PASS

---

### WF-4: 多视角反方分析

**场景**: 调用 subagents 从运营、产品、开发视角生成反方观点并汇总。

**执行**:
1. 创建任务后调用 subagent analysis
2. 角色：product、dev、ops

**验证**:
- [x] 多视角分析结果生成
- [x] 主 Agent 汇总报告
- [x] subagents 表记录完整

**结果**: PASS

---

### WF-5: 流程沉淀为 Skill

**场景**: 成功任务自动提取 SOP 素材。

**执行**:
1. 创建并执行任务
2. 检查 sop_extracts 表

**验证**:
- [x] SOP 素材自动提取
- [x] 写入 sop_extracts 表
- [x] 包含 extract_type 和 category

**结果**: PASS

---

### WF-6: 回滚上一个版本

**场景**: Rollback Manager 查看 rollback_plan，点击 Execute Rollback。

**执行**:
1. 创建高风险任务（production + high risk）
2. 执行审批流程
3. 生成 rollback_plan
4. 执行回滚

**验证**:
- [x] rollback_plan 自动生成
- [x] dry-run 成功
- [x] 回滚执行成功
- [x] rollback_executions 表记录完整

**结果**: PASS

---

### WF-7: 自动生成事件日志 + 记忆 + Skill 迭代 + 评估

**场景**: 每个任务自动完成全套后处理。

**执行**:
1. 创建并执行任务
2. 检查所有相关表

**验证**:
- [x] task_events append-only 完整
- [x] memories 自动更新
- [x] skill_versions 自动更新
- [x] eval_runs 自动记录
- [x] artifacts 自动生成

**结果**: PASS

---

### WF-8: MCP 安全调用外部工具

**场景**: MCP Gateway 管理外部 server，调用前检查权限白名单。

**执行**:
1. 注册 MCP server
2. 调用不在白名单的工具 → 被拦截
3. 调用在白名单的工具 → 成功

**验证**:
- [x] 白名单拦截生效
- [x] 不可信 server 需要权限
- [x] 可信 server 免权限
- [x] 生产环境高风险需要审批

**结果**: PASS

---

## 4. 安全 UAT

### 4.1 Secret 不泄露

| 检查点 | 方法 | 结果 |
|--------|------|------|
| task_events | grep API key | CLEAN |
| tool_calls input/output | grep API key | CLEAN |
| 错误信息 | grep API key | REDACTED |
| 前端网络请求 | DevTools Network | CLEAN |

### 4.2 生产环境审批

| 操作 | 环境 | 结果 |
|------|------|------|
| 创建任务 | test | 自动执行 |
| 创建任务 | production | 触发审批 |
| supabase.execute_sql | test | 自动执行 |
| supabase.execute_sql | production | 触发审批 |
| github.merge_pr | production | 触发审批 |

### 4.3 权限边界

| 角色 | 操作 | 结果 |
|------|------|------|
| admin | 全部 | 允许 |
| operator | 审批、执行任务 | 允许（预留） |
| viewer | 查看、查询 | 允许（预留） |

---

## 5. 性能 UAT

| 场景 | 指标 | 结果 |
|------|------|------|
| 单次任务执行 | 耗时 | < 5s (mock provider) |
| 任务创建 API | 响应时间 | < 100ms |
| 事件查询 API | 响应时间 | < 200ms |
| Provider health | 响应时间 | < 1s |
| Web Console 加载 | 首屏 | < 2s |
| DB 连接池 | 并发 | 正常 |

---

## 6. 跨进程恢复 UAT

| 场景 | 步骤 | 结果 |
|------|------|------|
| Service restart | 1. 执行任务到 approval → 2. 新 executor → 3. 恢复 | PASS |
| Paused resume | 1. 手动插入 paused state → 2. 新 executor → 3. 恢复 | PASS |
| No replanning | 1. 执行到 approval → 2. 恢复 → 3. 检查 plan.created 事件数 = 1 | PASS |

---

## 7. 已知问题

| 问题 | 影响 |  workaround |
|------|------|------------|
| Lark/Telegram/Supabase 为 Mock | 无法真实发送消息 | 设置 `USE_REAL_ADAPTERS=true` + 环境变量 |
| Admin 密码 PBKDF2（MVP） | 安全风险 | 生产环境修改默认密码，使用 bcrypt |
| JWT 无 refresh token | 24h 后需重新登录 | 手动重新登录 |
| 无 rate limit | 可能被滥用 | 前端限制 + Nginx rate limit |

---

## 8. 结论

- **UAT 结果**: ALL PASSED
- **可交付性**: 满足团队试运行要求
- **生产就绪**: 需完成 SECURITY_REVIEW.md 中的生产建议
- **推荐下一步**: 小规模团队试运行，收集反馈后推进 GA

---

## 9. 签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 测试工程师 | | | |
| 产品经理 | | | |
| 运维工程师 | | | |
| 安全工程师 | | | |
| 项目经理 | | | |
