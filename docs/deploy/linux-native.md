# Linux 原生部署

原生部署不依赖 Docker，但需要自行维护 Python、OpenCV 系统库、进程守护、日志和升级。以下命令以 Ubuntu/Debian 为例，建议 Python 3.11。

## 1. 安装系统依赖

```bash
sudo apt-get update
sudo apt-get install -y \
  git curl ca-certificates build-essential \
  python3.11 python3.11-venv python3-pip \
  libglib2.0-0 libgl1 libgomp1 libsm6 libxext6 libxrender1
```

依赖用途：

| 包 | 用途 |
| --- | --- |
| `python3.11-venv` | 创建隔离的 Python 虚拟环境 |
| `build-essential` | PyPI 无对应 wheel 时编译扩展 |
| `libglib2.0-0`、`libgl1`、`libsm6`、`libxext6`、`libxrender1` | OpenCV 动态库依赖 |
| `libgomp1` | NumPy/OpenCV 并行运行库 |

若发行版不提供 Python 3.11，请使用发行版受支持的 Python 3.10+ 并完整执行测试，不建议替换系统默认 Python。RHEL/Rocky Linux 对应库名可能不同，可用 `ldd` 检查缺失的 `.so`。

## 2. 创建服务用户并安装

```bash
sudo useradd --system --create-home --home-dir /opt/omrchecker \
  --shell /usr/sbin/nologin omrchecker
sudo -u omrchecker git clone <项目仓库地址> /opt/omrchecker/app
cd /opt/omrchecker/app

sudo -u omrchecker python3.11 -m venv .venv
sudo -u omrchecker .venv/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u omrchecker .venv/bin/python -m pip install -r requirements.txt

sudo -u omrchecker mkdir -p service_data inputs config
sudo -u omrchecker cp .env.example .env
sudo -u omrchecker cp config/robyn-service.example.json config/robyn-service.json
sudo chmod 600 .env config/robyn-service.json
```

`requirements.txt` 包含 Robyn、OpenCV、PyMuPDF、NumPy/Pandas 以及腾讯 COS SDK。即使使用本地 COS 模式，SDK 安装也不会触发网络访问 COS。

## 3. 配置

复制实际模板到 `/opt/omrchecker/app/inputs`，然后编辑：

- `/opt/omrchecker/app/.env`
- `/opt/omrchecker/app/config/robyn-service.json`

原生部署建议在 `.env` 中明确指定绝对路径：

```dotenv
OMR_SERVICE_HOST=127.0.0.1
OMR_SERVICE_PORT=8080
OMR_SERVICE_WORKERS=4
OMR_SERVICE_DATA_DIR=/opt/omrchecker/app/service_data
OMR_TEMPLATE_DIR=/opt/omrchecker/app/inputs
OMR_CALLBACK_URL=
COS_SECRET_ID=
COS_SECRET_KEY=
OMR_RECOGNITION_DEBUG_ARTIFACTS=false
```

同时把 JSON 中 SQLite 地址设为绝对路径：

```json
"database": {
  "url": "sqlite:////opt/omrchecker/app/service_data/omr_service.db"
}
```

注意 `sqlite:////绝对路径` 有四个斜杠。其余 COS、回调配置参考 [Docker Compose 配置](docker-compose.md#4-配置服务)。

## 4. 前台验证

```bash
cd /opt/omrchecker/app
sudo -u omrchecker .venv/bin/python web/robyn_app.py
```

另开终端验证：

```bash
curl --fail --show-error http://127.0.0.1:8080/health
```

验证完成后按 `Ctrl+C` 停止，再配置 systemd。若出现动态库错误，参考 [故障排查](operations.md)。

## 5. 配置 systemd

创建 `/etc/systemd/system/omrchecker.service`：

```ini
[Unit]
Description=OMRChecker Robyn Web Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=omrchecker
Group=omrchecker
WorkingDirectory=/opt/omrchecker/app
ExecStart=/opt/omrchecker/app/.venv/bin/python web/robyn_app.py
Restart=on-failure
RestartSec=5
TimeoutStopSec=60
KillSignal=SIGTERM

# 基础安全加固。服务需要写入 service_data。
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/omrchecker/app/service_data

# 避免并发识别打开文件过多。
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now omrchecker
sudo systemctl status omrchecker --no-pager
sudo journalctl -u omrchecker -n 100 --no-pager
curl --fail http://127.0.0.1:8080/health
```

如模板或配置位于 `/opt/omrchecker/app` 之外，需同步调整 systemd 的 `ReadWritePaths`/`ReadOnlyPaths`。不要为了省事关闭所有 systemd 安全限制。

## 6. 更新

```bash
sudo systemctl stop omrchecker
sudo -u omrchecker git -C /opt/omrchecker/app fetch --all --tags
sudo -u omrchecker git -C /opt/omrchecker/app checkout <已验证版本>
sudo -u omrchecker /opt/omrchecker/app/.venv/bin/python -m pip install -r /opt/omrchecker/app/requirements.txt
sudo systemctl start omrchecker
sudo systemctl status omrchecker --no-pager
```

更新前先按 Docker 文档中的原则备份配置、模板和 `service_data`。执行依赖升级后必须再次完成健康检查和一份真实样例识别。
