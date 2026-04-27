# Backup & Restore Guide — Enterprise Agent v0.3.1

**Version**: v0.3.1
**Date**: 2026-04-27

---

## 1. 备份策略

### 1.1 备份范围

| 数据 | 位置 | 备份频率 | 保留周期 |
|------|------|---------|---------|
| PostgreSQL 数据库 | `postgres_data` volume | 每日 | 30 天 |
| Redis 数据 | `redis_data` volume | 每日 | 7 天 |
| 任务产物 | `shared/artifacts/` | 实时同步 | 90 天 |
| 配置文件 | `.env`, `docker-compose.yml` | 变更时 | 永久 |

### 1.2 自动备份脚本

创建 `scripts/backup.sh`：

```bash
#!/usr/bin/env bash
set -e

BACKUP_DIR="/backup/enterprise-agent/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "=== Enterprise Agent Backup ==="
echo "Backup dir: $BACKUP_DIR"

# PostgreSQL
echo "1. Backing up PostgreSQL..."
docker compose exec -T postgres pg_dump -U agent -d agent_db > "$BACKUP_DIR/agent_db.sql"

# Redis (if persistence enabled)
echo "2. Backing up Redis..."
docker compose exec -T redis redis-cli BGSAVE
sleep 2
docker cp "$(docker compose ps -q redis)":/data/dump.rdb "$BACKUP_DIR/redis.rdb"

# Artifacts
echo "3. Backing up artifacts..."
tar czf "$BACKUP_DIR/artifacts.tar.gz" shared/artifacts/

# Config
echo "4. Backing up config..."
cp .env "$BACKUP_DIR/env.backup"
cp docker-compose.yml "$BACKUP_DIR/docker-compose.yml.backup"

echo "5. Backup complete: $BACKUP_DIR"
echo "Size: $(du -sh $BACKUP_DIR | cut -f1)"
```

### 1.3 Cron 定时备份

```bash
# 每天凌晨 2 点执行备份
0 2 * * * /path/to/enterprise-agent/scripts/backup.sh >> /var/log/ea-backup.log 2>>1
```

---

## 2. 手动备份

### 2.1 PostgreSQL

```bash
# 导出整个数据库
docker compose exec postgres pg_dump -U agent -d agent_db > backup_$(date +%Y%m%d).sql

# 导出特定表
docker compose exec postgres pg_dump -U agent -d agent_db --table=tasks --table=task_events > backup_critical.sql

# 压缩备份
docker compose exec postgres pg_dump -U agent -d agent_db | gzip > backup_$(date +%Y%m%d).sql.gz
```

### 2.2 数据目录

```bash
# Docker volume 备份
docker run --rm -v enterprise-agent_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz -C /data .

# Artifacts 备份
tar czf artifacts_$(date +%Y%m%d).tar.gz shared/artifacts/
```

---

## 3. 恢复流程

### 3.1 完整恢复（灾难恢复）

```bash
# 1. 停止服务
docker compose down

# 2. 恢复 PostgreSQL 数据卷
# 如果有 volume 备份
docker volume rm enterprise-agent_postgres_data || true
docker volume create enterprise-agent_postgres_data
docker run --rm -v enterprise-agent_postgres_data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres_data_YYYYMMDD.tar.gz -C /data

# 或使用 SQL 备份
docker compose up -d postgres
sleep 5
docker compose exec -T postgres psql -U agent -d agent_db < backup_YYYYMMDD.sql

# 3. 恢复 Redis
docker cp backup_YYYYMMDD/redis.rdb "$(docker compose ps -q redis)":/data/dump.rdb

# 4. 恢复 Artifacts
tar xzf backup_YYYYMMDD/artifacts.tar.gz

# 5. 恢复配置
cp backup_YYYYMMDD/env.backup .env

# 6. 启动服务
docker compose up -d

# 7. 验证
bash smoke-test.sh
```

### 3.2 数据库恢复到新实例

```bash
# 1. 创建新数据库
docker compose exec postgres psql -U agent -c "CREATE DATABASE agent_db_new;"

# 2. 导入数据
docker compose exec -T postgres psql -U agent -d agent_db_new < backup_YYYYMMDD.sql

# 3. 切换连接字符串（修改 .env 中的 DATABASE_URL）
# 4. 重启服务
```

### 3.3 单表恢复

```bash
# 恢复特定表
docker compose exec -T postgres psql -U agent -d agent_db <<EOF
DROP TABLE IF EXISTS tasks CASCADE;
EOF
docker compose exec -T postgres pg_restore -U agent -d agent_db --table=tasks backup_file
```

---

## 4. Migration 管理

### 4.1 添加新 Migration

1. 创建新文件：`packages/db-schema/migrations/005_xxx.sql`
2. 使用 `IF NOT EXISTS` 保证幂等性
3. 包含 rollback 语句（注释形式）

```sql
-- Migration: 005_add_index.sql
-- Add index on task_events for faster replay queries

CREATE INDEX IF NOT EXISTS idx_task_events_task_id_sequence ON task_events(task_id, sequence);

-- Rollback:
-- DROP INDEX IF EXISTS idx_task_events_task_id_sequence;
```

### 4.2 执行 Migration

```bash
# 单条执行
docker compose exec postgres psql -U agent -d agent_db -f /migrations/005_xxx.sql

# 批量执行（所有未执行的 migration）
# 推荐维护一个 migration 记录表
```

### 4.3 Migration 失败回滚

```bash
# 1. 查看当前数据库状态
docker compose exec postgres psql -U agent -d agent_db -c "\\dt"

# 2. 如果有事务性 migration，自动回滚
# 注意：PostgreSQL DDL 默认在事务中

# 3. 手动回滚（根据 migration 文件中的 rollback 注释）
```

---

## 5. 数据保留策略

### 5.1 任务事件保留

```sql
-- 保留最近 90 天的任务事件
DELETE FROM task_events
WHERE created_at < NOW() - INTERVAL '90 days';

-- 保留最近 90 天的工具调用记录
DELETE FROM tool_calls
WHERE created_at < NOW() - INTERVAL '90 days';
```

### 5.2 记忆保留

```sql
-- 软删除（推荐）
UPDATE memories SET is_active = FALSE
WHERE created_at < NOW() - INTERVAL '365 days' AND is_active = TRUE;

-- 硬删除（谨慎）
-- DELETE FROM memories WHERE is_active = FALSE AND created_at < NOW() - INTERVAL '180 days';
```

### 5.3 产物保留

```bash
# 删除 90 天前的产物
find shared/artifacts/ -type f -mtime +90 -delete
```

---

## 6. 验证备份完整性

```bash
# 验证 SQL 备份
docker compose exec -T postgres psql -U agent -d agent_db -f backup.sql --set ON_ERROR_STOP=on -c "SELECT 1;"

# 验证压缩备份
gunzip -t backup.sql.gz

# 验证 artifacts 备份
tar tzf artifacts.tar.gz > /dev/null
```

---

## 7. 云备份方案

### AWS S3

```bash
# 安装 AWS CLI 并配置
aws s3 sync /backup/enterprise-agent/ s3://my-backup-bucket/enterprise-agent/ --delete
```

### 阿里云 OSS

```bash
ossutil cp -r /backup/enterprise-agent/ oss://my-bucket/enterprise-agent/
```

### 定时同步

```bash
# 每天备份后同步到云存储
0 3 * * * /path/to/scripts/backup.sh && aws s3 sync /backup/enterprise-agent/ s3://bucket/enterprise-agent/
```
