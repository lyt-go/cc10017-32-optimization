"""流式血缘 DAG 拓扑接口：返回节点、连线图结构。"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.exporting import csv_download
from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services.stream_lineage import StreamLineageService

router = APIRouter(prefix="/api/stream_lineage", tags=["流式血缘"])
service = StreamLineageService()
LIST_FIELDS = ["记录编号", "上游主题", "下游表名", "转换节点", "字段映射", "采集时间", "延迟偏移", "链路版本"]
STATUSES = ["草稿", "待校验", "已生效", "已停用"]


@router.get("")
def get_graph() -> dict[str, Any]:
    """返回节点与边组成的 DAG 图数据。"""
    return service.get_graph()


@router.get("/export")
def export_entries() -> StreamingResponse:
    nodes, edges = service.raw_data()
    rows = [
        ["node", node.get("id", ""), node.get("name", ""), "", "", "", node.get("status", "")]
        for node in nodes
    ]
    rows += [
        ["edge", "", "", edge.get("from", ""), edge.get("to", ""), edge.get("label", ""), ""]
        for edge in edges
    ]
    return csv_download(["type", "id", "name", "from", "to", "label", "status"], rows, "stream_lineage")


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"血缘记录 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="血缘记录已登记", entry=entry_or_none)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)
