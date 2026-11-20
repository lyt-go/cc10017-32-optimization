"""流式补数 时间线接口：返回作业时间序列结构。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.exporting import csv_download_records
from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.backfill_stream import BackfillStreamService

router = APIRouter(prefix="/api/backfill_stream", tags=["流式补数"])
service = BackfillStreamService()
LIST_FIELDS = ["任务编号", "目标表名", "起始偏移", "截止偏移", "重放速率", "并行度", "覆盖策略", "结果校验"]
STATUSES = ["草稿", "运行中", "已完成", "已取消"]



@router.get("")
def list_entries() -> dict[str, Any]:
    items = service.get_timeline()
    return {"items": items}


@router.get("/export")
def export_entries() -> StreamingResponse:
    return csv_download_records(service.get_timeline(), "backfill_stream")


@router.get("/peak-partitions")
def get_peak_partitions() -> dict[str, Any]:
    """补数高峰分区：补数完成前仍占用文件、只能等待合并的分区。"""
    items = service.get_peak_partitions()
    return {"items": items, "total": len(items)}


@router.get("/{entry_id}/merge-schedule")
def get_merge_schedule(entry_id: int) -> dict[str, Any]:
    """跨模块读取该补数任务关联的合并排程数据结果。"""
    schedule = service.get_merge_schedule(entry_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"补数任务 {entry_id} 暂无合并排程")
    return schedule


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"补数任务 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="补数任务已登记", entry=entry_or_none)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)
