"""主题注册业务规则：状态流转、字段校验与筛选口径都收在这里。

增强：主题上线时自动触发下游连接器就绪检查，支持跨模块链路校验。
"""
from __future__ import annotations

from typing import Any

from app.services._common import list_module_entries
from app.store import store

MODULE = "topic_registry"
LIST_FIELDS = ["主题编号", "主题名称", "消息格式", "序列化协议", "分区键列", "保留时长", "压缩类型", "Schema版本"]
REQUIRED_FIELDS = ["主题编号", "主题名称", "消息格式"]
STATUS_ORDER = ["草稿", "待校验", "已上线", "已下线"]
ACTION_RULES = {"提交校验": "待校验", "确认上线": "已上线", "标记下线": "已下线"}
NEGATIVE_ACTIONS = []


class TopicRegistryService:
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
            MODULE, "主题编号", filters=filters, keyword=keyword, status=status, page=page, size=size
        )

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def find_by_topic_code(self, topic_code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if row.get("主题编号") == topic_code:
                return row
        return None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
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
            return None, f"数据主题 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于主题注册可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        # 状态机校验：不能跳级
        current_idx = STATUS_ORDER.index(entry["status"])
        target_idx = STATUS_ORDER.index(target)
        if target_idx < current_idx and action != "标记下线":
            return None, f"状态不能从「{entry['status']}」回退到「{target}」"

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS

        # 上线时触发下游校验
        if action == "确认上线":
            self._on_topic_online(entry)

        return entry, f"数据主题已{action}"

    def _on_topic_online(self, entry: dict[str, Any]) -> None:
        """主题上线时：检查关联的Kafka连接器和Schema规则是否存在。"""
        topic_code = entry.get("主题编号")
        # 检查kafka_connector
        kafka_ok = any(
            r.get("消费组名", "").startswith(topic_code.replace("TOPI", "").lower())
            for r in store.rows("kafka_connector")
        )
        # 检查schema_evolve
        schema_ok = any(
            r.get("关联主题") == topic_code and r.get("status") == "已生效"
            for r in store.rows("schema_evolve")
        )
        entry["_downstream_ready"] = kafka_ok and schema_ok
        entry["_kafka_ready"] = kafka_ok
        entry["_schema_ready"] = schema_ok

    def get_downstream_status(self, entry_id: int) -> dict[str, Any] | None:
        """查询主题的下游链路状态。"""
        entry = store.find(MODULE, entry_id)
        if not entry:
            return None
        topic_code = entry.get("主题编号")
        kafka = [r for r in store.rows("kafka_connector") if topic_code in str(r.get("死信队列", ""))]
        schemas = [r for r in store.rows("schema_evolve") if r.get("关联主题") == topic_code]
        flinks = [r for r in store.rows("flink_job") if r.get("消费主题") == topic_code]
        return {
            "topic_code": topic_code,
            "topic_status": entry.get("status"),
            "kafka_connectors": len(kafka),
            "schema_rules": len(schemas),
            "flink_jobs": len(flinks),
            "downstream_ready": entry.get("_downstream_ready", False),
        }
