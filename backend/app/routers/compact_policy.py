"""合并清理接口：维护清理策略，覆盖提交校验、标记生效、停用策略等动作。"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult, SchedulePlanPayload
from app.services.compact_policy import CompactPolicyService

router = APIRouter(prefix="/api/compact_policy", tags=["合并清理"])

service = CompactPolicyService()

LIST_FIELDS = ["策略编号", "目标表名", "触发条件", "合并并发", "目标文件大小", "最小文件数", "保留快照数", "执行时间窗口"]
STATUSES = ["草稿", "待校验", "已生效", "已停用"]


def query_filters(request: Request) -> dict[str, str]:
    """只接受当前模块声明过的字段，忽略分页等保留参数。"""
    return {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in LIST_FIELDS and value.strip()
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    keyword: str | None = Query(default=None, description="按策略编号检索"),
    status: str | None = Query(default=None, description="草稿、待校验、已生效、已停用"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    """按页面字段、策略编号关键字与状态过滤合并清理列表。"""
    items, total = service.list_entries(
        filters=query_filters(request), keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    """下载当前筛选条件下的 UTF-8 CSV；必须声明在 /{entry_id} 之前。"""
    items, _ = service.list_entries(
        filters=query_filters(request), keyword=keyword, status=status, page=1, size=1000000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *LIST_FIELDS, "status"])
    for item in items:
        row = []
        for value in [item.get("id"), *(item.get(field, "") for field in LIST_FIELDS), item.get("status", "")]:
            text = "" if value is None else str(value)
            row.append("'" + text if text.startswith(("=", "+", "-", "@")) else text)
        writer.writerow(row)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="compact_policy.csv"'})


@router.get("/schedules", response_model=dict)
def list_schedules(target_table: str | None = Query(default=None)) -> dict:
    """合并排程数据结果列表：保留优先文件集与延后分区。"""
    items = service.list_schedules()
    if target_table:
        items = [item for item in items if item.get("target_table") == target_table]
    return {"items": items, "total": len(items)}


@router.get("/schedules/{schedule_id}", response_model=dict)
def get_schedule(schedule_id: int) -> dict:
    """读取一份合并排程数据结果；刷新页面后仍是同一份。"""
    schedule = service.get_schedule_by_id(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"合并排程 {schedule_id} 不存在")
    return schedule


@router.post("/schedules/{schedule_id}/actions", response_model=ActionResult)
def run_schedule_action(schedule_id: int, payload: ActionPayload) -> ActionResult:
    """执行合并、模拟中断、断点恢复；已执行文件集在任何动作下都不会重复启动。"""
    schedule, message = service.run_schedule_action(schedule_id, payload.action.strip())
    if schedule is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=schedule)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条清理策略明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"清理策略 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: dict[str, object]) -> ActionResult:
    """登记一条清理策略，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="清理策略已登记", entry=entry)


@router.post("/{entry_id}/schedule", response_model=ActionResult)
def plan_schedule(entry_id: int, payload: SchedulePlanPayload) -> ActionResult:
    """为清理策略生成合并排程数据结果：补数状态纳入排程，冲突按优先级处置。"""
    schedule, message = service.plan_schedule(entry_id, payload.resolution.strip())
    if schedule is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=schedule)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    """对单条清理策略执行提交校验、标记生效、停用策略；不允许的动作会被拦下并说明原因。"""
    entry, message = service.run_action(entry_id, payload.action.strip())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
