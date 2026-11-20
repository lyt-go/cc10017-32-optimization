"""实时指标 分析看板接口：汇总指标、参数运行与结果导出。"""
from __future__ import annotations

import random
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.exporting import csv_download_records
from app.schemas import EntryPayload
from app.services.realtime_metrics import RealtimeMetricsService

router = APIRouter(prefix="/api/realtime_metrics", tags=["实时指标"])
service = RealtimeMetricsService()
LIST_FIELDS = ["指标编号", "指标名称", "聚合窗口", "聚合函数", "过滤条件", "分组维度", "输出表名", "指标版本"]
STATUSES = ["草稿", "待校验", "已生效", "已废弃"]


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    return {"metrics": [
        {"label": "覆盖数据源", "value": random.randint(12, 45), "trend": random.randint(-12, 25)},
        {"label": "最新指标值", "value": round(random.uniform(0.72, 0.99), 3), "trend": random.randint(-8, 15)},
        {"label": "异常记录", "value": random.randint(0, 8), "trend": -random.randint(1, 10)},
    ]}


@router.get("")
def list_results() -> dict[str, Any]:
    return {"items": service.list_results()}


@router.post("/run")
def run_analysis(payload: EntryPayload) -> dict[str, Any]:
    results = service.run_analysis(payload.values)
    return {"items": results}


@router.get("/export")
def export_entries() -> StreamingResponse:
    return csv_download_records(service.list_results(), "realtime_metrics")


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"指标定义 {entry_id} 不存在")
    return entry
