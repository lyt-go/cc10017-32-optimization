# 实时数据入湖平台

面向流式数据接入、实时转换、增量合并与湖上物化查询的实时数据入湖治理平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 主题注册 | `topic_registry` | 数据主题 | 主题编号、主题名称、消息格式 |
| 流式计算 | `flink_job` | 流式任务 | 任务编号、消费主题、转换逻辑 |
| 消息接入 | `kafka_connector` | 接入配置 | 配置编号、集群地址、消费组名 |
| Schema演进 | `schema_evolve` | 演进规则 | 规则编号、关联主题、新增字段 |
| 增量合并 | `upsert_merge` | 合并策略 | 策略编号、目标表名、合并键列 |
| 湖上分区 | `lake_partition` | 分区定义 | 分区编号、目标表名、分区列名 |
| 流式质量 | `stream_quality` | 质量规则 | 规则编号、监控主题、校验类型 |
| Iceberg管理 | `iceberg_table` | 表元数据 | 表编号、表名称、存储格式 |
| 水位追踪 | `watermark_track` | 水位标记 | 标记编号、数据主题、分区编号 |
| 死信处理 | `dead_letter` | 死信记录 | 记录编号、原始主题、原始分区 |
| 物化查询 | `materialized_view` | 物化视图 | 视图编号、查询SQL、基表名 |
| CDC捕获 | `change_capture` | CDC配置 | 配置编号、源数据库、源表名 |
| 合并清理 | `compact_policy` | 清理策略 | 策略编号、目标表名、触发条件 |
| 流式血缘 | `stream_lineage` | 血缘记录 | 记录编号、上游主题、下游表名 |
| 流式补数 | `backfill_stream` | 补数任务 | 任务编号、目标表名、起始偏移 |
| 下沉分发 | `sink_dispatch` | 分发规则 | 规则编号、湖表名、目标系统 |
| 数据生命周期 | `ttl_policy` | 生命周期 | 策略编号、目标表名、热数据保留 |
| 实时指标 | `realtime_metrics` | 指标定义 | 指标编号、指标名称、聚合窗口 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 合并排程（维护链）

合并清理的固定时间窗口不再无脑启动小文件合并：排程把补数高峰纳入判断，
生成一份**合并排程数据结果**（`compact_merge_schedules`），同时保留：

- `preferred_file_set`：本批优先合并的文件及其来源版本；
- `deferred_partitions`：延后分区，被补数占用的分区状态为「等待合并」；
- `completed_file_set`：已完整执行的合并文件，断点恢复后不会再次启动。

同一份模型被三个入口共用（`backend/app/services/compact_schedule.py`）：

| 入口 | 行为 |
| --- | --- |
| 合并清理页 `POST /api/compact_policy/{id}/schedule` | 生成排程，冲突处置可选「优先补数」或「优先合并」 |
| 合并清理页 `POST /api/compact_policy/schedules/{id}/actions` | 执行合并 / 模拟中断 / 断点恢复 |
| 流式补数 `POST /api/backfill_stream/{id}/actions` | 启动补数标记占用分区，完成后重排延后分区 |
| 管道维护链 `POST /api/pipeline/maintenance/backfill/{id}/compact` | 补数后执行合并，产物写回同一份排程 |

两种冲突处置留下的下游结果不同：优先补数会整窗顺延（延后分区与残留小文件更多，
查询延迟更高），优先合并只合并未被占用的分区。排程中断后恢复只重排延后分区，
已执行文件集原样保留。

领域：数据工程
子方向：数仓与数据湖
