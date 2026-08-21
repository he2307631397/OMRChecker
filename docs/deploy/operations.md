# 运维与故障排查

## 健康检查与监控

```bash
curl --fail --max-time 10 http://127.0.0.1:8080/health
```

建议监控：

- `/health` HTTP 状态和响应时间。
- 容器/systemd 进程是否频繁重启。
- CPU、内存、打开文件数和任务耗时。
- `service_data` 所在文件系统容量和 inode。
- 回调失败次数、COS 请求错误和 SQLite 错误。

`/health` 只检查进程，不检查 COS 权限、回调可达性和模板有效性。发布后必须额外执行一份已知样例的端到端任务。

## 日志

Docker Compose：

```bash
docker compose logs -f --tail=200 omr-service
docker inspect --format '{{json .State.Health}}' omrchecker-robyn
```

systemd：

```bash
sudo journalctl -u omrchecker -f
sudo journalctl -u omrchecker --since '30 minutes ago' --no-pager
```

日志可能包含对象键、任务 ID 和业务错误信息。接入日志平台时配置访问权限与保留周期，不应输出或采集 COS SecretKey。

## 常见问题

### 1. 容器一直 unhealthy

先查看启动异常：

```bash
docker compose ps
docker compose logs --tail=300 omr-service
docker exec omrchecker-robyn python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health').read())"
```

重点检查 `config/robyn-service.json` 是否为有效 JSON、端口是否被占用、目录是否可读写。配置中的回调 URL 必须为空、`null` 或合法的 `http://`/`https://` URL。

### 2. `Permission denied` 或 SQLite 无法写入

检查绑定目录：

```bash
ls -ld service_data inputs config
docker exec omrchecker-robyn sh -c 'id; touch /app/service_data/.write-test && rm /app/service_data/.write-test'
```

默认镜像当前以 root 用户运行，一般能够写入，但 NFS root squash、SELinux 或只读文件系统仍可能拒绝。不要直接使用 `chmod -R 777`。应把目录所有权授予实际运行 UID/GID，并只开放必需权限。SELinux 主机需要为 bind mount 配置正确标签，必要时在 Compose volume 后使用 `:Z`，但共享目录使用前先评估标签影响。

### 3. `libGL.so.1`、`libgthread` 或其他 `.so` 缺失

Docker 镜像已经安装 OpenCV 常用运行库。原生部署执行：

```bash
sudo apt-get install -y libglib2.0-0 libgl1 libgomp1 libsm6 libxext6 libxrender1
ldd /opt/omrchecker/app/.venv/lib/python*/site-packages/cv2/*.so | grep 'not found' || true
```

根据 `ldd` 结果安装对应发行版包。不要从不可信网站单独下载 `.so` 文件。

### 4. COS 任务报缺少 `qcloud_cos`

当前 `requirements.txt` 使用 PyPI 包名 `cos-python-sdk-v5`，导入模块名为 `qcloud_cos`。确认镜像或虚拟环境是用当前依赖重新安装的：

```bash
docker compose build --no-cache omr-service
# 原生部署
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c 'import qcloud_cos; print(qcloud_cos.__file__)'
```

### 5. COS 返回 403、签名错误或找不到对象

逐项核对：

- `region` 与 Bucket 所在地域一致，例如 `ap-guangzhou`。
- `bucket` 使用包含 APPID 的完整名称。
- SecretId/SecretKey 没有引号、换行或前后空格。
- 子账号策略允许目标前缀的 GetObject、PutObject 等必需操作。
- 服务器时间已通过 NTP 同步。
- 对象键大小写和前导斜杠符合调用约定。

可在容器内确认变量是否存在，但不要打印密钥值：

```bash
docker exec omrchecker-robyn python -c "import os; print(bool(os.getenv('COS_SECRET_ID')), bool(os.getenv('COS_SECRET_KEY')))"
```

### 6. 本地模拟 COS 找不到文件

设置：

```json
"cos": {
  "enabled": false,
  "localRoot": "/app/service_data/cos_mock"
}
```

请求中的对象键 `incoming/a.pdf` 对应宿主机文件：

```text
service_data/cos_mock/incoming/a.pdf
```

### 7. 回调失败

从服务运行环境验证 DNS、TLS 和网络连通性：

```bash
docker exec omrchecker-robyn python -c "import urllib.request; print(urllib.request.urlopen('https://callback.example.com/health', timeout=10).status)"
```

同时检查回调地址是否要求鉴权。当前服务回调客户端发送 JSON，但没有通用的自定义鉴权 Header 配置。业务系统仍应通过任务查询接口补偿轮询，不能只依赖回调。

### 8. 内存高或任务排队

识别 PDF/图片会消耗 CPU 和内存。两个接口各自拥有线程池，配置的 worker 数会分别用于单文件和批量任务，因此混合流量下活跃识别任务可能高于单个 worker 值。

处理建议：

1. 先把 `server.workers` 设为 `2` 或 `4`，重建/重启服务。
2. 限制上传文件大小、PDF 页数和上游并发。
3. 通过真实模板与文件压测，观察峰值 RSS 和 P95/P99 耗时。
4. 扩容前确认 SQLite 和共享目录的部署方式。不要让多个实例同时使用同一个本地 SQLite 文件。

### 9. 磁盘持续增长

检查：

```bash
du -h -d 2 service_data | sort -h | tail -30
find service_data -type f -mtime +30 -print | head
```

`OMR_RECOGNITION_DEBUG_ARTIFACTS=true` 会保留更多中间文件。生产环境应保持 `false`。制定清理策略前先确认哪些文件仍被任务查询、下载或审计使用，不要直接定时删除整个 `service_data`。

## 备份与恢复

至少备份：

- `.env` 和 `config/robyn-service.json`，应加密保存。
- `inputs/` 和业务模板目录。
- `service_data/omr_service.db` 及仍需保留的识别产物。

一致性最简单的做法是短暂停止服务后打包：

```bash
docker compose stop omr-service
tar -czf "/var/backups/omrchecker-$(date +%F-%H%M%S).tar.gz" \
  .env config/robyn-service.json inputs config service_data
docker compose start omr-service
```

备份不是恢复验证。应定期在隔离环境恢复备份，验证 SQLite 可打开、模板完整且样例任务可识别。

## 上线检查清单

- [ ] `.env` 和服务配置未提交 Git，文件权限为 `600`。
- [ ] 使用实际模板完成端到端识别并核对答案。
- [ ] COS 最小权限账号下载、上传均验证成功，或本地模式路径验证成功。
- [ ] 回调成功，同时业务侧实现任务轮询补偿。
- [ ] 公网流量经 TLS 反向代理，8080 未直接暴露。
- [ ] worker 数经过容量测试，不使用未经验证的高并发。
- [ ] `service_data` 有容量告警、备份和恢复演练。
- [ ] 明确发布版本、回滚版本和配置兼容性。
