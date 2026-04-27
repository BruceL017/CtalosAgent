# Contributing Guide — Enterprise Agent

感谢你对 Enterprise Agent 的兴趣。本项目采用 MIT 许可证，欢迎 Issue 和 Pull Request。

## 开发环境

### 前置条件

- Node.js ≥ 20.0.0
- pnpm ≥ 8.0.0
- Python ≥ 3.11.0
- Docker + Docker Compose
- PostgreSQL 16 client (可选，用于本地调试)

### 初始化

```bash
# 克隆仓库
git clone <repo-url>
cd enterprise-agent

# 安装依赖
pnpm install

# 配置环境
cp .env.example .env
# 编辑 .env — 本地开发无需真实 API key，mock provider 可工作

# 启动基础设施
docker compose up -d postgres redis

# 执行数据库迁移
pnpm run db:migrate
```

### 启动服务

```bash
# 方式 1：分别启动（推荐开发）
pnpm run dev:infra   # postgres + redis
pnpm run dev:api     # API Server @ :3001
pnpm run dev:agent   # Agent Runtime @ :8000
pnpm run dev:web     # Web Console @ :5173

# 方式 2：全部并行（需要较强机器）
pnpm run dev
```

## 代码规范

### TypeScript / Node.js

- 使用 strict TypeScript 配置
- 优先 `async/await`，避免回调地狱
- 所有路由需要类型定义
- API 返回统一格式：`{ success: boolean, data?: T, error?: string }`

### Python

- PEP 8 风格，4 空格缩进
- 类型注解（`from typing import`）
- 异步函数使用 `async def`
- 数据库操作使用参数化查询（`$1` / `%s`）

### 通用

- 不要提交 `.env`、日志、build 产物
- 新增依赖时同时更新 `package.json` / `requirements.txt`
- 敏感信息（API key、password）只能出现在 `.env` 和环境变量中

## 测试

```bash
# 全部测试
pnpm run test

# Python 单元测试（mock，无需 API key）
pnpm run test:python

# API Server 测试
pnpm run test:api

# Web Console 编译检查
pnpm run test:web

# 真实 Provider 测试（需要 API key）
pnpm run test:real

# Smoke test（需要服务已启动）
pnpm run smoke
```

**测试要求**：
- 新增功能必须附带测试
- 修改现有功能需确保相关测试通过
- 真实 API 测试标记为 `pytest.mark.skipif`（无 key 时自动跳过）

## 提交规范

```
type(scope): description

body (optional)

type 类型：
- feat: 新功能
- fix: Bug 修复
- docs: 文档更新
- test: 测试相关
- refactor: 重构（无行为变更）
- chore: 构建/工具链
- security: 安全修复

示例：
feat(provider): add Gemini 1.5 Pro support
fix(auth): validate JWT exp before signature
docs(readme): update deployment instructions
```

## 提交前检查清单

- [ ] `pnpm run test` 全部通过
- [ ] `pnpm run build` 成功
- [ ] `docker compose config` 无错误
- [ ] 代码中无真实 secret（运行 `grep -r "sk-" apps/` 确认）
- [ ] `.env.example` 已更新（如新增环境变量）
- [ ] 文档已更新（README / DEPLOYMENT / RUNBOOK）

## 模块说明

| 目录 | 用途 | 技术 |
|------|------|------|
| `apps/web-console` | Web 前端 | React 18 + Vite + TypeScript |
| `apps/api-server` | API 网关 | Fastify + Node.js + pg |
| `apps/agent-runtime` | Agent 核心 | Python 3.11 + FastAPI + asyncpg |
| `apps/cli` | 命令行工具 | Node.js + Commander |
| `packages/shared-types` | 类型定义 | TypeScript |
| `packages/db-schema` | 数据库迁移 | SQL |

## 沟通

- 功能建议：开 Issue，使用 `enhancement` 标签
- Bug 报告：开 Issue，提供复现步骤和环境信息
- 安全漏洞：参见 [SECURITY.md](SECURITY.md)，**不要**开公开 Issue
