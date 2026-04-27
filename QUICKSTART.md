# Quick Start — 5 分钟验证 Enterprise Agent

本指南帮助你在 clone 仓库后，**无需任何真实 API key**，通过 mock 模式验证系统是否正常工作。

## 前置条件

- Docker + Docker Compose
- Node.js ≥ 20 + pnpm ≥ 8（或 npm / yarn）
- Python ≥ 3.11

## 1. Clone & 配置（1 分钟）

```bash
git clone <repo-url>
cd enterprise-agent

# 复制环境模板（无需修改，mock 模式可直接工作）
cp .env.example .env
```

> `.env.example` 中所有 API key 都是占位符。系统默认使用 mock provider，无需真实 key。

## 2. 启动基础设施（1 分钟）

```bash
docker compose up -d postgres redis
```

确认启动成功：

```bash
docker compose ps
# 应看到 postgres 和 redis 为 healthy / running
```

## 3. 执行数据库迁移（1 分钟）

```bash
pnpm run db:migrate
```

或手动执行：

```bash
docker compose exec postgres psql -U agent -d agent_db -f /migrations/001_initial_schema.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/002_state_machine_subagents.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/003_sessions_and_memory_scope.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/004_workflow_states.sql
```

## 4. 启动服务（2 分钟）

打开 3 个终端窗口：

**终端 1 — API Server**

```bash
cd apps/api-server
pnpm install
pnpm dev
```

**终端 2 — Agent Runtime**

```bash
cd apps/agent-runtime
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**终端 3 — Web Console**

```bash
cd apps/web-console
pnpm install
pnpm dev
```

## 5. 验证（浏览器 + curl）

### 浏览器验证

1. 打开 http://localhost:5173
2. 使用默认账号登录：
   - Email: `admin@enterprise.local`
   - Password: `admin123`
3. 进入 Dashboard，创建测试任务
4. 查看 Task Events 实时流

### curl 验证

```bash
# 1. 健康检查
curl http://localhost:3001/health
curl http://localhost:8000/health/detailed

# 2. 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@enterprise.local","password":"admin123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")

echo "Token: $TOKEN"

# 3. 创建任务
curl -X POST http://localhost:3001/api/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Mock Demo","description":"Generate a test report","environment":"test"}'

# 4. 查看任务列表
curl -H "Authorization: Bearer $TOKEN" http://localhost:3001/api/tasks

# 5. 查看审批列表
curl -H "Authorization: Bearer $TOKEN" http://localhost:3001/api/approvals

# 6. Provider 健康
curl http://localhost:8000/providers/health
curl http://localhost:8000/providers/stats
```

## 6. Smoke Test（20 步端到端）

```bash
# 确保 API Server 和 Agent Runtime 已启动
pnpm run smoke
```

预期输出：20 步验证全部 PASS，覆盖 Auth → Health → Provider → Task → Session → Audit。

## 7. 运行测试

```bash
# 全部测试（mock，无需 API key）
pnpm run test

# 仅 Python 测试
pnpm run test:python

# 仅 API 测试
pnpm run test:api
```

预期：Python 48 passed, 8 skipped；API 3 passed；Web Console tsc EXIT 0。

## Mock vs Real Provider

| 模式 | 配置 | 说明 |
|------|------|------|
| **Mock（默认）** | 不配置任何 API key | 使用 mock provider，适合验证和开发 |
| **Real** | 在 `.env` 填入 `SILICONFLOW_API_KEY` 等 | 真实 LLM 调用，用于生产 |

切换 Real Provider：

```bash
# 编辑 .env
SILICONFLOW_API_KEY=sk-your-real-key
DEFAULT_PROVIDER=siliconflow

# 运行真实测试
pnpm run test:real
```

## 常见错误排查

### Docker 启动失败

```bash
# 端口占用？
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis

# 清理后重试
docker compose down -v
docker compose up -d postgres redis
```

### 数据库连接失败

```bash
# 确认迁移已执行
docker compose exec postgres psql -U agent -d agent_db -c "\dt"
# 应看到 tasks、task_events、memories 等表
```

### API Server 启动失败

```bash
# 确认数据库已启动
curl http://localhost:3001/health

# 检查日志
cd apps/api-server && pnpm dev
```

### Agent Runtime 启动失败

```bash
# 确认 .venv 已激活
which python  # 应指向 .venv/bin/python

# 检查依赖
pip install -r requirements.txt
```

### Smoke test 失败

```bash
# 确认所有服务已启动
curl http://localhost:3001/health
curl http://localhost:8000/health

# 重新运行
bash smoke-test.sh
```

## 下一步

- [完整部署指南](DEPLOYMENT.md)
- [安全审计](SECURITY_REVIEW.md)
- [运维手册](RUNBOOK.md)
- [备份恢复](BACKUP_RESTORE.md)
- [开发贡献](CONTRIBUTING.md)
