# Crawler Agent

简体中文说明文档。

## 简介

Crawler Agent 是一个用于网页抓取与任务调度的后端服务，包含爬虫、登录与调度逻辑，并带有一个基于 Vite 的前端仪表盘用于查看任务与数据。

## 主要功能

- 可扩展的爬虫架构（会话、代理、反爬绕过）
- 登录凭证与验证码处理模块
- 任务调度与进度上报（前端可视化）
- 简易 API（登录、任务管理、WebSocket 实时推送）

## 目录结构（摘要）

- `backend/` - 后端服务代码与测试
  - `app/` - 应用代码（agent、crawler、api、models、storage 等）
  - `run.py` - 后端启动脚本
  - `requirements.txt` - Python 依赖
- `frontend/` - 前端（Vite + React/TypeScript）

完整结构请参见项目根目录。

## 环境要求

- Python 3.10+
- Node.js 16+

## 快速开始（后端）

在 Windows PowerShell 中：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python backend/run.py
```

在 macOS / Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/run.py
```

后端启动后，默认会在配置中指定的端口提供 HTTP 和 WebSocket 接口，具体配置请参考 `app/config.py`。

## 快速开始（前端）

在 `frontend/` 目录下：

```bash
cd frontend
npm install
npm run dev
```

默认情况下前端会运行在 Vite 的本地开发服务器，前端通过 API 与后端通信，请确保后端在本地可访问。

## 配置

项目的可配置项集中在 `app/config.py`，生产环境建议使用环境变量或 `.env` 文件管理敏感信息（数据库 URL、代理、密钥等）。

常见环境变量示例（根据实际代码调整）：

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`

## 测试

后端单元/集成测试可使用 `pytest` 运行：

```bash
pip install -r backend/requirements.txt
pytest backend
```

项目中包含示例测试文件，如 `backend/test_crawl.py` 与 `backend/test_e2e.py`。

## 开发建议

- 运行后端时启用虚拟环境，保持 `requirements.txt` 与实际依赖同步。
- 前端使用 TypeScript，如需更多接口，请在 `frontend/src/api/client.ts` 中添加。
- 对接第三方代理或浏览器自动化时，请在 `backend/app/crawler/` 中查看现有工具类（`proxy.py`、`session.py`、`stealth.py`）。

## 部署

建议将后端部署在具备持久化存储（数据库/Redis）与可配置代理的服务器上。前端可以打包为静态文件托管在 CDN 或 Web 服务器。

基本部署流程：

1. 在目标服务器建立 Python 环境并安装依赖
2. 设置环境变量或 `.env`
3. 启动后端服务（可配合 process manager）
4. 构建前端并将静态文件上传至静态托管服务

## 贡献

欢迎提交 issue 与 PR。提交前请：

- 保持代码风格一致
- 为新增功能添加测试
- 在 PR 描述中说明变更目的与影响范围

## 许可

本仓库默认采用 MIT 许可（如需更改，请添加 `LICENSE` 文件并更新此处）。

## 联系

如有疑问请在仓库中打开 issue，或联系项目维护者。
