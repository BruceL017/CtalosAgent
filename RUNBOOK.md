# Runbook — Enterprise Agent v0.3.1

**Version**: v0.3.1
**Date**: 2026-04-27
**Purpose**: 运维工程师日常操作、故障排查、应急响应手册

---

## 1. 日常巡检

### 1.1 健康检查

```bash
# API Server
curl -s http://localhost:3001/health | jq .

# Agent Runtime
curl -s http://localhost:8000/health | jq .

# Agent Runtime 详细健康
curl -s http://localhost:8000/health/detailed | jq '.service, .status, .database.healthy'

# Provider 健康
curl -s http://localhost:8000/providers/health | jq '.data[] | {provider, healthy, latency_ms}'
```

### 1.2 容器状态

```bash
docker compose ps
docker stats --no-stream
```

### 1.3 日志检查

```bash
# 最近 100 行错误
docker compose logs --tail=100 api-server | grep -i error
docker compose logs --tail=100 agent-runtime | grep -i error

# 实时日志
docker compose logs -f api-server
docker compose logs -f agent-runtime
```

### 1.4 数据库检查

```bash
# 连接数
docker compose exec postgres psql -U agent -d agent_db -c "SELECT count(*) FROM pg_stat_activity;"

# 表大小
docker compose exec postgres psql -U agent -d agent_db -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# 任务统计
docker compose exec postgres psql -U agent -d agent_db -c "SELECT status, COUNT(*) FROM tasks GROUP BY status;"
```

---

## 2. 故障排查

### 2.1 任务失败排查

```bash
# 1. 查看失败任务
psql -U agent -d agent_db -c "SELECT id, title, status, error_message, created_at FROM tasks WHERE status = 'failed' ORDER BY created_at DESC LIMIT 10;"

# 2. 查看任务事件流
# API: GET /api/tasks/<task_id>/events

# 3. 查看工具调用
# API: GET /api/tasks/<task_id>/tool-calls

# 4. 查看审批记录
# API: GET /api/approvals?status=pending
```

### 2.2 Provider 失败

**症状**: 任务执行时 LLM 调用失败，或 `/providers/health` 显示 unhealthy

```bash
# 检查 Provider 健康
curl http://localhost:8000/providers/health
curl http://localhost:8000/providers/stats

# 检查 API key 是否配置正确
docker compose exec agent-runtime env | grep -i api_key

# 检查 Provider 日志
docker compose logs agent-runtime | grep -i "provider\|siliconflow\|openai"

# 手动测试 Provider
cd apps/agent-runtime
source .venv/bin/activate
PYTHONPATH=src python -c "from services.provider_router import ProviderRouter; import asyncio; p = ProviderRouter(); print(asyncio.run(p.health_check()))"
```

**恢复**:
- 检查 API key 余额和有效期
- 检查网络连通性（`curl https://api.siliconflow.cn/v1/models`）
- 切换到 fallback provider（修改 `DEFAULT_PROVIDER` 环境变量）
- 重启 Agent Runtime：`docker compose restart agent-runtime`

### 2.3 数据库连接池耗尽

**症状**: 请求超时，DB 连接数达到上限

```bash
# 检查活跃连接
docker compose exec postgres psql -U agent -d agent_db -c "SELECT state, COUNT(*) FROM pg_stat_activity GROUP BY state;"

# 查看是否有 idle 连接
docker compose exec postgres psql -U agent -d agent_db -c "SELECT pid, usename, state, query_start, query FROM pg_stat_activity WHERE state = 'idle' AND query_start < NOW() - INTERVAL '5 minutes';"

# 终止长期 idle 连接
docker compose exec postgres psql -U agent -d agent_db -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < NOW() - INTERVAL '10 minutes';"
```

**恢复**:
- 重启 API Server 和 Agent Runtime 释放连接
- 检查 asyncpg pool 配置（`min_size` / `max_size`）
- 增加 PostgreSQL `max_connections`（默认 100）

### 2.4 内存泄漏

**症状**: Agent Runtime 内存持续增长

```bash
# 查看内存使用
docker stats --no-stream agent_runtime

# 检查运行中的任务
curl http://localhost:8000/health/detailed | jq '.active_tasks'

# 检查 _running_tasks 和 _paused_tasks
docker compose logs agent-runtime | grep -i "running\|paused\|cancel"
```

