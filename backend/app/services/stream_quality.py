"""流式质量业务规则：质量规则管理、校验执行与死信联动。

增强：质量规则生效时触发水位检查，异常时生成死信记录。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services._common import list_module_entries
from app.store import store

MODULE = "stream_quality"
LIST_FIELDS = ["规则编号", "监控主题", "校验类型", "告警阈值", "采样比例", "检测窗口", "阻断动作", "规则版本"]
REQUIRED_FIELDS = ["规则编号", "监控主题", "校验类型"]
STATUS_ORDER = ["草稿", "待校验", "已生效", "已停用"]
ACTION_RULES = {"提交校验": "待校验", "标记生效": "已生效", "停用规则": "已停用"}
NEGATIVE_ACTIONS = ["停用规则"]


class StreamQualityService:
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        return list_module_entries(
            MODULE, "规则编号", filters=filters, keyword=keyword, status=status, page=page, size=size
        )

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        # 校验监控主题
        topic_code = values.get("监控主题")
        if topic_code:
            topic = self._find_topic(topic_code)
            if not topic:
                return None, [f"监控主题 {topic_code} 未注册"]

        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in LIST_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"质量规则 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于流式质量可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        if action == "标记生效":
            topic_code = entry.get("监控主题")
            watermark = self._find_watermark(topic_code)
            if not watermark:
                return None, f"主题 {topic_code} 未配置水位追踪"
            # 执行质量检查
            self._run_quality_check(entry, watermark)

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"质量规则已{action}"

    def _find_topic(self, topic_code: str) -> dict[str, Any] | None:
        for row in store.rows("topic_registry"):
            if row.get("主题编号") == topic_code:
                return row
        return None

    def _find_watermark(self, topic_code: str) -> dict[str, Any] | None:
        for row in store.rows("watermark_track"):
            if row.get("数据主题") == topic_code:
                return row
        return None

    def _run_quality_check(self, entry: dict[str, Any], watermark: dict[str, Any]) -> dict[str, Any]:
        """执行质量检查，异常时产生死信记录。"""
        try:
            threshold = float(entry.get("告警阈值", "0"))
        except (ValueError, TypeError):
            threshold = 0.0
        try:
            late_count = float(watermark.get("延迟记录数", "0"))
        except (ValueError, TypeError):
            late_count = 0.0

        violations = []
        if late_count > threshold:
            violations.append({
                "type": "延迟超限",
                "detail": f"延迟记录 {int(late_count)} 超过阈值 {threshold}",
                "topic": entry.get("监控主题"),
            })
            # 产生死信
            self._create_dead_letter(entry, watermark, "延迟超限")

        result = {
            "rule_id": entry.get("id"),
            "rule_code": entry.get("规则编号"),
            "topic": entry.get("监控主题"),
            "threshold": threshold,
            "late_count": late_count,
            "violations": violations,
            "checked_at": datetime.now().isoformat(),
            "passed": len(violations) == 0,
        }
        self._ensure_artifact_table("quality_check_results")
        store.rows("quality_check_results").append(result)
        entry["_last_check"] = result
        return result

    def _create_dead_letter(self, entry: dict[str, Any], watermark: dict[str, Any], reason: str) -> None:
        dl_rows = store.rows("dead_letter")
        dl_id = max((int(r.get("id", 0)) for r in dl_rows), default=0) + 1
        dl = {
            "id": dl_id,
            "status": "待处置",
            "pending": True,
            "abnormal": True,
            "记录编号": f"DEAD-{dl_id:04d}",
            "原始主题": entry.get("监控主题"),
            "原始分区": watermark.get("分区编号", "0"),
            "失败原因": reason,
            "原始消息体": f"延迟记录数:{watermark.get('延迟记录数')}",
            "重试次数": "0",
            "入库时间": datetime.now().isoformat(),
            "处置状态": "待分析",
        }
        dl_rows.append(dl)

    def get_quality_results(self, entry_id: int) -> list[dict[str, Any]]:
        self._ensure_artifact_table("quality_check_results")
        return [r for r in store.rows("quality_check_results") if r.get("rule_id") == entry_id]

    def _ensure_artifact_table(self, name: str) -> None:
        store.rows(name)
