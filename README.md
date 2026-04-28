# CtalosAgent v0.3.1

> CtalosAgent — 企业级中控 Agent 系统。具备 Web 控制台、CLI 入口、Agent Runtime、长期记忆、Skill 自我迭代、Subagent 编排、多模型 Provider 路由、真实工具集成、MCP Gateway、权限策略引擎、审批流、结构化事件日志、Replay 调试、补偿式回滚能力。

**当前版本**: v0.3.1 | **完成度**: 99/100 | **状态**: Release Candidate — 团队试运行就绪

**交付文档**:
- [Quick Start](QUICKSTART.md) — 5 分钟克隆验证指南
- [Release Notes](RELEASE_NOTES.md) — 版本发布说明
- [Changelog](CHANGELOG.md) — 版本变更记录
- [Deployment Guide](DEPLOYMENT.md) — 部署指南
- [Runbook](RUNBOOK.md) — 运维手册
- [Backup & Restore](BACKUP_RESTORE.md) — 备份恢复指南
- [Security Review](SECURITY_REVIEW.md) — 安全审计报告
- [Security Policy](SECURITY.md) — 漏洞报告和安全建议
- [UAT Report](UAT_REPORT.md) — 用户验收测试报告
- [Implementation Report](ENTERPRISE_AGENT_V0_3_REPORT.md) — 实现报告
- [Contributing](CONTRIBUTING.md) — 开发贡献指南

## 架构

```
Web Console (React + Vite) ──▶ API Server (Fastify + Node.js) ──▶ Agent Runtime (FastAPI + Python)
                                            │                              │
                                            └──────── PostgreSQL + Redis ──┘
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Web Console | React 18 + TypeScript + Vite |
| API Server | Node.js 20 + Fastify + pg |
| Agent Runtime | Python 3.11 + FastAPI + asyncpg + httpx + prometheus-client |
| 数据库 | PostgreSQL 16 + pgvector |
| 队列/缓存 | Redis 7 |
| 包管理 | pnpm workspaces |

## 核心能力

### Agent Runtime
- 完整状态机：`pending → planning → awaiting_approval → approved → running → completed/failed/cancelled/rolled_back`
- 支持 `pause`、`resume`、`retry`、`cancel`
- Claude/Anthropic 风格 tool calling 消息结构
- 每个状态转换写入 `task_events` 和 `task_state_transitions`

### Model Provider Router
- OpenAI (GPT-4o)、Anthropic Claude 3.5、Google Gemini 1.5、DeepSeek、智谱 GLM-4、Kimi Moonshot、SiliconFlow (GLM-4.7)
- 统一 chat/completion/tool_call 接口
- 自动 fallback、超时、错误重试、token/latency 统计
- Provider 健康检查 (`/providers/health`) 和统计 (`/providers/stats`)
- API key 从环境变量读取，异常信息自动脱敏
- 真实 Embedding 服务（SiliconFlow）接入 pgvector，支持语义搜索

### Memory System
- PostgreSQL + pgvector
- Episodic（任务轨迹）、Semantic（业务事实）、Procedural（SOP/避坑）、Performance（成功率/耗时）
- 任务前自动检索，任务后自动写入
- Web Console 支持查看、搜索、停用

### Skill/SOP 自我进化
- Skill 版本化存储（skills + skill_versions）
- 任务结束后 LLM 自动生成改进版本
- 自动提取 SOP 和避坑库素材
- 支持 rollback 到任意历史版本

### Tool Registry + 权限边界
- 所有工具 manifest 注册（risk_level、environment、approval_required、rollback_strategy）
- 四种权限模式：`read_only`、`workspace_write`、`approval_required`、`admin_full_access`
- 生产环境 + 高风险操作强制审批
- 测试环境 + 低风险操作自动执行
- MCP Server 白名单 + 权限校验 + 风险等级 + 默认不可信

### 真实工具集成
| 工具 | 能力 |
|------|------|
| GitHub | create_issue、create_branch、create_commit、create_pr、merge_pr、revert_commit、get_repo_files |
| Supabase | query、execute_sql（test/prod 区分） |
| Lark/飞书 | write_doc、send_message、create_task |
| Telegram | send_message、edit_message、delete_message |
| MCP Gateway | register_server、list_tools、call_tool、health_check |

### Subagent Manager
- 角色：product、dev、ops、data、security
- 独立上下文和权限
- 主 Agent 分发任务、汇总结果、冲突消解
- 支持多视角反方分析

### Replay / Audit / Rollback
- 完整事件流 `task_events`（append-only）
- 支持按 task replay、tool_call debug
- 高风险动作执行前生成 `rollback_plan`
- 补偿式回滚：Git revert、SQL reverse、Lark 文档修正、消息撤回/更正、Skill 版本回滚
- 结构化日志带 task_id/session_id/tool_call_id/trace_id
- Prometheus metrics 端点 (`/metrics`)
- Secret AES-256-GCM 加密存储

## 快速启动

### 1. 环境配置

```bash
cp .env.example .env
# 编辑 .env — Mock 模式下无需填入真实 API key，系统默认使用 mock provider
# 如需真实 LLM，填入 SILICONFLOW_API_KEY 等（可选）
```

### 2. 启动基础设施

```bash
docker compose up -d postgres redis
```

### 3. 数据库迁移

```bash
# 初始化 schema
docker compose exec postgres psql -U agent -d agent_db -f /migrations/001_initial_schema.sql

