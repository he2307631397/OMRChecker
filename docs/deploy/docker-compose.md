# Docker Compose 部署

这是 Linux 生产环境的推荐部署方式。项目根目录已有 `Dockerfile`、`docker-compose.yml`、`.dockerignore` 和 `.env.example`。

## 1. 安装 Docker Engine 和 Compose

优先按照 Docker 官方仓库安装，不要混用发行版旧版 `docker.io` 与 Docker 官方包。以下以 Ubuntu/Debian 为例：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

若当前账号需要无 `sudo` 操作 Docker：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

> `docker` 用户组近似 root 权限。安全要求较高的服务器可继续使用 `sudo docker ...`，无需加入用户组。RHEL、Rocky Linux 等系统请使用 Docker 官方对应发行版安装步骤。

## 2. 获取代码并创建目录

```bash
sudo mkdir -p /opt/omrchecker
sudo chown "$USER":"$USER" /opt/omrchecker
git clone <项目仓库地址> /opt/omrchecker
cd /opt/omrchecker

mkdir -p service_data inputs config
cp .env.example .env
cp config/robyn-service.example.json config/robyn-service.json
chmod 600 .env config/robyn-service.json
```

如果由发布包部署，解压后进入包含 `docker-compose.yml` 的项目根目录执行后续命令。

## 3. 准备模板

把经过验证的模板复制到宿主机 `inputs/`。Compose 以只读方式挂载该目录：

```text
inputs/
├── template.json
├── config.json
└── reference.png 或模板引用的其他图片
```

项目也可能按业务模板编码从 `config/` 读取模板目录。不要删除原有 `config/` 内容，只新增或更新对应模板目录。

部署前检查：

```bash
test -r inputs/template.json
test -r inputs/config.json
```

## 4. 配置服务

编辑 `.env`：

```dotenv
# 宿主机暴露端口。容器内始终监听 8080。
OMR_SERVICE_PORT=8080

# 不需要默认回调时留空。
OMR_CALLBACK_URL=https://business.example.com/api/omr/callback

# 仅在启用腾讯 COS 时填写。
COS_SECRET_ID=replace_me
COS_SECRET_KEY=replace_me

# 生产环境保持 false，排障时短期开启。
OMR_RECOGNITION_DEBUG_ARTIFACTS=false
```

编辑 `config/robyn-service.json`。真实 COS 示例：

```json
{
  "server": {
    "port": 8080,
    "workers": 4
  },
  "storage": {
    "serviceDataDir": "/app/service_data",
    "templateDir": "/app/inputs",
    "archivePrefix": "omr-archive"
  },
  "database": {
    "url": "sqlite:////app/service_data/omr_service.db"
  },
  "cos": {
    "enabled": true,
    "region": "ap-guangzhou",
    "bucket": "example-bucket-1250000000",
    "secretId": "${COS_SECRET_ID}",
    "secretKey": "${COS_SECRET_KEY}"
  },
  "callback": {
    "url": "https://business.example.com/api/omr/callback",
    "maxAttempts": 3,
    "timeoutSeconds": 10
  },
  "recognition": {
    "debugArtifacts": false
  }
}
```

配置注意事项：

- Bucket 必须是完整名称，通常包含 APPID，例如 `name-1250000000`。
- 腾讯 COS Python SDK 已列入 `requirements.txt`，镜像构建时会安装。
- 不使用 COS 时将 `cos.enabled` 改为 `false`，并增加 `"localRoot": "/app/service_data/cos_mock"`。批量接口此时从该目录模拟下载和上传对象。
- `.env` 中非空 `OMR_CALLBACK_URL` 会覆盖 JSON 的 `callback.url`。空值不会覆盖 JSON。若不使用回调，应在 JSON 中删除该 URL 或设为 `null`，同时保持 `.env` 为空。
- Compose 会用环境变量把数据和模板目录固定为 `/app/service_data`、`/app/inputs`。

检查 Compose 最终配置。输出中可能包含密钥，不要将结果粘贴到工单或日志平台：

```bash
docker compose config --quiet
```

## 5. 构建并启动

```bash
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 omr-service
```

首次构建需要从 Debian 和 PyPI 下载依赖。网络受限环境应配置 Docker Registry 和 pip 镜像，或在联网环境构建后通过私有镜像仓库/离线 tar 包分发。

等待健康状态变为 `healthy`：

```bash
docker inspect --format '{{.State.Health.Status}}' omrchecker-robyn
curl --fail --show-error http://127.0.0.1:${OMR_SERVICE_PORT:-8080}/health
```

预期响应类似：

```json
{"status":"ok","service":"omrchecker-robyn","workers":4,"template_dir":"/app/inputs"}
```

## 6. 最小业务验证

健康检查只证明进程正常。还应使用一份已知答案的样例执行端到端识别，并核对结果。

单文件上传示例：

```bash
curl --fail --show-error -X POST \
  http://127.0.0.1:${OMR_SERVICE_PORT:-8080}/api/omr/tasks \
  -F 'sheet.pdf=@/absolute/path/to/test-sheet.pdf'
```

记录返回的 `task_id`，然后查询：

```bash
curl --fail --show-error \
  http://127.0.0.1:${OMR_SERVICE_PORT:-8080}/api/omr/tasks/<task_id>
```

COS 批量接口的请求格式和本地模拟 COS 验证方式见 [API 文档](../robyn-web-service.md)。

## 7. 网络与反向代理

仅供内网调用时，用防火墙限制来源 IP。公网部署不要直接暴露 Robyn，建议使用 Nginx/Caddy 提供 TLS、请求体限制和访问日志。

如果 Nginx 与容器位于同一主机，可把 Compose 端口限制在回环地址。将 `docker-compose.yml` 的端口映射改为：

```yaml
ports:
  - "127.0.0.1:${OMR_SERVICE_PORT:-8080}:8080"
```

Nginx 站点示例：

```nginx
server {
    listen 443 ssl http2;
    server_name omr.example.com;

    ssl_certificate     /etc/letsencrypt/live/omr.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/omr.example.com/privkey.pem;

    client_max_body_size 100m;
    proxy_connect_timeout 10s;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

上传大小和超时应按实际 PDF 大小、识别耗时调整。TLS 证书申请和续期应由现有基础设施统一管理。

## 8. 日常操作

```bash
# 查看状态和资源
docker compose ps
docker stats omrchecker-robyn

# 跟踪日志
docker compose logs -f --tail=200 omr-service

# 重启
docker compose restart omr-service

# 修改配置后重建容器
docker compose up -d --force-recreate omr-service

# 停止但保留宿主机持久化数据
docker compose down
```

不要使用 `docker compose down -v` 清理生产服务。当前 Compose 使用宿主机绑定目录，不会因普通 `down` 删除数据，但执行清理命令前仍应先备份。

## 9. 升级与回滚

升级前备份 `.env`、`config/robyn-service.json`、模板和 `service_data`：

```bash
cd /opt/omrchecker
docker compose stop omr-service
tar -czf "/var/backups/omrchecker-$(date +%F-%H%M%S).tar.gz" \
  .env config/robyn-service.json inputs config service_data

git fetch --all --tags
git checkout <已验证的版本或提交>
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:${OMR_SERVICE_PORT:-8080}/health
```

升级失败时，停止服务、检出原版本、恢复与该版本匹配的配置和数据备份，然后重新构建启动。SQLite 备份应在服务停止后执行，或使用 SQLite 在线备份机制，不能只复制正在写入的单个 `.db` 文件。
