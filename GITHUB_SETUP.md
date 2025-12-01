# GitHub 仓库配置指南

## 必须配置的权限

### 1. 启用 GitHub Actions 写入权限

这是**最重要**的一步，否则 Actions 无法推送镜像！

**步骤：**

1. 进入你的 GitHub 仓库
2. 点击 **Settings**（设置）
3. 左侧菜单找到 **Actions** → **General**
4. 滚动到底部找到 **Workflow permissions**
5. 选择 **Read and write permissions** ✅
6. 勾选 **Allow GitHub Actions to create and approve pull requests** ✅
7. 点击 **Save** 保存

**截图路径：**
```
Settings → Actions → General → Workflow permissions
```

**为什么需要：**
- 允许 GitHub Actions 推送 Docker 镜像到 GHCR
- 允许 Actions 创建 releases 和 tags

---

### 2. 确认 Actions 已启用

**步骤：**

1. 在仓库主页，点击 **Settings**
2. 左侧菜单点击 **Actions** → **General**
3. 在 **Actions permissions** 部分
4. 选择 **Allow all actions and reusable workflows** ✅
5. 点击 **Save**

---

### 3. 设置 Package 为公开（可选但推荐）

首次推送后，镜像默认是私有的。要让其他人使用：

**步骤：**

1. 推送代码后，等待 Actions 构建完成
2. 进入你的 GitHub 个人主页
3. 点击顶部的 **Packages** 标签
4. 找到 `radarflow` 包，点击进入
5. 点击右侧的 **Package settings**
6. 滚动到底部 **Danger Zone**
7. 点击 **Change visibility**
8. 选择 **Public**
9. 输入仓库名称确认

**或者通过仓库设置：**
```
仓库页面 → Packages (右侧边栏) → radarflow → Package settings
```

---

## 验证配置是否正确

### 方法 1：检查 Actions 权限

```bash
# 提交一个测试文件
echo "test" > test.txt
git add test.txt
git commit -m "test: verify actions permissions"
git push origin main
```

然后访问：
```
https://github.com/你的用户名/RadarFlow/actions
```

- ✅ 如果构建成功 = 权限配置正确
- ❌ 如果提示权限错误 = 需要配置写入权限

### 方法 2：查看 Actions 日志

1. 进入 Actions 标签
2. 点击最新的 workflow run
3. 查看 "Build and push Docker image" 步骤
4. 如果看到 `push: true` 成功执行 = 配置正确

---

## 常见错误和解决方案

### ❌ 错误 1：`permission denied while trying to connect to the Docker daemon socket`

**原因：** Actions 没有 Docker 权限（这个一般不会出现，GitHub Actions 默认有）

**解决：** 无需处理，这是正常的

---

### ❌ 错误 2：`denied: permission_denied: write_package`

**原因：** Workflow permissions 设置为 Read-only

**解决：**
```
Settings → Actions → General → Workflow permissions
→ 选择 "Read and write permissions"
```

---

### ❌ 错误 3：镜像构建成功但无法拉取

**原因：** Package 是私有的

**解决：** 参考上面"设置 Package 为公开"

---

### ❌ 错误 4：Actions 标签页不显示

**原因：** Actions 可能被禁用

**解决：**
```
Settings → Actions → General → Actions permissions
→ 选择 "Allow all actions and reusable workflows"
```

---

## 推送后的检查清单

- [ ] 代码已推送到 GitHub
- [ ] Actions 工作流已触发（绿色勾 ✅）
- [ ] Packages 中可以看到镜像
- [ ] 镜像已设置为 Public
- [ ] 可以成功拉取镜像

---

## 快速检查命令

```bash
# 1. 推送代码
git push origin main

# 2. 等待 5-10 分钟后，测试拉取
docker pull ghcr.io/你的用户名/radarflow:latest

# 3. 如果成功 = 一切正常 ✅
```

---

## 完整配置流程总结

### 第一步：配置仓库权限（推送前）

1. Settings → Actions → General
2. Workflow permissions → Read and write permissions ✅
3. Actions permissions → Allow all actions ✅

### 第二步：推送代码

```bash
git add .
git commit -m "feat: add Docker support"
git push origin main
```

### 第三步：等待构建

访问 `https://github.com/你的用户名/RadarFlow/actions`

### 第四步：设置镜像公开

1. 进入 Packages
2. 点击 radarflow
3. Package settings → Change visibility → Public

### 第五步：测试

```bash
docker pull ghcr.io/你的用户名/radarflow:latest
```

---

## 需要帮助？

如果遇到问题：

1. 查看 Actions 日志：`仓库 → Actions → 点击 workflow run`
2. 检查权限设置：`Settings → Actions → General`
3. 确认 Package 可见性：`个人主页 → Packages`

---

**配置完成后，你的 CI/CD 就可以正常工作了！** 🎉