# 状态机、subagent、rollback 扩展
docker compose exec postgres psql -U agent -d agent_db -f /migrations/002_state_machine_subagents.sql

# Session、memory scope、approval plan_state
docker compose exec postgres psql -U agent -d agent_db -f /migrations/003_sessions_and_memory_scope.sql
```

### 4. 启动 API Server

```bash
cd apps/api-server
pnpm install
pnpm dev   # http://localhost:3001
```

### 5. 启动 Agent Runtime

```bash
cd apps/agent-runtime
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 8000   # http://localhost:8000
```

### 6. 启动 Web Console

```bash
cd apps/web-console
pnpm install
pnpm dev   # http://localhost:5173
```

### 一键 Docker Compose（完整堆栈）

```bash
# 配置 .env 后
docker compose up --build -d

# 执行迁移
docker compose exec postgres psql -U agent -d agent_db -f /migrations/001_initial_schema.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/002_state_machine_subagents.sql

# 查看日志
docker compose logs -f api-server
docker compose logs -f agent-runtime
```

## CLI 使用

所有 CLI 操作通过 API Server，不绕过控制面：

```bash
cd apps/cli && npm install

# Session 管理
node src/index.ts session:create "My Session" -d "Description"
node src/index.ts session:list
node src/index.ts session:show <session_id>

# 任务管理
node src/index.ts task:create "Report Generation" --session <session_id>
node src/index.ts task:run <task_id>
node src/index.ts task:status <task_id>
node src/index.ts task:events <task_id>

# 审批
node src/index.ts approvals:list
node src/index.ts approvals:approve <approval_id>

# 记忆和技能
node src/index.ts memory:list
node src/index.ts skill:list

