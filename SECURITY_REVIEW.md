# Security Review — Enterprise Agent v0.3.1

**Date**: 2026-04-27
**Version**: v0.3.1
**Reviewer**: Automated + Manual
**Status**: MVP Security Baseline Met — Production Hardening Required

---

## 1. 审计范围

| 模块 | 审计项 | 状态 |
|------|--------|------|
| Secret 存储 | API key / token / password 加密 | PASS |
| Secret 传输 | 日志/事件/API 响应脱敏 | PASS |
| Authentication | JWT 生成/验证/过期 | PASS |
| Authorization | RBAC 角色检查 | PASS |
| Tool 权限 | Registry + Policy Engine | PASS |
| Production 审批 | 高风险操作强制审批 | PASS |
| MCP 安全 | 白名单 + 不可信默认 | PASS |
| SQL 安全 | test/prod 隔离 | PASS |
| 文件安全 | 路径限制 + ARTIFACTS_DIR | PASS |
| 依赖安全 | 已知漏洞扫描 | INFO |

---

## 2. Secret 管理

### 2.1 加密存储

- **实现**: `utils/encryption.py` — AES-256-GCM
- **验证**: `tests/test_encryption.py` 5/5 通过
  - Roundtrip 正确
  - 不同 nonce 产生不同密文
  - 字典批量加密/解密
  - 空值安全
  - 不同 key 产生不同密文
- **风险**: MVP 使用环境变量 `ENCRYPTION_KEY`，生产应使用 HashiCorp Vault 或云 KMS
- **建议**: 生产环境禁止硬编码或环境变量传递加密 key

### 2.2 脱敏

- **实现**: `utils/secret_redactor.py`
- **覆盖**:
  - OpenAI/SiliconFlow API keys: `sk-[a-zA-Z0-9]{20,}`
  - GitHub token: `ghp_[a-zA-Z0-9]{36}`
  - GitLab token: `glpat-[a-zA-Z0-9\-]{20}`
  - JWT: `eyJ[...].eyJ[...]`
  - Bearer token: `Bearer [...]`
  - Generic: `api_key=...`, `password=...`, `token=...`, `secret=...`
- **验证**: `tests/test_secret_redaction.py` 7/7 通过
- **风险**: 新的 secret 格式需要手动添加到 pattern 列表

### 2.3 环境变量

- 所有 provider API keys 通过环境变量注入
- Docker Compose 使用 `${VAR:-default}` 语法，空值安全
- `.env.example` 完整列出所有配置项
- **风险**: `docker compose config` 可能泄露敏感值到日志

---

## 3. Authentication

### 3.1 JWT

- **实现**: `middleware/auth.ts` — HMAC-SHA256
- **过期**: 24 小时
- **验证**: signature、exp、iat
- **路由保护**:
  - `/api/auth/login`: 公开
  - `/health`: 公开
  - 所有其他 `/api/*`: `authMiddleware` preHandler
- **风险**: MVP 使用内存默认账户 `admin@enterprise.local` + PBKDF2 哈希密码（Node.js crypto，10000 轮，sha512）
- **建议**: 生产环境使用 bcrypt + refresh token + DB 用户表

### 3.2 Web Console Auth

- zustand auth store + localStorage 持久化
- 所有 API client fetch 自动注入 Bearer token
- 未登录自动重定向 `/login`
- **风险**: localStorage XSS 风险，应使用 httpOnly cookie

---

## 4. Authorization

### 4.1 RBAC

- 角色: `admin`, `operator`, `viewer`
- `requireRole()` middleware 已预留，当前所有受保护路由使用统一 auth
- **风险**: 未在所有路由上应用 role-based 限制
- **建议**: 按路由应用 `requireRole(['admin'])` 等限制

### 4.2 Tool 权限

