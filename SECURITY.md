# Security Policy — Enterprise Agent

## 支持的版本

| 版本 | 支持状态 |
|------|---------|
| v0.3.1 (RC) | 当前版本，接受安全报告 |
| < v0.3.0 | 不再支持 |

## 报告漏洞

如果你发现了安全漏洞，请通过以下方式私下报告：

1. 不要在公开的 Issue 或 Pull Request 中披露漏洞细节
2. 发送邮件至项目维护者（或在 GitHub Security Advisory 中提交）
3. 提供复现步骤、影响范围和建议修复方案

我们承诺在收到报告后 72 小时内确认，并在 14 天内提供修复计划或说明。

## 不要提交真实 Secret

**严禁**将以下任何内容提交到本仓库：

- API keys（OpenAI、Anthropic、Google、DeepSeek、SiliconFlow 等）
- GitHub / GitLab personal access tokens
- JWT secret、encryption key、database password
- Telegram bot token、Lark app secret
- Supabase service key / anon key
- 私钥、SSH key、OAuth client secret

提交前请执行：

```bash
# 确认没有 .env 被跟踪
git status

# 确认没有真实 secret 在代码中
grep -r "sk-" apps/ --include="*.py" --include="*.ts" --include="*.js"
grep -r "ghp_" apps/ --include="*.py" --include="*.ts" --include="*.js"
```

如果不小心提交了 secret：

1. **立即 rotate（撤销/轮换）该 key** — 不要只做 git revert
2. 如果已 push 到远程，需要重写 git history 或删除仓库后重建
3. 联系服务提供商确认该 key 的使用记录

## 生产部署安全建议

### 1. Secret 管理

| 配置项 | 开发占位符 | 生产要求 |
|--------|-----------|---------|
| JWT_SECRET | `change-this-to-a-random-string-at-least-32-chars` | 随机生成 ≥256-bit，存入 Vault |
| ENCRYPTION_KEY | `change-this-to-another-random-string-32-chars` | HashiCorp Vault / AWS KMS / 阿里云 KMS |
| 各 Provider API Key | `sk-...` 占位符 | Vault / Secret Manager |
| Database Password | `agent_secret` | 强密码 + 网络隔离 |

### 2. 密码存储

- **当前（MVP）**：PBKDF2（Node.js crypto，10000 轮，sha512）
- **生产要求**：bcrypt + salt，强制用户修改默认密码
- 默认开发密码 `admin123` **仅限本地 demo**，生产必须更换

### 3. Session 管理

- **当前**：localStorage 存储 JWT + localStorage XSS 风险
- **生产要求**：httpOnly + secure cookie + refresh token + CSRF 防护

### 4. 网络层

- 使用 HTTPS/TLS（Let's Encrypt / Cloudflare）
- Nginx 反向代理 + rate limit
- CORS 白名单（不要 `*`）
- 防火墙限制数据库端口（5432、6379）仅内网访问

### 5. 审计与监控

- 启用 `audit_logs` 表的全量记录
- 定期审查 `approvals` 表中异常审批
- Prometheus `/metrics` 接入告警系统（PagerDuty / OpsGenie）
- 日志聚合（ELK / Loki）+ 保留策略

### 6. 数据库安全

- PostgreSQL 使用 SSL 连接
- 独立数据库用户，最小权限原则
- 定期 `pg_dump` 备份，异地存储
- Redis 启用 AUTH + 网络隔离

### 7. 工具权限

- 生产环境高风险工具强制审批（已默认启用）
- MCP Server 默认不可信，白名单校验（已默认启用）
- Secret 传输自动脱敏（已默认启用）
- 无 rollback_plan 的高风险任务禁止执行（已默认启用）

## 已知安全限制（MVP）

| 限制 | 风险 | 缓解措施 |
|------|------|---------|
| PBKDF2 非 bcrypt | 密码破解 | 团队试运行可控，GA 前升级 |
| JWT 无 refresh token | 24h 后需重新登录 | 手动重新登录 |
| 无 rate limit | 可能被滥用 | Nginx 层限制 |
| 依赖漏洞未自动扫描 | 供应链风险 | 手动 `npm audit` / `pip audit` |
| CORS 开发模式较宽松 | CSRF | 生产收紧为白名单 |

## 安全事件响应

### Secret 泄露

1. 立即轮换泄露的 API key
2. 检查 `task_events` 和 `tool_calls` 中是否存在未脱敏的 secret
3. 更新 `SECRET_PATTERNS` 防止类似泄露
4. 审查 `audit_logs` 确认泄露范围

### 权限绕过

1. 检查 `approvals` 表中异常审批记录
2. 审查 `task_state_transitions` 中的状态变更
3. 回滚可疑任务：`POST /api/tasks/:id/rollback`

### 入侵响应

1. 立即撤销所有 JWT（更换 JWT_SECRET）
2. 检查 `audit_logs` 和 `task_events` 的异常模式
3. 隔离受影响的 Agent Runtime 实例
4. 从最近一次 clean 备份恢复数据
