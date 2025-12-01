# Docker 部署指南

本指南详细说明如何使用 Docker 部署 RadarFlow。

## 快速开始

### 1. 准备配置文件

```bash
# 复制配置示例
cp config/config.example.yaml config/config.yaml

# 复制环境变量示例
cp .env.example .env

# 编辑配置文件和环境变量
vim config/config.yaml
vim .env
```

### 2. 使用 docker-compose 启动（推荐）

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 镜像来源

### 使用 GitHub Container Registry（推荐）

项目每次推送到 main 分支或创建 tag 时，会自动构建并发布镜像到 GHCR。

```bash
# 拉取最新版本
docker pull ghcr.io/yourusername/radarflow:latest

# 拉取特定版本
docker pull ghcr.io/yourusername/radarflow:v1.0.0
```

### 本地构建

```bash
# 构建镜像
docker build -t radarflow:local .

# 使用本地镜像
docker run -d \
  --name radarflow \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/state:/app/state \
  radarflow:local
```

## 环境变量配置

优先级：环境变量 > config.yaml > 默认值

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | `sk-xxx` |
| `ARK_API_KEY` | 火山引擎 API Key | `xxx` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | `123:abc` |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | `-100xxx` |
| `WEWORK_WEBHOOK` | 企业微信 Webhook | `https://...` |
| `FEISHU_WEBHOOK` | 飞书 Webhook | `https://...` |
| `DINGTALK_WEBHOOK` | 钉钉 Webhook | `https://...` |
| `EMAIL_PASSWORD` | 邮箱密码 | `xxx` |

## 数据持久化

容器内有两个重要目录：

- `/app/config` - 配置文件目录
- `/app/state` - 数据库和状态文件

**必须**挂载这两个目录到宿主机：

```yaml
volumes:
  - ./config:/app/config:ro     # 只读
  - ./state:/app/state           # 读写
```

## 日志查看

```bash
# 实时查看日志
docker-compose logs -f

# 查看最近 100 行
docker-compose logs --tail=100

# 只查看特定服务
docker-compose logs -f radarflow
```

## 资源限制

在 `docker-compose.yml` 中已配置默认限制：

- CPU: 最大 1 核心
- 内存: 最大 1GB

根据实际需求调整：

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
```

## 健康检查

容器包含健康检查机制：

```bash
# 查看容器健康状态
docker inspect --format='{{.State.Health.Status}}' radarflow

# 查看健康检查日志
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' radarflow
```

## 更新镜像

```bash
# 拉取最新镜像
docker-compose pull

# 重启服务
docker-compose up -d

# 清理旧镜像
docker image prune
```

## 常见问题

### 1. 配置文件找不到

确保已复制并编辑配置文件：

```bash
ls config/config.yaml
# 如果不存在，执行：
cp config/config.example.yaml config/config.yaml
```

### 2. 数据库权限问题

```bash
# 创建 state 目录并设置权限
mkdir -p state
chmod 755 state
```

### 3. 时区不正确

在 `.env` 中设置：

```bash
TZ=Asia/Shanghai
```

### 4. 容器启动后立即退出

查看日志：

```bash
docker-compose logs
```

常见原因：
- 配置文件语法错误
- API Key 未设置
- 端口冲突

## 多实例部署

如需运行多个实例（如测试环境 + 生产环境）：

```bash
# 创建不同的配置目录
mkdir -p config-prod config-test

# 使用不同的 compose 文件
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.test.yml up -d
```

## 备份与恢复

### 备份

```bash
# 备份配置和数据
tar -czf radarflow-backup-$(date +%Y%m%d).tar.gz \
  config/ state/
```

### 恢复

```bash
# 解压备份
tar -xzf radarflow-backup-20250101.tar.gz

# 重启容器
docker-compose restart
```

## 监控

### 查看资源使用

```bash
docker stats radarflow
```

### 导出日志

```bash
docker-compose logs > radarflow.log
```

## 卸载

```bash
# 停止并删除容器
docker-compose down

# 删除镜像
docker rmi ghcr.io/yourusername/radarflow:latest

# 删除数据（谨慎！）
rm -rf state/
```
