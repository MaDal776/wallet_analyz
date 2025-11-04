# 聪明钱包分析工具部署与使用指南

本项目提供一个 Polymarket 风格的钱包交易分析平台，分为 **FastAPI 后端** 与 **Vite + React 前端**。后端负责抓取并聚合 TRADE/REDEEM 交易数据，前端展示统计结果并提供交互式分析体验。本文档涵盖本地开发、云端部署（后端）以及将前端部署到 Netlify 的完整步骤。

---

## 1. 项目结构

```
├── csv_analyzer.py                # 原始 CSV 聚合逻辑（被后端复用）
├── wallet_analyzer.py             # Polymarket API 数据抓取工具
├── web_app/
│   ├── backend/                   # FastAPI 服务端代码
│   │   ├── app/
│   │   │   ├── main.py            # FastAPI 入口，暴露 /api/analyze
│   │   │   ├── schemas.py         # 请求/响应 Pydantic 模型
│   │   │   └── services/
│   │   │       └── analysis_pipeline.py
│   │   └── requirements.txt       # Python 依赖
│   └── frontend/                  # Vite + React 前端
│       ├── index.html
│       ├── netlify-aware src 代码
│       └── public/polymarket-favicon.svg
├── netlify.toml                   # Netlify 构建与反向代理配置
└── README.md
```

---

## 2. 运行前置条件

| 组件 | 版本建议 |
|------|----------|
| Python | ≥ 3.10（推荐 3.11） |
| Node.js | 18 LTS 或以上 |
| npm | ≥ 9 |
| (可选) Nginx | 用于反向代理后端 |

---

## 3. 本地开发

### 3.1 后端（FastAPI）

```bash
cd /path/to/聪明钱包交易分析
python3 -m venv .venv
source .venv/bin/activate
pip install -r web_app/backend/requirements.txt
uvicorn web_app.backend.app.main:app --host 0.0.0.0 --port 8000
```

访问 <http://localhost:8000/docs> 可查看 OpenAPI 文档。需要停止时 `Ctrl+C`，退出虚拟环境可执行 `deactivate`。

### 3.2 前端（Vite + React）

```bash
cd /path/to/聪明钱包交易分析/web_app/frontend
npm install
npm run dev
```

开发服务器默认运行在 <http://localhost:5173>，对 `/api` 的请求会通过 Vite 代理转发到本地后端。

---

## 4. 后端云服务器部署示例

以下示例以 Ubuntu Server + systemd + Nginx 为参考，请根据实际环境调整路径与域名。

1. **创建部署目录**

   ```bash
   sudo mkdir -p /opt/smart-wallet
   sudo chown $USER:$USER /opt/smart-wallet
   ```

2. **上传代码**（可使用 `git clone` 或 `scp` 上传当前仓库）。

3. **创建虚拟环境并安装依赖**

   ```bash
   cd /opt/smart-wallet
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r web_app/backend/requirements.txt
   deactivate
   ```

4. **编写 systemd 服务（可选）** — `/etc/systemd/system/smart-wallet.service`

   ```ini
   [Unit]
   Description=Smart Wallet FastAPI Service
   After=network.target

   [Service]
   User=www-data
   WorkingDirectory=/opt/smart-wallet
   ExecStart=/opt/smart-wallet/.venv/bin/uvicorn web_app.backend.app.main:app \
             --host 0.0.0.0 --port 8000 --workers 1
   Restart=on-failure
   Environment="PYTHONUNBUFFERED=1"

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now smart-wallet.service
   sudo systemctl status smart-wallet.service
   ```

5. **配置 Nginx 反向代理（可选但推荐）**

   `/etc/nginx/sites-available/smart-wallet`：

   ```nginx
   server {
       listen 80;
       server_name backend.example.com;  # 替换为后端域名或 IP

       location /api/ {
           proxy_pass http://127.0.0.1:8000/api/;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   ```bash
   sudo ln -s /etc/nginx/sites-available/smart-wallet /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

   需要启用 HTTPS 时，可使用 Let’s Encrypt（如 `certbot --nginx`）。

---

## 5. 前端部署到 Netlify

### 5.1 配置说明

- `netlify.toml` 已提供构建命令和静态文件目录：
  ```toml
  [build]
    command = "cd web_app/frontend && npm install && npm run build"
    publish = "web_app/frontend/dist"

  [build.environment]
    VITE_API_BASE_URL = "https://your-backend-domain.com"

  [[redirects]]
    from = "/api/*"
    to = "https://your-backend-domain.com/api/:splat"
    status = 200
    force = true
  ```
- **务必将 `https://your-backend-domain.com` 替换为后端真实域名或 IP**（若是 IP 请使用 `http://xx.xx.xx.xx`）。
- Netlify 将使用 `VITE_API_BASE_URL` 注入前端构建结果，前端会自动指向云端后端；`[[redirects]]` 确保直接访问 `/api/*` 仍能转发到后端。

### 5.2 部署步骤

1. 登录 Netlify 控制台，选择 **Add new site → Import an existing project**。
2. 连接 Git 仓库或上传打包文件。如果使用 Git，请确保仓库根目录包含本 README 所述结构。
3. 在 **Build settings** 中：
   - Build command: `cd web_app/frontend && npm install && npm run build`
   - Publish directory: `web_app/frontend/dist`
4. 在 **Site settings → Environment variables** 添加：
   - `VITE_API_BASE_URL` = `https://your-backend-domain.com`
5. 点击 **Deploy site**。部署完成后，访问 Netlify 提供的域名即可加载前端。

> 注意：Netlify 仅托管静态前端，后端必须部署在可公网访问的服务器上，并允许跨域（FastAPI `main.py` 已启用 `CORSMiddleware`）。

---

## 6. 生产环境快速验证

部署完成后，可通过以下方式验证：

1. 打开 Netlify 域名，输入测试钱包地址（如 `0x` 开头的真实地址），并选择时间范围。
2. 观察加载进度提示，等待分析结果展示。
3. 如遇错误，可在浏览器 DevTools 中查看网络请求；若返回 4xx/5xx，请检查后端日志与 Nginx 配置。

---

## 7. 常见问题

| 问题 | 解决方案 |
|------|----------|
| 前端提示 `network error` | 检查 Netlify 环境变量 `VITE_API_BASE_URL` 是否正确，后端是否开启 CORS。 |
| 后端报错 `ModuleNotFoundError: No module named 'fastapi'` | 确认已激活虚拟环境或使用 `.venv/bin/uvicorn` 启动。 |
| 数据量大时响应缓慢 | 可将 `AnalysisRequestPayload.max_workers` 调高（最大 16），或在服务器上加大 CPU。 |
| 时区问题 | 后端以 CST（UTC+8）进行日期划分，确保传入时间范围与期望一致。 |

---

## 8. 后续规划建议

- 编写 systemd / Nginx 脚本自动化部署。
- 针对常用钱包地址添加缓存或异步任务队列。
- 增加错误追踪（Sentry 等）和性能监控。

如在部署或使用过程中遇到其他问题，请记录日志与操作步骤，方便进一步排查。祝部署顺利！
