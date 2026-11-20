"""合并排程共用逻辑：合并清理、流式补数与管道维护链只保留这一份实现。

职责：
1. 读取合并清理策略（固定时间窗口）与同表补数高峰，判定分区级冲突；
2. 生成"合并排程数据结果"：优先文件集、延后分区、仍被补数占用的分区与来源版本；
3. 支持两种冲突处置（优先补数 / 优先合并），两者留下不同的文件集合与查询延迟；
4. 写入中断后从断点恢复：保留已执行文件集，只重排延后分区，已完成文件不会重复启动；
5. 供合并清理页、流式补数页和管道引擎共用，避免同样的排程逻辑各写一遍。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.store import store

SCHEDULE_TABLE = "compact_merge_schedules"

RESOLUTION_BACKFILL = "优先补数"
RESOLUTION_COMPACT = "优先合并"
RESOLUTIONS = (RESOLUTION_BACKFILL, RESOLUTION_COMPACT)

STATUS_PLANNED = "已排程"
STATUS_WAITING = "等待合并"
STATUS_INTERRUPTED = "已中断"
STATUS_DONE = "已完成"

PARTITION_COUNT = 4
FILES_PER_PARTITION = 3
OCCUPIED_PARTITION_COUNT = 2
MAX_EVENTS = 20


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _find_by_field(module: str, field: str, value: Any) -> dict[str, Any] | None:
    for row in store.rows(module):
        if str(row.get(field, "")) == str(value):
            return row
    return None


def table_partitions(target_table: str, count: int = PARTITION_COUNT) -> list[str]:
    """按天给出目标表最近的分区，最新分区在前；名称稳定，便于排程复用。"""
    today = date.today()
    return [
        f"{target_table}/dt={(today - timedelta(days=index)).isoformat()}"
        for index in range(count)
    ]


def _source_version(target_table: str) -> str:
    """合并清理保留来源版本：取 Iceberg 表当前的元数据版本。"""
    iceberg = _find_by_field("iceberg_table", "表名称", target_table)
    return str(iceberg.get("元数据版本") or "v1") if iceberg else "v1"


def _files_for(partition: str, index: int, source_version: str) -> list[dict[str, Any]]:
    return [
        {
            "file": f"{partition}/part-{index:02d}{seq:02d}.parquet",
            "partition": partition,
            "size_mb": 24 + index * 8 + seq * 6,
            "source_version": source_version,
        }
        for seq in range(1, FILES_PER_PARTITION + 1)
    ]


def _files_for_partitions(
    partitions: list[str], all_partitions: list[str], versions: dict[str, str]
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for partition in partitions:
        index = all_partitions.index(partition)
        files.extend(_files_for(partition, index, versions[partition]))
    return files


def _deferred_partition(partition: str, state: str, reason: str, source_version: str) -> dict[str, Any]:
    return {
        "partition": partition,
        "state": state,
        "reason": reason,
        "file_count": FILES_PER_PARTITION,
        "source_version": source_version,
    }


def _active_backfills(target_table: str) -> list[dict[str, Any]]:
    """补数高峰：同表处于运行中的补数任务。"""
    return [
        row
        for row in store.rows("backfill_stream")
        if str(row.get("目标表名", "")) == target_table and row.get("status") == "运行中"
    ]


def _occupied_partitions(target_table: str) -> list[str]:
    if not _active_backfills(target_table):
        return []
    return table_partitions(target_table)[:OCCUPIED_PARTITION_COUNT]


def _occupied_markers(target_table: str) -> list[dict[str, Any]]:
    backfills = _active_backfills(target_table)
    if not backfills:
        return []
    backfill = backfills[0]
    return [
        {
            "partition": partition,
            "state": STATUS_WAITING,
            "still_holding_files": True,
            "backfill_id": backfill.get("id"),
            "backfill_code": backfill.get("任务编号"),
        }
        for partition in table_partitions(target_table)[:OCCUPIED_PARTITION_COUNT]
    ]


def _conflict_detail(record: dict[str, Any]) -> dict[str, Any] | None:
    table = record["target_table"]
    backfills = _active_backfills(table)
    occupied = [marker["partition"] for marker in record.get("occupied_partitions", [])]
    if not backfills and not occupied:
        return None
    return {
        "window": record.get("execution_window"),
        "backfill_codes": [str(row.get("任务编号")) for row in backfills],
        "overlap_partitions": occupied,
        "resolution": record.get("resolution"),
    }


def _downstream_metrics(record: dict[str, Any]) -> dict[str, Any]:
    """排程留下的下游结果：延后文件越多，小文件残留与查询延迟越高。"""
    deferred_files = sum(int(item.get("file_count", 0)) for item in record["deferred_partitions"])
    planned_files = len(record["preferred_file_set"])
    return {
        "planned_files": planned_files,
        "deferred_files": deferred_files,
        "small_files_remaining": deferred_files,
        "query_latency_ms": 80 + deferred_files * 15 + len(record["deferred_partitions"]) * 10,
    }


class CompactScheduleService:
    """合并排程的生成、标记、执行与断点恢复；所有入口都走这里。"""

    # ── 读取 ──────────────────────────────────────────────

    def list_schedules(self, target_table: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(SCHEDULE_TABLE)
        if target_table:
            rows = [row for row in rows if row.get("target_table") == target_table]
        return sorted(rows, key=lambda row: int(row.get("id", 0)))

    def get_schedule(self, schedule_id: int) -> dict[str, Any] | None:
        return store.find(SCHEDULE_TABLE, schedule_id)

    def latest_for_table(self, target_table: str | None) -> dict[str, Any] | None:
        matches = self.list_schedules(target_table)
        return matches[-1] if matches else None

    def latest_for_policy(self, policy_id: int) -> dict[str, Any] | None:
        matches = [
            row for row in self.list_schedules() if int(row.get("compact_policy_id", 0)) == policy_id
        ]
        return matches[-1] if matches else None

    def effective_policy(self, target_table: str) -> dict[str, Any] | None:
        for row in store.rows("compact_policy"):
            if row.get("目标表名") == target_table and row.get("status") == "已生效":
                return row
        return None

    # ── 生成 ──────────────────────────────────────────────

    def plan(self, policy_id: int, resolution: str = RESOLUTION_BACKFILL) -> tuple[dict[str, Any] | None, str]:
        """生成合并排程数据结果；补数高峰纳入排程，冲突按 resolution 处置。"""
        policy = store.find("compact_policy", policy_id)
        if policy is None:
            return None, f"清理策略 {policy_id} 不存在或已归档"
        if resolution not in RESOLUTIONS:
            return None, f"排程优先级「{resolution}」不在允许范围（{'、'.join(RESOLUTIONS)}）"
        if policy.get("status") != "已生效":
            return None, f"清理策略 {policy.get('策略编号')} 尚未生效，不能生成合并排程"
        target_table = str(policy.get("目标表名") or "").strip()
        if not target_table:
            return None, f"清理策略 {policy.get('策略编号')} 未配置目标表名"

        partitions = table_partitions(target_table)
        version = _source_version(target_table)
        versions = {partition: version for partition in partitions}
        occupied = _occupied_partitions(target_table)
        conflict = bool(occupied)

        preferred_partitions: list[str] = []
        deferred: list[dict[str, Any]] = []
        if conflict and resolution == RESOLUTION_BACKFILL:
            # 补数优先：整窗暂停合并，占用的分区只能等待，其余分区也顺延。
            status = STATUS_WAITING
            deferred = [
                _deferred_partition(p, STATUS_WAITING, "补数高峰占用，等待补数完成", version)
                for p in occupied
            ]
            deferred += [
                _deferred_partition(p, "待下一批", "优先补数，整窗顺延到补数完成", version)
                for p in partitions
                if p not in occupied
            ]
        elif conflict:
            # 合并优先：只合并未被补数占用的分区，被占用的分区等待补数完成。
            status = STATUS_PLANNED
            preferred_partitions = [p for p in partitions if p not in occupied]
            deferred = [
                _deferred_partition(p, STATUS_WAITING, "补数高峰占用，等待补数完成", version)
                for p in occupied
            ]
        else:
            status = STATUS_PLANNED
            preferred_partitions = list(partitions)

        rows = store.rows(SCHEDULE_TABLE)
        record: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "target_table": target_table,
            "compact_policy_id": int(policy.get("id", 0)),
            "compact_policy_code": policy.get("策略编号"),
            "execution_window": policy.get("执行时间窗口"),
            "resolution": resolution,
            "conflict": conflict,
            "status": status,
            "batch_no": 1,
            "revision": 0,
            "source_version": version,
            "source_versions": versions,
            "preferred_file_set": _files_for_partitions(preferred_partitions, partitions, versions),
            "deferred_partitions": deferred,
            "occupied_partitions": _occupied_markers(target_table),
            "completed_file_set": [],
            "events": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        record["conflict_detail"] = _conflict_detail(record)
        record["downstream_metrics"] = _downstream_metrics(record)
        self._touch(record, "生成合并排程", f"{resolution}；优先文件 {len(record['preferred_file_set'])} 个，延后分区 {len(deferred)} 个")
        rows.append(record)
        return record, "合并排程已生成"

    # ── 跨模块：补数标记与补数结束 ───────────────────────

    def mark_backfill(self, backfill: dict[str, Any]) -> tuple[dict[str, Any] | None, bool, str]:
        """流式补数接收合并排程结果，标记仍占用文件的分区。"""
        target_table = str(backfill.get("目标表名") or "").strip()
        if not target_table:
            return None, False, f"补数任务 {backfill.get('任务编号')} 未配置目标表名"

        record = self.latest_for_table(target_table)
        created = False
        if record is None or record.get("status") == STATUS_DONE:
            policy = self.effective_policy(target_table)
            if policy is None:
                return None, False, f"表 {target_table} 未配置已生效的合并策略，无法接收合并排程"
            record, message = self.plan(int(policy.get("id", 0)), RESOLUTION_BACKFILL)
            if record is None:
                return None, False, message
            created = True

        partitions = table_partitions(target_table)
        version = _source_version(target_table)
        occupied = _occupied_partitions(target_table)

        # 仍占用文件的分区只能等待合并：从优先文件集里摘出来，放进延后分区。
        record["preferred_file_set"] = [
            item for item in record["preferred_file_set"] if item.get("partition") not in occupied
        ]
        deferred_map = {item["partition"]: item for item in record["deferred_partitions"]}
        for partition in occupied:
            if partition in deferred_map:
                deferred_map[partition]["state"] = STATUS_WAITING
                deferred_map[partition]["reason"] = "补数高峰占用，等待补数完成"
            else:
                deferred_map[partition] = _deferred_partition(
                    partition, STATUS_WAITING, "补数高峰占用，等待补数完成", version
                )
        record["deferred_partitions"] = list(deferred_map.values())
        record["occupied_partitions"] = _occupied_markers(target_table)
        record["conflict"] = True
        record["conflict_detail"] = _conflict_detail(record)
        record["downstream_metrics"] = _downstream_metrics(record)
        if record.get("status") != STATUS_INTERRUPTED:
            record["status"] = STATUS_PLANNED if record["preferred_file_set"] else STATUS_WAITING
        self._touch(
            record,
            "补数高峰标记",
            f"{backfill.get('任务编号')} 标记 {len(occupied)} 个分区仍占用文件",
        )
        return record, created, f"补数任务 {backfill.get('任务编号')} 已标记 {len(occupied)} 个分区仍占用文件"

    def release_after_backfill(self, backfill: dict[str, Any]) -> dict[str, Any] | None:
        """补数完成或取消：刷新占用标记并重排延后分区；中断中的排程只刷新状态。"""
        target_table = str(backfill.get("目标表名") or "").strip()
        record = self.latest_for_table(target_table)
        if record is None:
            policy = self.effective_policy(target_table)
            if policy is None:
                return None
            record, _ = self.plan(int(policy.get("id", 0)), RESOLUTION_COMPACT)
            if record is None:
                return None

        if record.get("status") == STATUS_INTERRUPTED:
            record["occupied_partitions"] = _occupied_markers(target_table)
            record["conflict"] = bool(record["occupied_partitions"])
            record["conflict_detail"] = _conflict_detail(record)
            record["downstream_metrics"] = _downstream_metrics(record)
            self._touch(record, "补数状态变化", "排程仍处于中断状态，等待断点恢复")
            return record

        self._rebuild(record)
        self._touch(record, "补数结束", "已按最新补数状态重排延后分区")
        return record

    def execute_after_backfill(self, backfill: dict[str, Any]) -> dict[str, Any] | None:
        """管道维护链：补数完成后执行合并清理，产物写回同一份排程结果。"""
        record = self.release_after_backfill(backfill)
        if record is None or record.get("status") == STATUS_INTERRUPTED:
            return record
        if record["preferred_file_set"]:
            self.execute(int(record["id"]))
        return self.get_schedule(int(record["id"]))

    # ── 排程推进 ──────────────────────────────────────────

    def execute(self, schedule_id: int) -> tuple[dict[str, Any] | None, str]:
        record = self.get_schedule(schedule_id)
        if record is None:
            return None, f"合并排程 {schedule_id} 不存在"
        if record.get("status") == STATUS_INTERRUPTED:
            return None, "合并排程已中断，请先断点恢复再执行"
        if not record["preferred_file_set"]:
            return None, "当前批次没有可执行的合并文件，补数高峰分区仍在等待合并"

        batch = [item["file"] for item in record["preferred_file_set"]]
        completed = set(record.get("completed_file_set", [])) | set(batch)
        record["completed_file_set"] = sorted(completed)
        record["preferred_file_set"] = []
        record["batch_no"] = int(record.get("batch_no", 1)) + 1
        # 已执行的文件不会再回到延后分区：只有本轮没合到的分区才等待下一批。
        self._rebuild(record)
        self._touch(record, "执行合并", f"已合并 {len(batch)} 个文件，保留来源版本 {record['source_version']}")
        return record, f"已合并 {len(batch)} 个文件"

    def interrupt(self, schedule_id: int) -> tuple[dict[str, Any] | None, str]:
        """模拟写入中断：已完整执行的文件保留，未完成分区转为延后分区。"""
        record = self.get_schedule(schedule_id)
        if record is None:
            return None, f"合并排程 {schedule_id} 不存在"
        if record.get("status") == STATUS_INTERRUPTED:
            return None, "合并排程已处于中断状态，可直接断点恢复"
        if record.get("status") == STATUS_DONE:
            return None, "合并排程已完成，无需模拟中断"

        version = record.get("source_version", "v1")
        deferred_map = {item["partition"]: item for item in record["deferred_partitions"]}
        for partition in dict.fromkeys(item["partition"] for item in record["preferred_file_set"]):
            if partition not in deferred_map:
                deferred_map[partition] = _deferred_partition(
                    partition, "待下一批", "写入中断，断点恢复后重排", version
                )
        record["deferred_partitions"] = list(deferred_map.values())
        record["preferred_file_set"] = []
        record["status"] = STATUS_INTERRUPTED
        record["downstream_metrics"] = _downstream_metrics(record)
        self._touch(
            record,
            "写入中断",
            f"保留已执行文件 {len(record.get('completed_file_set', []))} 个，未完成分区转入延后",
        )
        return record, "合并排程已标记为写入中断"

    def resume(self, schedule_id: int) -> tuple[dict[str, Any] | None, str]:
        """断点恢复：只重排延后分区，已执行文件集原样保留、不会再次启动。"""
        record = self.get_schedule(schedule_id)
        if record is None:
            return None, f"合并排程 {schedule_id} 不存在"
        if record.get("status") != STATUS_INTERRUPTED:
            return None, f"合并排程当前状态为「{record.get('status')}」，无需断点恢复"

        completed_before = len(record.get("completed_file_set", []))
        record["batch_no"] = int(record.get("batch_no", 1)) + 1
        self._rebuild(record)
        if record["preferred_file_set"]:
            record["status"] = STATUS_PLANNED
        elif record["deferred_partitions"]:
            record["status"] = STATUS_WAITING
        else:
            record["status"] = STATUS_DONE
        self._touch(
            record,
            "断点恢复",
            f"保留已完成合并文件 {completed_before} 个，仅重排延后分区 {len(record['deferred_partitions'])} 个",
        )
        if record["status"] == STATUS_WAITING:
            return record, "已保留已执行文件集；补数高峰分区仍在等待合并"
        if record["status"] == STATUS_DONE:
            return record, "已保留已执行文件集；延后分区均已处理"
        return record, "合并排程已从断点恢复"

    # ── 内部 ──────────────────────────────────────────────

    def _rebuild(self, record: dict[str, Any]) -> None:
        """按实时补数状态重排未完成分区；已执行文件永不回到优先文件集。"""
        target_table = record["target_table"]
        partitions = table_partitions(target_table)
        versions = record.get("source_versions") or {}
        completed = set(record.get("completed_file_set", []))
        occupied = _occupied_partitions(target_table)

        # 未合并的分区既可能在优先文件集里，也可能已在延后分区里，两者一起重排。
        pending: list[str] = []
        for partition in [item["partition"] for item in record["preferred_file_set"]] + [
            item["partition"] for item in record["deferred_partitions"]
        ]:
            if partition not in pending:
                pending.append(partition)

        preferred: list[dict[str, Any]] = []
        remaining_deferred: list[dict[str, Any]] = []
        for partition in pending:
            if partition in occupied:
                remaining_deferred.append(
                    _deferred_partition(
                        partition, STATUS_WAITING, "补数高峰占用，等待补数完成",
                        versions.get(partition, record["source_version"]),
                    )
                )
                continue
            index = partitions.index(partition) if partition in partitions else 0
            files = [
                file
                for file in _files_for(partition, index, versions.get(partition, record["source_version"]))
                if file["file"] not in completed
            ]
            if files:
                preferred.extend(files)
            # 文件已全部合并的分区直接出列，不再占用延后分区的位置。

        record["preferred_file_set"] = preferred
        record["deferred_partitions"] = remaining_deferred
        record["occupied_partitions"] = _occupied_markers(target_table)
        record["conflict"] = bool(record["occupied_partitions"])
        record["conflict_detail"] = _conflict_detail(record)
        record["source_versions"] = {partition: versions.get(partition, record["source_version"]) for partition in partitions}
        record["downstream_metrics"] = _downstream_metrics(record)
        if record.get("status") == STATUS_INTERRUPTED:
            return
        if preferred:
            record["status"] = STATUS_PLANNED
        elif remaining_deferred:
            record["status"] = STATUS_WAITING
        else:
            record["status"] = STATUS_DONE

    def _touch(self, record: dict[str, Any], event: str, detail: str = "") -> None:
        record["revision"] = int(record.get("revision", 0)) + 1
        record["updated_at"] = _now()
        events = record.setdefault("events", [])
        events.append({"at": record["updated_at"], "event": event, "detail": detail})
        del events[:-MAX_EVENTS]


compact_schedule_service = CompactScheduleService()
