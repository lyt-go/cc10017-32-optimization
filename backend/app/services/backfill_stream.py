"""流式补数 时间线服务：生成作业时间序列和示例数据。

增强：补数开始/结束时接收合并清理的合并排程数据结果，标记仍占用文件的分区，
并把补数高峰写回同一份排程（由 compact_schedule_service 统一维护）。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.services.compact_schedule import compact_schedule_service
from app.store import store

MODULE = "backfill_stream"
REQUIRED_FIELDS = ["任务编号", "目标表名", "起始偏移"]
STATUS_ORDER = ["草稿", "运行中", "已完成", "已取消"]
ACTION_RULES = {"启动补数": "运行中", "确认完成": "已完成", "取消补数": "已取消"}
NEGATIVE_ACTIONS = []


class BackfillStreamService:
    def get_timeline(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        today = date.today()
        items: list[dict] = []
        for i, row in enumerate(rows):
            start = (today - timedelta(days=7 - i * 2)).isoformat()
            end = (today + timedelta(days=3 - i)).isoformat()
            items.append({
                "id": int(row.get("id", i + 1)),
                "name": str(row.get(list(row.keys())[1] if len(row) > 1 else "name", "")),
                "start": start,
                "end": end,
                "status": str(row.get("status", STATUS_ORDER[i % len(STATUS_ORDER)])),
                "logs": f"[{start}] 作业启动\n[{start}] 正在处理...\n[{end}] 任务{'完成' if row.get('status') == STATUS_ORDER[-1] else '进行中'}",
            })
        return items

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [f for f in REQUIRED_FIELDS if not str(values.get(f) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(r.get("id", 0)) for r in rows), default=0) + 1}
        entry.update({f: values.get(f) for f in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"补数任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于流式补数可执行范围"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS

        schedule = None
        if target == "运行中":
            schedule, _, _ = compact_schedule_service.mark_backfill(entry)
        elif action in ("确认完成", "取消补数"):
            schedule = compact_schedule_service.release_after_backfill(entry)
        if schedule is not None:
            entry["merge_schedule_id"] = schedule.get("id")
        return entry, f"补数任务已{action}"

    def get_merge_schedule(self, entry_id: int) -> dict[str, Any] | None:
        """补数任务关联的合并排程：同表最近一份，含仍被占用的分区。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return compact_schedule_service.latest_for_table(str(entry.get("目标表名") or ""))

    def get_peak_partitions(self) -> list[dict[str, Any]]:
        """补数高峰分区：仍占用文件、在补数完成前只能等待合并的分区。"""
        peaks: list[dict[str, Any]] = []
        for entry in store.rows(MODULE):
            if entry.get("status") != "运行中":
                continue
            schedule = compact_schedule_service.latest_for_table(str(entry.get("目标表名") or ""))
            if schedule is None:
                continue
            occupied = {item["partition"] for item in schedule.get("occupied_partitions", [])}
            for item in schedule.get("deferred_partitions", []):
                if item.get("partition") in occupied:
                    peaks.append({
                        "backfill_id": entry.get("id"),
                        "backfill_code": entry.get("任务编号"),
                        "target_table": entry.get("目标表名"),
                        "partition": item.get("partition"),
                        "state": item.get("state"),
                        "schedule_id": schedule.get("id"),
                    })
        return peaks
