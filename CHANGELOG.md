# Changelog

## v0.3.1 (2026-04-27)

### Added
- Web Console Auth 集成：Login 页面、JWT Bearer Token 注入、zustand auth store
- ProviderConfig 监控面板：health badge、latency、requests、tokens、errors metrics overview
- 跨进程恢复测试套件：`test_cross_process_resume.py`（3 个测试全部通过）
- GitHub 真实适配器测试：`test_github_real.py`（3 个只读测试全部通过）
- 根目录统一脚本：`npm run test`、`npm run test:real`、`npm run smoke`、`npm run build`
- 交付文档：RELEASE_NOTES、CHANGELOG、RUNBOOK、DEPLOYMENT、BACKUP_RESTORE、SECURITY_REVIEW、UAT_REPORT

### Fixed
- smoke-test.sh 更新至 v0.3.1，包含 JWT auth 登录流程
- EventLogger sequence cache 在跨进程时从 DB 重新加载，避免 duplicate key
- .env.example 补全 TELEGRAM_BOT_TOKEN、USE_REAL_ADAPTERS、ARTIFACTS_DIR
- 版本号统一：API Server、Agent Runtime、Web Console 全部对齐 v0.3.x

### Security
- 所有 API 调用（除 /health、/api/auth/login）受 Bearer Token 保护
- Secret redaction 覆盖 API key、GitHub token、GitLab token、JWT、Bearer、password、token、secret
- AES-256-GCM 加密 at rest（MVP 级别，生产应使用 Vault/KMS）
- 生产环境删除/合并/部署操作强制审批
- 无回滚能力的高风险操作强制审批
- MCP Server 默认不可信，需显式注册能力和权限

## v0.3.0 (2026-04-26)

### Added
- Embedding 服务：SiliconFlow 真实 embedding + Mock fallback，pgvector 存储
- AES-256-GCM Secret 加密：`utils/encryption.py`
- JWT Auth：HMAC-SHA256，RBAC 角色（admin/operator/viewer）
- 结构化日志：`utils/structured_logger.py`，JSON 格式，含 trace_id/task_id/session_id
- Prometheus Metrics：`/metrics` 端点，Counter + Histogram
- MCP Gateway 权限硬化：trusted 标志、capabilities 白名单、risk_level 映射、生产审批
- Web Console：ProviderConfig、MCPServers、Sessions、TaskReplay、Audit 页面

### Fixed
- Docker Compose 配置：传递 embedding、JWT、encryption 环境变量
- TypeScript 编译：API Server `tsc --noEmit` 通过

## v0.2.0 (2026-04-25)

### Added
- 完整状态机：pending → planning → awaiting_approval → approved → running → completed/failed/cancelled/rolled_back
- Workflow Engine：plan generation、step execution、state persistence
- TaskExecutor：memory/skill/rollback/eval post-processing
- 审批流：plan approval、tool approval、approval record DB 持久化
- 跨进程恢复：workflow_states DB 表、_pending_plans 内存缓存
- Rollback Service：compensation rollback、dry-run
- Replay：task event replay、timeline
- Subagent Manager：multi-perspective analysis
- Policy Engine：risk-based permission、environment escalation
- Event Logger：append-only structured events、sequence ordering

## v0.1.0 (2026-04-24)

### Added
- 项目初始化：monorepo、PostgreSQL schema、Tool Registry
- Web Console：Dashboard、TaskCreate、TaskDetail、MemoryManager、SkillManager
- API Server：Fastify、tasks、events、skills、memories endpoints
- Agent Runtime：FastAPI、Provider Router、Mock adapters
- 基础集成：GitHub、Supabase、Lark、Telegram、MCP Gateway mock
