# Deployment Guide — Enterprise Agent v0.3.1

**Version**: v0.3.1
**Date**: 2026-04-27
**Target**: 单服务器 / 小型集群 Docker Compose 部署

---

## 1. 前置条件

| 组件 | 版本 | 说明 |
|------|------|------|
| Docker | 24.x+ | 含 docker compose plugin |
| Docker Compose | 2.x+ | |
| Git | 2.x+ | 克隆仓库 |
| 内存 | 4GB+ | 推荐 8GB |
| 磁盘 | 20GB+ | 含 PostgreSQL 数据 |

---

## 2. 环境准备

### 2.1 克隆仓库

```bash
git clone <repo-url> enterprise-agent
cd enterprise-agent
```

### 2.2 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入以下必填项：

```bash
# === Database ===
DATABASE_URL=postgresql://agent:agent_secret@127.0.0.1:5432/agent_db

# === Security (必须修改默认值) ===
JWT_SECRET=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)

# === LLM Provider (至少配置一个) ===
# SiliconFlow（推荐，国内可用）
SILICONFLOW_API_KEY=sk-...
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Pro/zai-org/GLM-4.7
DEFAULT_PROVIDER=siliconflow

# 或 OpenAI
# OPENAI_API_KEY=sk-...
# DEFAULT_PROVIDER=openai

# === Embedding (可选，不配置则使用 Mock) ===
SILICONFLOW_EMBEDDING_API_KEY=sk-...
SILICONFLOW_EMBEDDING_MODEL=Qwen/Qwen3-VL-Embedding-8B

# === GitHub (可选，用于真实 GitHub 集成) ===
GITHUB_TOKEN=ghp_...

# === 其他可选 ===
SUPABASE_URL=...
LARK_APP_ID=...
TELEGRAM_BOT_TOKEN=...
```

### 2.3 生成随机密钥

```bash
# 生成安全的 JWT_SECRET 和 ENCRYPTION_KEY
openssl rand -hex 32
```

---

## 3. Docker Compose 部署（推荐）

### 3.1 一键启动

```bash
docker compose up --build -d
```

### 3.2 执行数据库迁移

```bash
docker compose exec postgres psql -U agent -d agent_db -f /migrations/001_initial_schema.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/002_state_machine_subagents.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/003_sessions_and_memory_scope.sql
docker compose exec postgres psql -U agent -d agent_db -f /migrations/004_workflow_states.sql
```

### 3.3 验证部署

```bash
# API Server
curl http://localhost:3001/health

# Agent Runtime
curl http://localhost:8000/health

# 认证登录
curl -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@enterprise.local","password":"admin123"}'

# Smoke Test
bash smoke-test.sh
```

### 3.4 查看日志

```bash
docker compose logs -f api-server
docker compose logs -f agent-runtime
docker compose logs -f web-console
```

### 3.5 停止服务

```bash
docker compose down
```

---

## 4. 分步部署（开发/调试）

### 4.1 基础设施

```bash
docker compose up -d postgres redis
```

### 4.2 API Server

```bash
cd apps/api-server
pnpm install
pnpm dev
# 或生产模式：pnpm build && pnpm start
```

### 4.3 Agent Runtime

```bash
cd apps/agent-runtime
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4.4 Web Console

```bash
cd apps/web-console
pnpm install
pnpm dev
# 或生产模式：pnpm build && pnpm preview
```

---

## 5. 端口映射

| 服务 | 端口 | 说明 |
|------|------|------|
| Web Console | 5173 | 开发 / 80 (Docker) |
| API Server | 3001 | REST API |
| Agent Runtime | 8000 | Agent 执行引擎 |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 缓存/队列 |

---

## 6. 生产环境额外配置

### 6.1 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name agent.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name agent.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.2 HTTPS

建议使用 Let's Encrypt + certbot 自动管理证书。

### 6.3 防火墙

```bash
# 仅暴露必要端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# 如需直接访问（不推荐）：
# sudo ufw allow 3001/tcp
# sudo ufw allow 8000/tcp
```

### 6.4 资源限制

编辑 `docker-compose.yml` 添加资源限制：

```yaml
services:
  agent-runtime:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
```

---

## 7. 升级流程

### 7.1 滚动升级（推荐）

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 备份数据库（见 BACKUP_RESTORE.md）

# 3. 查看是否有新 migration
ls packages/db-schema/migrations/

# 4. 如有新 migration，先执行
# docker compose exec postgres psql -U agent -d agent_db -f /migrations/00X_xxx.sql

# 5. 重新构建并启动
docker compose down
docker compose up --build -d

# 6. 验证
bash smoke-test.sh
```

### 7.2 回滚

```bash
# 回滚到上一个镜像
docker compose down
docker image ls | grep enterprise-agent
# docker tag <old-image> enterprise-agent:latest
docker compose up -d
```

---

## 8. 故障排查

### 8.1 容器无法启动

```bash
docker compose logs <service>
docker compose ps
```

### 8.2 数据库连接失败

```bash
# 检查 PostgreSQL 健康状态
docker compose exec postgres pg_isready -U agent -d agent_db
# 检查 migration 是否执行
docker compose exec postgres psql -U agent -d agent_db -c "\\dt"
```

### 8.3 Provider 调用失败

```bash
curl http://localhost:8000/providers/health
curl http://localhost:8000/providers/stats
```

---

## 9. 验证清单

部署完成后，确认以下检查项：

- [ ] `docker compose ps` 所有服务状态为 `Up`
- [ ] `curl http://localhost:3001/health` 返回 `{"status":"ok"}`
- [ ] `curl http://localhost:8000/health` 返回 `{"status":"ok"}`
- [ ] 登录 `/api/auth/login` 成功返回 JWT
- [ ] `bash smoke-test.sh` 20 步全部通过
- [ ] Web Console 可以正常访问和登录
- [ ] Provider 页面显示健康状态
- [ ] 创建并执行测试任务成功

---

## 10. 云部署参考

### AWS ECS / EKS

- 使用 RDS PostgreSQL + ElastiCache Redis
- Agent Runtime 和 API Server 作为独立 Service
- Web Console 静态文件托管到 S3 + CloudFront

### 阿里云

- RDS PostgreSQL + Redis
- ECS 部署 Docker Compose
- SLB 负载均衡

### 腾讯云

- TDSQL-C PostgreSQL + Redis
- CVM 部署
- CLB 负载均衡
