"""合并排程数据结果测试：补数高峰纳入排程、冲突处置、断点恢复与跨模块联动。"""
from __future__ import annotations

import unittest

from app.pipeline_engine import pipeline_engine
from app.services.backfill_stream import BackfillStreamService
from app.services.compact_policy import CompactPolicyService
from app.services.compact_schedule import RESOLUTION_BACKFILL, RESOLUTION_COMPACT, compact_schedule_service
from app.store import store


class ScheduleFixture(unittest.TestCase):
    """每个用例用独立的表名，避免与种子数据和其他用例互相污染。"""

    suffix = "base"

    def setUp(self) -> None:
        # 每个用例一张独立目标表：store 是进程内共享的，避免用例间排程互相污染。
        scope = f"{self.suffix}_{self._testMethodName}"
        self.table = f"sched_orders_{scope}"
        policies = CompactPolicyService()
        policy, missing = policies.create_entry({
            "策略编号": f"COMP-{scope}", "目标表名": self.table, "触发条件": "文件数>10",
            "合并并发": "2", "目标文件大小": "128MB", "最小文件数": "5",
            "保留快照数": "3", "执行时间窗口": "02:00-04:00",
        })
        self.assertFalse(missing)
        policies.run_action(policy["id"], "标记生效")
        self.policy = policy

        backfills = BackfillStreamService()
        self.backfill, _ = backfills.create_entry({
            "任务编号": f"BACK-{scope}", "目标表名": self.table, "起始偏移": "0", "截止偏移": "1000",
        })
        self.backfills = backfills

    def start_peak(self) -> None:
        entry, message = self.backfills.run_action(self.backfill["id"], "启动补数")
        self.assertEqual(entry["status"], "运行中", message)


class TestPlanWithoutPeak(ScheduleFixture):
    suffix = "nopeak"

    def test_plan_keeps_all_partitions_preferred(self) -> None:
        record, message = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        self.assertEqual(message, "合并排程已生成")
        self.assertFalse(record["conflict"])
        self.assertEqual(record["status"], "已排程")
        self.assertGreater(len(record["preferred_file_set"]), 0)
        self.assertEqual(record["deferred_partitions"], [])
        self.assertEqual(record["downstream_metrics"]["deferred_files"], 0)

    def test_plan_rejects_inactive_policy(self) -> None:
        policies = CompactPolicyService()
        draft, _ = policies.create_entry({
            "策略编号": "COMP-draft", "目标表名": f"{self.table}_draft", "触发条件": "文件数>5",
        })
        record, message = compact_schedule_service.plan(draft["id"], RESOLUTION_COMPACT)
        self.assertIsNone(record)
        self.assertIn("尚未生效", message)


class TestPeakConflict(ScheduleFixture):
    suffix = "peak"

    def test_priority_backfill_defers_whole_window(self) -> None:
        self.start_peak()
        record, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_BACKFILL)
        self.assertTrue(record["conflict"])
        self.assertEqual(record["status"], "等待合并")
        self.assertEqual(record["preferred_file_set"], [])
        occupied = record["conflict_detail"]["overlap_partitions"]
        self.assertEqual(len(occupied), 2)
        waiting = [item for item in record["deferred_partitions"] if item["state"] == "等待合并"]
        self.assertEqual([item["partition"] for item in waiting], occupied)
        # 补数完成前占用分区只能等待合并
        self.assertTrue(all(marker["still_holding_files"] for marker in record["occupied_partitions"]))

    def test_two_resolutions_leave_different_downstream_results(self) -> None:
        self.start_peak()
        defer, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_BACKFILL)
        merge, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        self.assertEqual(defer["resolution"], RESOLUTION_BACKFILL)
        self.assertEqual(merge["resolution"], RESOLUTION_COMPACT)
        self.assertGreater(len(merge["preferred_file_set"]), len(defer["preferred_file_set"]))
        self.assertLess(
            merge["downstream_metrics"]["small_files_remaining"],
            defer["downstream_metrics"]["small_files_remaining"],
        )
        self.assertLess(merge["downstream_metrics"]["query_latency_ms"], defer["downstream_metrics"]["query_latency_ms"])

    def test_invalid_resolution_rejected(self) -> None:
        record, message = compact_schedule_service.plan(self.policy["id"], "优先删除")
        self.assertIsNone(record)
        self.assertIn("不在允许范围", message)