**恢复**:
- 取消卡死任务：`POST /api/tasks/<task_id>/cancel`
- 重启 Agent Runtime：`docker compose restart agent-runtime`

### 2.5 Web Console 无法访问

```bash
# 检查 Web Console 容器
docker compose ps web-console
docker compose logs web-console

# 检查 API Server 是否可达
curl http://localhost:3001/health

# 检查 Nginx 配置（Docker 模式）
docker compose exec web-console nginx -t
```

---

## 3. 审批操作

### 3.1 查看待审批

```bash
curl -H "Authorization: Bearer <token>" http://localhost:3001/api/approvals?status=pending
```

### 3.2 审批通过

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://localhost:3001/api/approvals/<approval_id>/approve \
  -d '{"reason":"Approved by ops"}'
```

### 3.3 审批拒绝

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://localhost:3001/api/approvals/<approval_id>/reject \
  -d '{"reason":"Risk too high"}'
```

---

## 4. 回滚操作

### 4.1 查看回滚计划

```bash
curl -H "Authorization: Bearer <token>" http://localhost:3001/api/rollbacks
```

### 4.2 Dry-run 回滚

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:3001/api/rollbacks/<plan_id>/dry-run
```

### 4.3 执行回滚

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:3001/api/rollbacks/<plan_id>/execute
```

### 4.4 任务级回滚

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:3001/api/tasks/<task_id>/rollback
```

---

## 5. 监控指标

### 5.1 Prometheus Metrics

```bash
# Agent Runtime metrics
curl http://localhost:8000/metrics

# API Server metrics proxy
curl -H "Authorization: Bearer <token>" http://localhost:3001/api/providers/metrics
```

### 5.2 关键指标

| 指标 | 来源 | 告警阈值 |
|------|------|---------|
| request_latency_seconds | `/metrics` | P99 > 5s |
| request_count_total | `/metrics` | 异常突增 |
| task_count_total | `/metrics` | — |
| provider_latency_ms | `/providers/stats` | > 10s |
| provider_errors | `/providers/stats` | > 5% |
| DB connections | PostgreSQL | > 80 |

---

## 6. 紧急响应

### 6.1 服务完全不可用

```bash
# 1. 检查容器状态
docker compose ps

# 2. 检查资源
docker stats --no-stream
free -h
df -h

# 3. 重启服务
docker compose down
docker compose up -d

# 4. 验证
bash smoke-test.sh
```

### 6.2 Secret 泄露

1. 立即轮换泄露的 API key
2. 检查 `task_events` 和 `tool_calls` 中是否存在未脱敏的 secret
3. 更新 `SECRET_PATTERNS`
4. 审查 `audit_logs`

### 6.3 数据损坏

1. 停止写入：`docker compose stop agent-runtime api-server`
2. 从备份恢复（见 BACKUP_RESTORE.md）
3. 验证数据完整性
4. 逐步恢复服务

### 6.4 高负载 / DDoS

1. 启用 rate limit（如有配置）
2. 检查异常任务来源
3. 取消可疑任务
4. 考虑水平扩展 Agent Runtime

---

## 7. 维护窗口

### 7.1 日常维护（每周）

- [ ] 检查日志中的 error/warning
- [ ] 检查磁盘使用率
- [ ] 检查数据库连接数
- [ ] 检查 Provider 健康状态
- [ ] 备份数据库

### 7.2 月度维护

- [ ] 更新依赖（`npm audit`, `pip audit`）
- [ ] 清理过期任务事件（保留策略见 BACKUP_RESTORE.md）
- [ ] 检查 SSL 证书过期
- [ ] 审查审批记录和审计日志

### 7.3 升级维护

- [ ] 阅读 RELEASE_NOTES
- [ ] 备份数据库
- [ ] 执行 migration
- [ ] 滚动升级
- [ ] Smoke test

---

## 8. 联系信息

| 角色 | 职责 |
|------|------|
| 运维工程师 | 日常巡检、故障排查、升级 |
| 安全工程师 | Secret 轮换、安全审计、权限审查 |
| 开发工程师 | Bug 修复、feature 开发、代码 review |
| 管理员 | 审批、RBAC 配置、重大决策 |
