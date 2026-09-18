# 样本交接链路审计系统

基于 **Python FastAPI + SQLite + 原生 HTML/CSS/JavaScript** 的单页应用。
为每个样本录入带时间与经手人的交接事件，系统自动按时间排序并审计交接链路，
在时间线上标出**逆序、重叠、责任断档、时间断档**等冲突，给出可读的审计结论，
并支持编辑事件与导出当前样本的审计报告（Markdown / HTML）。

## 功能特性

- **样本管理**：新建 / 编辑 / 删除样本（编号、名称、描述）。
- **交接事件录入**：发生时间、交出方、接收方、交接地点、备注；支持编辑与删除。
- **链路审计**（事件按发生时间排序后逐条校验）：
  | 规则 | 级别 | 说明 |
  |---|---|---|
  | 录入逆序 | 严重 | 录入顺序中后一条事件的发生时间早于前一条 |
  | 时间重叠 | 严重 | 时间排序后相邻两条事件发生时间完全相同 |
  | 责任断档 | 警告 | 前一条的接收方与后一条的交出方不一致 |
  | 时间断档 | 提示 | 相邻两条间隔超过阈值（默认 24 小时，页面可调） |
  | 自交接 | 提示 | 交出方与接收方为同一方 |
- **时间线可视化**：按时间排序展示，冲突节点以红 / 橙 / 蓝描边和标签标出，
  并附录入序号，便于看出“录入顺序”和“实际时间序”的偏差。
- **可读审计结论**：横幅结论（通过 / 通过有警告 / 不通过 / 无事件）+ 异常逐条说明 + 数量统计。
- **报告导出**：
  - Markdown（`.md`）：含元信息、结论、时间线表格、异常清单；
  - HTML（`.html`）：带样式的独立报告，浏览器直接打开即可，也可直接打印。

## 技术栈

- 后端：FastAPI、Uvicorn、Pydantic
- 数据库：SQLite（标准库 `sqlite3`，零额外服务，启动自动建库建表）
- 前端：原生 HTML / CSS / JavaScript，无构建步骤、无外部 CDN

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI 路由（样本/事件 CRUD、审计、报告导出、静态页）
│   ├── database.py    # SQLite 连接、初始化与数据访问
│   ├── audit.py       # 审计引擎（排序、冲突检测、结论汇总）
│   ├── report.py      # Markdown / HTML 报告生成
│   └── schemas.py     # Pydantic 请求模型
├── static/
│   ├── index.html     # 单页界面
│   ├── style.css
│   └── app.js
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 方式一：Docker Compose 启动（推荐）

```bash
docker compose up -d --build
```

容器启动时会自动安装依赖并初始化数据库（表结构 + 数据目录）。
浏览器访问固定端口：

> **http://localhost:8000**

SQLite 数据文件保存在命名卷 `audit-data`（容器内 `/data/audit.db`），
容器重建不丢数据。停止与清理：

```bash
docker compose down          # 停止
docker compose down -v       # 停止并删除数据卷（清空数据）
```

## 方式二：本地直接运行

需要 Python 3.11+：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 。数据库默认创建在 `./data/audit.db`。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AUDIT_DB_PATH` | `data/audit.db`（容器内 `/data/audit.db`） | SQLite 数据库文件路径，启动时自动创建 |
| `GAP_HOURS` | `24` | 时间断档阈值（小时），仅作默认值；页面右上角可临时调整 |

## 使用说明

1. 左侧点击「＋ 新建」创建样本（填写编号、名称）。
2. 在样本详情页点击「＋ 录入交接事件」，填写发生时间、交出方、接收方。
   - 建议每一条记录表示一次“交接”：谁交给谁。
   - 链路完整时，相邻事件应满足：**上一条的接收方 = 下一条的交出方**。
3. 录入后审计自动刷新：时间线按时间排序，冲突节点着色并附标签，
   下方「冲突与异常」给出逐条可读说明，顶部给出总体结论。
4. 点击时间线节点上的「编辑 / 删除」可修正事件，审计结果实时重算。
5. 右上角调整“时间断档阈值”后立即重新审计。
6. 点击「导出 Markdown / HTML 报告」下载当前样本（按当前阈值）的审计报告。

## HTTP API 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/samples` | 样本列表 |
| POST | `/api/samples` | 新建样本 |
| GET | `/api/samples/{id}` | 样本详情 |
| PUT | `/api/samples/{id}` | 更新样本 |
| DELETE | `/api/samples/{id}` | 删除样本（级联删除事件） |
| POST | `/api/samples/{id}/events` | 录入事件 |
| PUT | `/api/events/{id}` | 更新事件 |
| DELETE | `/api/events/{id}` | 删除事件 |
| GET | `/api/samples/{id}/audit?gap_hours=24` | 执行审计，返回时间线/异常/结论 |
| GET | `/api/samples/{id}/report?fmt=markdown` | 导出 Markdown 报告 |
| GET | `/api/samples/{id}/report?fmt=html` | 导出 HTML 报告 |

交互文档（Swagger UI）：http://localhost:8000/docs

## 审计规则示例

录入以下三条事件（注意录入顺序与时间）：

1. `10:00` 采样组-张三 → 运输组-李四
2. `14:00` 运输组-李四 → 检测组-王五
3. `09:00` 采样组-张三 → 运输组-李四（补录）

审计将标出：第 3 条与录入顺序**逆序**；若把第 2 条交出方写成别人，则标记**责任断档**；
两条事件时间写成同一时刻则标记**时间重叠**；间隔超过阈值标记**时间断档**。