class TestInterruptResume(ScheduleFixture):
    suffix = "resume"

    def test_resume_keeps_completed_files_and_replans_deferred_only(self) -> None:
        self.start_peak()
        record, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        record, _ = compact_schedule_service.execute(record["id"])
        completed_before = list(record["completed_file_set"])
        self.assertGreater(len(completed_before), 0)

        record, _ = compact_schedule_service.interrupt(record["id"])
        self.assertEqual(record["status"], "已中断")
        self.assertEqual(record["completed_file_set"], completed_before)

        record, _ = compact_schedule_service.resume(record["id"])
        replanned = {item["file"] for item in record["preferred_file_set"]}
        # 已完成合并的文件不会再次启动
        self.assertEqual(replanned & set(completed_before), set())
        self.assertEqual(sorted(record["completed_file_set"]), sorted(completed_before))
        deferred = {item["partition"] for item in record["deferred_partitions"]}
        self.assertTrue({item["partition"] for item in record["preferred_file_set"]} <= deferred)

    def test_interrupt_refuses_on_completed_schedule(self) -> None:
        record, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        record, _ = compact_schedule_service.execute(record["id"])
        self.assertEqual(record["status"], "已完成")
        record, message = compact_schedule_service.interrupt(record["id"])
        self.assertIsNone(record)
        self.assertIn("已完成", message)

    def test_resume_requires_interrupted_state(self) -> None:
        record, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        record, message = compact_schedule_service.resume(record["id"])
        self.assertIsNone(record)
        self.assertIn("无需断点恢复", message)


class TestCrossModuleMarking(ScheduleFixture):
    suffix = "cross"

    def test_backfill_start_marks_occupied_partitions(self) -> None:
        record, message = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        self.assertEqual(record["status"], "已排程")
        self.start_peak()
        latest = compact_schedule_service.latest_for_table(self.table)
        occupied = {marker["partition"] for marker in latest["occupied_partitions"]}
        self.assertEqual(len(occupied), 2)
        # 仍占用文件的分区从优先文件集摘出，只能等待合并
        self.assertFalse({item["partition"] for item in latest["preferred_file_set"]} & occupied)
        waiting = {item["partition"] for item in latest["deferred_partitions"] if item["state"] == "等待合并"}
        self.assertEqual(waiting, occupied)

        peaks = self.backfills.get_peak_partitions()
        self.assertTrue(any(peak["schedule_id"] == latest["id"] for peak in peaks))

    def test_backfill_start_creates_schedule_when_missing(self) -> None:
        self.assertIsNone(compact_schedule_service.latest_for_table(self.table))
        entry, message = self.backfills.run_action(self.backfill["id"], "启动补数")
        self.assertEqual(entry["status"], "运行中", message)
        record = compact_schedule_service.latest_for_table(self.table)
        self.assertIsNotNone(record)
        self.assertEqual(record["compact_policy_id"], self.policy["id"])
        self.assertEqual(entry["merge_schedule_id"], record["id"])

    def test_backfill_finish_replans_deferred_partitions(self) -> None:
        self.start_peak()
        record, _ = compact_schedule_service.plan(self.policy["id"], RESOLUTION_COMPACT)
        self.assertTrue(record["deferred_partitions"])
        self.backfills.run_action(self.backfill["id"], "确认完成")
        latest = compact_schedule_service.latest_for_table(self.table)
        self.assertFalse(latest["conflict"])
        self.assertEqual(latest["deferred_partitions"], [])
        self.assertEqual(latest["occupied_partitions"], [])

    def test_pipeline_compaction_writes_back_schedule(self) -> None:
        result = pipeline_engine.run_backfill_then_compact(self.backfill["id"])
        self.assertTrue(result["ok"])
        compact_result = result["result"]
        self.assertIsNotNone(compact_result["merge_schedule_id"])
        self.assertGreater(len(compact_result["completed_file_set"]), 0)
        schedule = compact_schedule_service.get_schedule(compact_result["merge_schedule_id"])
        self.assertEqual(schedule["source_version"], compact_result["source_version"])
        self.assertEqual(schedule["completed_file_set"], compact_result["completed_file_set"])
        self.assertTrue(any(row.get("backfill_id") == self.backfill["id"] for row in store.rows("compact_results")))


class TestSharedExport(unittest.TestCase):
    """导出逻辑只保留一份：各路由都从 app.exporting 取用。"""

    def test_csv_cell_neutralises_formula_injection(self) -> None:
        from app.exporting import csv_cell

        self.assertEqual(csv_cell("=SUM(A1)"), '"\'=SUM(A1)"')
        self.assertEqual(csv_cell('a"b'), '"a""b"')
        self.assertEqual(csv_cell(None), '""')

    def test_router_exports_share_implementation(self) -> None:
        from app.routers import backfill_stream, change_capture, flink_job, realtime_metrics, stream_lineage

        for module in (backfill_stream, change_capture, flink_job, realtime_metrics, stream_lineage):
            self.assertFalse(hasattr(module, "csv_cell"), f"{module.__name__} 仍保留重复的 csv_cell")


if __name__ == "__main__":
    unittest.main()
