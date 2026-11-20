"""流式计算 时间线接口：返回作业时间序列结构。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.exporting import csv_download_records
from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.flink_job import FlinkJobService

router = APIRouter(prefix="/api/flink_job", tags=["流式计算"])
service = FlinkJobService()
LIST_FIELDS = ["任务编号", "消费主题", "转换逻辑", "输出表名", "并行度", "检查点间隔", "状态后端", "水位策略"]
STATUSES = ["草稿", "待校验", "运行中", "已停止"]



@router.get("")
def list_entries() -> dict[str, Any]:
    items = service.get_timeline()
    return {"items": items}


@router.get("/export")
def export_entries() -> StreamingResponse:
    return csv_download_records(service.get_timeline(), "flink_job")


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"流式任务 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="流式任务已登记", entry=entry_or_none)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)