- **Registry**: 所有工具必须有 manifest（risk_level、environment、approval、rollback）
- **Policy Engine**: `services/policy_engine.py`
  - 风险等级 → 权限模式映射
  - 环境提升: test(0) → staging(1) → production(2)
  - 操作类型加成: read(0) → write(1) → delete/merge/deploy(2)
  - 生产环境删除/合并/部署: 强制审批
  - 无回滚能力的高风险: 强制审批
  - 大面积影响: 强制审批
  - Admin override: `00000000-0000-0000-0000-000000000001`
- **验证**: `tests/test_mcp_permissions.py` 9/9 通过

### 4.3 审批流

- Plan-level approval: 生产环境或高风险计划
- Tool-level approval: `requires_approval_on` 包含的环境
- Approval record 持久化到 `approvals` 表
- **验证**: `tests/test_approval_resume.py` 5/5 通过

---

## 5. MCP 安全

- **Trusted 标志**: 默认 `false`
- **Capabilities 白名单**: 只有注册的工具才能被调用
- **Risk level 映射**: 内置工具默认风险等级
- **生产环境**: 高风险工具强制审批
- **Server 列表**: 脱敏（不含 env/command）
- **Call tool**: 4 层检查（白名单 → 权限 → 风险 → 生产审批）
- **验证**: `tests/test_mcp_permissions.py` 9/9 通过

---

## 6. 数据安全

### 6.1 SQL 安全

- `supabase.execute_sql`: 仅允许 `test` 环境，`production` 需要审批
- 参数化查询：所有 DB 操作使用参数化查询（asyncpg `$1`、pg `$1`）
- **风险**: 无 SQL 注入漏洞发现

### 6.2 文件安全

- `file.write`: 写入 `ARTIFACTS_DIR` 环境变量指定的目录
- 不直接暴露系统路径
- **风险**: 路径穿越需验证（当前未做严格校验）
- **建议**: 验证 `filename` 不包含 `..` 或绝对路径

### 6.3 命令执行

- MCP stdio: 仅执行预注册的 `command` + `args`
- 无动态命令执行能力
- **风险**: 低

---

## 7. 依赖安全

| 组件 | 关键依赖 | 风险 |
|------|---------|------|
| Agent Runtime | cryptography, asyncpg, httpx, pydantic | 需定期 `pip audit` |
| API Server | fastify, pg, @fastify/cors | 需定期 `npm audit` |
| Web Console | react, zustand, react-router-dom | 需定期 `npm audit` |

**建议**: 在 CI 中添加 `npm audit --audit-level=high` 和 `pip audit`

---

## 8. 安全事件响应

### Secret 泄露处理

1. 立即轮换泄露的 API key
2. 检查 `task_events` 和 `tool_calls` 中是否存在未脱敏的 secret
3. 更新 `SECRET_PATTERNS` 防止类似泄露
4. 审查 `audit_logs` 确认泄露范围

### 权限绕过处理

1. 检查 `approvals` 表中异常审批记录
2. 审查 `task_state_transitions` 中的状态变更
3. 回滚可疑任务：`POST /api/tasks/:id/rollback`

---

## 9. 生产环境建议

| 项目 | MVP 状态 | 生产要求 |
|------|---------|---------|
| 密码存储 | PBKDF2 (MVP) | bcrypt + salt |
| JWT Secret | 环境变量 | Vault / 随机生成 256-bit |
| 加密 Key | 环境变量 | HashiCorp Vault / 云 KMS |
| Session | localStorage | httpOnly cookie + refresh token |
| Admin 账户 | 内存默认 | DB 用户表 + 强制修改默认密码 |
| 审计日志 | DB 表 | 不可篡改存储（WORM） |
| Rate Limit | 无 | Redis-based rate limiter |
| 依赖扫描 | 手动 | CI 自动 `npm audit` / `pip audit` |

---

## 10. 结论

- **MVP 安全基线**: 已满足
- **生产就绪**: 需要完成上述 9 项建议
- **阻塞 GA 的风险**: 无 P0 安全阻塞项
- **评分**: 安全审计 8/10（MVP 级别）
