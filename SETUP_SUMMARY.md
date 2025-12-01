# 🎉 GitHub Actions + Docker 自动化部署设置完成

## ✅ 已完成的配置

### 1. Docker 相关文件

- ✅ `Dockerfile` - 优化的 Docker 镜像构建文件
  - 多阶段构建优化
  - 时区配置（Asia/Shanghai）
  - 健康检查
  - 标签元数据

- ✅ `.dockerignore` - Docker 构建忽略文件
  - 排除测试、文档、配置敏感文件
  - 减小镜像体积

- ✅ `docker-compose.yml` - Docker Compose 配置
  - 环境变量支持
  - 卷挂载配置
  - 资源限制
  - 健康检查
  - 日志轮转

- ✅ `.env.example` - 环境变量模板
  - 所有必需的环境变量
  - 详细注释说明

### 2. GitHub Actions 工作流

- ✅ `.github/workflows/docker-publish.yml`
  - 自动构建多架构镜像（amd64/arm64）
  - 自动发布到 GitHub Container Registry
  - 缓存优化加速构建
  - 版本标签管理

### 3. 文档

- ✅ `DOCKER.md` - Docker 部署详细指南
- ✅ `SETUP_SUMMARY.md` - 本文件
- ✅ `README.md` - 更新了 Docker 相关说明

## 🚀 如何使用

### 首次设置

1. **推送代码到 GitHub**
   ```bash
   git add .
   git commit -m "Add Docker and GitHub Actions support"
   git push origin main
   ```

2. **GitHub Actions 自动构建**
   - 推送后，GitHub Actions 会自动触发
   - 访问 https://github.com/yourusername/RadarFlow/actions 查看构建进度
   - 构建完成后，镜像会发布到 GHCR

3. **使其他人可以拉取镜像**

   在 GitHub 仓库设置中：
   - 进入 Settings > Packages
   - 找到 radarflow 包
   - 点击 "Package settings"
   - 选择 "Change visibility" → "Public"

### 使用镜像

**方式 1：docker-compose（推荐）**

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/RadarFlow.git
cd RadarFlow

# 2. 配置环境
cp config/config.example.yaml config/config.yaml
cp .env.example .env
vim .env  # 填入真实 API Key

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

**方式 2：直接使用 docker run**

```bash
docker run -d \
  --name radarflow \
  --restart unless-stopped \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/state:/app/state \
  -e OPENAI_API_KEY="sk-xxx" \
  -e TELEGRAM_BOT_TOKEN="xxx" \
  ghcr.io/yourusername/radarflow:latest
```

## 📦 镜像版本管理

### 自动触发构建

1. **推送到 main 分支** → 构建 `main` 和 `latest` 标签
   ```bash
   git push origin main
   ```

2. **创建版本标签** → 构建版本号标签
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   # 会生成: v1.0.0, v1.0, v1, latest
   ```

3. **手动触发** → 在 GitHub Actions 页面点击 "Run workflow"

### 镜像标签说明

| 标签 | 何时构建 | 用途 |
|------|---------|------|
| `latest` | 每次推送 main | 生产环境稳定版 |
| `main` | 每次推送 main | 跟踪主分支 |
| `v1.0.0` | 创建 tag v1.0.0 | 固定版本 |
| `v1.0` | 创建 tag v1.0.x | 次版本号 |
| `v1` | 创建 tag v1.x.x | 主版本号 |

## 🔒 敏感信息保护

已确保以下文件不会被提交到 Git：

- ✅ `config/config.yaml` - 本地配置（含 API Key）
- ✅ `config/config-豆包.yaml` - 豆包配置
- ✅ `.env` - 环境变量文件
- ✅ `state/` - 数据库文件

仅提交示例文件：
- ✅ `config/config.example.yaml`
- ✅ `.env.example`

## 📝 下一步操作

### 1. 更新 README 中的用户名

将 README.md 和相关文件中的 `yourusername` 替换为你的 GitHub 用户名：

```bash
# 例如你的用户名是 bobsmith
find . -type f -name "*.md" -o -name "*.yml" | xargs sed -i 's/yourusername/bobsmith/g'
```

或手动修改：
- `README.md`
- `Dockerfile`
- `docker-compose.yml`
- `DOCKER.md`

### 2. 创建第一个版本

```bash
# 提交所有更改
git add .
git commit -m "feat: add Docker and CI/CD support"
git push origin main

# 创建第一个版本标签
git tag v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

### 3. 设置镜像为公开

1. 访问 https://github.com/yourusername?tab=packages
2. 点击 `radarflow` 包
3. Settings → Change visibility → Public

### 4. 测试镜像

```bash
# 在另一台机器上测试拉取
docker pull ghcr.io/yourusername/radarflow:latest
```

## 🎯 工作流说明

### GitHub Actions 做了什么？

1. **代码检出** - 拉取最新代码
2. **设置 Docker Buildx** - 支持多架构构建
3. **登录 GHCR** - 使用 GitHub Token 自动登录
4. **提取元数据** - 生成镜像标签和标签
5. **构建和推送** - 构建镜像并推送到 GHCR
6. **缓存** - 使用 GitHub Actions Cache 加速构建

### 构建时间

- 首次构建：约 5-10 分钟
- 后续构建（有缓存）：约 2-3 分钟

### 支持的平台

- ✅ `linux/amd64` (x86_64)
- ✅ `linux/arm64` (ARM64/Apple Silicon)

## 🛠️ 故障排查

### Actions 构建失败

查看错误日志：
1. 进入 GitHub 仓库
2. 点击 "Actions" 标签
3. 点击失败的 workflow run
4. 查看详细日志

常见问题：
- **权限错误** → 确保启用了 "Read and write permissions" in Settings > Actions > General
- **Dockerfile 语法错误** → 本地测试 `docker build .`
- **依赖安装失败** → 检查 requirements.txt

### 镜像拉取失败

```bash
# 确认镜像是否存在
docker pull ghcr.io/yourusername/radarflow:latest

# 如果需要登录（私有镜像）
echo $GITHUB_TOKEN | docker login ghcr.io -u yourusername --password-stdin
```

## 📚 相关链接

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [GitHub Container Registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Dockerfile 最佳实践](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)

## ✨ 特性亮点

- 🚀 **自动化部署** - 推送代码即自动构建发布
- 🔄 **多架构支持** - x86_64 和 ARM64
- 📦 **版本管理** - 语义化版本标签
- 💾 **构建缓存** - 加速后续构建
- 🔒 **安全** - 使用 GitHub Token，无需额外配置
- 📝 **完整文档** - 详细的使用和部署指南

---

**恭喜！🎉 你的项目现在具备了生产级的 Docker 化和 CI/CD 能力！**
