"""CDC捕获 时间线接口：返回作业时间序列结构。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.exporting import csv_download_records
from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.change_capture import ChangeCaptureService

router = APIRouter(prefix="/api/change_capture", tags=["CDC捕获"])
service = ChangeCaptureService()
LIST_FIELDS = ["配置编号", "源数据库", "源表名", "快照模式", "捕获列", "变更序号", "增量阶段", "目标主题"]
STATUSES = ["草稿", "待校验", "运行中", "已停止"]



@router.get("")
def list_entries() -> dict[str, Any]:
    items = service.get_timeline()
    return {"items": items}


@router.get("/export")
def export_entries() -> StreamingResponse:
    return csv_download_records(service.get_timeline(), "change_capture")


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"CDC配置 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="CDC配置已登记", entry=entry_or_none)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)
