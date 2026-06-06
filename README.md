# 企微群会话分析系统（wxwork_analytics）

企业微信客户群的**只读监测**与运营分析后台：群活跃度四级分类、回复率/响应率统计、
数据可视化、沉默群预警，以及基于**豆包大模型**的客户消息情绪分析。

> 仅只读监测 · 不发送任何消息 · 数据安全合规

这是基于原项目骨架重建的完整、可独立运行的版本。技术栈：

- **后端**：Python + FastAPI + SQLAlchemy + JWT（默认 SQLite，零配置即可跑）
- **前端**：Vue 3 + TypeScript + Element Plus + Pinia + ECharts + Vite

---

## 一、目录结构

```
wxwork_analytics/
├── backend/                    # 后端
│   ├── app/
│   │   ├── main.py             # 入口：建表、挂路由、演示数据
│   │   ├── core/               # config / database / security / wxwork_client
│   │   ├── models/models.py    # 全部数据表
│   │   ├── services/           # 活跃度、同步、演示数据、豆包情绪分析
│   │   └── api/                # auth / groups / admin / alerts 路由
│   ├── requirements.txt
│   └── .env.example
└── frontend/                   # 前端
    ├── src/
    │   ├── api/                # axios 封装与接口定义
    │   ├── stores/             # Pinia
    │   ├── router/
    │   ├── layout/ + views/    # 布局与页面
    │   └── main.ts / App.vue
    ├── package.json
    └── vite.config.ts
```

---

## 二、启动（开发模式）

### 1. 后端

需要 **Python 3.10+**（Windows 请去 python.org 安装，勿用应用商店占位版）。

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # 按需修改；默认即可开箱跑
uvicorn app.main:app --reload --port 8000
```

启动后：
- API 文档： http://127.0.0.1:8000/docs
- 健康检查： http://127.0.0.1:8000/api/health
- 因 `DEMO_MODE=true`，首次启动会**自动生成一批演示数据**（12 个群 + 成员 + 14 天消息/统计 + 预警）。

### 2. 前端

需要 **Node.js 18+**。

```powershell
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 ，在登录页点 **「演示登录」→「进入演示」**，
无需企业微信凭证即可查看完整界面与模拟数据。

---

## 三、切换到真实企业微信数据

1. 在企业微信管理后台创建自建应用，拿到 **CorpID / AgentID / Secret**，并配置服务器可信 IP。
2. 登录系统 → 「API配置后台」→ 填入并保存、点「测试连接」。
3. 点右上角「同步数据」：检测到有效 Secret 时会调用企业微信接口拉取真实客户群；
   否则回落到演示数据。

> 说明：真实拉取客户群需要应用具备「客户联系」相关权限，且 Secret 对应的应用已开通对应接口。

---

## 四、豆包 AI 情绪分析（可选增强）

群详情页「AI 情绪分析」卡片，调用**豆包大模型（火山方舟 Ark）**对群内客户发言做
情绪倾向 + 投诉/流失风险识别。

启用方式：在 `backend/.env` 填入

```
DOUBAO_API_KEY=你的火山方舟API Key
DOUBAO_MODEL=ep-xxxxxxxx     # 方舟控制台创建的「推理接入点ID」，或模型名
```

未配置时该功能优雅降级（卡片提示未启用），不影响其他功能。
接口为 OpenAI 兼容协议，实现见 `backend/app/services/sentiment_service.py`，
返回 `{sentiment, score, risk, summary, keywords}`。

---

## 五、生产部署要点

- 把 `SECRET_KEY` 改成随机长字符串，`DEMO_MODE=false` 关闭演示。
- 数据库换成 MySQL：改 `.env` 的 `DATABASE_URL`（并 `pip install pymysql`）。
- 前端 `npm run build` 生成 `dist/`，用 Nginx 托管；`/api` 反向代理到后端。
- 后端用 `uvicorn` + 进程守护（systemd / supervisor）运行。

---

## 六、与原部署版（wx.zjyxgj.com）的关系

本项目是**按原项目暴露的接口/字段重建的等价实现**，并非原服务器源码的逐字拷贝。
前后端接口、数据模型、四级活跃度逻辑均与原系统对齐，可独立运行与二次开发。
重建时已修复原代码的几处问题：去除调试残留、堵住 `corp_id` 静默兜底、
新用户默认最低权限、后台任务使用独立数据库会话。
