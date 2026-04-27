# Release Notes — Enterprise Agent v0.3.1

**Release Date**: 2026-04-27
**Version**: v0.3.1
**Status**: Release Candidate — 团队试运行就绪
**Score**: 99/100

---

## TL;DR

Enterprise Agent v0.3.1 是从 "功能基本完成" 推进到 "可交付、可部署、可验收、可运维、可回滚" 的 Release Candidate。

- 62 个自动化测试全部通过（48 mock + 14 real API）
- Web Console 完成 Auth 集成和 Provider 监控面板
- 跨进程恢复、GitHub 真实适配器、Secret 加密、结构化日志全部验证
- 完整交付文档：部署指南、运维手册、安全审计、备份恢复、UAT 报告

---

## What's New

### Web Console Auth 集成
- 登录页面 (`/login`)：邮箱/密码登录，默认管理员 `admin@enterprise.local` / `admin123`
- 所有 API 调用自动注入 `Authorization: Bearer <token>`
- 未登录自动重定向，登录后显示用户信息和角色 badge
- 支持角色：admin、operator、viewer

### Provider 监控面板
- 实时显示 provider 健康状态（healthy/unhealthy）
- Metrics Overview：Total Requests、Total Tokens、Avg Latency、Errors
- 每个 provider card 显示：状态、延迟、请求数、token 消耗

### 跨进程恢复测试
- Service restart 后从 DB workflow_states 恢复
- 验证 paused 状态恢复、tool_approval 恢复、无重复 replanning
- EventLogger sequence 跨进程安全

### GitHub 真实适配器验证
- 3 个只读测试：读取公开仓库文件列表、目录、无效仓库处理
- 自动通过 `gh auth token` 获取 CLI token

---

## System Requirements

| 组件 | 最低要求 | 推荐 |
|------|---------|------|
| Node.js | 20.x | 20.x LTS |
| Python | 3.11 | 3.12 |
| PostgreSQL | 16 + pgvector | 16 + pgvector |
| Redis | 7 | 7 |
| Docker | 24.x | 24.x + |
| pnpm | 8.x | 8.15+ |

---

## Quick Start

```bash
# 1. 克隆仓库
git clone <repo> && cd enterprise-agent

# 2. 配置环境
cp .env.example .env
# 编辑 .env 填入 API keys

# 3. 启动基础设施
pnpm run dev:infra

# 4. 执行数据库迁移
pnpm run db:migrate

# 5. 安装依赖并启动（终端 1：API Server）
cd apps/api-server && pnpm install && pnpm dev

# 6. 启动 Agent Runtime（终端 2）
cd apps/agent-runtime
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd src && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 7. 启动 Web Console（终端 3）
cd apps/web-console && pnpm install && pnpm dev

# 8. Smoke Test
pnpm run smoke
```

---

## Docker Compose（生产部署）

```bash
# 一键启动完整堆栈
docker compose up --build -d

# 执行迁移
docker compose exec postgres psql -U agent -d agent_db -f /migrations/001_initial_schema.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/002_state_machine_subagents.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/003_sessions_and_memory_scope.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/004_workflow_states.sql

# 查看日志
docker compose logs -f api-server
docker compose logs -f agent-runtime
```

---

## Known Issues

1. **Admin Auth MVP**: JWT HMAC-SHA256 + 内存默认账户，生产环境应使用 bcrypt + refresh token + DB 用户表
2. **Secret Encryption MVP**: AES-256-GCM + 环境变量 key，生产环境应使用 HashiCorp Vault 或云 KMS
3. **Lark/Telegram/Supabase**: 仍为 Mock adapter，需设置 `USE_REAL_ADAPTERS=true` 和对应环境变量启用真实 API
4. **MCP stdio**: 模拟通信，未接入真实 MCP server SDK
5. **并发任务**: 未做 soak test，长任务堆积处理机制待验证

---

## Upgrade from v0.3.0

1. 执行新增 migration `004_workflow_states.sql`（如未执行）
2. Web Console 重新安装依赖（新增 zustand）
3. 更新 `.env`：确保包含 `JWT_SECRET`、`ENCRYPTION_KEY`
4. 重启所有服务

---

## Deprecations

无。

---

## Contributors

- Core: Enterprise Agent Team
- LLM Provider: SiliconFlow (OpenAI-compatible)
- Embedding: Qwen/Qwen3-VL-Embedding-8B

---

## License

MIT