# 健康检查
node src/index.ts health
```

## 标杆工作流验证

1. **回忆 bug + 修改 + HTML 演示**
   - Web Console 创建任务："Fix login bug and generate HTML demo"
   - Agent Runtime 检索记忆 → 读取 Skill → 规划 → 执行 mock.analyze → file.write → 生成 artifact

2. **竞品调研报告写入 Lark**
   - 创建任务："Competitor analysis report for product X"
   - Agent 自动调用 lark.write_doc 写入飞书文档

3. **更新全部 Skills**
   - 任务结束后每个 Skill 自动生成新版本
   - 在 Skill Manager 查看版本历史和 changelog

4. **多视角反方分析**
   - 创建任务后调用 Subagent：product + dev + ops 视角
   - 主 Agent 汇总并消解冲突

5. **流程沉淀为 Skill**
   - 成功任务自动提取 SOP 素材
   - 写入 sop_extracts 表

6. **回滚上一个版本**
   - Rollback Manager 查看 rollback_plan
   - 点击 Execute Rollback 执行补偿

7. **自动生成事件日志 + 记忆 + Skill 迭代 + 评估**
   - 每个任务自动完成全套后处理

8. **MCP 安全调用外部工具**
   - MCP Gateway 管理外部 server
   - 调用前检查权限白名单

## 数据库 Schema

### 核心表
- `users` — 用户（MVP 单管理员，预留 RBAC）
- `tasks` — 任务（含状态机、重试计数）
- `task_events` — append-only 结构化事件流
- `task_state_transitions` — 状态转换记录
- `tool_calls` — 工具调用记录
- `approvals` — 审批流
- `rollback_plans` — 回滚计划
- `rollback_executions` — 回滚执行记录
- `memories` — 长期记忆（含 is_active 软删除）
- `memory_embeddings` — pgvector 向量索引
- `skills` — Skill 定义
- `skill_versions` — Skill 版本历史（支持 rollback）
- `subagents` — Subagent 执行记录
- `artifacts` — 任务产物
- `provider_configs` — 模型供应商配置
- `mcp_servers` — MCP Server 注册
- `replay_sessions` — 重放会话
- `audit_logs` — 审计日志
- `sop_extracts` — SOP/避坑库素材
- `sessions` — 会话（聊天上下文）
- `session_messages` — 会话消息
- `session_task_links` — 会话与任务关联
- `eval_runs` — 评估记录

## API 端点

### API Server (`:3001`)
- `GET /health` — 服务健康
- `POST /api/auth/login` — 管理员登录（JWT）
- `GET /api/auth/me` — 当前用户
- `GET/POST /api/tasks` — 任务 CRUD
- `POST /api/tasks/:id/execute` — 执行任务
- `POST /api/tasks/:id/cancel|pause|resume|rollback` — 状态控制
- `GET /api/tasks/:id/events|tool-calls` — 事件和工具调用
- `GET /api/events` — 事件查询
- `GET /api/skills` — Skill 管理
- `GET /api/memories` — 记忆管理
- `GET/POST /api/approvals` — 审批队列
- `GET/POST /api/rollbacks` — 回滚管理
- `GET/POST /api/replay` — Replay 会话
- `GET /api/providers` — Provider 状态
- `GET /api/providers/metrics` — Prometheus metrics
- `GET/POST /api/mcp/servers` — MCP 管理
- `GET /api/audit` — 审计日志
- `GET /api/subagents` — Subagent 查询
- `GET/POST /api/sessions` — Session 管理
- `POST /api/sessions/:id/messages` — 会话消息
- `POST /api/sessions/:id/tasks` — 会话内创建任务

> 所有 `/api/*` 端点（除 `/api/auth/login`）需要 Bearer Token 认证

### Agent Runtime (`:8000`)
- `POST /execute` — 启动 Agent Run
- `POST /tasks/:id/cancel|pause|resume|rollback` — 状态控制
- `POST /tasks/:id/subagents/analyze` — Subagent 分析
- `POST /tasks/:id/replay` — 创建 Replay
- `POST /rollback-plans/:id/execute` — 执行回滚
- `POST /rollback-plans/:id/dry-run` — Dry-run 回滚
- `GET /providers` — Provider 列表
- `GET /providers/health` — Provider 健康检查
- `GET /providers/stats` — Provider 调用统计
- `POST /providers/chat` — 统一 LLM 调用
- `GET/POST /mcp/servers` — MCP 管理
- `GET /tools` — Tool Registry
- `GET /metrics` — Prometheus metrics
- `GET /health/detailed` — DB + Provider + Embedding 健康状态

## 测试

```bash
# 统一测试（根目录）
npm run test              # 全部测试（mock 模式，无需 API key）
npm run test:python       # Python 测试（48 passed）
npm run test:api          # API Server 测试（3 passed）
npm run test:web          # Web Console 编译检查
npm run test:real         # 真实 Provider 测试（14 passed，需要 API key）
npm run typecheck         # TypeScript 类型检查（API Server + Web Console）
npm run smoke             # Smoke test（20 步端到端验证）

# Python 自动化测试
cd apps/agent-runtime && PYTHONPATH=src .venv/bin/python -m pytest tests/ -v

# 仅真实 Provider 测试（需要 SILICONFLOW_API_KEY + SILICONFLOW_EMBEDDING_API_KEY）
export SILICONFLOW_API_KEY=sk-your-key-here
export SILICONFLOW_EMBEDDING_API_KEY=sk-your-key-here
export DEFAULT_PROVIDER=siliconflow
PYTHONPATH=src .venv/bin/python -m pytest tests/test_provider_real.py tests/test_end_to_end_real_llm.py tests/test_embedding_service.py tests/test_github_real.py -v

# API 自动化测试
cd apps/api-server && npx vitest run

# TypeScript 编译检查
cd apps/api-server && npx tsc --noEmit
cd apps/web-console && npx tsc --noEmit

# Docker 验证
docker compose config
docker compose build --dry-run

# 手动验证
curl http://localhost:3001/health
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed
curl http://localhost:8000/providers/health
curl http://localhost:8000/providers/stats

# 登录获取 token（默认 demo 密码，生产必须更换）
curl -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@enterprise.local","password":"admin123"}'

# 创建任务（需要 Bearer token）
curl -X POST http://localhost:3001/api/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title":"Test Report","description":"Generate a test report","environment":"test"}'
```

## 项目结构

```
enterprise-agent/
├── apps/
│   ├── web-console/          # React + Vite + TypeScript
│   │   ├── src/
│   │   │   ├── pages/        # Login, Dashboard, ProviderConfig...
│   │   │   ├── stores/       # Auth store (zustand)
│   │   │   ├── api/          # API client with Bearer token
│   │   │   └── App.tsx
│   ├── api-server/           # Fastify + Node.js + TypeScript
│   │   ├── src/
│   │   │   ├── middleware/   # JWT auth
│   │   │   ├── routes/       # tasks, auth, providers...
│   │   │   └── index.ts
│   └── agent-runtime/        # FastAPI + Python
│       └── src/
│           ├── main.py
│           ├── models/       # Pydantic schemas, state machine
│           ├── services/     # executor, provider_router, memory, skill, subagent, rollback, replay, policy_engine
│           ├── tools/        # registry, adapters, integrations
│           ├── utils/        # encryption, secret_redactor, structured_logger
│           └── tests/        # 60+ 测试用例
├── packages/
│   ├── shared-types/         # TypeScript 类型定义
│   └── db-schema/
│       └── migrations/       # 001-004 SQL migrations
├── shared/artifacts/         # 任务产物存储
├── docker-compose.yml
├── package.json              # 根目录统一脚本
├── .env.example
├── smoke-test.sh             # 20 步端到端验证
├── RELEASE_NOTES.md          # 发布说明
├── CHANGELOG.md              # 版本变更
├── DEPLOYMENT.md             # 部署指南
├── RUNBOOK.md                # 运维手册
├── BACKUP_RESTORE.md         # 备份恢复
├── SECURITY_REVIEW.md        # 安全审计
├── SECURITY.md               # 漏洞报告政策
├── UAT_REPORT.md             # 用户验收测试
├── ENTERPRISE_AGENT_V0_3_REPORT.md  # 实现报告
├── CONTRIBUTING.md           # 开发贡献指南
├── QUICKSTART.md             # 5 分钟快速验证
├── LICENSE                   # MIT License
└── README.md
```

## Mock Mode vs Real Provider Mode

| 模式 | 无需 API key | 说明 |
|------|-------------|------|
| **Mock（默认）** | 是 | 系统使用 mock provider，所有外部调用被模拟。适合 clone 验证、CI、本地开发。 |
| **Real Provider** | 否 | 填入真实 API key 后，Agent 会调用真实 LLM 和外部服务。 |

**默认安全配置**：
- 默认使用 mock provider（`DEFAULT_PROVIDER=openai`，但无 key 时 fallback 到 mock）
- 默认外部 adapter 为 mock（`USE_REAL_ADAPTERS=false`）
- 默认 high-risk / production 操作需要审批
- 默认日志脱敏（API key、token、password 自动 redact）
- 默认 admin 密码为 `admin123`（**仅限 demo**，生产必须使用 `DEFAULT_ADMIN_PASSWORD` 环境变量更换）

**⚠️ 警告**：不要将 `.env` 文件提交到 git。提交前运行 `git status` 确认没有敏感文件。

## 安全边界

- 所有 `/api/*` 端点（除 `/health` 和 `/api/auth/login`）需要 Bearer Token
- 生产环境高风险工具强制审批（policy_engine）
- MCP Server 默认不可信，白名单校验
- Secret 传输自动脱敏（7 种 pattern）
- AES-256-GCM 加密存储敏感数据
- SQL 参数化查询，无注入漏洞
- 文件写入限制在 `ARTIFACTS_DIR` 目录

详见 [SECURITY.md](SECURITY.md) 和 [SECURITY_REVIEW.md](SECURITY_REVIEW.md)。

## 哪些能力是 Mock

| 能力 | 状态 | 启用真实版本 |
|------|------|------------|
| Lark/飞书 | Mock | `USE_REAL_ADAPTERS=true` + `LARK_APP_ID` |
| Telegram | Mock | `USE_REAL_ADAPTERS=true` + `TELEGRAM_BOT_TOKEN` |
| Supabase SQL | Mock | `USE_REAL_ADAPTERS=true` + `SUPABASE_URL` |
| MCP stdio | Mock | 未接入真实 MCP SDK |
| LLM Provider | Mock（无 key 时） | 填入对应 `*_API_KEY` |

## 许可证

MIT
